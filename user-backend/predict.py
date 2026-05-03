"""
predict.py — ML Engine + Business Rules Layer
Loads 6 .pkl artefacts once. predict_lead() is called for every user event.
Business Rules Layer sits on top of ML score to handle new signals.
"""
import os
import numpy as np
import pandas as pd
import joblib

_BASE = os.path.join(os.path.dirname(__file__), "ml_models")

try:
    _model          = joblib.load(os.path.join(_BASE, "hgb_model_calibrated.pkl"))
    _preprocessor   = joblib.load(os.path.join(_BASE, "preprocessor.pkl"))
    _kmeans         = joblib.load(os.path.join(_BASE, "kmeans.pkl"))
    _pca            = joblib.load(os.path.join(_BASE, "pca.pkl"))
    _scaler_cluster = joblib.load(os.path.join(_BASE, "scaler_cluster.pkl"))
    _config         = joblib.load(os.path.join(_BASE, "model_config.pkl"))
    CLUSTER_FEATURES = _config["cluster_features"]
    PERSONA_MAP      = _config["persona_map"]
    BEST_THRESHOLD   = _config["best_threshold"]
    print("[ML] All 6 artefacts loaded.")
except Exception as e:
    print(f"[ML] WARNING: Could not load artefacts — {e}")
    print("[ML] Running in mock mode. Copy .pkl files to ml_models/ to enable real predictions.")
    _model = None


def _engineer(row: pd.DataFrame) -> pd.DataFrame:
    """Exact mirror of ml_pipeline_final.py feature engineering."""
    r = row.copy()
    r["EngagementScore"] = (
        r["TotalVisits"]*5 + r["TotalTimeOnWebsite"]/10 +
        r["PageViewsPerVisit"]*15 + r["VideoWatched"]*20 +
        r["BrochureDownloaded"]*25 + r["ChatInitiated"]*15
    )
    r["IntentScore"] = (
        r["BrochureDownloaded"]*3 + r["PricingPageVisited"]*3 +
        r["TestimonialVisited"]*2 + r["WebinarAttended"]*4 +
        r["ChatInitiated"]*2 + r["WhatsAppOptIn"]*1
    )
    r["VisitIntensity"]    = r["TotalTimeOnWebsite"] / (r["TotalVisits"] + 1)
    r["PagesPerMinute"]    = r["PageViewsPerVisit"]  / (r["TotalTimeOnWebsite"] + 1)
    r["LeadInterestScore"] = r["EngagementScore"] * r["PagesPerMinute"]
    r["Visits_x_Time"]     = r["TotalVisits"] * r["TotalTimeOnWebsite"]
    r["IsReturningVisitor"]= (r["TotalVisits"] > 1).astype(int)
    r["IsHighActivity"]    = (r["TotalTimeOnWebsite"] > 600).astype(int)
    r["IsDeepResearcher"]  = ((r["TestimonialVisited"]==1)&(r["BrochureDownloaded"]==1)).astype(int)
    r["EmailEngaged"]      = (r["DoNotEmail"] == "No").astype(int)
    r["PhoneEngaged"]      = (r["DoNotCall"]  == "No").astype(int)
    r["CommScore"]         = r["EmailEngaged"] + r["PhoneEngaged"]
    HIGH_Q = ["Google","Organic Search","Direct Traffic","Reference","Webinar"]
    r["HighQualityTraffic"]  = r["LeadSource"].isin(HIGH_Q).astype(int)
    r["MotivationScore"]     = (
        r["CommScore"]*1.0 + r["HighQualityTraffic"]*1.2 +
        r["WebinarAttended"]*2.0 + r["WhatsAppOptIn"]*0.8 + r["BrochureDownloaded"]*1.5
    )
    r["Engagement_x_Source"] = r["EngagementScore"] * r["HighQualityTraffic"]
    ir = (
        r["TotalVisits"]*0.3 + r["TotalTimeOnWebsite"]/300 +
        r["PageViewsPerVisit"]*0.4 + r["BrochureDownloaded"]*2.0 +
        r["VideoWatched"]*1.5 + r["WebinarAttended"]*3.0
    )
    r["CourseInterestLevel"] = pd.cut(ir,bins=[-np.inf,2,5,np.inf],labels=["Low","Medium","High"]).astype(str)
    r["ProfileCompleteness"] = (
        (r["City"]!="Unknown").astype(int) + (r["Country"]!="Other").astype(int) +
        r["AgeBracket"].notna().astype(int) + (r["HowDidYouHear"]!="Unknown").astype(int) + 1
    )
    r["VisitBucket"] = pd.cut(r["TotalVisits"],bins=[-1,1,4,100],labels=["Low","Medium","High"]).astype(str)
    r["TimeBucket"]  = pd.cut(r["TotalTimeOnWebsite"],bins=[-1,300,800,10000],labels=["Low","Medium","High"]).astype(str)
    return r


