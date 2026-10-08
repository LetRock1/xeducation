"""
Checks for the v6.2 fixes, on a COPY of the database (the real one is never touched; no servers needed).

    user-backend\\venv\\Scripts\\python.exe tests\\test_v62_fixes.py

  1. every lead is re-scored by the model by itself (no hand-written decay, no stale model versions)
  2. no group of leads shares one score (the old decay capped them all at 59.9 / 79.9 / 39.9)
  3. the batch re-scoring gives exactly the same inputs and scores as scoring one person
  4. customers are not floored to 80; their page shows what they bought instead of a chance to buy
  5. a click on one of our emails never lowers a score; time away lowers it (as learned)
  6. the recommendation and the what-if paths agree, step by step, for many leads
  7. "Do it now" is logged as a hand-made decision and kept out of the uplift model's training data
  8. pressing "Retrain now" with nothing new does not add a duplicate run
  9. the email button opens the course page itself (with the email's token), not a tracking server
"""
import os
import random
import shutil
import sqlite3
import sys
import tempfile
import time
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "user-backend")
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)
os.environ.setdefault("PYTHONUTF8", "1")

RESULTS = []


def check(name, fn):
    t0 = time.perf_counter()
    try:
        info = fn()
        RESULTS.append(True)
        print(f"PASS  {name}  {info or ''}  ({(time.perf_counter() - t0):.1f} s)", flush=True)
    except Exception as e:
        RESULTS.append(False)
        print(f"FAIL  {name}  {type(e).__name__}: {e}", flush=True)


