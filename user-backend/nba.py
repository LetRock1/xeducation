"""
nba.py — Next-Best-Action at serving time.

decide()  : for one lead at one trigger (cart / checkout / wishlist / inactivity /
            enquiry), estimate P(buy) under every allowed action with the uplift
            model, pick the action with the best incremental profit (or nothing),
            with a small random exploration share, and LOG the decision with its
            propensity. Those logs + later purchases are what the closed loop
            retrains on (learning.py), and what lets us measure
            the policy honestly (inverse-propensity estimates).
execute() : carry the action out — send the email (with or without a coupon),
            or create a call / WhatsApp task for the sales team.
"""
import json
import os
import threading

import joblib
import numpy as np

import catalog
import database as db
import ml_features as F
import nba_core as N
import settings

MODEL_PATH = os.path.join(os.path.dirname(__file__), "ml_models", "nba_model.pkl")
EXPLORE_RATE = float(os.getenv("NBA_EXPLORE_RATE", settings.S["exploration_rate"]))
DAILY_CALL_CAPACITY = int(os.getenv("NBA_DAILY_CALLS", settings.S["daily_call_capacity"]))

_lock = threading.Lock()
_state = {"bundle": None, "mtime": None, "warned": False}
_rng = np.random.default_rng()


def _load():
    try:
        mtime = os.path.getmtime(MODEL_PATH)
    except OSError:
        if not _state["warned"]:
            print("[NBA] nba_model.pkl not found — using the built-in prior. start-all.bat trains it on first start.")
            _state["warned"] = True
        return None
    if _state["mtime"] != mtime:
        with _lock:
            try:
                _state.update(bundle=joblib.load(MODEL_PATH), mtime=mtime)
                print(f"[NBA] Loaded uplift model {_state['bundle']['version']}")
            except Exception as e:
                print(f"[NBA] Could not load {MODEL_PATH}: {e} — using the built-in prior.")
                _state.update(bundle=None, mtime=mtime)
    return _state["bundle"]


# Fallback when no trained model exists: conservative prior effects (log-odds)
_PRIOR = {"email_info": [0.05, 0, 0, 0, 0, 0, 0.2, 0, 0], "email_coupon_10": [0.1, 0, 0.4, -0.2, 0, 0, 0.1, 0, 0],
          "email_coupon_20": [0.2, 0, 0.7, -0.2, 0, 0, 0.1, 0, 0], "call": [0.1, 0, 0, 0, 0.7, 0.3, 0, 0, -0.4],
          "whatsapp": [0.1, 0, 0, 0, 0.2, 0, 0, 0.1, 0]}


def _anchor(probs: dict, base_prob: float) -> dict:
    """The lead model says how likely this person is to buy on their own (the learning loop keeps that
    honest on the control group); the uplift model says how much each action changes it. Every action's
    log-odds are shifted by the same amount so that 'do nothing' equals the lead score exactly: one number
    for 'on their own' everywhere (score, decision table, what-if paths), each action keeping its effect."""
    clip = lambda p: min(max(float(p), 1e-4), 1 - 1e-4)
    d = N._logit([clip(base_prob)])[0] - N._logit([clip(probs["none"])])[0]
    return {a: float(1 / (1 + np.exp(-(N._logit([clip(p)])[0] + d)))) for a, p in probs.items()}


def action_probabilities(features: dict, base_prob: float) -> dict:
    """P(buy within the outcome window | this person, action), for every action."""
    frame = F.to_model_frame([features])
    ctx = N.context(frame, np.array([base_prob]))
    b = _load()
    if b is None:
        base = N._logit([base_prob])[0]
        return {a: float(1 / (1 + np.exp(-(base + (np.dot(ctx[0], _PRIOR[a]) if a != "none" else 0)))))
                for a in N.ACTION_LIST}
    probs = N.predict_actions(b["model"], frame, np.array([base_prob]))
    return _anchor({a: float(p[0]) for a, p in probs.items()}, base_prob)


def _calls_today():
    return db.fetchone("""SELECT COUNT(*) AS c FROM sales_tasks WHERE task_type='call'
                          AND date(created_at)=date('now','localtime')""")["c"]


def _why(action, values, base_p, price):
    v = values[action]
    if action == "none":
        best_other = max((a for a in values if a != "none"), key=lambda a: values[a]["incremental_profit"])
        if base_p >= 0.7:
            return (f"Likely to buy anyway ({base_p*100:.0f}%) — contacting or discounting would mostly "
                    f"cost money without changing the outcome.")
        return (f"No action is expected to pay for itself right now (best option, "
                f"{N.ACTIONS[best_other]['label'].lower()}, would change the odds by "
                f"{values[best_other]['uplift']*100:+.1f} pts).")
    return (f"Expected to raise the chance of buying from {values['none']['p_convert']*100:.0f}% to "
            f"{v['p_convert']*100:.0f}% ({v['uplift']*100:+.1f} pts), worth about "
            f"₹{v['incremental_profit']:,.0f} more than doing nothing"
            + (f" even after the {int(N.ACTIONS[action]['discount']*100)}% discount" if N.ACTIONS[action]['discount'] else "")
            + ".")


