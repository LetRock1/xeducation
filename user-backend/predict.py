"""
predict.py — Lead scoring engine (v6)

Loads ONE file: ml_models/lead_model.pkl. The score has two parts (see lead_model.py):
a base model over every signal the website records (ml/train_model.py) and a live layer
learned from this CRM's own outcomes by the learning loop (learning.py). Features are
engineered with ml_features.py — the same code used at training time — so training and
serving cannot drift apart.

What changed vs the old version:
  * No KMeans/PCA persona: persona now comes from the calibrated score, so a
    "Hot Lead" really is more likely to buy than a "Warm Lead".
  * No hand-written floors/caps that override the model (cart = 62, enquiry
    = 42, Student cap 72 × 0.85 ...). Cart, checkout, wishlist and enquiry
    are now model features, learned from data. v6.2 also removed the last one
    (customers floored to 80): a customer is shown as a customer, not as a
    number (the model predicts a first purchase, not a repeat purchase).
  * lead_score == conversion_probability × 100, always, so the number on the
    dashboard and the number in PLV always agree.
  * Time since the person was last on the site (raw["away_days"]) lowers the
    score by what the learning loop learned for it (lead_model.recency_effect)
    — this replaced the hand-written "lead decay" rule.
  * The model file is reloaded automatically when retrained — no restart.
  * If the model file is missing, a deterministic fallback is used (the old
    mock returned a RANDOM score on every call).
"""
import os
import threading

import joblib
import numpy as np
import pandas as pd

import lead_model as LM
import ml_features as F

MODEL_PATH = os.path.join(os.path.dirname(__file__), "ml_models", "lead_model.pkl")

_lock = threading.Lock()
_state = {"bundle": None, "mtime": None, "warned": False}


def _load():
    """(Re)load the model bundle when the file changes on disk."""
    try:
        mtime = os.path.getmtime(MODEL_PATH)
    except OSError:
        if not _state["warned"]:
            print(f"[ML] WARNING: {MODEL_PATH} not found — using fallback scoring.")
            print("[ML]          start-all.bat creates it on first start (or run ml/train_model.py).")
            _state["warned"] = True
        _state["bundle"] = None
        return None
    if _state["mtime"] == mtime and _state["bundle"] is not None:
        return _state["bundle"]
    with _lock:
        if _state["mtime"] == mtime and _state["bundle"] is not None:
            return _state["bundle"]
        try:
            bundle = joblib.load(MODEL_PATH)
            if bundle.get("feature_version") != F.FEATURE_VERSION or "starter" not in bundle:
                raise ValueError(f"model feature_version {bundle.get('feature_version')} "
                                 f"!= code feature_version {F.FEATURE_VERSION}; delete user-backend/ml_models and run start-all.bat")
            import sklearn
            if bundle.get("sklearn_version") != sklearn.__version__:
                print(f"[ML] WARNING: model trained with scikit-learn {bundle.get('sklearn_version')}, "
                      f"running {sklearn.__version__}. Delete user-backend/ml_models and run start-all.bat if scores look wrong.")
            _state.update(bundle=bundle, mtime=mtime, warned=False)
            print(f"[ML] Loaded lead model {bundle['version']} ({bundle['model_type']}, "
                  f"AUC {bundle['metrics'].get('roc_auc')}, sklearn {bundle['sklearn_version']})")
        except Exception as e:
            print(f"[ML] ERROR loading {MODEL_PATH}: {e} — using fallback scoring.")
            _state.update(bundle=None, mtime=mtime)
    return _state["bundle"]


def model_info() -> dict:
    b = _load()
    if not b:
        return {"loaded": False, "version": "fallback"}
    info = {"loaded": True, **{k: v for k, v in b.items() if k not in ("starter", "pipeline")}}
    info["learned_signals"] = LM.learned_points(b)
    return info


def reload():
    """Forget the cached model so the next score reads the file again (used after retraining in-process)."""
    with _lock:
        _state.update(bundle=None, mtime=None)


def _legacy_keys(raw: dict) -> dict:
    """Accept the old lowercase context keys as well as the new feature names."""
    r = dict(raw)
    if r.get("cart_abandoned"):
        r.setdefault("AddedToCart", 1)
    if (r.get("wishlist_count") or 0) > 0:
        r.setdefault("AddedToWishlist", 1)
    if r.get("enquiry_submitted"):
        r.setdefault("EnquirySubmitted", 1)
    return r


def _fallback_probs(frame: pd.DataFrame):
    """Deterministic stand-in used only when no trained model is available."""
    import numpy as np
    z = (-2.4 + 0.5 * np.log(frame["TotalVisits"]) + 0.2 * np.log1p(frame["TotalTimeOnWebsite"] / 60)
         + 0.5 * frame["VideoWatched"] + 0.5 * frame["PricingPageVisited"] + 0.6 * frame["BrochureDownloaded"]
         + 0.5 * frame["ChatInitiated"] + 0.8 * frame["WebinarAttended"] + 0.4 * frame["AddedToWishlist"]
         + 1.0 * frame["AddedToCart"] + 1.2 * frame["CheckoutStarted"] + 1.1 * frame["EnquirySubmitted"]
         + 0.15 * frame["EmailOpenedCount"].clip(upper=4)
         + (frame["CurrentOccupation"] == "Working Professional") * 0.6
         - frame["DoNotEmail"] * 0.5)
    return 1 / (1 + np.exp(-z))


def _logits(b, rows, days):
    z = LM.combined_logit(b, F.to_model_frame(rows))
    if days is not None:
        z = z + LM.recency_effects(b, days)
    return np.asarray(z, dtype=float)


