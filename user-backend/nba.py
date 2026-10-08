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


def _calls_today(user_id=None):
    """Call tasks created today for people like this one. Simulated learners are called by the simulated
    advisor (ml/live_simulation.py), who has the same daily capacity of their own, so they never use up a real
    advisor's calls (and real people never use up theirs)."""
    sql = """SELECT COUNT(*) AS c FROM sales_tasks t JOIN users u ON u.id = t.user_id
             WHERE t.task_type='call' AND date(t.created_at)=date('now','localtime')"""
    if user_id is not None:
        user = db.get_user_by_id(user_id) or {}
        sim = settings.is_simulated_email(user.get("email"))
        sql += f" AND u.email {'LIKE' if sim else 'NOT LIKE'} '%@{settings.SIMULATED_DOMAIN}'"
    return db.fetchone(sql)["c"]


def _why(action, values, base_p, price):
    """The decision in plain words (also used by the simulated history)."""
    v = values[action]
    if action == "none":
        others = [a for a in values if a != "none"]
        best_other = max(others, key=lambda a: values[a]["incremental_profit"]) if others else None
        if base_p >= 0.7:
            return (f"Likely to buy anyway ({base_p*100:.0f}% chance without any step) — a discount or a call would "
                    f"mostly cost money without changing the outcome.")
        if best_other is None:
            return "No step is possible for this person right now."
        o = values[best_other]
        return (f"No step pays for itself right now: the best one ({N.ACTIONS[best_other]['label'].lower()}) would "
                f"change the chance of buying by {o['uplift']*100:+.1f} pts, worth ₹{o['incremental_profit']:,.0f} "
                f"after its cost and any discount.")
    disc = N.ACTIONS[action]["discount"]
    p_from, p_to = values['none']['p_convert'] * 100, v['p_convert'] * 100
    if v["uplift"] < 0:
        change = f"Expected to lower the chance of buying within 14 days from {p_from:.0f}% to {p_to:.0f}% ({v['uplift']*100:+.1f} pts)"
    else:
        change = f"Raises the chance of buying within 14 days from {p_from:.0f}% to {p_to:.0f}% ({v['uplift']*100:+.1f} pts)"
    if v["incremental_profit"] >= 0:
        money = (f", worth about ₹{v['incremental_profit']:,.0f} more than doing nothing"
                 + (f" even after the {int(disc*100)}% discount" if disc else ""))
    else:
        money = (f"; it costs about ₹{-v['incremental_profit']:,.0f} compared with doing nothing"
                 + (f" (the {int(disc*100)}% discount also goes to people who would buy anyway)" if disc else ""))
    return change + money + "."


def model_version():
    b = _load()
    return b["version"] if b else "prior"


def evaluate(user_id, pred, course_slug=None, allowed=None, trigger=None):
    """What every possible step is worth for this person now: chance to buy, change vs doing nothing, extra
    profit, and why a step is not allowed. The ONE calculation behind the automatic decisions, the lead page's
    recommendation and the what-if paths, so they can never disagree."""
    features = pred["features"]
    profile = db.get_profile(user_id) or {}
    has_phone = bool((profile.get("phone") or "").strip())
    base_p = float(pred["conversion_probability"])
    price = catalog.price_of(course_slug) or catalog.average_price()
    probs = action_probabilities(features, base_p)
    values = N.expected_values(probs, price)
    blocked = N.eligible(features, has_phone)
    if _calls_today(user_id) >= DAILY_CALL_CAPACITY and not blocked["call"]:
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
    options = [{"action": a, "label": N.ACTIONS[a]["label"], "blocked": blocked[a],
                "discount": N.ACTIONS[a]["discount"], "cost": N.ACTIONS[a]["cost_inr"], **values[a]}
               for a in N.ACTION_LIST]
    return {"features": features, "base_p": base_p, "price": price, "probs": probs, "values": values,
            "blocked": blocked, "has_phone": has_phone, "options": options}


def best_action(ev):
    """The step the model picks (no random exploration): highest extra profit, or nothing."""
    _, _, _, best = N.choose(ev["values"], ev["blocked"], 0.0, _rng)
    return best


