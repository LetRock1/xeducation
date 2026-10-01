"""
predict.py — Lead scoring engine (v4)

Loads ONE file: ml_models/lead_model.pkl (built by ml/train_model.py).
The pipeline inside it already contains the preprocessing, and features are
engineered with ml_features.py — the same code used at training time — so
training and serving can no longer drift apart.

What changed vs the old version:
  * No KMeans/PCA persona: persona now comes from the calibrated score, so a
    "Hot Lead" really is more likely to buy than a "Warm Lead".
  * No hand-written floors/caps that override the model (cart = 62, enquiry
    = 42, Student cap 72 × 0.85 ...). Cart, checkout, wishlist and enquiry
    are now model features, learned from data. The only rule left: existing
    customers are floored to Target Immediately (the model predicts first
    purchase, not repeat purchase).
  * lead_score == conversion_probability × 100 (except that customer rule),
    so the number on the dashboard and the number in PLV always agree.
  * The model file is reloaded automatically when retrained — no restart.
  * If the model file is missing, a deterministic fallback is used (the old
    mock returned a RANDOM score on every call).
"""
import os
import threading

import joblib
import pandas as pd

import ml_features as F

MODEL_PATH = os.path.join(os.path.dirname(__file__), "ml_models", "lead_model.pkl")
CUSTOMER_FLOOR = 80.0

_lock = threading.Lock()
_state = {"bundle": None, "mtime": None, "warned": False}


def _load():
    """(Re)load the model bundle when the file changes on disk."""
    try:
        mtime = os.path.getmtime(MODEL_PATH)
    except OSError:
        if not _state["warned"]:
            print(f"[ML] WARNING: {MODEL_PATH} not found — using fallback scoring.")
            print("[ML]          Run train-model.bat (or ml/train_model.py) to create it.")
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
            if bundle.get("feature_version") != F.FEATURE_VERSION:
                raise ValueError(f"model feature_version {bundle.get('feature_version')} "
                                 f"!= code feature_version {F.FEATURE_VERSION}; retrain the model")
            import sklearn
            if bundle.get("sklearn_version") != sklearn.__version__:
                print(f"[ML] WARNING: model trained with scikit-learn {bundle.get('sklearn_version')}, "
                      f"running {sklearn.__version__}. Re-run train-model.bat if scores look wrong.")
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
    return {"loaded": True, **{k: v for k, v in b.items() if k != "pipeline"}}


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


def _probs(rows: list) -> list:
    frame = F.to_model_frame(rows)
    b = _load()
    if b is None:
        return list(_fallback_probs(frame))
    return list(b["pipeline"].predict_proba(frame)[:, 1])


def _explain(clean: dict, prob: float) -> list:
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
        variants.append(v)
        meta.append((feat, label))
    if not variants:
        return []
    alt = _probs(variants)
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
        elif feat in ("CurrentOccupation", "LeadSource"):
            detail = str(value)
        else:
            detail = "Yes"
        factors.append({"factor": label, "detail": detail,
                        "impact": f"{delta:+.0f} pts", "points": round(delta, 1)})
    factors.sort(key=lambda f: -abs(f["points"]))
    return factors[:6]


def predict_lead(raw: dict, explain: bool = False) -> dict:
    """
    raw: the lead's features (see ml_features.RAW_FEATURES) plus optional
         context: past_purchases (int). Missing/unknown values are handled.
    """
    r = _legacy_keys(raw)
    clean = F.normalize_raw(r)
    prob = float(_probs([clean])[0])
    score = round(prob * 100, 2)

    is_customer = (r.get("past_purchases") or 0) > 0
    if is_customer:
        score = max(score, CUSTOMER_FLOOR)

    persona = F.persona_for(score, is_customer)
    out = {
        "lead_score": score,
        "conversion_probability": round(prob, 4),
        "persona": persona,
        "customer_segment": persona,          # kept for old columns/UI
        "recommended_action": F.tier_for(score),
        "model_version": model_info().get("version", "fallback"),
    }
    if explain:
        factors = _explain(clean, prob)
        if is_customer:
            factors.insert(0, {"factor": "Paying customer",
                               "detail": f"{r.get('past_purchases')} past purchase(s)",
                               "impact": f"floor {CUSTOMER_FLOOR:.0f}", "points": 0})
        if not factors:
            factors = [{"factor": "Baseline", "detail": "No strong signals yet",
                        "impact": "baseline", "points": 0}]
        out["factors"] = factors
    out["features"] = clean
    return out


# Warm up at import so the first request isn't slow and load errors show at startup
_load()
