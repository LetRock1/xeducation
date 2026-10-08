"""
End-to-end test: drives the whole system over HTTP, the way a learner and the marketing team use it.

    1. both backends answer; the marketing team can log in
    2. a learner signs up (the code is read from the local database: test addresses are never
       e-mailed), completes the profile and browses: every event re-scores them live
    3. they add a course to the cart and leave; the automation runs; next-best-action decides
    4. the marketing dashboard shows them everywhere: leads (one pool with the simulated learners,
       tagged), profile, "why this score", what-if paths, today's actions, stats, model health,
       journeys, learning loop; the simulated learners are live and one can be sent to the website
       now; only the team can close a real person's call task
    5. A/B test: plan, create a draft, open it, delete it; campaign: create a draft, delete it
    6. the learning loop runs (dry run: compares models, changes nothing)
    7. the learner buys; the purchase reaches the dashboard
    8. the learner deletes their account; nothing of theirs is left

Run it while the servers are up (after start-all.bat):
    user-backend\\venv\\Scripts\\python.exe tests\\e2e_test.py
Options: --user URL  --mkt URL  --db PATH (user database)  --send-ab (also SEND a test A/B test:
only for sandboxes, it e-mails the audience).
The test learner is ...@e2e.xeducation.test and is deleted at the end.
"""
import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = []


def read_env(path):
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def call(base, method, path, body=None, token=None, headers=None, expect=200):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    h.update(headers or {})
    req = urllib.request.Request(base + path, data=data, method=method, headers=h)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            status, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    ms = (time.perf_counter() - t0) * 1000
    try:
        payload = json.loads(raw.decode() or "null")
    except ValueError:
        payload = raw.decode(errors="replace")
    if expect is not None and status != expect:
        raise AssertionError(f"{method} {path} -> {status} (expected {expect}): {str(payload)[:300]}")
    return payload, ms


def check(name, fn):
    t0 = time.perf_counter()
    try:
        info = fn()
        RESULTS.append(("PASS", name, info or "", (time.perf_counter() - t0) * 1000))
        print(f"PASS  {name}  {info or ''}", flush=True)
        return True
    except Exception as e:
        RESULTS.append(("FAIL", name, f"{type(e).__name__}: {e}", (time.perf_counter() - t0) * 1000))
        print(f"FAIL  {name}  {type(e).__name__}: {e}", flush=True)
        return False