def decide(user_id, trigger, pred, course_slug=None, explore=True, allowed=None, lead_id=None):
    """Choose the next best action for this lead and log the decision."""
    features = pred["features"]
    profile = db.get_profile(user_id) or {}
    has_phone = bool((profile.get("phone") or "").strip())
    base_p = float(pred["conversion_probability"])
    price = catalog.price_of(course_slug) or catalog.average_price()
    probs = action_probabilities(features, base_p)
    values = N.expected_values(probs, price)
    blocked = N.eligible(features, has_phone)
    if _calls_today() >= DAILY_CALL_CAPACITY and not blocked["call"]:
        blocked["call"] = "today's call capacity is used up"
    if allowed is not None:
        for a in N.ACTION_LIST:
            if a not in allowed and not blocked[a]:
                blocked[a] = f"not used for {trigger}"
    if (pred.get("raw", {}).get("past_purchases") or 0) > 0:
        for a in ("email_coupon_20",):
            blocked[a] = blocked[a] or "existing customer"
    if all(blocked[a] for a in N.ACTION_LIST):
        blocked["none"] = None      # nothing else is possible (opted out everywhere): do nothing
    action, policy, propensity, best = N.choose(values, blocked, EXPLORE_RATE if explore else 0.0, _rng)
    holdout = settings.in_global_control(user_id)
    if holdout:          # the untouched control group: decide (for the record) but never act
        action, policy, propensity = "none", "holdout", 1.0
    b = _load()
    options = [{"action": a, "label": N.ACTIONS[a]["label"], "blocked": blocked[a], **values[a]} for a in N.ACTION_LIST]
    if holdout:
        why = (f"In the {settings.S['global_control']['share']:.0%} control group: the CRM never contacts this lead "
               f"automatically, so what they do shows what happens without us. (The model would have chosen: "
               f"{N.ACTIONS[best]['label'].lower()}.)")
    else:
        why = _why(action, values, base_p, price) + (f" (Chosen at random as part of the {EXPLORE_RATE:.0%} learning sample.)"
                                                     if policy == "explore" and action != best else "")
    decision = {
        "action": action, "label": N.ACTIONS[action]["label"], "policy": policy, "propensity": propensity,
        "model_best": best, "trigger": trigger, "why": why,
        "detail": f"Course price ₹{price:,.0f} · model {b['version'] if b else 'prior'} · trigger {trigger}",
        "options": options, "model_version": b["version"] if b else "prior", "price": price,
    }
    decision["decision_id"] = db.execute("""
        INSERT INTO nba_decisions (user_id, lead_id, trigger_reason, action, model_best, policy, propensity,
                                   base_probability, price, options_json, features_json, model_version)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (user_id, lead_id, trigger, action, best, policy, propensity, base_p, price,
         json.dumps(options), json.dumps(features), decision["model_version"]))
    return decision


def offer_pct(action):
    return int(round(N.ACTIONS[action]["discount"] * 100))


def attach_to_lead(lead_id, decision):
    db.execute("UPDATE leads SET nba_action=?, nba_json=? WHERE id=?",
               (decision["action"], json.dumps({k: v for k, v in decision.items()}), lead_id))
    db.execute("UPDATE nba_decisions SET lead_id=? WHERE id=?", (lead_id, decision["decision_id"]))


def create_task(user_id, lead_id, decision, title, detail):
    ch = N.ACTIONS[decision["action"]]["channel"]
    gain = next(o["incremental_profit"] for o in decision["options"] if o["action"] == decision["action"])
    existing = db.fetchone("SELECT id, expected_gain FROM sales_tasks WHERE user_id=? AND task_type=? AND status='open'",
                           (user_id, ch))
    if existing:   # one open call / WhatsApp per person — refresh it instead of duplicating
        db.execute("UPDATE sales_tasks SET lead_id=?, decision_id=?, title=?, detail=?, expected_gain=? WHERE id=?",
                   (lead_id, decision["decision_id"], title, detail, max(gain, existing["expected_gain"] or 0),
                    existing["id"]))
        return existing["id"]
    return db.execute("""INSERT INTO sales_tasks (user_id, lead_id, decision_id, task_type, title, detail,
                                                  expected_gain)
                         VALUES (?,?,?,?,?,?,?)""",
                      (user_id, lead_id, decision["decision_id"], ch, title, detail,
                       next(o["incremental_profit"] for o in decision["options"] if o["action"] == decision["action"])))


def mark_executed(decision_id):
    db.execute("UPDATE nba_decisions SET executed_at=datetime('now','localtime') WHERE id=?", (decision_id,))
