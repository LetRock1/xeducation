"""
lead_model.py — what the lead score is made of (v6).

    logit P(buy within 14 days | lead, if we do nothing now)
        = a · logit( base(x) )           base model: trained once on simulated leads (ml/train_model.py)
        + b + Σ_j  w_j · s_j(x)          live layer: learned from THIS CRM's own outcomes

base(x)     a calibrated classifier over every signal the website records (profile, visits,
            time, video, pricing, brochure, chat, webinar, wishlist, cart, checkout, enquiry,
            email clicks, WhatsApp, consent). It reacts to every click from the first minute.
a, b        re-calibration to this business: how strongly the base score carries over (a,
            starts at 1) and the overall level of buying within 14 days (b, starts at 0).
s_j(x), w_j corrections for the strongest site signals (cart, checkout, video ...): start at 0,
            shrunk towards 0 (ridge), so they only move as far as real outcomes support.

The learning loop (learning.py) fits a, b and w WITH the CRM's own follow-ups as extra inputs and
then predicts with those inputs set to "no action": the score is the chance of buying if we do
nothing, so the system's own emails, coupons and calls are never counted as lead quality.
"""
import numpy as np
import pandas as pd

import ml_features as F

# inputs of the base model (bundles also store the list they were trained with)
STARTER_COLUMNS = list(F.MODEL_COLUMNS)

# (name, label shown to sales, function of the model frame)
LIVE_SIGNALS = [
    ("VideoWatched",       "Watched a course video",   lambda f: f["VideoWatched"]),
    ("BrochureDownloaded", "Downloaded a brochure",    lambda f: f["BrochureDownloaded"]),
    ("ChatInitiated",      "Opened chat",              lambda f: f["ChatInitiated"]),
    ("PricingPageVisited", "Spent time on pricing",    lambda f: f["PricingPageVisited"]),
    ("TestimonialVisited", "Read testimonials",        lambda f: f["TestimonialVisited"]),
    ("WebinarAttended",    "Joined a webinar",         lambda f: f["WebinarAttended"]),
    ("AddedToWishlist",    "Wishlisted a course",      lambda f: f["AddedToWishlist"]),
    ("AddedToCart",        "Added to cart",            lambda f: f["AddedToCart"]),
    ("CheckoutStarted",    "Started checkout",         lambda f: f["CheckoutStarted"]),
    ("EnquirySubmitted",   "Sent an enquiry",          lambda f: f["EnquirySubmitted"]),
    ("EmailEngagement",    "Clicked our emails",       lambda f: np.minimum(f["EmailOpenedCount"], 4) / 4.0),
    ("WhatsAppOptIn",      "Opted in to WhatsApp",     lambda f: f["WhatsAppOptIn"]),
    ("MobileDevice",       "Browses on mobile",        lambda f: (f["DeviceType"] == "Mobile").astype(float)),
]
LIVE_NAMES = [n for n, _, _ in LIVE_SIGNALS]
LIVE_LABELS = {n: lab for n, lab, _ in LIVE_SIGNALS}


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.asarray(z, dtype=float)))


def logit(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-5, 1 - 1e-5)
    return np.log(p / (1 - p))


def live_matrix(frame: pd.DataFrame) -> np.ndarray:
    """s(x): the site-specific signals, one column per LIVE_SIGNALS entry."""
    return np.column_stack([np.asarray(fn(frame), dtype=float) for _, _, fn in LIVE_SIGNALS])


def empty_live():
    return {"signals": list(LIVE_NAMES), "weights": [0.0] * len(LIVE_NAMES), "intercept": 0.0, "slope": 1.0,
            "outcomes_used": 0, "trained_at": None, "learning_run": None}


_cache = {}


def starter_logit(bundle, frame: pd.DataFrame) -> np.ndarray:
    """logit of the base model. Single rows are cached (scoring one row at a time is sklearn's
    slowest case, and the same lead is often re-scored with unchanged inputs)."""
    X = frame[bundle.get("starter_columns") or STARTER_COLUMNS]
    if len(X) == 1:
        key = (id(bundle["starter"]), tuple(X.iloc[0].tolist()))
        hit = _cache.get(key)
        if hit is None:
            if len(_cache) > 50000:
                _cache.clear()
            hit = _cache[key] = float(logit(bundle["starter"].predict_proba(X)[:, 1])[0])
        return np.array([hit])
    return logit(bundle["starter"].predict_proba(X)[:, 1])


