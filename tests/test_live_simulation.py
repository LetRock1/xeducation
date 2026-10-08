"""
The simulated learners, live (ml/live_simulation.py), checked on a PRIVATE copy of the website and its
database: the test starts its own user-backend on a free port with a copy of xeducation_user.db, so your
real data is never touched. The servers do not need to be running. Takes about a minute.

    user-backend\\venv\\Scripts\\python.exe tests\\test_live_simulation.py

  1. the simulated learners are exactly the people of the 6-month history (re-created from its seed)
  2. the simulator's shortcut for "how much a step changes this person" equals the CRM's own calculation
  3. the live world continues the history at the same pace (purchases per day)
  4. a visit sends exactly the requests a browser sends, and the CRM reacts to them (scores, decides)
  5. buying goes through cart -> checkout -> payment, with the best valid coupon
  6. an e-mail the CRM sends can be clicked: the website's click endpoint, then a visit "from an e-mail"
  7. the simulated advisor closes simulated learners' call tasks — never a real person's
  8. simulated learners have their own daily call capacity (they never use up a real advisor's calls)
  9. a new learner signs up like a person: sign-up, code from the inbox, profile, first visit
 10. time when the website was off is not replayed; pausing stops everything
 11. every request the simulated people sent was answered
"""
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "user-backend")
ML = os.path.join(ROOT, "ml")
for _p in (ML, BACKEND):
    if _p not in sys.path:
        sys.path.insert(0, _p)
os.chdir(BACKEND)
os.environ.setdefault("PYTHONUTF8", "1")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")     # ₹ and → on any Windows console
except (AttributeError, ValueError):
    pass
RESULTS = []


def check(name, fn):
    t0 = time.perf_counter()
    try:
        info = fn()
        RESULTS.append(True)
        print(f"PASS  {name}  {info or ''}  ({time.perf_counter() - t0:.1f} s)", flush=True)
    except Exception as e:
        RESULTS.append(False)
        print(f"FAIL  {name}  {type(e).__name__}: {e}", flush=True)


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


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def main():
    src = os.path.join(BACKEND, "xeducation_user.db")
    if not os.path.exists(src):
        print("No database yet: run start-all.bat once first.")
        return 1
    tmp = tempfile.mkdtemp(prefix="xedu-sim-")
    copy = os.path.join(tmp, "xeducation_user.db")
    con = sqlite3.connect(src)
    try:
        con.execute(f"VACUUM INTO '{copy}'")              # a consistent copy, even while the servers run
    finally:
        con.close()
    conf = json.load(open(os.path.join(ROOT, "crm_settings.json"), encoding="utf-8"))
    conf.setdefault("live_simulation", {})["enabled"] = False      # the private server's own simulation stays off
    conf.setdefault("learning", {})["check_every_minutes"] = {"demo": 100000, "live": 100000}   # no model swaps here
    settings_copy = os.path.join(tmp, "crm_settings.json")
    json.dump(conf, open(settings_copy, "w", encoding="utf-8"), indent=2)
    port = free_port()
    env = dict(os.environ, USER_DB_PATH_OVERRIDE=copy, CRM_SETTINGS=settings_copy, DEMO_MODE="true",
               SIM_WORLD_DB=os.path.join(tmp, "server_world.db"), MKT_DB_PATH=os.path.join(tmp, "no_marketing.db"))
    log = open(os.path.join(tmp, "server.log"), "w", encoding="utf-8")
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port)],
                              cwd=BACKEND, env=env, stdout=log, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(120):
            try:
                with urllib.request.urlopen(base + "/api/health", timeout=2) as r:
                    if r.status == 200:
                        break
            except Exception:
                time.sleep(0.5)
        else:
            print(f"The private test server did not start (log: {os.path.join(tmp, 'server.log')}).")
            return 1
        print(f"Private copy of the website on {base} with a copy of the database ({tmp})\n", flush=True)
        return run(base, copy, tmp)
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        log.close()
        import shutil
        time.sleep(1)                                  # Windows releases the files a moment after the server stops
        shutil.rmtree(tmp, ignore_errors=True)         # the private copy is thrown away


