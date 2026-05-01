"""
scheduler.py — Background jobs using APScheduler.

Jobs:
  1. cart_abandonment_job  — every 5 min → checks carts idle > 60 min
  2. session_end_job       — every 10 min → ALL users inactive > 15 min
                             who browsed ANY course page (page_view counts)
                             Creates lead record for marketing dashboard.

KEY FIX: session_end_job now captures PURE BROWSERS — users who only
scrolled/viewed pages without adding to cart or wishlist. Any behaviour
event (including page_view) qualifies. This is how the marketing team
sees Low Priority leads who never took a strong action.
"""
import os
from apscheduler.schedulers.background import BackgroundScheduler
import database as db
from predict      import predict_lead
from genai_mock   import generate_content
from email_service import send_marketing_email

scheduler = BackgroundScheduler(timezone="Asia/Kolkata")


def _build_raw(user_id, profile, behaviour, course_title,
               cart_abandoned=False, wishlist_count=0,
               enquiry=False, past_purchases=0,
               source="Direct Traffic"):
    """Build the 24-feature dict for predict_lead()."""
    return {
        "LeadOrigin":         "Landing Page Submission",
        "LeadSource":          source,
        "DeviceType":          "Mobile",
        "TotalVisits":         behaviour.get("total_visits", 1),
        "TotalTimeOnWebsite":  min(behaviour.get("total_time_on_website", 0), 4000),
        "PageViewsPerVisit":   behaviour.get("page_views_per_visit", 1.0),
        "SessionsCount":       behaviour.get("sessions_count", 1),
        "VideoWatched":        behaviour.get("video_watched", 0),
        "BrochureDownloaded":  behaviour.get("brochure_downloaded", 0),
        "ChatInitiated":       behaviour.get("chat_initiated", 0),
        "PricingPageVisited":  behaviour.get("pricing_page_visited", 0),
        "TestimonialVisited":  behaviour.get("testimonial_visited", 0),
        "WebinarAttended":     behaviour.get("webinar_attended", 0),
        "EmailOpenedCount":    0,
        "CurrentOccupation":   profile.get("current_occupation", "Unemployed"),
        "Specialization":      profile.get("specialization", "Business Administration"),
        "CourseType":          course_title,
        "City":                profile.get("city", "Unknown"),
        "Country":             profile.get("country", "India"),
        "AgeBracket":          profile.get("age_bracket"),
        "HowDidYouHear":       profile.get("how_did_you_hear", "Unknown"),
        "DoNotEmail":          profile.get("do_not_email", "No"),
        "DoNotCall":           profile.get("do_not_call", "No"),
        "WhatsAppOptIn":       profile.get("whatsapp_opt_in", 0),
        # Business rules signals (not in original 24 but handled by predict.py)
        "cart_abandoned":      cart_abandoned,
        "wishlist_count":      wishlist_count,
        "enquiry_submitted":   enquiry,
        "past_purchases":      past_purchases,
    }