def _business_rules(score: float, raw: dict) -> tuple[float, str]:
    adjusted = score

    # Enquiry submitted → always at least Marketing Campaign
    if raw.get("enquiry_submitted"):
        adjusted = max(adjusted, 42.0)

    # Cart abandoned → escalate to at least Nurture
    if raw.get("cart_abandoned"):
        adjusted = max(adjusted, 62.0)

    # Wishlist item exists → small boost
    if raw.get("wishlist_count", 0) > 0:
        adjusted = min(adjusted + 5.0, 100.0)

    # 👇 NEW: Occupation-based dampening for low-conversion profiles
    occupation = raw.get("CurrentOccupation", "")
    low_conv_occupations = ["Student", "Unemployed", "Housewife"]
    if occupation in low_conv_occupations:
        # Allow full score only if cart abandoned or enquiry submitted
        if not raw.get("cart_abandoned") and not raw.get("enquiry_submitted"):
            # Cap the score to a max of 72 for these occupations
            adjusted = min(adjusted, 72.0)
            # Optionally reduce the score slightly to keep it believable
            adjusted = adjusted * 0.85   # 15% reduction for low-conv occupations

    # Clip to valid range
    adjusted = max(0.0, min(100.0, adjusted))

    if   adjusted >= 80: action = "Target Immediately"
    elif adjusted >= 60: action = "Nurture via Email/WhatsApp"
    elif adjusted >= 40: action = "Marketing Campaign"
    else:                action = "Low Priority"

    return round(adjusted, 2), action


def predict_lead(raw: dict) -> dict:
    """
    raw must contain all 24 CSV features + optional new signals:
      cart_abandoned, wishlist_count, enquiry_submitted, past_purchases
    """
    # ── Mock mode if no .pkl files ────────────────────────────────────
    if _model is None:
        import random
        score = random.uniform(20, 95)
        score, action = _business_rules(score, raw)
        return {
            "lead_score": score,
            "conversion_probability": round(score/100, 4),
            "persona": "Warm Lead" if score >= 60 else "Cold Lead",
            "customer_segment": "1",
            "recommended_action": action,
        }

    # ── Real prediction ───────────────────────────────────────────────
    row = pd.DataFrame([raw])
    row = _engineer(row)

    cluster_scaled = _scaler_cluster.transform(row[CLUSTER_FEATURES])
    cluster_pca    = _pca.transform(cluster_scaled)
    segment        = str(_kmeans.predict(cluster_pca)[0])
    persona        = PERSONA_MAP.get(segment, "Cold Lead")
    row["CustomerSegment"] = segment
    row["Persona"]         = persona

    row_proc = _preprocessor.transform(row)
    prob     = float(_model.predict_proba(row_proc)[0, 1])
    score    = round(prob * 100, 2)

    score, action = _business_rules(score, raw)

    return {
        "lead_score":             score,
        "conversion_probability": round(prob, 4),
        "persona":                persona,
        "customer_segment":       segment,
        "recommended_action":     action,
    }


def create_or_update_lead_snapshot(user_id: int, raw: dict):
    pred = predict_lead(raw)
    import database as db
    db.execute("""
        INSERT INTO leads (
            user_id, course_type, lead_score, conversion_probability,
            persona, customer_segment, recommended_action, trigger_reason
        ) VALUES (?,?,?,?,?,?,?,?)
    """, (
        user_id,
        raw.get("CourseType","Browsing"),
        pred["lead_score"],
        pred["conversion_probability"],
        pred["persona"],
        pred["customer_segment"],
        pred["recommended_action"],
        "behaviour_snapshot"
    ))
    return pred