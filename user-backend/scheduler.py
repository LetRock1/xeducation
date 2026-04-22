"""
scheduler.py — Background jobs using APScheduler.
Runs inside the FastAPI process.

Jobs:
  1. cart_abandonment_job  — every 5 min → checks carts idle > 60 min
  2. session_end_job       — every 10 min → processes ended sessions for Low Priority / Nurture leads
"""
import os
from apscheduler.schedulers.background import BackgroundScheduler
import database as db
from predict    import predict_lead
from genai_mock import generate_content
from email_service import send_marketing_email

ABANDON_THRESHOLD = int(os.getenv("CART_ABANDON_THRESHOLD_MINUTES", "60"))

scheduler = BackgroundScheduler(timezone="Asia/Kolkata")


def _build_raw_features(user_id: int, profile: dict, behaviour: dict,
                         course_type: str, source: str = "Direct Traffic") -> dict:
    """Build the 24-feature dict required by predict_lead()."""
    return {
        "LeadOrigin":          "Landing Page Submission",
        "LeadSource":          source,
        "DeviceType":          "Mobile",
        "TotalVisits":         behaviour.get("total_visits", 1),
        "TotalTimeOnWebsite":  behaviour.get("total_time_on_website", 0),
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
        "CourseType":          course_type,
        "City":                profile.get("city", "Unknown"),
        "Country":             profile.get("country", "India"),
        "AgeBracket":          profile.get("age_bracket"),
        "HowDidYouHear":       profile.get("how_did_you_hear", "Unknown"),
        "DoNotEmail":          profile.get("do_not_email", "No"),
        "DoNotCall":           profile.get("do_not_call", "No"),
        "WhatsAppOptIn":       profile.get("whatsapp_opt_in", 0),
        # Business rules signals
        "cart_abandoned":      True,
        "wishlist_count":      0,
        "enquiry_submitted":   False,
        "past_purchases":      0,
    }


