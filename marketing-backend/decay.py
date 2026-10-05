"""
decay.py — Lead decay / re-scoring job.
Downgrades a lead's tier one step if the user has shown no fresh
behaviour_events or email opens since the lead was created / last active.

Tiers and the inactivity period come from crm_settings.json
(decay_inactive_minutes: 10 in demo mode so it can be shown, 7 days otherwise).
"""
import os
import sqlite3
from dotenv import load_dotenv

import settings

load_dotenv()

USER_DB = os.getenv("USER_DB_PATH", "../user-backend/xeducation_user.db")
DEMO_MODE = settings.DEMO_MODE
DECAY_INACTIVITY_MINUTES = int(settings.by_mode("decay_inactive_minutes"))

_TIERS = settings.tiers()                                   # [(min_score, name), ...] highest first
TIER_ORDER = [name for _, name in _TIERS]
# highest score a lead may keep after being moved down into a tier
TIER_CEILING = {name: (100.0 if i == 0 else _TIERS[i - 1][0] - 0.1) for i, (_, name) in enumerate(_TIERS)}
LOWEST_TIER = TIER_ORDER[-1]


def _conn():
    c = sqlite3.connect(USER_DB, check_same_thread=False, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout=30000")
    return c


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
            "SELECT * FROM leads WHERE recommended_action != ? AND decayed = 0 "
            "AND id IN (SELECT MAX(id) FROM leads GROUP BY user_id) "  # latest lead per user
            "AND user_id NOT IN (SELECT user_id FROM purchases)",       # customers don't decay
            (LOWEST_TIER,)
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
        return downgraded
    except Exception as e:
        print("[DECAY JOB ERROR]", e)
        return 0
    finally:
        conn.close()
