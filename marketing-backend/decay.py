"""
decay.py — Lead decay / re-scoring job.
Downgrades a lead's tier one step if the user has shown no fresh
behaviour_events or email opens since the lead was created / last active.
"""
import os
import sqlite3
from dotenv import load_dotenv

load_dotenv()

USER_DB = os.getenv("USER_DB_PATH", "../user-backend/xeducation_user.db")
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"

# In DEMO_MODE, decay after 2 minutes of inactivity so it's demoable;
# otherwise decay leads inactive for 7 days.
DECAY_INACTIVITY_MINUTES = 2 if DEMO_MODE else 7 * 24 * 60

TIER_ORDER = [
    "Target Immediately",
    "Nurture via Email/WhatsApp",
    "Marketing Campaign",
    "Low Priority",
]

PLV_TIER_MULTIPLIER = {
    "Target Immediately": 1.5,
    "Nurture via Email/WhatsApp": 1.0,
    "Marketing Campaign": 0.6,
    "Low Priority": 0.2,
}


def _recompute_plv(conn, user_id, recommended_action, conversion_probability):
    spent = conn.execute(
        "SELECT COALESCE(SUM(price_paid),0) as s FROM purchases WHERE user_id=?", (user_id,)
    ).fetchone()["s"]
    avg_price = conn.execute("SELECT COALESCE(AVG(price),0) as p FROM cart").fetchone()["p"] or 5000.0
    multiplier = PLV_TIER_MULTIPLIER.get(recommended_action, 0.3)
    p = float(conversion_probability or 0)
    p = p / 100.0 if p > 1 else p          # stored as 0-1 by predict_lead()
    return round(spent + avg_price * p * multiplier, 2)


def _conn():
    c = sqlite3.connect(USER_DB, check_same_thread=False, timeout=30)
    c.row_factory = sqlite3.Row
    return c


def lead_decay_job():
    conn = _conn()
    try:
        cutoff = conn.execute(
            "SELECT datetime('now','localtime',?) as c", (f"-{DECAY_INACTIVITY_MINUTES} minutes",)
        ).fetchone()["c"]

        leads = conn.execute(
            "SELECT * FROM leads WHERE recommended_action != 'Low Priority' AND decayed = 0"
        ).fetchall()
        print(f"[DECAY JOB] Checking {len(leads)} active-tier leads")

        downgraded = 0
        for lead in leads:
            user_id = lead["user_id"]
            last_event = conn.execute(
                "SELECT MAX(created_at) as t FROM behaviour_events WHERE user_id=?", (user_id,)
            ).fetchone()["t"]
            last_open = conn.execute(
                "SELECT MAX(opened_at) as t FROM email_sends WHERE user_id=?", (user_id,)
            ).fetchone()["t"]

            candidates = [x for x in (lead["created_at"], last_event, last_open) if x]
            last_active = max(candidates) if candidates else lead["created_at"]

            if last_active >= cutoff:
                continue  # still active

            idx = TIER_ORDER.index(lead["recommended_action"]) if lead["recommended_action"] in TIER_ORDER else len(TIER_ORDER) - 1
            new_tier = TIER_ORDER[min(idx + 1, len(TIER_ORDER) - 1)]

            new_plv = _recompute_plv(conn, user_id, new_tier, lead["conversion_probability"] or 0.5)
            conn.execute("UPDATE leads SET recommended_action=?, decayed=1, plv=? WHERE id=?",
                         (new_tier, new_plv, lead["id"]))
            conn.execute(
                """INSERT INTO lead_score_history (lead_id, user_id, old_score, new_score, old_tier, new_tier, reason)
                   VALUES (?,?,?,?,?,?,?)""",
                (lead["id"], user_id, lead["lead_score"], lead["lead_score"],
                 lead["recommended_action"], new_tier, "decay"),
            )
            downgraded += 1

        conn.commit()
        print(f"[DECAY JOB] Downgraded {downgraded} lead(s)")
    except Exception as e:
        print("[DECAY JOB ERROR]", e)
    finally:
        conn.close()
