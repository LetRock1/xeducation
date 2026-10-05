"""
adoption.py — A/B winners that the CRM adopts by itself, and keeps checking.

When an A/B test is final (its 14-day window has passed) and one email variant clearly won, the
winning wording becomes the standard INFORMATION email for the test's audience: every automatic
"send an information email" step of the next-best-action engine uses it from then on.

It is never adopted blindly. A check group (crm_settings.json: ab_testing.adoption_check_share,
default 10 % of the audience, chosen by a hash of the person) keeps getting the old standard
email. The CRM compares the two continuously with the same statistics as the A/B tests:
    confirmed  the adopted email is still better (95 % interval of the lift above zero)
    checking   not enough evidence yet either way
    reverted   the adopted email is now WORSE than the old one -> the CRM switches back by itself
(Industry practice calls this "ship the winner with a holdback".)

Only content winners are adopted: a variant that carries a discount is not, because whether to
give a discount is the next-best-action engine's decision for each person.

No web code here, so the dashboard API (main.py) and the history generator share it.
"""
import json
from datetime import datetime, timedelta

import experiments as X

CHECK = "check"
ADOPTED = "adopted"
MIN_PER_ARM = 30
ARM_TEXT = {CHECK: "Old standard email (check group)", ADOPTED: "Adopted winner"}


def _ts(s):
    return datetime.strptime(str(s)[:19], "%Y-%m-%d %H:%M:%S")


def arms(check_share):
    s = min(max(float(check_share), 0.01), 0.5)
    return [(CHECK, s), (ADOPTED, 1.0 - s)]


def arm_for(adoption_id, user_id, check_share):
    """('adopted' | 'check', probability) — fixed per person, like every assignment in the CRM."""
    return X.arm_for("adoption", adoption_id, user_id, arms(check_share))


def winner_to_adopt(test, analysis, variants):
    """The variant to adopt, or None. test: ab_tests row; analysis: experiments.analyse() output."""
    if not analysis or not analysis.get("final"):
        return None
    v = analysis.get("verdict") or {}
    if v.get("status") != "winner":
        return None
    key = v.get("winner")
    var = next((x for x in variants if x.get("key") == key), None)
    if not var or int(var.get("offer_pct") or 0) > 0:
        return None
    comp = next((c for c in analysis.get("comparisons", []) if c.get("variant") == key), None)
    return {"variant": var, "comparison": comp}