def cart_abandonment_job():
    """Check for abandoned carts and send personalised recovery emails."""
    try:
        abandoned = db.get_abandoned_carts()
        for item in abandoned:
            user_id = item["user_id"]
            if item.get("do_not_email") == "Yes":
                db.mark_cart_email_sent(item["id"])
                continue

            profile   = db.get_profile(user_id) or {}
            behaviour = db.get_behaviour_summary(user_id)
            purchases = db.get_purchases(user_id)
            past_count = len(purchases)

            # Build course title from slug
            course_title = item.get("course_title", "our programme")

            raw = _build_raw_features(user_id, profile, behaviour, course_title)
            raw["cart_abandoned"]  = True
            raw["past_purchases"]  = past_count

            prediction = predict_lead(raw)
            action     = prediction["recommended_action"]

            # Only Nurture, Campaign, Target get cart emails (Low Priority gets session-end emails instead)
            if action == "Low Priority":
                action = "Marketing Campaign"   # cart abandonment escalates floor

            content = generate_content(
                name          = item.get("name", ""),
                occupation    = profile.get("current_occupation", "Professional"),
                specialization= profile.get("specialization", "your field"),
                course        = course_title,
                action        = action,
                trigger       = "cart_abandon",
                past_purchases= past_count,
            )

            # Save lead record
            db.execute("""
                INSERT INTO leads (
                    user_id, lead_origin, lead_source, device_type,
                    total_visits, total_time_on_website, page_views_per_visit,
                    sessions_count, video_watched, brochure_downloaded, chat_initiated,
                    pricing_page_visited, testimonial_visited, webinar_attended,
                    email_opened_count, course_type, lead_score, conversion_probability,
                    persona, customer_segment, recommended_action,
                    email_subject, email_body, whatsapp_message, coupon_code, call_script,
                    trigger_reason
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                user_id, raw["LeadOrigin"], raw["LeadSource"], raw["DeviceType"],
                raw["TotalVisits"], raw["TotalTimeOnWebsite"], raw["PageViewsPerVisit"],
                raw["SessionsCount"], raw["VideoWatched"], raw["BrochureDownloaded"],
                raw["ChatInitiated"], raw["PricingPageVisited"], raw["TestimonialVisited"],
                raw["WebinarAttended"], raw["EmailOpenedCount"], course_title,
                prediction["lead_score"], prediction["conversion_probability"],
                prediction["persona"], prediction["customer_segment"], action,
                content["email_subject"], content["email_body"], content["whatsapp_message"],
                content["coupon_code"], content["call_script"], "cart_abandon"
            ))

            # Issue coupon if applicable
            if content["coupon_code"]:
                discount = 25 if "25" in content["coupon_code"] else 15 if "15" in content["coupon_code"] else 10
                db.execute("""
                    INSERT OR IGNORE INTO coupons_issued
                    (user_id, coupon_code, discount_pct, tier, expires_at)
                    VALUES (?, ?, ?, ?, datetime('now','localtime','+72 hours'))
                """, (user_id, content["coupon_code"], discount, action))

            # Send email
            ok, msg = send_marketing_email(
                item["email"], content["email_subject"], content["email_body"]
            )
            if ok:
                db.mark_cart_email_sent(item["id"])
                db.execute(
                    "UPDATE leads SET email_sent=1, email_sent_at=datetime('now','localtime') WHERE user_id=? AND trigger_reason='cart_abandon' ORDER BY created_at DESC LIMIT 1",
                    (user_id,)
                )
                print(f"[SCHEDULER] Cart abandon email sent → {item['email']}")
            else:
                print(f"[SCHEDULER] Email failed → {item['email']}: {msg}")
    except Exception as e:
        print(f"[SCHEDULER] cart_abandonment_job error: {e}")


def session_end_job():
    """
    For Low Priority + Nurture users: send behaviour-based insight emails
    after their session appears to have ended (last_active > 15 min ago).
    Only fires for users who viewed a course or added to wishlist — not every browse.
    """
    try:
        # Find sessions inactive > 15 min with wishlist/course-view activity and no recent email
        inactive_users = db.fetchall("""
            SELECT DISTINCT us.user_id, u.email, u.name
            FROM user_sessions us
            JOIN users u ON us.user_id = u.id
            WHERE us.last_active <= datetime('now','localtime','-15 minutes')
              AND us.user_id NOT IN (
                SELECT user_id FROM leads
                WHERE created_at >= datetime('now','localtime','-24 hours')
              )
              AND us.user_id IN (
                SELECT DISTINCT user_id FROM behaviour_events
                WHERE event_type IN ('wishlist_add','cart_add','video_play','brochure_dl')
                  AND created_at >= datetime('now','localtime','-2 hours')
              )
        """)

        for user in inactive_users:
            user_id = user["user_id"]
            profile   = db.get_profile(user_id) or {}
            if profile.get("do_not_email") == "Yes":
                continue

            behaviour = db.get_behaviour_summary(user_id)
            purchases = db.get_purchases(user_id)
            past_count = len(purchases)
            top_course = behaviour.get("top_course_slug") or "our programme"

            # Map slug to title
            from recommendations import _slug_to_title
            course_title = _slug_to_title(top_course)

            raw = _build_raw_features(user_id, profile, behaviour, course_title)
            raw["wishlist_count"]  = len(db.get_wishlist(user_id))
            raw["past_purchases"]  = past_count

            prediction = predict_lead(raw)
            action     = prediction["recommended_action"]

            # Session-end emails: only for Low Priority and Nurture
            if action not in ("Low Priority", "Nurture via Email/WhatsApp"):
                continue

            content = generate_content(
                name          = user.get("name", ""),
                occupation    = profile.get("current_occupation", "Professional"),
                specialization= profile.get("specialization", "your field"),
                course        = course_title,
                action        = action,
                trigger       = "session_end",
                past_purchases= past_count,
            )

            db.execute("""
                INSERT INTO leads (
                    user_id, course_type, lead_score, conversion_probability,
                    persona, customer_segment, recommended_action,
                    email_subject, email_body, whatsapp_message,
                    coupon_code, call_script, trigger_reason,
                    total_visits, total_time_on_website, sessions_count,
                    video_watched, brochure_downloaded, chat_initiated,
                    pricing_page_visited, testimonial_visited
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                user_id, course_title, prediction["lead_score"],
                prediction["conversion_probability"], prediction["persona"],
                prediction["customer_segment"], action,
                content["email_subject"], content["email_body"],
                content["whatsapp_message"], content["coupon_code"],
                content["call_script"], "session_end",
                behaviour["total_visits"], behaviour["total_time_on_website"],
                behaviour["sessions_count"], behaviour["video_watched"],
                behaviour["brochure_downloaded"], behaviour["chat_initiated"],
                behaviour["pricing_page_visited"], behaviour["testimonial_visited"],
            ))

            ok, _ = send_marketing_email(
                user["email"], content["email_subject"], content["email_body"]
            )
            if ok:
                print(f"[SCHEDULER] Session-end insight email → {user['email']} ({action})")
    except Exception as e:
        print(f"[SCHEDULER] session_end_job error: {e}")


def start_scheduler():
    scheduler.add_job(cart_abandonment_job, "interval", minutes=5,  id="cart_job")
    scheduler.add_job(session_end_job,      "interval", minutes=10, id="session_job")
    scheduler.start()
    print("[SCHEDULER] Background jobs started → cart (5 min) + session-end (10 min)")
