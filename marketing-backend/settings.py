"""
settings.py — reads crm_settings.json (project root): the business rules of the CRM in one place
(tiers, actions and their costs, timings, learning loop, A/B testing defaults).

The same file is used by user-backend, marketing-backend and the ML scripts, so a rule is
changed in exactly one place. Missing keys fall back to the defaults below, so an old or
partial settings file still works.
"""
import copy
import hashlib
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.getenv("CRM_SETTINGS", os.path.join(HERE, "..", "crm_settings.json"))

DEFAULTS = {
    "business": {"name": "X Education", "crm_name": "X Education CRM", "currency": "INR", "currency_symbol": "₹"},
    "tiers": [{"min_score": 80, "name": "Target Immediately"}, {"min_score": 60, "name": "Nurture via Email/WhatsApp"},
              {"min_score": 40, "name": "Marketing Campaign"}, {"min_score": 0, "name": "Low Priority"}],
    "actions": {
        "none":            {"label": "Do nothing for now", "channel": None, "discount": 0.00, "cost": 0},
        "email_info":      {"label": "Send an information email", "channel": "email", "discount": 0.00, "cost": 2},
        "email_coupon_10": {"label": "Send email with 10% coupon", "channel": "email", "discount": 0.10, "cost": 2},
        "email_coupon_20": {"label": "Send email with 20% coupon", "channel": "email", "discount": 0.20, "cost": 2},
        "call":            {"label": "Advisor phone call", "channel": "call", "discount": 0.00, "cost": 150},
        "whatsapp":        {"label": "WhatsApp message", "channel": "whatsapp", "discount": 0.00, "cost": 5},
    },
    "daily_call_capacity": 20,
    "exploration_rate": 0.15,
    "outcome_window_days": 14,
    "coupon_valid_hours": 72,
    "automation_minutes": {
        "demo": {"job_every": 1, "visit_ended": 1, "cart_abandoned": 1, "checkout_abandoned": 1, "wishlist": 1},
        "live": {"job_every": 5, "visit_ended": 15, "cart_abandoned": 60, "checkout_abandoned": 30, "wishlist": 30},
    },
    "cooldown_hours": {"visit": 6, "cart": 12, "checkout": 12, "wishlist": 24},
    "decay_inactive_minutes": {"demo": 10, "live": 10080},
    "learning": {"check_every_minutes": {"demo": 5, "live": 60}, "min_new_outcomes": 30, "swap_confidence": 0.90,
                 "ridge": 2.0, "bootstrap_resamples": 300},
    "ab_testing": {"control_share": 0.20, "alpha": 0.05, "power": 0.80, "min_detectable_effect": 0.05,
                   "outcome_window_days": 14, "max_variants": 3, "min_per_segment_arm": 30,
                   "auto_adopt": True, "adoption_check_share": 0.10},
    "campaigns": {"holdout_share": 0.10},
    "global_control": {"share": 0.05},
    "starting_history": {"create_on_first_start": True, "learners": 2000, "days": 180},
}


def _merge(base, extra):
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        if k.startswith("_"):
            continue
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load(path=PATH):
    try:
        with open(path, encoding="utf-8") as f:
            return _merge(DEFAULTS, json.load(f))
    except FileNotFoundError:
        return copy.deepcopy(DEFAULTS)
    except ValueError as e:
        print(f"[SETTINGS] {path} is not valid JSON ({e}) — using the built-in defaults.")
        return copy.deepcopy(DEFAULTS)


S = load()
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"
MODE = "demo" if DEMO_MODE else "live"


def by_mode(section):
    """A value that differs between demo mode and live mode, e.g. by_mode('decay_inactive_minutes')."""
    v = S[section]
    return v[MODE] if isinstance(v, dict) and MODE in v else v


def tiers():
    """[(min_score, name), ...] from the highest tier down."""
    return sorted(((float(t["min_score"]), t["name"]) for t in S["tiers"]), reverse=True)


def tier_names():
    return [name for _, name in tiers()]


def in_global_control(user_id):
    """True for the fixed random share of people (global_control.share, default 5%) whom the CRM never
    contacts automatically: no next-best-action steps, campaigns or A/B emails. Comparing them with
    everyone else measures the CRM's total impact, and their outcomes are the learning loop's honest
    check (nobody's follow-ups shaped them). Decided by a hash of the person, so it never changes."""
    share = float((S.get("global_control") or {}).get("share", 0) or 0)
    if share <= 0 or user_id is None:
        return False
    h = hashlib.sha256(f"global-control:{user_id}".encode()).hexdigest()
    return int(h[:15], 16) / float(16 ** 15) < share
