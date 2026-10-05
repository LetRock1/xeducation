"""
nba_core.py — Next-Best-Action: the shared core (used by training, evaluation
and the live server, exactly like ml_features.py).

The question a lead SCORE answers:   "How likely is this person to buy?"
The question NEXT-BEST-ACTION answers: "Which of our actions will CHANGE
whether they buy, and is it worth what it costs?"

They are different. The old playbook (and tier-based workflows in typical
CRMs) gave the biggest discount to the hottest leads — people who would
mostly have bought anyway — so the discount was money given away. An uplift
model estimates, for every action a, P(buy | person, a) and picks

    a* = argmax_a  E[profit | a] − E[profit | do nothing]
       E[profit | a] = P(buy | x, a) × price × (1 − discount_a) − cost_a

and does nothing at all when no action pays for itself.

Model: a logistic "S-learner" with action × context interactions:
    logit P(buy | x, a) = β·c(x) + γ_a·c(x)        (γ_none = 0)
where c(x) is a small, interpretable context vector built on top of the
lead-score model's own probability. Each γ_a is literally "how much action a
moves the odds for people like this", so the decision is explainable.
"""
import numpy as np
import pandas as pd

# ── The actions the system can take ───────────────────────────────────────────
# cost_inr = cost of performing the action (advisor time, messaging), charged
# whether or not the person buys. discount = fraction of price given up IF they buy.
_DEFAULT_ACTIONS = {
    "none":            {"label": "Do nothing for now", "channel": None, "discount": 0.00, "cost_inr": 0},
    "email_info":      {"label": "Send an information email", "channel": "email", "discount": 0.00, "cost_inr": 2},
    "email_coupon_10": {"label": "Send email with 10% coupon", "channel": "email", "discount": 0.10, "cost_inr": 2},
    "email_coupon_20": {"label": "Send email with 20% coupon", "channel": "email", "discount": 0.20, "cost_inr": 2},
    "call":            {"label": "Advisor phone call", "channel": "call", "discount": 0.00, "cost_inr": 150},
    "whatsapp":        {"label": "WhatsApp message", "channel": "whatsapp", "discount": 0.00, "cost_inr": 5},
}


def _actions_from_settings():
    """Labels, costs and discounts come from crm_settings.json; the set of actions is fixed
    (the uplift model is trained on exactly these)."""
    try:
        import settings
        conf = settings.S.get("actions", {})
    except Exception:
        conf = {}
    out = {}
    for key, d in _DEFAULT_ACTIONS.items():
        c = conf.get(key, {})
        out[key] = {"label": c.get("label", d["label"]), "channel": d["channel"],
                    "discount": float(c.get("discount", d["discount"])),
                    "cost_inr": float(c.get("cost", d["cost_inr"]))}
    return out


ACTIONS = _actions_from_settings()
ACTION_LIST = list(ACTIONS)
TREATMENTS = [a for a in ACTION_LIST if a != "none"]

PRICE_SENSITIVE_OCC = {"Student", "Unemployed", "Housewife"}
PROFESSIONAL_OCC = {"Working Professional", "Businessman"}

CONTEXT_NAMES = ["bias", "base_logit", "price_sensitive", "high_intent", "cart_or_enquiry",
                 "professional", "email_engaged", "whatsapp_opt_in", "low_engagement"]


