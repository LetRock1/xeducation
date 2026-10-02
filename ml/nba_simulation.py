"""
nba_simulation.py — semi-synthetic campaign simulator for the next-best-action
engine.

Why a simulator: an uplift model needs to know what WOULD have happened under
each action, but in real data every person only ever receives one action
(the "fundamental problem of causal inference"). The accepted way to evaluate
uplift / next-best-action policies, used throughout the causal-ML literature
(e.g. the IHDP and ACIC benchmarks), is a semi-synthetic setup: realistic
covariates + outcome functions whose treatment effects are KNOWN, so every
policy can be scored against the truth. Real randomized data (the Hillstrom
email experiment) is used separately to validate on real outcomes.

The response assumptions below are explicit and documented so they can be
reported in the paper and challenged:
  * discounts mostly move price-sensitive people (students, unemployed,
    homemakers, or people who added to cart but stopped before checkout);
    they barely move people already at checkout ("sure things")
  * an advisor call helps people who showed explicit intent (cart / enquiry)
    and professionals; calling cold, barely-engaged people backfires
  * emails help people who engage with emails; WhatsApp gives a small lift
  * each person also has an individual, unobservable response (noise)
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "user-backend")
sys.path.insert(0, BACKEND)
import ml_features as F   # noqa: E402
import nba_core as N      # noqa: E402

# true effect on the log-odds of buying, per action, as a function of context c(x)
#                      bias  base  price  high   cart/enq  prof  email  wa   low_eng
TRUE_EFFECTS = {
    "none":            [0.00, 0,    0.00,  0.00,  0.00,    0.00, 0.00,  0.0, 0.00],
    "email_info":      [0.08, 0,    0.00,  0.00,  0.05,    0.00, 0.30,  0.0, -0.05],
    "email_coupon_10": [0.15, 0,    0.60, -0.20,  0.05,   -0.05, 0.10,  0.0, 0.00],
    "email_coupon_20": [0.25, 0,    1.00, -0.20,  0.05,   -0.05, 0.10,  0.0, 0.00],
    "call":            [0.10, 0,    0.00,  0.10,  0.90,    0.35, 0.00,  0.0, -0.50],
    "whatsapp":        [0.12, 0,    0.10,  0.00,  0.25,    0.00, 0.00,  0.15, 0.00],
}
EFFECT_NOISE_SD = 0.15


def _catalog_prices():
    path = os.path.join(BACKEND, "catalog.json")
    try:
        with open(path, encoding="utf-8") as f:
            courses = json.load(f)
    except OSError:
        return {}, 40000.0
    by_type = {}
    for c in courses:
        ct = F.COURSE_TYPE_BY_SLUG.get(c["slug"], "Unknown")
        by_type.setdefault(ct, []).append(c["price"])
    avg = float(np.mean([c["price"] for c in courses]))
    return {k: float(np.mean(v)) for k, v in by_type.items()}, avg


def prices_for(frame: pd.DataFrame) -> np.ndarray:
    by_type, avg = _catalog_prices()
    return frame["CourseType"].map(lambda t: by_type.get(t, avg)).to_numpy(dtype=float)


def true_probabilities(frame: pd.DataFrame, p_true_none, seed=0) -> dict:
    """True P(buy | x, a) for every action (simulation ground truth)."""
    rng = np.random.default_rng(seed)
    ctx = N.context(frame, np.full(len(frame), 0.5))         # base_logit column unused (coef 0)
    base = N._logit(p_true_none)
    blocked = _blocked_matrix(frame)
    out = {}
    for a in N.ACTION_LIST:
        eff = ctx @ np.asarray(TRUE_EFFECTS[a])
        if a != "none":
            eff = eff + rng.normal(0, EFFECT_NOISE_SD, len(frame))
            eff = np.where(blocked[a], 0.0, eff)             # can't reach them: no effect
        out[a] = 1 / (1 + np.exp(-(base + eff)))
    return out


def _blocked_matrix(frame):
    b = {}
    has_phone = np.ones(len(frame), dtype=bool)   # assume a phone number when not opted out
    b["none"] = np.zeros(len(frame), dtype=bool)
    for a in ("email_info", "email_coupon_10", "email_coupon_20"):
        b[a] = frame["DoNotEmail"].to_numpy() == 1
    b["call"] = (frame["DoNotCall"].to_numpy() == 1) | ~has_phone
    b["whatsapp"] = frame["WhatsAppOptIn"].to_numpy() == 0
    return b


def simulate_randomized_campaign(raw: pd.DataFrame, base_prob, seed=1, exploration=1.0, policy=None):
    """A logged campaign: each eligible person gets a uniformly random allowed action
    (a randomized experiment), and we observe only that action's outcome."""
    rng = np.random.default_rng(seed)
    frame = F.to_model_frame(raw)
    truth = true_probabilities(frame, raw["_p_true"].to_numpy(), seed=seed + 7)
    blocked = _blocked_matrix(frame)
    actions, props = [], []
    for i in range(len(frame)):
        allowed = [a for a in N.ACTION_LIST if not blocked[a][i]]
        a = allowed[int(rng.integers(len(allowed)))]
        actions.append(a)
        props.append(1 / len(allowed))
    actions = np.array(actions)
    p = np.array([truth[a][i] for i, a in enumerate(actions)])
    y = (rng.random(len(frame)) < p).astype(int)
    return frame, actions, np.array(props), y, truth