def _save_lead(user_id, raw, pred, content, trigger):
    """Insert a lead record and issue coupon if applicable."""
    db.execute("""
        INSERT INTO leads (
            user_id, lead_origin, lead_source, device_type,
            total_visits, total_time_on_website, page_views_per_visit,
            sessions_count, video_watched, brochure_downloaded, chat_initiated,
            pricing_page_visited, testimonial_visited, webinar_attended,
            email_opened_count, course_type,
            lead_score, conversion_probability, persona,
            customer_segment, recommended_action,
            email_subject, email_body, whatsapp_message,
            coupon_code, call_script, trigger_reason
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        user_id,
        raw["LeadOrigin"], raw["LeadSource"], raw["DeviceType"],
        raw["TotalVisits"], raw["TotalTimeOnWebsite"], raw["PageViewsPerVisit"],
        raw["SessionsCount"], raw["VideoWatched"], raw["BrochureDownloaded"],
        raw["ChatInitiated"], raw["PricingPageVisited"], raw["TestimonialVisited"],
        raw["WebinarAttended"], raw["EmailOpenedCount"], raw["CourseType"],
        pred["lead_score"], pred["conversion_probability"], pred["persona"],
        pred["customer_segment"], pred["recommended_action"],
        content["email_subject"], content["email_body"], content["whatsapp_message"],
        content["coupon_code"], content.get("call_script", ""), trigger,
    ))
    # Hardcoded discount — matches the coupon name, not derived from user input
    _COUPON_DISCOUNTS = {
        "VIP_URGENT_25":  25,
        "FUTURE_READY_15": 15,
        "EARLY_BIRD_10":  10,
        "LOYAL_20":       20,
    }
    if content["coupon_code"] and content["coupon_code"] in _COUPON_DISCOUNTS:
        disc = _COUPON_DISCOUNTS[content["coupon_code"]]
        db.execute("""
            INSERT OR IGNORE INTO coupons_issued
            (user_id, coupon_code, discount_pct, tier, expires_at)
            VALUES (?, ?, ?, ?, datetime('now','localtime','+72 hours'))
        """, (user_id, content["coupon_code"], disc, pred["recommended_action"]))


# ── JOB 1: Cart abandonment (every 5 minutes) ────────────────────────────────

def cart_abandonment_job():
    """
    TRIGGER: Cart item added > 60 minutes ago, no email sent yet.
    ACTION:  ML score → GenAI content (min Nurture tier) → Email sent.
    TIER:    Cart abandonment always escalates to minimum Nurture tier.
    """
    try:
        abandoned = db.get_abandoned_carts()
        for item in abandoned:
            user_id = item["user_id"]
            if item.get("do_not_email") == "Yes":
                db.mark_cart_email_sent(item["id"])
                continue

            profile    = db.get_profile(user_id) or {}
            behaviour  = db.get_behaviour_summary(user_id)
            purchases  = db.get_purchases(user_id)
            past_count = len(purchases)
            course_title = item.get("course_title", "our programme")

            raw  = _build_raw(user_id, profile, behaviour, course_title,
                               cart_abandoned=True, past_purchases=past_count)
            pred = predict_lead(raw)

            # Cart abandonment always escalates: minimum Nurture
            if pred["recommended_action"] == "Low Priority":
                pred["recommended_action"] = "Nurture via Email/WhatsApp"
                pred["lead_score"] = max(pred["lead_score"], 62.0)

            content = generate_content(
                name           = item.get("name", ""),
                occupation     = profile.get("current_occupation", "Professional"),
                specialization = profile.get("specialization", "your field"),
                course         = course_title,
                action         = pred["recommended_action"],
                trigger        = "cart_abandon",
                past_purchases = past_count,
            )

            _save_lead(user_id, raw, pred, content, "cart_abandon")

            ok, msg = send_marketing_email(
                item["email"], content["email_subject"], content["email_body"]
            )
            if ok:
                db.mark_cart_email_sent(item["id"])
                db.execute("""
                    UPDATE leads SET email_sent=1,
                    email_sent_at=datetime('now','localtime')
                    WHERE user_id=? AND trigger_reason='cart_abandon'
                    ORDER BY created_at DESC LIMIT 1
                """, (user_id,))
                print(f"[CART JOB] Email sent → {item['email']} | Score: {pred['lead_score']} | Tier: {pred['recommended_action']}")
            else:
                print(f"[CART JOB] Email failed → {item['email']}: {msg}")

    except Exception as e:
        print(f"[CART JOB] Error: {e}")


# ── JOB 2: Session end (every 10 minutes) ────────────────────────────────────

def session_end_job():
    """
    TRIGGER: User inactive > 15 min AND had ANY behaviour event in last 2 hrs.
             This includes pure browsers (page_view only) — the key fix.
             NOT triggered if the user already got an email in last 24 hrs.

    THIS IS WHERE LOW PRIORITY USERS ARE CREATED.
    A user who just browses, scrolls, reads course info — no cart, no enquiry —
    will appear in the marketing dashboard as a Low Priority lead after their
    session ends. The ML model scores them based on time spent, pages viewed,
    and profile (occupation, city, etc.)
    """
    try:
        # ── KEY FIX: event_type IN (...) now includes 'page_view' ──────────
        # Previously only 'wishlist_add','cart_add','video_play','brochure_dl'
        # were included — this missed all pure browsers.
        inactive_users = db.fetchall("""
            SELECT DISTINCT us.user_id, u.email, u.name
            FROM user_sessions us
            JOIN users u ON us.user_id = u.id
            WHERE us.last_active <= datetime('now','localtime','-15 minutes')
              AND u.is_verified = 1
              AND us.user_id NOT IN (
                SELECT user_id FROM leads
                WHERE created_at >= datetime('now','localtime','-24 hours')
              )
              AND us.user_id IN (
                SELECT DISTINCT user_id FROM behaviour_events
                WHERE event_type IN (
                  'page_view','video_play','brochure_dl','chat',
                  'pricing_view','testimonial_view','webinar_view',
                  'wishlist_add','cart_add','review_submit'
                )
                AND created_at >= datetime('now','localtime','-2 hours')
              )
        """)

        for user in inactive_users:
            user_id  = user["user_id"]
            profile  = db.get_profile(user_id) or {}

            if profile.get("do_not_email") == "Yes":
                continue

            behaviour  = db.get_behaviour_summary(user_id)
            purchases  = db.get_purchases(user_id)
            past_count = len(purchases)
            top_course = behaviour.get("top_course_slug")

            # If user never viewed a specific course, use their specialization
            from recommendations import _slug_to_title
            course_title = _slug_to_title(top_course) if top_course else "our programmes"

            raw  = _build_raw(user_id, profile, behaviour, course_title,
                               wishlist_count=len(db.get_wishlist(user_id)),
                               past_purchases=past_count)
            pred = predict_lead(raw)
            action = pred["recommended_action"]

            # Session-end emails → only Low Priority and Nurture.
            # Marketing Campaign and Target Immediately are handled by
            # cart abandonment and enquiry form triggers respectively.
            if action not in ("Low Priority", "Nurture via Email/WhatsApp"):
                # Still create the lead record so marketing can see them
                # but only send email for lower tiers
                content = generate_content(
                    name=user.get("name",""), occupation=profile.get("current_occupation","Professional"),
                    specialization=profile.get("specialization","your field"),
                    course=course_title, action=action, trigger="session_end",
                    past_purchases=past_count,
                )
                _save_lead(user_id, raw, pred, content, "session_end")
                print(f"[SESSION JOB] Lead created (no email) → {user['email']} | Tier: {action}")
                continue

            content = generate_content(
                name           = user.get("name", ""),
                occupation     = profile.get("current_occupation", "Professional"),
                specialization = profile.get("specialization", "your field"),
                course         = course_title,
                action         = action,
                trigger        = "session_end",
                past_purchases = past_count,
            )

            _save_lead(user_id, raw, pred, content, "session_end")

            ok, _ = send_marketing_email(
                user["email"], content["email_subject"], content["email_body"]
            )
            if ok:
                db.execute("""
                    UPDATE leads SET email_sent=1,
                    email_sent_at=datetime('now','localtime')
                    WHERE user_id=? AND trigger_reason='session_end'
                    ORDER BY created_at DESC LIMIT 1
                """, (user_id,))
                print(f"[SESSION JOB] Email sent → {user['email']} | Score: {pred['lead_score']} | Tier: {action}")
            else:
                print(f"[SESSION JOB] Lead saved, email failed → {user['email']}")

    except Exception as e:
        print(f"[SESSION JOB] Error: {e}")


def start_scheduler():
    scheduler.add_job(cart_abandonment_job, "interval", minutes=5,  id="cart_job")
    scheduler.add_job(session_end_job,      "interval", minutes=10, id="session_job")
    scheduler.start()
    print("[SCHEDULER] Jobs started: cart abandonment (5 min) + session end (10 min)")