def _probs(rows: list, away_days=None) -> list:
    """P(buy within 14 days | lead, no action now). away_days: one value for all rows, a list (one per
    row) or None (no time-since-last-visit adjustment).

    Guard: clicking one of our emails never LOWERS the score. The base model counts clicks as interest,
    but the learning loop can learn a negative correction for them: people who keep getting follow-ups
    without buying stay in its data longer and pile up clicks (survivorship). That is an artefact of
    how often the CRM writes to someone, not lower interest, so a click is worth at least nothing."""
    b = _load()
    if b is None:
        return list(_fallback_probs(F.to_model_frame(rows)))
    days = None
    if away_days is not None:
        days = list(away_days) if isinstance(away_days, (list, tuple, np.ndarray)) else [away_days] * len(rows)
    z = _logits(b, rows, days)
    clicked = [i for i, r in enumerate(rows) if (r.get("EmailOpenedCount") or 0) > 0]
    if clicked:
        z0 = _logits(b, [dict(rows[i], EmailOpenedCount=0) for i in clicked],
                     [days[i] for i in clicked] if days is not None else None)
        for k, i in enumerate(clicked):
            z[i] = max(z[i], z0[k])
    return list(1.0 / (1.0 + np.exp(-z)))


def _explain(clean: dict, prob: float, away_days=None) -> list:
    """What moved this lead's score: re-score with each present signal removed."""
    variants, meta = [], []
    for feat, label, absent in F.EXPLAIN_SIGNALS:
        value = clean.get(feat)
        if value == absent or (isinstance(absent, (int, float)) and not isinstance(value, str)
                               and value <= absent):
            continue
        v = dict(clean)
        v[feat] = absent
        if feat == "TotalVisits":
            v["TotalTimeOnWebsite"] = clean["TotalTimeOnWebsite"] / max(clean["TotalVisits"], 1)
        if feat == "EnquirySubmitted":            # the enquiry is also what makes the origin a lead form
            v["LeadOrigin"] = "Landing Page Submission"
        variants.append(v)
        meta.append((feat, label))
    if not variants:
        return []
    alt = _probs(variants, away_days)
    factors = []
    for (feat, label), p_without in zip(meta, alt):
        delta = (prob - p_without) * 100
        if abs(delta) < 0.5:
            continue
        value = clean[feat]
        if feat == "TotalTimeOnWebsite":
            detail = f"{int(value // 60)} min {int(value % 60)} s on site in total"
        elif feat == "TotalVisits":
            detail = f"{int(value)} visits"
        elif feat == "EmailOpenedCount":
            detail = f"{int(value)} email open(s)/click(s)"
        elif feat in ("CurrentOccupation", "LeadSource", "Specialization"):
            detail = str(value)
        else:
            detail = "Yes"
        factors.append({"factor": label, "detail": detail,
                        "impact": f"{delta:+.0f} pts", "points": round(delta, 1)})
    factors.sort(key=lambda f: -abs(f["points"]))
    return factors[:6]


def _away_text(days):
    d = float(days)
    if d < 2:
        return "1 day ago"
    return f"{d:.0f} days ago"


def predict_lead(raw: dict, explain: bool = False) -> dict:
    """
    raw: the lead's features (see ml_features.RAW_FEATURES) plus optional
         context: past_purchases (int), away_days (days since the person was last
         on the website; None = no adjustment). Missing/unknown values are handled.
    """
    r = _legacy_keys(raw)
    clean = F.normalize_raw(r)
    away = r.get("away_days")
    prob = float(_probs([clean], away)[0])
    score = round(prob * 100, 2)

    is_customer = (r.get("past_purchases") or 0) > 0
    persona = F.persona_for(score, is_customer)
    out = {
        "lead_score": score,
        "conversion_probability": round(prob, 4),
        "persona": persona,
        "customer_segment": persona,          # kept for old columns/UI
        "recommended_action": F.tier_for(score),
        "model_version": model_info().get("version", "fallback"),
        "is_customer": is_customer,
        "away_days": None if away is None else round(float(away), 1),
    }
    if explain:
        factors = _explain(clean, prob, away)
        if away is not None and LM.recency_bucket(away):
            p_now = float(_probs([clean], 0.0)[0])
            delta = (prob - p_now) * 100
            if abs(delta) >= 0.5:
                factors.append({"factor": "Time since last visit", "detail": f"Last on the site {_away_text(away)}",
                                "impact": f"{delta:+.0f} pts", "points": round(delta, 1)})
                factors.sort(key=lambda f: -abs(f["points"]))
                factors = factors[:6]
        if is_customer:
            factors.insert(0, {"factor": "Already a customer",
                               "detail": f"{r.get('past_purchases')} purchase(s); the score is the chance of buying "
                                         "another course, which the model was not trained for",
                               "impact": "—", "points": 0})
        if not factors:
            factors = [{"factor": "Baseline", "detail": "No strong signals yet",
                        "impact": "baseline", "points": 0}]
        out["factors"] = factors
    out["features"] = clean
    return out


def predict_many(raws: list) -> list:
    """Score many people at once (the score refresh job): [(probability, score, tier, persona), ...].
    Same numbers as predict_lead, one model call for everyone."""
    if not raws:
        return []
    rows = [_legacy_keys(r) for r in raws]
    cleans = [F.normalize_raw(r) for r in rows]
    away = [r.get("away_days") for r in rows]
    probs = _probs(cleans, away)
    out = []
    for r, p in zip(rows, probs):
        p = float(p)
        score = round(p * 100, 2)
        out.append((round(p, 4), score, F.tier_for(score), F.persona_for(score, (r.get("past_purchases") or 0) > 0)))
    return out


# Warm up at import so the first request isn't slow and load errors show at startup
_load()