def new_adoption(test, pick, check_share, now):
    """Row for adopted_emails."""
    var, comp = pick["variant"], pick["comparison"] or {}
    lo, hi = (comp.get("lift_ci") or [None, None])
    return {"ab_test_id": test["id"], "test_name": test.get("name"), "audience": test.get("tier") or "All leads",
            "metric": test.get("metric") or "purchase", "variant_key": var.get("key"),
            "variant_label": var.get("label") or f"Variant {var.get('key')}", "subject": var.get("subject"),
            "body": var.get("body"), "test_lift": comp.get("lift"), "test_lift_lo": lo, "test_lift_hi": hi,
            "check_share": float(check_share), "status": "active", "adopted_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "simulated": 1 if str(test.get("name", "")).startswith("(simulated)") or test.get("simulated") else 0}


def evaluate(adoption, assignments, purchases, clicks, now, window_days=14, alpha=0.05):
    """Adopted vs old email on the people assigned so far. Returns (state, check dict)."""
    t = {"id": adoption["id"], "metric": adoption.get("metric") or "purchase",
         "variants": [{"key": CHECK, "label": ARM_TEXT[CHECK]}, {"key": ADOPTED, "label": ARM_TEXT[ADOPTED]}]}
    a = X.analyse(t, assignments, purchases, clicks, now=now, window_days=window_days, alpha=alpha)
    arm = {s["arm"]: s for s in a["arms"]}
    comp = next((c for c in a["comparisons"] if c["variant"] == ADOPTED), None)
    n_check, n_adopt = arm.get(CHECK, {}).get("n", 0), arm.get(ADOPTED, {}).get("n", 0)
    state, why = "checking", None
    if comp and n_check >= MIN_PER_ARM and n_adopt >= MIN_PER_ARM:
        lo, hi = comp["lift_ci"]
        if hi is not None and hi < 0:
            state = "reverted"
            why = (f"The adopted email is now worse than the old one ({comp['lift']*100:+.1f} points, 95% interval "
                   f"{lo*100:+.1f} to {hi*100:+.1f}) — switched back to the old email.")
        elif lo is not None and lo > 0:
            state = "confirmed"
            why = (f"Still winning: {comp['lift']*100:+.1f} points vs the old email "
                   f"(95% interval {lo*100:+.1f} to {hi*100:+.1f}).")
        else:
            why = f"No clear difference yet ({comp['lift']*100:+.1f} points; the 95% interval still includes zero)."
    else:
        why = f"Collecting evidence: {n_adopt} people got the adopted email, {n_check} the old one (need {MIN_PER_ARM}+ each)."
    check = {"at": now.strftime("%Y-%m-%d %H:%M:%S"), "metric": t["metric"], "state": state, "why": why,
             "arms": [dict({k: arm[x].get(k) for k in ("arm", "n", "rate", "rate_ci", "purchases", "clicks")},
                           label=ARM_TEXT[x]) for x in (ADOPTED, CHECK) if x in arm],
             "lift": comp["lift"] if comp else None, "lift_ci": comp["lift_ci"] if comp else None,
             "p": comp.get("p_value") if comp else None}
    return state, check


def analyse_ab(uq, test, variants, now, window_days=14, alpha=0.05, power=0.8, mde=0.05, email_cost=2.0,
               min_segment=30):
    """experiments.analyse() for an A/B test stored in the marketing DB (assignments in the user DB).
    Same inputs as the dashboard's analysis (main._analyse); used by the history generator."""
    rows = uq("""SELECT user_id, arm, probability, assigned_at, tier, occupation, device, source
                 FROM experiment_assignments WHERE experiment_type='ab' AND experiment_id=?""", (test["id"],))
    users = sorted({r["user_id"] for r in rows})
    purchases, clicks = {}, {}
    for i in range(0, len(users), 500):
        chunk = users[i:i + 500]
        q = ",".join("?" * len(chunk))
        for p in uq(f"SELECT user_id, purchased_at, price_paid, discount_amount FROM purchases WHERE user_id IN ({q})", chunk):
            purchases.setdefault(p["user_id"], []).append((p["purchased_at"], p["price_paid"] or 0, p["discount_amount"] or 0))
    for c in uq("SELECT user_id, first_clicked_at FROM email_sends WHERE ab_test_id=? AND first_clicked_at IS NOT NULL",
                (test["id"],)):
        clicks[c["user_id"]] = c["first_clicked_at"]
    t = {"id": test["id"], "metric": test.get("metric") or "click", "variants": variants}
    return X.analyse(t, rows, purchases, clicks, now=now, window_days=window_days, alpha=alpha, power=power,
                     mde=float(test.get("mde") or mde), email_cost=email_cost, min_segment=min_segment)


def load_inputs(uq, adoption_id):
    """Assignments, purchases and first clicks for one adoption (uq: query function on the user DB)."""
    rows = uq("""SELECT user_id, arm, probability, assigned_at, tier, occupation, device, source
                 FROM experiment_assignments WHERE experiment_type='adoption' AND experiment_id=?""", (adoption_id,))
    users = sorted({r["user_id"] for r in rows})
    purchases, clicks = {}, {}
    for i in range(0, len(users), 500):
        chunk = users[i:i + 500]
        q = ",".join("?" * len(chunk))
        for p in uq(f"SELECT user_id, purchased_at, price_paid, discount_amount FROM purchases WHERE user_id IN ({q})", chunk):
            purchases.setdefault(p["user_id"], []).append((p["purchased_at"], p["price_paid"] or 0, p["discount_amount"] or 0))
    for c in uq("""SELECT user_id, MIN(first_clicked_at) AS t FROM email_sends WHERE adoption_id=? AND first_clicked_at IS NOT NULL
                   GROUP BY user_id""", (adoption_id,)):
        clicks[c["user_id"]] = c["t"]
    return rows, purchases, clicks


def run_checks(uq, uex, tests, analyse_fn, variants_fn, now, check_share, window_days=14, alpha=0.05,
               auto_adopt=True, log=print):
    """One pass: adopt new final winners, re-check active adoptions. Returns a list of what changed.
    uq/uex: query/execute on the user DB; tests: ab_tests rows; analyse_fn(test, now) -> analysis;
    variants_fn(test) -> variant list."""
    changes = []
    have = {r["ab_test_id"] for r in uq("SELECT ab_test_id FROM adopted_emails")}
    if auto_adopt:
        for t in tests:
            if t["id"] in have or not t.get("sent_at") or not t.get("variants_json"):
                continue
            try:
                started = _ts(t.get("started_at") or t["sent_at"])
            except ValueError:
                continue
            if now < started + timedelta(days=window_days):
                continue
            pick = winner_to_adopt(t, analyse_fn(t, now), variants_fn(t))
            if not pick:
                continue
            row = new_adoption(t, pick, check_share, now)
            cols = list(row)
            new_id = uex(f"INSERT INTO adopted_emails ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                         tuple(row[c] for c in cols))
            # an older adoption for the same audience is superseded by the new winner
            uex("""UPDATE adopted_emails SET status='superseded', decided_at=?, reason=? WHERE id != ? AND audience=?
                   AND status IN ('active','confirmed')""",
                (row["adopted_at"], f"Replaced by the winner of '{row['test_name']}'.", new_id, row["audience"]))
            changes.append({"adopted": new_id, "test": t.get("name"), "variant": row["variant_label"]})
            log(f"[ADOPT] '{t.get('name')}': '{row['variant_label']}' is now the standard information email for "
                f"{row['audience']} ({int(round(row['check_share'] * 100))}% keep the old email as a check)")
    for a in uq("SELECT * FROM adopted_emails WHERE status IN ('active','confirmed')"):
        rows, purchases, clicks = load_inputs(uq, a["id"])
        state, check = evaluate(a, rows, purchases, clicks, now, window_days, alpha)
        new_status = "reverted" if state == "reverted" else ("confirmed" if state == "confirmed" else "active")
        if new_status != a["status"] and new_status == "reverted":
            uex("UPDATE adopted_emails SET status='reverted', decided_at=?, reason=?, check_json=? WHERE id=?",
                (now.strftime("%Y-%m-%d %H:%M:%S"), check["why"], json.dumps(check), a["id"]))
            changes.append({"reverted": a["id"], "test": a["test_name"]})
            log(f"[ADOPT] reverted '{a['variant_label']}' ({a['audience']}): {check['why']}")
        else:
            uex("UPDATE adopted_emails SET status=?, check_json=? WHERE id=?", (new_status, json.dumps(check), a["id"]))
    return changes


def personalise(text, first_name, course):
    return (text or "").replace("{first_name}", first_name or "there").replace("{course}", course or "our programmes")