def run(base, copy, tmp):
    import numpy as np
    import database as db
    db.DB_PATH = copy                          # this process reads the same copy as the private server
    import generate_dataset as G
    import live_simulation as LS
    import ml_features as F
    import nba
    import nba_core as N
    import nba_simulation as S
    import settings

    key = read_env(os.path.join(BACKEND, ".env")).get("INTERNAL_API_KEY") or os.getenv("INTERNAL_API_KEY", "xedu-internal-dev")

    class Recorder(LS.HttpApi):
        """The website's API, with every request the simulated people send written down."""
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.calls = []

        def call(self, method, path, body=None, token=None, internal=False):
            code, r = super().call(method, path, body, token, internal)
            self.calls.append({"method": method, "path": path.split("?")[0], "code": code, "token": bool(token),
                               "body": body, "reply": r})
            return code, r

    class Always:
        """Makes every 'maybe' of a visit happen, so every kind of request is exercised; the rest (how many pages,
        how long, when) is still drawn by numpy."""
        def __init__(self, seed=7):
            self.g = np.random.default_rng(seed)

        def random(self, size=None):
            return np.zeros(size) if size is not None else 0.0

        def __getattr__(self, name):
            return getattr(self.g, name)

    api = Recorder(base=base, internal_key=key)
    world = LS.World(api=api, path=os.path.join(tmp, "test_world.db"), rng=np.random.default_rng(11))
    real_now = datetime.now().replace(microsecond=0)
    world.clock = lambda: real_now
    S_ = {}

    def at(t):
        world.clock = lambda t=t: t

    def drain(until, limit=600):
        """Run every queued step at its own time: the clock jumps from one step to the next."""
        n = 0
        while True:
            row = world.q1("SELECT MIN(due_at) AS d FROM queue")
            if not row or not row["d"] or LS.parse(row["d"]) > until:
                return n
            t = LS.parse(row["d"])
            at(t)
            world.process_queue(t)
            n += 1
            assert n < limit, "the queue does not empty"

    def internal(method, path, body=None):
        req = urllib.request.Request(base + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"X-Internal-Key": key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, json.loads(r.read().decode() or "null")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode() or "null")

    # 1 ── the people
    def same_people():
        hist = LS.history_traits()
        rows = db.fetchall("""SELECT u.id, u.email, u.name, p.phone FROM users u LEFT JOIN user_profiles p ON p.user_id=u.id
                              WHERE u.email LIKE ?""", (LS.LIKE,))
        first_course = {r["user_id"]: r["course_slug"] for r in db.fetchall(
            "SELECT user_id, course_slug FROM leads WHERE id IN (SELECT MIN(id) FROM leads GROUP BY user_id)")}
        matched = [r for r in rows if r["email"] in hist]
        assert len(matched) >= min(len(hist), 1), "no simulated learner of the history found"
        bad = [r["email"] for r in matched if r["name"] != hist[r["email"]]["name"]
               or (r["phone"] or None) != hist[r["email"]]["phone"] or first_course.get(r["id"]) != hist[r["email"]]["slug"]]
        assert not bad, f"{len(bad)} learners differ, e.g. {bad[:3]}"
        return f"{len(matched):,} of {len(hist):,} history learners re-created exactly (name, phone, course)"
    check("the simulated learners are the history's people", same_people)

    # 2 ── the context of the true effects
    def same_context():
        rows = [json.loads(r["features_json"]) for r in db.fetchall(
            "SELECT features_json FROM score_snapshots ORDER BY RANDOM() LIMIT 300")]
        bad = sum(not np.array_equal(LS.context_of(f), N.context(F.to_model_frame([f]), np.array([0.5]))[0]) for f in rows)
        assert rows and bad == 0, f"{bad} of {len(rows)} differ"
        return f"{len(rows)} people: identical"
    check("the simulator's effect context equals the CRM's own", same_context)

    # 3 ── the pace
    def pace():
        world.sync(real_now)
        last = db.fetchone("""SELECT MAX(s.login_at) AS t FROM user_sessions s JOIN users u ON u.id=s.user_id
                              WHERE u.email LIKE ?""", (LS.LIKE,))["t"]
        end = LS.parse(last)
        at(end)
        world.roll(end, 1e-9)                       # computes today's chances, practically no dice
        expected = float(world.meta("expected_purchases_per_day") or 0)
        happened = db.fetchone("""SELECT COUNT(*) AS c FROM purchases p JOIN users u ON u.id=p.user_id
                                  WHERE u.email LIKE ? AND p.purchased_at > ? AND p.purchased_at <= ?""",
                               (LS.LIKE, LS.ts(end - timedelta(days=30)), LS.ts(end)))["c"] / 30.0
        world.x("DELETE FROM queue")
        at(real_now)
        if happened < 1:
            return f"history too small to compare (expected {expected:.1f}/day)"
        assert 0.5 <= expected / happened <= 2.0, f"expected {expected:.1f} purchases/day, the history had {happened:.1f}"
        return f"expected {expected:.1f} purchases/day; the history's last 30 days: {happened:.1f}/day"
    check("the live world continues the history at the same pace", pace)

    # pick learners for the next checks: still deciding, not in the control group, e-mail allowed
    beh = world.behaviour()
    bought = {r["user_id"] for r in db.fetchall("SELECT DISTINCT user_id FROM purchases")}
    pool = [L for L in world.q("SELECT * FROM learners WHERE bought=0")
            if L["user_id"] not in bought and not settings.in_global_control(L["user_id"]) and not L["dne"]]
    fresh = [L for L in pool if not any(beh.get(L["user_id"], {}).get(f) for f, *_ in LS.H.EVENTS)
             and L["phone"] and not L["dnc"]]
    assert pool and fresh, "no suitable simulated learners in this database"

    # 4 ── a visit
    def visit():
        L = world.learner(fresh[0]["user_id"])
        S_["visitor"] = L["user_id"]
        before = db.fetchone("SELECT COALESCE(MAX(id),0) AS m FROM behaviour_events")["m"]
        first_call = len(api.calls)
        world.rng = Always()
        plan = world.plan_visit(L, real_now)
        world.rng = np.random.default_rng(12)
        drain(real_now + timedelta(hours=3))
        mine = api.calls[first_call:]
        assert mine and mine[0]["path"] == "/api/session/start", "a visit must start like the website's tracker"
        sid = mine[0]["reply"]["session_id"]
        tracks = [c for c in mine if c["path"] == "/api/track"]
        assert tracks and all(c["token"] and c["body"]["session_id"] == sid for c in tracks), "events outside the visit"
        long_pages = [c for c in tracks if c["body"]["event_type"] == "page_view" and c["body"]["time_spent_sec"] > 30]
        pings = [c for c in mine if c["path"] == "/api/session/ping"]
        assert not long_pages or (pings and all(c["body"]["session_id"] == sid for c in pings)), \
            "a page longer than 30 s without the tracker's 'still here' ping"
        ev = {r["event_type"]: r["n"] for r in db.fetchall("""SELECT event_type, COUNT(*) AS n FROM behaviour_events
                                                               WHERE user_id=? AND id > ? GROUP BY event_type""",
                                                            (L["user_id"], before))}
        need = {"page_view", "video_play", "pricing_view", "testimonial_view", "brochure_dl", "chat", "webinar_register",
                "wishlist_add", "cart_add", "checkout_start", "enquiry_submit"}
        assert need <= set(ev), f"missing {need - set(ev)}"
        assert db.fetchone("SELECT id FROM cart WHERE user_id=?", (L["user_id"],)), "nothing in the cart"
        assert db.fetchone("SELECT id FROM wishlist WHERE user_id=?", (L["user_id"],)), "nothing on the wishlist"
        assert db.fetchone("SELECT id FROM checkout_sessions WHERE user_id=? AND completed=0", (L["user_id"],))
        assert db.fetchone("SELECT id FROM chat_messages WHERE user_id=? AND role='user'", (L["user_id"],)), "no chat"
        dec = db.fetchone("""SELECT action, policy FROM nba_decisions WHERE user_id=? AND trigger_reason='enquiry'
                             ORDER BY id DESC LIMIT 1""", (L["user_id"],))
        assert dec, "the CRM did not decide at the enquiry"
        paths = []
        for c in mine:
            if not paths or paths[-1] != c["path"]:
                paths.append(c["path"])
        return (f"{plan['summary']} — {len(mine)} requests ({' → '.join(p.replace('/api/', '') for p in paths[:7])} …); "
                f"the CRM decided at the enquiry: {dec['action']} ({dec['policy']})")
    check("a visit sends the requests a browser sends; the CRM reacts", visit)

    # 5 ── buying
    def buy():
        uid = S_.get("visitor") or fresh[0]["user_id"]
        L = world.learner(uid)
        price = float(LS.catalog.price_of(L["slug"]))
        for pct, hours in ((10, 72), (20, 72), (30, -1)):
            db.execute("""INSERT INTO coupons_issued (user_id, coupon_code, discount_pct, tier, expires_at)
                          VALUES (?,?,?,?,datetime('now','localtime',?))""",
                       (uid, f"TEST{pct}_{uid}", pct, "test", f"{hours:+d} hours"))
        valid = db.fetchall("""SELECT coupon_code, discount_pct FROM coupons_issued WHERE user_id=? AND used=0
                               AND (expires_at IS NULL OR expires_at > datetime('now','localtime'))""", (uid,))
        best = max(valid, key=lambda c: c["discount_pct"])
        world.buy(L, real_now)
        p = db.fetchone("SELECT * FROM purchases WHERE user_id=? ORDER BY id DESC LIMIT 1", (uid,))
        assert p and p["coupon_used"] == best["coupon_code"], (dict(p) if p else None, best)
        assert abs(p["price_paid"] - round(price * (1 - best["discount_pct"] / 100), 2)) < 0.01
        assert world.learner(uid)["bought"] == 1 and not db.fetchone("SELECT id FROM cart WHERE user_id=?", (uid,))
        expired = db.fetchone("SELECT used FROM coupons_issued WHERE coupon_code=?", (f"TEST30_{uid}",))
        assert expired["used"] == 0, "an expired coupon was used"
        return f"paid ₹{p['price_paid']:,.0f} for {p['course_title']} with {best['coupon_code']} ({best['discount_pct']}% off, the best valid one)"
    check("buying: cart → checkout → pay with the best valid coupon", buy)

    # 6 ── an e-mail and its click
    def click():
        for L in pool[1:40]:
            code, r = internal("POST", f"/api/internal/lead/{L['user_id']}/act", {"action": "email_info"})
            if code == 200:
                break
        else:
            raise AssertionError(f"could not send an e-mail to a simulated learner: {code} {r}")
        uid = L["user_id"]
        e = db.fetchone("SELECT * FROM email_sends WHERE user_id=? ORDER BY id DESC LIMIT 1", (uid,))
        world.set_meta("email_wm", e["id"] - 1)
        world.rng = Always()
        world.handle_emails(real_now)
        world.rng = np.random.default_rng(13)
        q = world.q1("SELECT * FROM queue WHERE user_id=? AND kind='click'", (uid,))
        assert q, "the click was not planned"
        eff = world.q1("SELECT * FROM effects WHERE ref=?", (f"email:{e['token']}",))
        assert eff and eff["kind"] == N.ACTIONS["email_info"]["label"].lower(), eff
        drain(LS.parse(q["due_at"]) + timedelta(minutes=30))
        e2 = db.fetchone("SELECT click_count, first_clicked_at FROM email_sends WHERE id=?", (e["id"],))
        assert e2["click_count"] >= 1 and e2["first_clicked_at"], "the click did not reach the CRM"
        back = db.fetchone("""SELECT lead_source FROM user_sessions WHERE user_id=? ORDER BY id DESC LIMIT 1""", (uid,))
        assert back and back["lead_source"] == "Email Campaign", back
        hours = (LS.parse(q["due_at"]) - LS.parse(e["sent_at"])).total_seconds() / 3600
        return (f"clicked {hours:.1f} h after sending (POST /api/email/click), came back 'from an e-mail'; "
                f"true effect of that e-mail on buying: {eff['effect']:+.2f} log-odds for 14 days")
    check("an e-mail is clicked through the website and brings them back", click)

    # 7 ── the simulated advisor, and real people's tasks
    def advisor():
        task = None
        for L in [p for p in pool[40:200] if p["phone"] and not p["dnc"]]:
            for action in ("call", "whatsapp"):
                code, r = internal("POST", f"/api/internal/lead/{L['user_id']}/act", {"action": action})
                if code == 200:
                    task = db.fetchone("SELECT * FROM sales_tasks WHERE user_id=? AND status='open' ORDER BY id DESC LIMIT 1",
                                       (L["user_id"],))
                    break
            if task:
                break
        assert task, "could not create a call or WhatsApp task for a simulated learner"
        world.set_meta("task_wm", task["id"] - 1)
        world.handle_tasks(real_now)
        w = world.q1("SELECT * FROM tasks WHERE task_id=?", (task["id"],))
        assert w and not w["handled"], "the task was not picked up"
        hours = (LS.parse(w["due_at"]) - LS.parse(task["created_at"])).total_seconds() / 3600
        assert 1 <= hours <= 24.01, hours
        later = real_now + timedelta(hours=25)
        at(later)
        world.handle_tasks(later)
        t = db.fetchone("SELECT * FROM sales_tasks WHERE id=?", (task["id"],))
        assert t["status"] == "done" and t["done_by"] == "simulated advisor", dict(t)
        assert t["outcome"] in (("reached", "no_answer", "not_interested") if task["task_type"] == "call" else ("sent",))
        if t["outcome"] in ("reached", "sent"):
            assert world.q1("SELECT * FROM effects WHERE ref=?", (f"task:{task['id']}",)), "no effect recorded"
        at(real_now)
        # a real person's task: the simulated advisor is refused
        real = None
        for i in range(6):
            email = f"simtest-{int(time.time() * 1000)}-{i}@e2e.xeducation.test"
            api.call("POST", "/api/auth/signup", {"name": "Real Tester", "email": email, "password": "Test-pass-1"})
            otp = db.fetchone("SELECT otp FROM otp_tokens WHERE email=? AND used=0 ORDER BY id DESC LIMIT 1", (email,))["otp"]
            code, r = api.call("POST", "/api/auth/verify-otp", {"email": email, "otp": otp})
            uid, tok = r["user"]["id"], r["token"]
            api.call("POST", "/api/profile/complete", {"current_occupation": "Working Professional",
                                                       "specialization": "Finance Management", "phone": "+919800000001"}, token=tok)
            code, r = internal("POST", f"/api/internal/lead/{uid}/act", {"action": "call"})
            if code == 200:
                real = db.fetchone("SELECT * FROM sales_tasks WHERE user_id=? AND status='open'", (uid,))
                break
        assert real, "could not create a call task for a real test person"
        S_["real_uid"] = uid
        code, r = internal("POST", f"/api/internal/tasks/{real['id']}/done", {"outcome": "reached"})
        assert code == 403, (code, r)
        still = db.fetchone("SELECT status FROM sales_tasks WHERE id=?", (real["id"],))["status"]
        assert still == "open"
        return (f"{task['task_type']} task done by the simulated advisor {hours:.1f} h after it was created "
                f"(outcome: {t['outcome']}); a real person's call task: refused (403), still open")
    check("the simulated advisor: simulated learners only", advisor)

    # 8 ── separate call capacity
    def capacity():
        sim_uid, real_uid = pool[-1]["user_id"], S_.get("real_uid")
        assert real_uid, "needs the real test person from the previous check"
        sim0, real0 = nba._calls_today(sim_uid), nba._calls_today(real_uid)
        for L in pool[-25:]:
            db.execute("INSERT INTO sales_tasks (user_id, task_type, title, status) VALUES (?, 'call', 'capacity test', 'done')",
                       (L["user_id"],))
        sim1, real1 = nba._calls_today(sim_uid), nba._calls_today(real_uid)
        assert sim1 == sim0 + 25 and real1 == real0, (sim0, sim1, real0, real1)
        assert sim1 >= nba.DAILY_CALL_CAPACITY
        import scoring
        pred = scoring.score_user(real_uid, source="test")
        ev = nba.evaluate(real_uid, pred, course_slug=None)
        blocked = {o["action"]: o["blocked"] for o in ev["options"]}
        assert blocked.get("call") != "today's call capacity is used up", blocked
        return (f"simulated learners' calls today {sim0} → {sim1} (cap {nba.DAILY_CALL_CAPACITY}); "
                f"a real person's count stays {real1} and their call is still possible")
    check("simulated learners have their own call capacity", capacity)

    # 9 ── a new learner signs up
    def signup():
        world.rng = np.random.default_rng(21)
        L = world.signup(real_now)
        assert L, "sign-up failed"
        u = db.fetchone("SELECT * FROM users WHERE id=?", (L["user_id"],))
        prof = db.get_profile(L["user_id"]) or {}
        lead = db.fetchone("SELECT trigger_reason FROM leads WHERE user_id=? ORDER BY id LIMIT 1", (L["user_id"],))
        tr = LS.new_traits(L["k"])
        assert u["is_verified"] == 1 and lead and lead["trigger_reason"] == "signup"
        assert u["email"] == tr["email"] and L["joined"] == "live"
        if tr["occ"] != "Unknown":
            assert prof.get("profile_complete") == 1 and prof.get("current_occupation") == tr["occ"], prof
        assert bool(prof.get("whatsapp_opt_in")) == bool(tr["wa"])
        drain(real_now + timedelta(hours=1))
        first = db.fetchone("""SELECT lead_source, device_type FROM user_sessions WHERE user_id=? AND lead_source IS NOT NULL
                               ORDER BY id DESC LIMIT 1""", (L["user_id"],))
        pages = db.fetchone("SELECT COUNT(*) AS c FROM behaviour_events WHERE user_id=? AND event_type='page_view'",
                            (L["user_id"],))["c"]
        assert first and first["lead_source"] == tr["source"] and pages >= 1, (dict(first) if first else None, pages)
        return (f"{u['name']} ({u['email']}): verified with the code from the inbox, profile "
                f"{'complete' if tr['occ'] != 'Unknown' else 'skipped (like 15% of people)'}; first visit from "
                f"{first['lead_source']} on {first['device_type']}, {pages} page(s)")
    check("a new learner signs up like a person", signup)

    # 10 ── time off is not replayed; pause
    def offline_and_pause():
        L = world.learner(pool[3]["user_id"])
        n = len(api.calls)
        world.enqueue(real_now - timedelta(minutes=20), L["user_id"], "page", {"slug": L["slug"], "secs": 30}, "late-visit")
        world.process_queue(real_now)
        assert len(api.calls) == n and not world.q1("SELECT id FROM queue WHERE visit='late-visit'"), "a step was replayed"
        world.set_enabled(False)
        world.enqueue(real_now, L["user_id"], "visit", {})
        world.tick()
        assert len(api.calls) == n, "paused, yet it acted"
        try:
            world.visit_now()
            raise AssertionError("visit_now worked while paused")
        except LS.Paused:
            pass
        world.set_enabled(True)
        world.x("DELETE FROM queue")
        return "a step 20 min late (website off) was dropped; while paused nothing happened and 'send one now' was refused"
    check("time the website was off is not replayed; pause stops everything", offline_and_pause)

    # 11 ── every request answered
    def all_answered():
        bad = [c for c in api.calls if c["code"] != 200]
        ok = [c for c in bad if c["path"].endswith("/act")]        # 'Do it now' refusals while picking learners
        bad = [c for c in bad if c not in ok]
        assert not bad, [(c["method"], c["path"], c["code"], str(c["reply"])[:80]) for c in bad[:5]]
        kinds = sorted({c["path"] for c in api.calls})
        return f"{len(api.calls)} requests, {len(kinds)} different endpoints, all answered"
    check("every request the simulated people sent was answered", all_answered)

    if world._con is not None:
        world._con.close()                             # so the private copy can be deleted (Windows)
    ok = sum(RESULTS)
    print(f"\n{ok} of {len(RESULTS)} checks passed.")
    return 0 if ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