def decide(user_id, trigger, pred, course_slug=None, explore=True, allowed=None, lead_id=None, force_action=None):
    """Choose the next best action for this lead and log the decision.
    force_action: a step a person on the team chose by hand ("Do it now" on the lead page). It is carried out
    and logged like any decision (policy 'manual'), so the learning loop is told about it too."""
    ev = evaluate(user_id, pred, course_slug, allowed=allowed, trigger=trigger)
    values, blocked, base_p, price = ev["values"], ev["blocked"], ev["base_p"], ev["price"]
    holdout = settings.in_global_control(user_id)
    if force_action is not None:
        if force_action not in N.ACTIONS:
            raise ValueError(f"Unknown step '{force_action}'.")
        if blocked.get(force_action):
            raise ValueError(f"Not possible for this person: {blocked[force_action]}.")
        if holdout:
            raise ValueError("This person is in the control group: the CRM never contacts them, so their outcome "
                             "shows what happens without us.")
        best = best_action(ev)
        action, policy, propensity = force_action, "manual", 1.0
    else:
        action, policy, propensity, best = N.choose(values, blocked, EXPLORE_RATE if explore else 0.0, _rng)
        if holdout:          # the untouched control group: decide (for the record) but never act
            action, policy, propensity = "none", "holdout", 1.0
    b = _load()
    options = ev["options"]
    if holdout:
        why = (f"In the {settings.S['global_control']['share']:.0%} control group: the CRM never contacts this lead "
               f"automatically, so what they do shows what happens without us. (The model would have chosen: "
               f"{N.ACTIONS[best]['label'].lower()}.)")
    elif policy == "manual":
        why = ("Chosen by hand from the lead page. " + _why(action, values, base_p, price)
               + ("" if action == best else f" (The model's own pick: {N.ACTIONS[best]['label'].lower()}.)"))
    else:
        why = _why(action, values, base_p, price) + (f" (Chosen at random as part of the {EXPLORE_RATE:.0%} learning sample;"
                                                     f" the model's own pick: {N.ACTIONS[best]['label'].lower()}.)"
                                                     if policy == "explore" and action != best else "")
    decision = {
        "action": action, "label": N.ACTIONS[action]["label"], "policy": policy, "propensity": propensity,
        "model_best": best, "model_best_label": N.ACTIONS[best]["label"], "trigger": trigger, "why": why,
        "detail": f"Course price ₹{price:,.0f} · model {b['version'] if b else 'prior'} · trigger {trigger}",
        "options": options, "model_version": b["version"] if b else "prior", "price": price,
        "base_probability": base_p, "lead_model_version": pred.get("model_version"),
    }
    decision["decision_id"] = db.execute("""
        INSERT INTO nba_decisions (user_id, lead_id, trigger_reason, action, model_best, policy, propensity,
                                   base_probability, price, options_json, features_json, model_version)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (user_id, lead_id, trigger, action, best, policy, propensity, base_p, price,
         json.dumps(options), json.dumps(ev["features"]), decision["model_version"]))
    return decision


def recommend_now(user_id):
    """What the CRM would do for this person if a step were taken right now (nothing is logged or sent).
    Same calculation as an automatic decision (evaluate), on the person as they are now: current behaviour,
    time since their last visit, current models. Used by the lead page and the what-if paths."""
    import scoring
    from predict import predict_lead
    user = db.get_user_by_id(user_id)
    if not user:
        return None
    purchases = db.get_purchases(user_id)
    owned = {p["course_slug"] for p in purchases}
    cart = [c for c in db.get_cart(user_id) if c["course_slug"] not in owned]
    base = {"user_id": user_id, "name": user["name"], "control_group": settings.in_global_control(user_id),
            "customer": bool(purchases), "away_days": scoring.days_since(scoring.last_seen(user_id)),
            "purchases": [{"course": p["course_title"], "course_slug": p["course_slug"], "paid": p["price_paid"],
                           "coupon": p.get("coupon_used"), "at": p["purchased_at"]} for p in purchases],
            "lead_model": None, "nba_model": model_version()}
    if purchases and not cart:
        return {**base, "recommendation": None,
                "message": (f"{user['name']} is a customer (bought {purchases[0]['course_title']}). The CRM does not chase "
                            "customers for a course they own; it only acts again if they put another course in the cart.")}
    slug = cart[0]["course_slug"] if cart else scoring.interest_slug(user_id)
    if slug in owned:
        slug = None
    raw = scoring.build_raw(user_id, course=slug, recency=True)
    pred = predict_lead(raw, explain=True)
    pred["raw"] = raw
    ev = evaluate(user_id, pred, slug)
    best = best_action(ev)
    tips = []
    try:
        import recourse
        tips = recourse.tips_for(pred["features"], pred["lead_score"])
    except Exception:
        pass
    return {**base, "lead_model": pred["model_version"],
            "course": {"slug": slug, "title": catalog.title_of(slug) if slug else None, "price": ev["price"]},
            "score": pred["lead_score"], "probability": pred["conversion_probability"], "tier": pred["recommended_action"],
            "away_days": pred.get("away_days"), "factors": pred.get("factors") or [], "tips": tips,
            "features": ev["features"], "options": ev["options"],
            "recommendation": {"action": best, "label": N.ACTIONS[best]["label"],
                               "why": _why(best, ev["values"], ev["base_p"], ev["price"]),
                               "extra_profit": ev["values"][best]["incremental_profit"],
                               "p_buy": ev["values"][best]["p_convert"]}}


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
