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

# In DEMO_MODE, decay after 10 minutes of inactivity so it can be shown in a demo
# (long enough not to demote a lead while you are still presenting it);
# otherwise decay leads inactive for 7 days.
DECAY_INACTIVITY_MINUTES = 10 if DEMO_MODE else 7 * 24 * 60

TIER_ORDER = [
    "Target Immediately",
    "Nurture via Email/WhatsApp",
    "Marketing Campaign",
    "Low Priority",
]

TIER_CEILING = {
    "Target Immediately": 100.0,
    "Nurture via Email/WhatsApp": 79.9,
    "Marketing Campaign": 59.9,
    "Low Priority": 39.9,
}

def _recompute_plv(conn, user_id, course_slug, probability):
    """PLV = money already spent + P(convert) × price of the course of interest."""
    import catalog
    spent = conn.execute(
        "SELECT COALESCE(SUM(price_paid),0) as s FROM purchases WHERE user_id=?", (user_id,)
    ).fetchone()["s"]
    price = catalog.price_of(course_slug) or catalog.average_price()
    p = float(probability or 0)
    p = p / 100.0 if p > 1 else p
    return round(spent + price * p, 2)


def lead_decay_job():
    conn = _conn()
    try:
        cutoff = conn.execute(
            "SELECT datetime('now','localtime',?) as c", (f"-{DECAY_INACTIVITY_MINUTES} minutes",)
        ).fetchone()["c"]

        leads = conn.execute(
            "SELECT * FROM leads WHERE recommended_action != 'Low Priority' AND decayed = 0 "
            "AND id IN (SELECT MAX(id) FROM leads GROUP BY user_id) "  # latest lead per user
            "AND user_id NOT IN (SELECT user_id FROM purchases)"        # customers don't decay
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

            # keep score and tier consistent: cap the score at the new tier's ceiling,
            # and value the lead at that (lower) effective probability
            new_score = min(lead["lead_score"] or 0, TIER_CEILING[new_tier])
            course_slug = lead["course_slug"] if "course_slug" in lead.keys() else None
            new_plv = _recompute_plv(conn, user_id, course_slug,
                                     min(lead["conversion_probability"] or 0, new_score / 100))
            conn.execute("UPDATE leads SET recommended_action=?, lead_score=?, decayed=1, plv=? WHERE id=?",
                         (new_tier, new_score, new_plv, lead["id"]))
            conn.execute(
                """INSERT INTO lead_score_history (lead_id, user_id, old_score, new_score, old_tier, new_tier, reason)
                   VALUES (?,?,?,?,?,?,?)""",
                (lead["id"], user_id, lead["lead_score"], new_score,
                 lead["recommended_action"], new_tier, "decay"),
            )
            downgraded += 1

        conn.commit()
        print(f"[DECAY JOB] Downgraded {downgraded} lead(s)")
    except Exception as e:
        print("[DECAY JOB ERROR]", e)
    finally:
        conn.close()