def main():
    ap = argparse.ArgumentParser()
    # 127.0.0.1, not localhost: on Windows "localhost" is tried as IPv6 first (about 2 s per connection)
    ap.add_argument("--user", default=os.getenv("E2E_USER_URL", "http://127.0.0.1:8000"))
    ap.add_argument("--mkt", default=os.getenv("E2E_MKT_URL", "http://127.0.0.1:8001"))
    ap.add_argument("--db", default=os.path.join(ROOT, "user-backend", "xeducation_user.db"))
    ap.add_argument("--send-ab", action="store_true")
    a = ap.parse_args()
    U, M = a.user.rstrip("/"), a.mkt.rstrip("/")
    menv = read_env(os.path.join(ROOT, "marketing-backend", ".env"))
    uenv = read_env(os.path.join(ROOT, "user-backend", ".env"))
    S = {"email": f"e2e-{uuid.uuid4().hex[:8]}@e2e.xeducation.test", "password": "E2e-test-pass-1"}
    internal = {"X-Internal-Key": uenv.get("INTERNAL_API_KEY") or os.getenv("INTERNAL_API_KEY", "xedu-internal-dev")}

    def db():
        con = sqlite3.connect(a.db, timeout=30)
        con.row_factory = sqlite3.Row
        return con

    # 1 ─ servers and login
    check("user backend is up", lambda: call(U, "GET", "/api/health")[0]["status"])

    def mkt_login():
        r, _ = call(M, "POST", "/api/mkt/login", {"email": menv.get("MARKETING_EMAIL", "admin@xeducation.in"),
                                                  "password": menv.get("MARKETING_PASSWORD", "marketing_admin_2025")})
        S["mtok"] = r["token"]
        return "token received"
    if not check("marketing team logs in", mkt_login):
        return finish()
    check("dashboard rejects requests without login", lambda: call(M, "GET", "/api/mkt/stats", expect=401) and "401")

    # 2 ─ learner signs up and browses
    def signup():
        call(U, "POST", "/api/auth/signup", {"name": "E2E Tester", "email": S["email"], "password": S["password"]})
        with db() as con:
            otp = con.execute("SELECT otp FROM otp_tokens WHERE email=? AND used=0 ORDER BY id DESC LIMIT 1",
                              (S["email"],)).fetchone()["otp"]
        call(U, "POST", "/api/auth/verify-otp", {"email": S["email"], "otp": "000000" if otp != "000000" else "111111"},
             expect=400)
        r, _ = call(U, "POST", "/api/auth/verify-otp", {"email": S["email"], "otp": otp})
        S.update(tok=r["token"], sid=r["session_id"], uid=r["user"]["id"])
        return f"user {S['uid']} verified (wrong code refused first)"
    if not check("learner signs up and verifies the e-mail code", signup):
        return finish()
    check("learner completes the profile", lambda: call(U, "POST", "/api/profile/complete",
          {"current_occupation": "Working Professional", "specialization": "IT Projects Management",
           "age_bracket": "25-34", "city": "Mumbai", "phone": "+919812345678"}, S["tok"])[0] and "saved")

    def courses():
        r, _ = call(U, "GET", "/api/courses")
        items = r if isinstance(r, list) else r.get("courses", [])
        S["slug"] = items[0]["slug"]
        return f"{len(items)} courses; using {S['slug']}"
    check("course catalogue loads", courses)

    def browse():
        scores, times = [], []
        for ev, secs in [("page_view", 40), ("video_play", 240), ("pricing_view", 90), ("testimonial_view", 60),
                         ("brochure_dl", 5)]:
            r, ms = call(U, "POST", "/api/track", {"session_id": S["sid"], "course_slug": S["slug"], "event_type": ev,
                                                   "time_spent_sec": secs}, S["tok"])
            scores.append(round(r["live_score"])), times.append(ms)
        S["score_after_browse"] = scores[-1]
        assert len(set(scores)) > 1, "the score never changed"
        return f"live score {scores[0]} -> {scores[-1]}; event-to-score {sorted(times)[len(times) // 2]:.0f} ms median"
    check("browsing re-scores the learner live", browse)
    check("unknown event types are refused", lambda: call(U, "POST", "/api/track", {"session_id": S["sid"],
          "event_type": "hack"}, S["tok"], expect=400) and "400")

    def still_here():
        with db() as con:
            con.execute("UPDATE user_sessions SET last_active=datetime('now','localtime','-5 minutes') WHERE id=?",
                        (S["sid"],))
            con.commit()
        call(U, "POST", "/api/session/ping", {"session_id": S["sid"]}, S["tok"])
        with db() as con:
            age = con.execute("SELECT (julianday('now','localtime') - julianday(last_active)) * 86400 FROM user_sessions "
                              "WHERE id=?", (S["sid"],)).fetchone()[0]
            events = con.execute("SELECT COUNT(*) FROM behaviour_events WHERE user_id=?", (S["uid"],)).fetchone()[0]
        assert age < 30, f"last active {age:.0f} s ago after the ping"
        return f"the visit stays open while the learner reads (last active {age:.0f} s ago; no event recorded, {events} events)"
    check("'still here' ping keeps a long read from ending the visit", still_here)

    # 3 ─ cart, leave, automation decides
    def cart_and_leave():
        call(U, "POST", "/api/cart", {"course_slug": S["slug"]}, S["tok"])
        call(U, "POST", "/api/track", {"session_id": S["sid"], "course_slug": S["slug"], "event_type": "cart_add"}, S["tok"])
        call(U, "POST", "/api/checkout/start", {}, S["tok"], expect=None)
        with db() as con:     # make the visit 2 hours old (only this test learner) instead of waiting
            for sql in ("UPDATE cart SET added_at=datetime('now','localtime','-2 hours') WHERE user_id=?",
                        "UPDATE checkout_sessions SET started_at=datetime('now','localtime','-2 hours') WHERE user_id=?",
                        "UPDATE user_sessions SET last_active=datetime('now','localtime','-2 hours') WHERE user_id=?"):
                con.execute(sql, (S["uid"],))
            con.commit()
        r, ms = call(M, "POST", "/api/mkt/run-automations", {}, S["mtok"])
        with db() as con:
            d = con.execute("SELECT action, policy, trigger_reason FROM nba_decisions WHERE user_id=? ORDER BY id DESC LIMIT 1",
                            (S["uid"],)).fetchone()
        assert d, "no next-best-action decision was made"
        S["decision"] = dict(d)
        return f"{d['trigger_reason']} -> {d['action']} ({d['policy']}); automation run {ms:.0f} ms"
    check("left checkout: the automation decides the next step", cart_and_leave)

    # 4 ─ the dashboard sees everything
    def find_lead():
        r, _ = call(M, "GET", f"/api/mkt/leads?search={S['email']}", token=S["mtok"])
        rows = r if isinstance(r, list) else r.get("leads", [])
        mine = [x for x in rows if x.get("email") == S["email"]]
        assert mine, "learner not in the leads list"
        S["lead"] = mine[0]["id"]
        return f"lead {S['lead']}, score {round(mine[0]['lead_score'])}, {mine[0]['recommended_action']}"
    if check("learner appears in the leads list", find_lead):
        def lead_detail():
            r, _ = call(M, "GET", f"/api/mkt/leads/{S['lead']}", token=S["mtok"])
            assert r["email"] == S["email"] and r.get("nba"), "no recommended action on the lead"
            return f"action: {r['nba']['label']}; control group: {r.get('global_control')}"
        check("lead profile with its recommended action", lead_detail)
        def why():
            r, _ = call(M, "GET", f"/api/mkt/leads/{S['lead']}/explain", token=S["mtok"])
            assert r["factors"], "no reasons"
            return "; ".join(f"{f['factor']} {f['impact']}" for f in r["factors"][:4])
        check("why this score (reasons in points)", why)

        def paths():
            r, ms = call(M, "GET", f"/api/mkt/leads/{S['lead']}/paths?depth=3", token=S["mtok"])
            assert r["steps"] and r["best"] and r["summary"], "empty what-if paths"
            return f"{len(r['steps'])} first steps, best: {r['best']} ({ms:.0f} ms)"
        check("what-if paths for the lead", paths)

        def agree():
            now, _ = call(M, "GET", f"/api/mkt/leads/{S['lead']}/now", token=S["mtok"])
            p, _ = call(M, "GET", f"/api/mkt/leads/{S['lead']}/paths", token=S["mtok"])
            rec = now["recommendation"]["action"]
            assert p["best"] == rec, f"what-if says {p['best']}, recommendation says {rec}"
            first = {x["action"]: x for x in p["steps"]}
            for o in now["options"]:
                if o["action"] in first:
                    assert abs(first[o["action"]]["p_buy_step"] - o["p_convert"]) < 1e-9, f"{o['action']}: numbers differ"
            assert now["options"] and all("incremental_profit" in o for o in now["options"]), "no receipt"
            return f"both pick '{rec}', same chance for every step ({len(now['options'])} steps on the receipt)"
        check("recommended action and what-if paths agree (one calculation)", agree)

        def do_it_now():
            now, _ = call(M, "GET", f"/api/mkt/leads/{S['lead']}/now", token=S["mtok"])
            if now["control_group"]:
                call(M, "POST", f"/api/mkt/leads/{S['lead']}/act", {"action": "email_info"}, S["mtok"], expect=409)
                return "learner is in the control group: Do it now refused, as it should be"
            r, _ = call(M, "POST", f"/api/mkt/leads/{S['lead']}/act", {"action": "email_info"}, S["mtok"])
            with db() as con:
                d = con.execute("SELECT action, policy, propensity FROM nba_decisions WHERE id=?", (r["decision_id"],)).fetchone()
                e = con.execute("SELECT token, subject FROM email_sends WHERE user_id=? ORDER BY id DESC LIMIT 1",
                                (S["uid"],)).fetchone()
            assert d["policy"] == "manual" and d["action"] == "email_info" and d["propensity"] == 1.0, dict(d)
            assert e, "no email recorded"
            S["email_token"] = e["token"]
            call(M, "POST", f"/api/mkt/leads/{S['lead']}/act", {"action": "nonsense"}, S["mtok"], expect=400)
            return f"{r['message']}; logged as a hand-made decision (the model's pick: {r['model_pick']})"
        check("Do it now: sends the email and logs the decision", do_it_now)

        def email_click():
            if not S.get("email_token"):
                return "skipped (no email was sent to this learner)"
            r, _ = call(U, "POST", "/api/email/click", {"token": S["email_token"]})
            assert r["ok"] and r["first_click"], r
            call(U, "POST", "/api/email/click", {"token": "not-a-token"}, expect=400)
            lead, _ = call(M, "GET", f"/api/mkt/leads/{S['lead']}", token=S["mtok"])
            mine = [x for x in lead["decisions"] if x.get("email") and x["email"].get("clicked_at")]
            assert mine, "the click is not shown with its decision"
            return f"click recorded and shown with its decision ({mine[0]['label']})"
        check("email button: the course page reports the click", email_click)

        def real_task():
            r, _ = call(M, "POST", f"/api/mkt/leads/{S['lead']}/act", {"action": "call"}, S["mtok"], expect=None)
            if not isinstance(r, dict) or not r.get("ok"):
                return f"skipped: no call possible for this learner now ({(r or {}).get('detail') if isinstance(r, dict) else r})"
            acts, _ = call(M, "GET", "/api/mkt/actions?segment=real", token=S["mtok"])
            mine = [t for t in acts["actions"] if t["user_id"] == S["uid"] and t["task_type"] == "call"]
            assert mine, "the call task is not in Today's actions"
            tid = mine[0]["id"]
            call(U, "POST", f"/api/internal/tasks/{tid}/done", {"outcome": "reached"}, headers=internal, expect=403)
            call(M, "POST", f"/api/mkt/actions/{tid}/done", {"outcome": "reached"}, S["mtok"])
            done, _ = call(M, "GET", "/api/mkt/actions?status=done&segment=real", token=S["mtok"])
            t = [x for x in done["actions"] if x["id"] == tid]
            assert t and t[0]["done_by"] == "team" and t[0]["outcome"] == "reached", t
            return "call task for a real person: the simulated advisor is refused (403); 'Spoke to them' records it (done by the team)"
        check("only the team closes a real person's call task", real_task)

        def attribution():
            r, _ = call(M, "GET", f"/api/mkt/leads/{S['lead']}/attribution", token=S["mtok"])
            return f"{len(r['timeline'])} touchpoints"
        check("attribution timeline", attribution)

        def pipeline():
            def card():
                b, ms = call(M, "GET", f"/api/mkt/pipeline?search={S['email']}", token=S["mtok"])
                cards = [c for col in b["columns"] for c in col["cards"] if c["user_id"] == S["uid"]]
                assert len(cards) == 1, f"learner on {len(cards)} cards"
                return cards[0], ms
            c, ms = card()
            assert c["stage"] == "SQL" and c["auto_stage"] == "SQL", f"expected SQL after cart+checkout, got {c['stage']}"
            call(M, "PUT", f"/api/mkt/pipeline/{S['uid']}", {"stage": "MQL", "note": "e2e"}, S["mtok"])
            moved, _ = card()
            assert moved["stage"] == "MQL" and moved["moved_by_hand"] and moved["auto_stage"] == "SQL"
            call(M, "PUT", f"/api/mkt/pipeline/{S['uid']}", {"stage": "Customer"}, S["mtok"], expect=400)
            call(M, "DELETE", f"/api/mkt/pipeline/{S['uid']}", token=S["mtok"])
            back, _ = card()
            assert back["stage"] == "SQL" and not back["moved_by_hand"]
            return f"SQL by behaviour; moved to MQL by hand and back to auto; 'Customer' refused ({ms:.0f} ms)"
        check("pipeline board: stage from behaviour, manual move, back to auto", pipeline)
    def segments():
        everyone, _ = call(M, "GET", "/api/mkt/leads", token=S["mtok"])
        c = everyone["counts"]
        assert everyone["segment"] == "all" and c["all"] == c["real"] + c["simulated"], c
        assert any(x["email"] == S["email"] for x in call(M, "GET", f"/api/mkt/leads?search={S['email']}",
                                                           token=S["mtok"])[0]["leads"]), "the learner is not in the one pool"
        real, _ = call(M, "GET", "/api/mkt/leads?segment=real", token=S["mtok"])
        sim, _ = call(M, "GET", "/api/mkt/leads?segment=simulated&tier=Marketing%20Campaign", token=S["mtok"])
        assert not any(x["simulated"] for x in real["leads"]), "a simulated learner under 'signed up themselves'"
        assert all(x["simulated"] for x in sim["leads"]), "a real learner under 'simulated'"
        scores = [round(x["lead_score"], 2) for x in sim["leads"]]
        if len(scores) >= 10:
            from collections import Counter
            top = Counter(scores).most_common(1)[0][1]
            assert top <= max(3, len(scores) // 5), f"{top} of {len(scores)} leads share one score"
        return (f"one pool of {c['all']:,} (signed up themselves {c['real']}, simulated {c['simulated']:,}) with tags and "
                f"filters; Campaign-tier scores all different")
    check("leads list: one pool, tagged and filterable, no identical scores", segments)

    # 4c ─ the simulated learners keep using the website (ml/live_simulation.py, run by the user-backend)
    def simulation_live():
        st, _ = call(M, "GET", "/api/mkt/simulation", token=S["mtok"])
        if not st["learners"]["total"]:
            return "no simulated learners in this database (starting history removed)"
        if not st["enabled"]:
            return "paused on the Dashboard (nothing to check)"
        last = st.get("last_tick")
        assert last, "the simulation never ran"
        age = time.time() - time.mktime(time.strptime(last[:19], "%Y-%m-%d %H:%M:%S"))
        assert age < 120, f"the simulation last ran {age:.0f} s ago"
        d = st["last_24h"]
        return (f"{st['learners']['total']:,} simulated learners, {st['learners']['still_deciding']} still deciding; last 24 h: "
                f"{d['visits']} visits, {d['email_clicks']} e-mail clicks, {d['purchases']} purchases, {d['signups']} sign-ups")
    check("simulated learners are using the website live", simulation_live)

    def simulation_visit():
        st, _ = call(M, "GET", "/api/mkt/simulation", token=S["mtok"])
        if not st["enabled"] or not st["learners"]["total"]:
            return "skipped (paused, or no simulated learners)"
        t0 = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 2))
        r, _ = call(M, "POST", "/api/mkt/simulation/visit", {"kind": "returning"}, S["mtok"])
        uid = r["user_id"]
        for _ in range(40):
            with db() as con:
                s = con.execute("SELECT id, lead_source, device_type FROM user_sessions WHERE user_id=? AND login_at >= ? "
                                "ORDER BY id DESC LIMIT 1", (uid, t0)).fetchone()
            if s:
                break
            time.sleep(1)
        assert s, f"{r['name']} did not start a visit within 40 s"
        lead, _ = call(M, "GET", f"/api/mkt/leads/{r['lead_id']}", token=S["mtok"])
        assert lead["simulated"], "not tagged simulated"
        return f"{r['name']} opened the website (session {s['id']}, {s['device_type']}, {s['lead_source']}) through the public API"
    check("Dashboard: send a simulated learner to the website now", simulation_visit)

    for name, path in [("dashboard stats", "/api/mkt/stats"), ("model health", "/api/mkt/model/health"),
                       ("priority queue", "/api/mkt/priority-queue"), ("today's actions", "/api/mkt/actions"),
                       ("next-best-action report", "/api/mkt/nba/performance"), ("forecast", "/api/mkt/forecast"),
                       ("campaign influence", "/api/mkt/campaign-influence"), ("journeys", "/api/mkt/journeys?days=180"),
                       ("learning loop page", "/api/mkt/learning/overview"), ("A/B tests list", "/api/mkt/ab-tests"),
                       ("campaigns list", "/api/mkt/campaigns"), ("coupons", "/api/mkt/coupons"),
                       ("callbacks", "/api/mkt/callbacks"), ("Q&A", "/api/mkt/qna")]:
        check(f"page data: {name}", lambda p=path: f"{call(M, 'GET', p, token=S['mtok'])[1]:.0f} ms")

    # 4b ─ Copilot (answers from live data; drafts only) and adopted A/B winners
    def copilot():
        out = []
        for q, intent in [("Who should we call today?", "call_list"), ("Which leads are most likely to buy?", "hot_leads"),
                          ("Is the learning loop fooling itself?", "learning"), ("How is the pipeline looking?", "pipeline"),
                          (f"Tell me about {S['email']}", "lead"), ("Draft an A/B test for a better subject line", "draft_ab_test")]:
            r, ms = call(M, "POST", "/api/mkt/copilot", {"question": q}, S["mtok"])
            assert r["intent"] == intent, f"{q!r} -> {r['intent']}"
            assert r["answer"] and r["tools"] and r["tools"][0]["source"], "answer without its data source"
            out.append(f"{intent} {ms:.0f} ms")
            if intent == "lead":
                assert "E2E Tester" in r["answer"], r["answer"][:120]
            if intent == "draft_ab_test":
                assert r["drafts"] and r["drafts"][0]["type"] == "ab_test" and len(r["drafts"][0]["variants"]) == 2
        call(M, "POST", "/api/mkt/copilot", {"question": " "}, S["mtok"], expect=400)
        log, _ = call(M, "GET", "/api/mkt/copilot", token=S["mtok"])
        assert len(log["recent"]) >= 6, "questions are not logged"
        return "; ".join(out)
    check("Copilot answers 6 kinds of question from live data (and logs them)", copilot)

    def adoptions():
        r, _ = call(M, "POST", "/api/mkt/adoptions/check", {}, S["mtok"])
        rows = r["adoptions"]
        live = [x for x in rows if x["status"] in ("active", "confirmed")]
        tests, _ = call(M, "GET", "/api/mkt/ab-tests", token=S["mtok"])
        flagged = [t for t in tests["ab_tests"] if t.get("adoption")]
        assert len(flagged) == len(rows), "A/B list and adoptions disagree"
        if live:
            a = live[0]
            return (f"{len(rows)} adopted winner(s); '{a['variant_label']}' for {a['audience']}: {a['status']} "
                    f"({(a.get('check') or {}).get('why', '')[:90]})")
        return f"{len(rows)} adopted winner(s) (none in use)"
    check("adopted A/B winners are listed and re-checked", adoptions)

    # 5 ─ A/B test and campaign drafts
    def ab_flow():
        plan, _ = call(M, "GET", "/api/mkt/ab-tests/plan?tier=All%20leads&metric=purchase&variants=2&control_share=0.2",
                       token=S["mtok"])
        r, _ = call(M, "POST", "/api/mkt/ab-tests", {"name": "E2E test", "tier": "All leads", "hypothesis": "test",
                    "metric": "purchase", "control_share": 0.2,
                    "variants": [{"label": "A", "subject": "Hi {first_name}", "body": "Body A"},
                                 {"label": "B", "subject": "Hello {first_name}", "body": "Body B", "offer_pct": 10}]},
                    S["mtok"])
        tid = r["id"]
        res, _ = call(M, "GET", f"/api/mkt/ab-tests/{tid}/results", token=S["mtok"])
        assert res["plan"]["planned_per_arm"] > 0
        call(M, "POST", "/api/mkt/ab-tests", {"name": "bad", "tier": "All leads", "variants": [
             {"subject": "x", "body": "y"}]}, S["mtok"], expect=400)
        info = ""
        if a.send_ab:
            sent, _ = call(M, "POST", f"/api/mkt/ab-tests/{tid}/send", {}, S["mtok"])
            res, _ = call(M, "GET", f"/api/mkt/ab-tests/{tid}/results", token=S["mtok"])
            info = f"; sent {sent['counts']}, verdict: {res['results']['verdict']['status']}"
        else:
            call(M, "DELETE", f"/api/mkt/ab-tests/{tid}", token=S["mtok"])
        return f"plan {plan['planned_per_arm']} per arm for {plan['audience']} people{info}"
    check("A/B test: plan, draft, results, validation", ab_flow)

    def campaign_flow():
        r, _ = call(M, "POST", "/api/mkt/campaigns", {"name": "E2E draft", "tier": "Low Priority", "subject": "S",
                    "body": "B", "scheduled_at": "2099-01-01T10:00", "holdout_share": 0.1}, S["mtok"])
        rows, _ = call(M, "GET", "/api/mkt/campaigns", token=S["mtok"])
        rows = rows if isinstance(rows, list) else rows.get("campaigns", [])
        mine = [c for c in rows if c.get("name") == "E2E draft"]
        assert mine, f"campaign not listed ({str(r)[:120]})"
        call(M, "DELETE", f"/api/mkt/campaigns/{mine[0]['id']}", token=S["mtok"])
        return f"scheduled, listed and deleted (hold-out {mine[0].get('holdout_share')})"
    check("campaign: schedule and delete", campaign_flow)

    # 6 ─ learning loop
    def learn():
        r, _ = call(M, "POST", "/api/mkt/learning/run?dry_run=true", {}, S["mtok"])
        assert r.get("status") in ("dry_run", "busy"), r
        return (f"{r.get('outcomes_known')} decisions with an outcome, control group {r.get('control_people')} people, "
                f"lead model: {r.get('lead_decision')}, next-best-action: {(r.get('nba') or {}).get('decision')}")
    check("learning loop dry run", learn)

    # 7 ─ purchase
    def buy():
        r, _ = call(U, "POST", "/api/checkout", {"coupon_code": ""}, S["tok"])
        p, _ = call(U, "GET", "/api/purchases", token=S["tok"])
        p = p if isinstance(p, list) else p.get("purchases", [])
        assert p, "no purchase recorded"
        lead, _ = call(M, "GET", f"/api/mkt/leads/{S['lead']}", token=S["mtok"])
        assert lead.get("purchases"), "purchase not visible to marketing"
        return f"{len(p)} purchase(s), visible in the dashboard"
    check("learner buys; the dashboard sees it", buy)

    def customer_view():
        lead, _ = call(M, "GET", f"/api/mkt/leads/{S['lead']}", token=S["mtok"])
        assert lead["customer"], "not marked as a customer"
        now, _ = call(M, "GET", f"/api/mkt/leads/{S['lead']}/now", token=S["mtok"])
        assert now["recommendation"] is None and now["purchases"], "a customer still gets a recommendation"
        p, _ = call(M, "GET", f"/api/mkt/leads/{S['lead']}/paths", token=S["mtok"])
        assert p.get("customer") and not p["steps"], "a customer still gets what-if paths"
        call(M, "POST", f"/api/mkt/leads/{S['lead']}/act", {"action": "email_coupon_10"}, S["mtok"], expect=409)
        rows, _ = call(M, "GET", f"/api/mkt/leads?tier=Customers&search={S['email']}", token=S["mtok"])
        assert any(x["email"] == S["email"] for x in rows["leads"]), "not in the Customers tab"
        rows, _ = call(M, "GET", f"/api/mkt/leads?tier=Low%20Priority&search={S['email']}", token=S["mtok"])
        assert not any(x["email"] == S["email"] for x in rows["leads"]), "a customer is still listed in a tier"
        bought = [x for x in lead["decisions"] if x.get("outcome") == "bought"]
        assert bought, "the purchase is not credited to the decisions before it"
        return f"shown as a customer: no recommendation, no paths, no Do it now; {len(bought)} decision(s) now say 'bought'"
    check("a customer is shown as a customer", customer_view)

    # 8 ─ delete the account
    def delete():
        # the team sends a WhatsApp message first: the marketing database logs it with the phone number
        call(U, "PUT", "/api/profile/preferences", {"whatsapp_opt_in": True}, S["tok"])
        call(M, "POST", "/api/mkt/whatsapp", {"lead_id": S["lead"], "message": "Hi {first_name}, test message"},
             token=S["mtok"])
        logged = [m for m in call(M, "GET", "/api/mkt/sms-queue", token=S["mtok"])[0]["messages"]
                  if m.get("user_id") == S["uid"]]
        assert logged, "the WhatsApp message was not logged"
        call(U, "DELETE", "/api/me", token=S["tok"])
        still = [m for m in call(M, "GET", "/api/mkt/sms-queue", token=S["mtok"])[0]["messages"]
                 if m.get("user_id") == S["uid"]]
        assert not still, f"{len(still)} WhatsApp log row(s) left in the marketing database"
        call(U, "POST", "/api/auth/login", {"email": S["email"], "password": S["password"]}, expect=401)
        with db() as con:
            left = {}
            for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'"):
                cols = [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
                if "user_id" in cols:
                    n = con.execute(f"SELECT COUNT(*) FROM {t} WHERE user_id=?", (S["uid"],)).fetchone()[0]
                    if n:
                        left[t] = n
        assert not left, f"rows left: {left}"
        return "account and every linked row deleted"
    check("learner deletes the account and data", delete)
    return finish()


def finish():
    ok = sum(1 for r in RESULTS if r[0] == "PASS")
    print(f"\n{ok} of {len(RESULTS)} checks passed.")
    return 0 if ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
