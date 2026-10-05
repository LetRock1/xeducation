"""
adopted.py — which information email to send, now that A/B winners can be adopted.

The marketing backend (marketing-backend/adoption.py) turns a final, clear A/B winner into the
standard information email of its audience and keeps a check group on the old email. This module
is the sending side: for an automatic "information email" step it finds the adopted email that
applies to the lead's tier, decides by a fixed hash of the person whether they are in the check
group, and records that assignment so both groups can be compared.
"""
import hashlib

import database as db


def _unit(kind, experiment_id, user_id):
    """Same rule as marketing-backend/experiments.py unit(): fixed per (experiment, person)."""
    h = hashlib.sha256(f"{kind}:{experiment_id}:{user_id}".encode()).hexdigest()
    return int(h[:15], 16) / float(16 ** 15)


def current_for(tier):
    """The adopted information email for this tier (a tier-specific one first, else 'All leads')."""
    try:
        rows = db.fetchall("""SELECT * FROM adopted_emails WHERE status IN ('active','confirmed')
                              AND audience IN (?, 'All leads') ORDER BY id DESC""", (tier or "",))
    except Exception:                     # table not there yet (older database before init)
        return None
    for r in rows:
        if r["audience"] == tier:
            return dict(r)
    return dict(rows[0]) if rows else None


def arm(adoption, user_id):
    """('adopted' | 'check', probability of that arm)."""
    share = min(max(float(adoption.get("check_share") or 0.10), 0.01), 0.5)
    return ("check", share) if _unit("adoption", adoption["id"], user_id) < share else ("adopted", 1.0 - share)


def personalise(text, first_name, course):
    return (text or "").replace("{first_name}", first_name or "there").replace("{course}", course or "our programmes")


def record(adoption, user_id, lead_id, arm_name, prob, tier=None, occupation=None, device=None, source=None, at=None):
    """First assignment per person (later emails keep the same arm and are not new data points)."""
    db.execute("""INSERT OR IGNORE INTO experiment_assignments (experiment_type, experiment_id, user_id, lead_id, arm,
                  probability, tier, occupation, device, source, assigned_at)
                  VALUES ('adoption', ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, datetime('now','localtime')))""",
               (adoption["id"], user_id, lead_id, arm_name, prob, tier, occupation, device, source, at))