def _logit(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def context(frame: pd.DataFrame, base_prob) -> np.ndarray:
    """c(x): interpretable context for uplift. frame = ml_features.to_model_frame(...)."""
    f = frame
    occ = f["CurrentOccupation"].astype(str)
    return np.column_stack([
        np.ones(len(f)),
        _logit(base_prob),
        (occ.isin(PRICE_SENSITIVE_OCC) | ((f["AddedToCart"] == 1) & (f["CheckoutStarted"] == 0))).astype(float),
        (f["CheckoutStarted"] == 1).astype(float),
        ((f["AddedToCart"] == 1) | (f["EnquirySubmitted"] == 1)).astype(float),
        occ.isin(PROFESSIONAL_OCC).astype(float),
        (f["EmailOpenedCount"] > 0).astype(float),
        (f["WhatsAppOptIn"] == 1).astype(float),
        (f["TotalTimeOnWebsite"] < 120).astype(float),
    ])


def design(ctx: np.ndarray, actions) -> np.ndarray:
    """[c(x) | 1{a=k}·c(x) for every treatment k] — the S-learner design matrix."""
    actions = np.asarray(actions)
    blocks = [ctx]
    for k in TREATMENTS:
        blocks.append(ctx * (actions == k)[:, None])
    return np.hstack(blocks)


def eligible(features: dict, has_phone: bool) -> dict:
    """Which actions are allowed for this person (consent + contact details)."""
    out = {}
    for a in ACTION_LIST:
        ch = ACTIONS[a]["channel"]
        reason = None
        if ch == "email" and features.get("DoNotEmail"):
            reason = "opted out of email"
        elif ch == "call" and (features.get("DoNotCall") or not has_phone):
            reason = "opted out of calls" if features.get("DoNotCall") else "no phone number"
        elif ch == "whatsapp" and (not features.get("WhatsAppOptIn") or not has_phone):
            reason = "not opted in to WhatsApp" if not features.get("WhatsAppOptIn") else "no phone number"
        out[a] = reason
    return out


def expected_values(p_by_action: dict, price: float) -> dict:
    """Expected profit of each action, and its uplift over doing nothing."""
    base = p_by_action["none"] * price
    out = {}
    for a, p in p_by_action.items():
        spec = ACTIONS[a]
        value = p * price * (1 - spec["discount"]) - spec["cost_inr"]
        out[a] = {"p_convert": float(p), "uplift": float(p - p_by_action["none"]),
                  "expected_profit": float(value), "incremental_profit": float(value - base)}
    return out


class FlexibleSLearner:
    """Second model family for the closed loop: gradient boosting on ALL lead features + the action,
    with no hand-designed context. It can pick up effects the interpretable model cannot see (hidden,
    non-linear drivers) but needs more data and cannot be read as per-action effects. The robustness
    study (ml/experiments/nba_robustness.py) shows each family winning in different worlds, so
    the learning loop (learning.py) keeps whichever earns more on held-out REAL decisions."""
    kind = "flexible_gbm"

    def __init__(self, random_state=0):
        self.random_state = random_state

    def _X(self, frame, actions):
        A = np.column_stack([(np.asarray(actions) == t).astype(float) for t in TREATMENTS])
        return np.hstack([self.pre.transform(frame), A])

    def fit(self, frame, actions, y, sample_weight=None):
        from sklearn.compose import ColumnTransformer
        from sklearn.ensemble import HistGradientBoostingClassifier
        from sklearn.preprocessing import OneHotEncoder
        import ml_features as F
        self.pre = ColumnTransformer([("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                                       F.MODEL_CATEGORICAL)], remainder="passthrough").fit(frame)
        self.clf = HistGradientBoostingClassifier(
            learning_rate=0.05, max_iter=300, max_leaf_nodes=15, min_samples_leaf=100, early_stopping=True,
            validation_fraction=0.15, n_iter_no_change=20, random_state=self.random_state)
        self.clf.fit(self._X(frame, actions), y, sample_weight=sample_weight)
        return self

    def predict_all(self, frame) -> dict:
        return {a: self.clf.predict_proba(self._X(frame, np.full(len(frame), a)))[:, 1] for a in ACTION_LIST}


def predict_actions(model, frame: pd.DataFrame, base_prob) -> dict:
    """P(buy | x, a) for every action, for either model family (arrays, one entry per row of frame)."""
    if hasattr(model, "predict_all"):
        return model.predict_all(frame)
    ctx = context(frame, base_prob)
    return {a: model.predict_proba(design(ctx, np.full(len(frame), a)))[:, 1] for a in ACTION_LIST}


def model_kind(model) -> str:
    return getattr(model, "kind", "s_learner_lr")


def choose(values: dict, blocked: dict, explore_rate: float = 0.0, rng=None):
    """Greedy on incremental profit among allowed actions, with ε-exploration.
    Returns (action, policy, propensity of the chosen action, the model's best action)."""
    allowed = [a for a in ACTION_LIST if not blocked.get(a)] or ["none"]
    best = max(allowed, key=lambda a: (values[a]["incremental_profit"], a == "none"))
    if values[best]["incremental_profit"] <= 0 and "none" in allowed:
        best = "none"     # nothing pays for itself (when doing nothing is an option, e.g. not at an enquiry)
    rng = rng or np.random.default_rng()
    k = len(allowed)
    if explore_rate > 0 and rng.random() < explore_rate:
        chosen, policy = allowed[int(rng.integers(k))], "explore"
    else:
        chosen, policy = best, "model"
    propensity = (1 - explore_rate) * (chosen == best) + explore_rate / k
    return chosen, policy, float(propensity), best