def main():
    src = os.path.join(BACKEND, "xeducation_user.db")
    if not os.path.exists(src):
        print("No database yet: run start-all.bat once first.")
        return 1
    tmp = tempfile.mkdtemp(prefix="xedu-test-")
    db_copy = os.path.join(tmp, "xeducation_user.db")
    con = sqlite3.connect(src)
    try:
        con.execute(f"VACUUM INTO '{db_copy}'")          # a consistent copy even while the servers run
    finally:
        con.close()

    import database as db
    db.DB_PATH = db_copy                                  # every module below now works on the copy
    import learning
    import nba
    import outreach
    import paths
    import predict
    import scoring

    def open_leads(limit=None):
        rows = db.fetchall("""SELECT l.id, l.user_id, l.lead_score, l.recommended_action, l.model_version
                              FROM leads l WHERE l.id IN (SELECT MAX(id) FROM leads GROUP BY user_id)
                              AND l.user_id NOT IN (SELECT user_id FROM purchases)""")
        return rows[:limit] if limit else rows

    def refresh():
        r = scoring.refresh_scores("test", verbose=False)
        assert r["status"] == "done", r
        version = predict.model_info().get("version")
        stale = db.fetchone("""SELECT COUNT(*) AS c FROM leads WHERE id IN (SELECT MAX(id) FROM leads GROUP BY user_id)
                               AND COALESCE(model_version, '') != ?""", (version,))["c"]
        assert stale == 0, f"{stale} leads still carry an older model's score"
        again = scoring.refresh_scores("test", verbose=False)
        assert again["updated"] == 0, f"a second refresh changed {again['updated']} leads (should be stable)"
        return f"{r['checked']} people, {r['updated']} re-scored with {version} in {r['seconds']} s; stable on a second run"
    check("every lead is re-scored by the current model, by itself", refresh)

    def no_identical():
        rows = [r for r in open_leads() if r["lead_score"] >= 20]
        if len(rows) < 20:
            return f"only {len(rows)} open leads with a score of 20+ (nothing to compare)"
        value, n = Counter(round(r["lead_score"], 2) for r in rows).most_common(1)[0]
        assert n <= max(3, len(rows) // 20), f"{n} of {len(rows)} leads share the score {value}"
        capped = [r for r in rows if round(r["lead_score"], 1) in (39.9, 59.9, 79.9)]
        assert len(capped) <= max(3, len(rows) // 20), f"{len(capped)} leads sit exactly at a tier ceiling"
        return f"{len(rows)} leads scored 20+; the most common score is shared by {n}"
    check("no group of leads shares one score (the old decay cap is gone)", no_identical)

    def batch_equals_single():
        ids = [r["user_id"] for r in db.fetchall("SELECT id AS user_id FROM users")]
        sample = random.Random(7).sample(ids, min(150, len(ids)))
        many = scoring.build_raw_many(sample)
        for u in sample:
            one = scoring.build_raw(u, recency=True)
            m = {k: v for k, v in many[u].items() if not k.startswith("_")}
            for k, v in one.items():
                if k == "away_days":
                    assert (v is None) == (m[k] is None) and (v is None or abs(v - m[k]) < 0.01), (u, k, v, m[k])
                else:
                    assert v == m[k], (u, k, v, m[k])
        p1 = [predict.predict_lead(scoring.build_raw(u, recency=True))["conversion_probability"] for u in sample[:40]]
        p2 = [x[0] for x in predict.predict_many([many[u] for u in sample[:40]])]
        assert max(abs(a - b) for a, b in zip(p1, p2)) < 1e-9
        return f"{len(sample)} people: identical inputs; identical scores"
    check("batch re-scoring = scoring one person at a time", batch_equals_single)

    def customers():
        row = db.fetchone("SELECT user_id FROM purchases ORDER BY id DESC LIMIT 1")
        if not row:
            return "no customers yet (nothing to check)"
        uid = row["user_id"]
        pred = predict.predict_lead(scoring.build_raw(uid, recency=True))
        assert abs(pred["lead_score"] - pred["conversion_probability"] * 100) < 0.01, "score is not the probability"
        now = nba.recommend_now(uid)
        owned = {p["course_slug"] for p in db.get_purchases(uid)}
        if not [c for c in db.get_cart(uid) if c["course_slug"] not in owned]:
            assert now["recommendation"] is None and now["customer"] and now["purchases"], now
            assert paths.plan(uid)["customer"]
        return f"customer {uid}: score = model probability ({pred['lead_score']:.1f}); page shows the purchase, no recommendation"
    check("customers are customers (no floor at 80, no chance-to-buy, no paths)", customers)

    def click_and_time():
        u = open_leads(1)[0]["user_id"]
        raw = scoring.build_raw(u, recency=True)
        s0 = predict.predict_lead(dict(raw, EmailOpenedCount=0))["lead_score"]
        for k in (1, 2, 4):
            assert predict.predict_lead(dict(raw, EmailOpenedCount=k))["lead_score"] >= s0 - 1e-9, f"{k} click(s) lowered the score"
        near = predict.predict_lead(dict(raw, away_days=0))["lead_score"]
        far = predict.predict_lead(dict(raw, away_days=60))["lead_score"]
        eff = (predict._load() or {}).get("live", {}).get("own_effects", {}).get("away_30_days_plus")
        if eff is not None and eff < 0:
            assert far < near, "60 days away did not lower the score although the loop learned it should"
        return f"clicks never lower it ({s0:.1f}); last seen today {near:.1f} vs 60 days ago {far:.1f}"
    check("email clicks never lower a score; time away lowers it", click_and_time)

    def agree():
        leads = open_leads()
        sample = random.Random(3).sample(leads, min(25, len(leads)))
        n = 0
        for l in sample:
            now = nba.recommend_now(l["user_id"])
            if now["recommendation"] is None:
                continue
            p = paths.plan(l["user_id"])
            assert p["best"] == now["recommendation"]["action"], (l["user_id"], p["best"], now["recommendation"])
            first = {s["action"]: s for s in p["steps"]}
            for o in now["options"]:
                if not o["blocked"]:
                    assert abs(first[o["action"]]["p_buy_step"] - o["p_convert"]) < 1e-9, (l["user_id"], o["action"])
            n += 1
        return f"{n} leads: same pick and same numbers"
    check("recommendation and what-if paths agree", agree)

    def manual_logged():
        cand = None
        for l in open_leads():              # a simulated learner: their address is never e-mailed
            u = db.get_user_by_id(l["user_id"])
            prof = db.get_profile(l["user_id"]) or {}
            if (u["email"].endswith("@demo.xeducation.test") and prof.get("do_not_email") != "Yes"
                    and not nba.settings.in_global_control(l["user_id"])):
                cand = l["user_id"]
                break
        if not cand:
            return "skipped: no simulated learner to try it on (the real ones are never e-mailed by a test)"
        from playbook import handle_trigger
        u = db.get_user_by_id(cand)
        now = nba.recommend_now(cand)
        slug = (now.get("course") or {}).get("slug")
        _, _, d = handle_trigger(cand, u["name"], u["email"], "manual", slug, force_action="email_info")
        row = db.fetchone("SELECT policy, propensity, action FROM nba_decisions WHERE id=?", (d["decision_id"],))
        assert row["policy"] == "manual" and row["propensity"] == 1.0 and row["action"] == "email_info", row
        con = db.get_conn()
        try:
            log = learning._decision_log(con, "2999-01-01 00:00:00")
        finally:
            con.close()
        assert d["decision_id"] not in set(log["id"]) if len(log) else True, "a hand-made decision is in the uplift training data"
        return f"decision {d['decision_id']} logged as 'manual' and kept out of the uplift model's training data"
    check("'Do it now' is logged and kept out of the uplift training", manual_logged)

    def no_duplicate_runs():
        n_known = learning.count_outcomes()
        db.execute("""INSERT INTO learning_runs (started_at, finished_at, as_of, reason, status, outcomes_known, new_outcomes)
                      VALUES (datetime('now','localtime'), datetime('now','localtime'), datetime('now','localtime'),
                              'test', 'done', ?, 0)""", (n_known,))
        before = db.fetchone("SELECT COUNT(*) AS c FROM learning_runs")["c"]
        r = learning.run(reason="manual", force=True, verbose=False)
        after = db.fetchone("SELECT COUNT(*) AS c FROM learning_runs")["c"]
        assert r["status"] == "nothing_new" and after == before, (r.get("status"), before, after)
        return f"'Retrain now' with 0 new outcomes: {r['message'][:60]}…"
    check("'Retrain now' with nothing new adds no run", no_duplicate_runs)

    def email_link():
        link = outreach.tracked_link("0" * 32, "d2c-brand-building")
        assert link.endswith("/courses/d2c-brand-building?ref=" + "0" * 32), link
        assert "/api/" not in link, link
        assert outreach.unsubscribe_link("0" * 32).endswith("/unsubscribe?t=" + "0" * 32)
        return link
    check("the email button opens the course page itself", email_link)

    shutil.rmtree(tmp, ignore_errors=True)
    ok = sum(RESULTS)
    print(f"\n{ok} of {len(RESULTS)} checks passed.")
    return 0 if ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
