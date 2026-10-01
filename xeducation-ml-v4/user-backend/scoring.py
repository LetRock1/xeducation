"""
scoring.py — the ONE place where a user's data becomes a lead score.

Before this file, main.py and scheduler.py each built their own feature
dict (6 copies) with different hard-coded values: LeadOrigin "Website
Interaction" in one, DeviceType "Mobile" in another, Specialization
"Business" in a third... Every endpoint and job now calls build_raw() and
score_user(), so the model sees the same, correct inputs everywhere.
"""
import json

import database as db
import ml_features as F
from predict import predict_lead

_DISCOUNTS = {"VIP_URGENT_25": 25, "FUTURE_READY_15": 15, "EARLY_BIRD_10": 10,
              "LOYAL_20": 20, "LAST_CHANCE_30": 30}


def build_raw(user_id, course=None, lead_source=None, whatsapp_opt_in=None):
    """Collect everything we know about the user as model features."""
    profile = db.get_profile(user_id) or {}
    b = db.get_behaviour_summary(user_id)
    e = db.get_email_engagement(user_id)
    return {
        "LeadOrigin": "Lead Add Form" if b["enquiry_submitted"] else "Landing Page Submission",
        "LeadSource": lead_source or b.get("lead_source") or "Direct Traffic",
        "DeviceType": b.get("device_type") or "Desktop",
        "CurrentOccupation": profile.get("current_occupation"),
        "Specialization": profile.get("specialization"),
        "CourseType": course or b.get("top_course_slug"),
        "City": profile.get("city"),
        "Country": profile.get("country"),
        "AgeBracket": profile.get("age_bracket"),
        "HowDidYouHear": profile.get("how_did_you_hear"),
        "TotalVisits": b["total_visits"],
        "TotalTimeOnWebsite": b["total_time_on_website"],
        "PageViewsPerVisit": b["page_views_per_visit"],
        "EmailOpenedCount": e["opens"] or 0,
        "VideoWatched": b["video_watched"],
        "BrochureDownloaded": b["brochure_downloaded"],
        "ChatInitiated": b["chat_initiated"],
        "PricingPageVisited": b["pricing_page_visited"],
        "TestimonialVisited": b["testimonial_visited"],
        "WebinarAttended": b["webinar_attended"],
        "AddedToWishlist": b["added_to_wishlist"],
        "AddedToCart": b["added_to_cart"],
        "CheckoutStarted": b["checkout_started"],
        "EnquirySubmitted": b["enquiry_submitted"],
        "WhatsAppOptIn": profile.get("whatsapp_opt_in", 0) if whatsapp_opt_in is None else whatsapp_opt_in,
        "DoNotEmail": profile.get("do_not_email") or "No",
        "DoNotCall": profile.get("do_not_call") or "No",
        "past_purchases": len(db.get_purchases(user_id)),
    }


def score_user(user_id, source, course=None, explain=False, snapshot_gap_minutes=0, **kw):
    """Score a user, record a snapshot for closed-loop retraining, update the live score."""
    raw = build_raw(user_id, course=course, **kw)
    pred = predict_lead(raw, explain=explain)
    pred["raw"] = raw
    db.add_score_snapshot(user_id, source, pred["features"], pred["conversion_probability"],
                          pred["lead_score"], pred["recommended_action"], pred["model_version"],
                          min_gap_minutes=snapshot_gap_minutes)
    db.execute("""
        INSERT INTO live_user_state (user_id, live_score, persona, updated_at)
        VALUES (?, ?, ?, datetime('now','localtime'))
        ON CONFLICT(user_id) DO UPDATE SET live_score=excluded.live_score,
            persona=excluded.persona, updated_at=excluded.updated_at
    """, (user_id, pred["lead_score"], pred["persona"]))
    return pred


def save_lead(user_id, pred, content, trigger, course_label=None):
    """Insert a lead row (with its explanation), issue the coupon, store PLV."""
    f = pred["features"]
    lead_id = db.execute("""
        INSERT INTO leads (
            user_id, lead_origin, lead_source, device_type,
            total_visits, total_time_on_website, page_views_per_visit,
            sessions_count, video_watched, brochure_downloaded, chat_initiated,
            pricing_page_visited, testimonial_visited, webinar_attended, email_opened_count,
            course_type, lead_score, conversion_probability, persona,
            customer_segment, recommended_action,
            email_subject, email_body, whatsapp_message, coupon_code, call_script,
            trigger_reason, score_factors, model_version
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        user_id, f["LeadOrigin"], f["LeadSource"], f["DeviceType"],
        int(f["TotalVisits"]), int(f["TotalTimeOnWebsite"]), f["PageViewsPerVisit"],
        int(f["TotalVisits"]), f["VideoWatched"], f["BrochureDownloaded"], f["ChatInitiated"],
        f["PricingPageVisited"], f["TestimonialVisited"], f["WebinarAttended"],
        int(f["EmailOpenedCount"]),
        course_label or f["CourseType"],
        pred["lead_score"], pred["conversion_probability"], pred["persona"],
        pred["customer_segment"], pred["recommended_action"],
        content.get("email_subject"), content.get("email_body"), content.get("whatsapp_message"),
        content.get("coupon_code"), content.get("call_script"),
        trigger, json.dumps(pred.get("factors") or []), pred["model_version"],
    ))

    code = content.get("coupon_code")
    if code and _DISCOUNTS.get(code, 0) > 0:
        db.execute("""
            INSERT OR IGNORE INTO coupons_issued (user_id, coupon_code, discount_pct, tier, expires_at)
            VALUES (?,?,?,?,datetime('now','localtime','+72 hours'))
        """, (user_id, code, _DISCOUNTS[code], pred["recommended_action"]))

    plv = db.compute_plv(user_id, pred["recommended_action"], pred["conversion_probability"])
    db.update_lead_plv(lead_id, plv)
    return lead_id


def rescore_latest_lead(user_id, reason):
    """Re-run the model for the user's latest lead row (email click, purchase...)."""
    lead = db.get_user_lead(user_id)
    pred = score_user(user_id, source=reason, explain=True)
    if not lead:
        return None, pred
    plv = db.compute_plv(user_id, pred["recommended_action"], pred["conversion_probability"])
    f = pred["features"]
    db.execute("""
        UPDATE leads SET lead_score=?, conversion_probability=?, recommended_action=?,
               persona=?, customer_segment=?, plv=?, email_opened_count=?,
               score_factors=?, model_version=?, decayed=0
        WHERE id=?
    """, (pred["lead_score"], pred["conversion_probability"], pred["recommended_action"],
          pred["persona"], pred["customer_segment"], plv, int(f["EmailOpenedCount"]),
          json.dumps(pred.get("factors") or []), pred["model_version"], lead["id"]))
    if (round(lead["lead_score"] or 0, 2) != pred["lead_score"]
            or lead["recommended_action"] != pred["recommended_action"]):
        db.log_score_change(lead["id"], user_id, lead["lead_score"], pred["lead_score"],
                            lead["recommended_action"], pred["recommended_action"], reason)
    return lead, pred