def combined_logit(bundle, frame: pd.DataFrame, starter=None) -> np.ndarray:
    """a·logit(base) + b + s·w  (the live layer on top of the base model)."""
    z0 = starter_logit(bundle, frame) if starter is None else np.asarray(starter, dtype=float)
    live = bundle.get("live") or empty_live()
    w = np.asarray(live["weights"], dtype=float)
    if len(w) != len(LIVE_NAMES):                 # bundle from another code version: ignore the live layer
        return z0
    return float(live.get("slope", 1.0)) * z0 + float(live["intercept"]) + live_matrix(frame) @ w


def predict_proba(bundle, frame: pd.DataFrame) -> np.ndarray:
    """P(buy within the outcome window | lead, no action) for every row of a model frame."""
    return _sigmoid(combined_logit(bundle, frame))


# ── How long since the person was last on the website (learned by the loop) ────────────────
# The learning loop fits "last seen 1-7 / 7-14 / 14-30 / 30+ days ago" next to the CRM's own actions
# (learning.py: RECENCY_COLS) and stores the effects in live["own_effects"]. Applying them when scoring
# makes the score fall by itself when someone goes quiet: the old "lead decay" rule (cap the score at
# the top of the next tier) is not needed any more, and the drop is learned from outcomes, not set by hand.
RECENCY_BUCKETS = [("away_1_7_days", 1, 7), ("away_7_14_days", 7, 14),
                   ("away_14_30_days", 14, 30), ("away_30_days_plus", 30, None)]
RECENCY_LABELS = {"away_1_7_days": "1-7 days", "away_7_14_days": "7-14 days",
                  "away_14_30_days": "14-30 days", "away_30_days_plus": "30+ days"}


def recency_bucket(days):
    """The learning loop's bucket for 'days since last seen' (same edges as learning.assemble)."""
    if days is None:
        return None
    d = float(days)
    for name, lo, hi in RECENCY_BUCKETS:
        if d > lo and (hi is None or d <= hi):
            return name
    return None                                    # seen within the last day: no adjustment


def recency_effect(bundle, days) -> float:
    """Log-odds the loop learned for this many days away (0 if nothing learned yet)."""
    name = recency_bucket(days)
    if not name:
        return 0.0
    effects = ((bundle or {}).get("live") or {}).get("own_effects") or {}
    return float(effects.get(name, 0.0) or 0.0)


def recency_effects(bundle, days_list) -> np.ndarray:
    return np.array([recency_effect(bundle, d) for d in days_list], dtype=float)


def learned_points(bundle, base_prob=0.30):
    """How many score points each live signal adds for a typical lead (base_prob), for display."""
    live = bundle.get("live") or empty_live()
    out = []
    z0 = float(logit([base_prob])[0])
    p0 = float(_sigmoid(z0))
    for name, w in zip(live["signals"], live["weights"]):
        p1 = float(_sigmoid(z0 + float(w)))
        out.append({"signal": name, "label": LIVE_LABELS.get(name, name), "weight": round(float(w), 3),
                    "points": round((p1 - p0) * 100, 1)})
    return out


# ── Offset logistic regression (used by the learning loop) ─────────────────────
def fit_offset_logreg(X, y, offset, sample_weight=None, l2=None, max_iter=60, tol=1e-7):
    """Logistic regression with a fixed offset and per-coefficient ridge penalties (IRLS).
    X must include any intercept column; l2 is a vector (0 = unpenalised)."""
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    off = np.asarray(offset, dtype=float)
    n, k = X.shape
    sw = np.ones(n) if sample_weight is None else np.asarray(sample_weight, dtype=float)
    lam = np.zeros(k) if l2 is None else np.asarray(l2, dtype=float)
    beta = np.zeros(k)
    for _ in range(max_iter):
        p = _sigmoid(off + X @ beta)
        W = sw * p * (1 - p)
        grad = X.T @ (sw * (y - p)) - lam * beta
        H = (X * W[:, None]).T @ X + np.diag(lam) + 1e-9 * np.eye(k)
        step = np.linalg.solve(H, grad)
        # damped Newton step for stability on small, separable data
        scale = min(1.0, 3.0 / max(np.abs(step).max(), 1e-12))
        beta = beta + scale * step
        if np.abs(scale * step).max() < tol:
            break
    return beta
