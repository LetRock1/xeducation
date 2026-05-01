import os
from apscheduler.schedulers.background import BackgroundScheduler
import database as db
from predict import predict_lead
from genai_mock import generate_content
from email_service import send_marketing_email

scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

# ============================================================
COOLDOWN_SESSION_HOURS = 6
COOLDOWN_CART_HOURS = 12
COOLDOWN_WISHLIST_HOURS = 24

# ============================================================
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"
SESSION_INACTIVE_MINUTES = 1 if DEMO_MODE else 15
CART_ABANDON_MINUTES = 2 if DEMO_MODE else 60
WISHLIST_DELAY_MINUTES = 2 if DEMO_MODE else 30


# ============================================================
# SHARED HELPER
# ============================================================
def _build_raw(user_id, profile, behaviour, course_title,
               cart_abandoned=False, wishlist_count=0,
               enquiry=False, past_purchases=0,
               source="Direct Traffic"):
    return {
        "LeadOrigin": "Landing Page Submission",
        "LeadSource": source,
        "DeviceType": "Mobile",
        "TotalVisits": behaviour.get("total_visits", 1),
        "TotalTimeOnWebsite": behaviour.get("total_time_on_website", 0),
        "PageViewsPerVisit": behaviour.get("page_views_per_visit", 1.0),
        "SessionsCount": behaviour.get("sessions_count", 1),
        "VideoWatched": behaviour.get("video_watched", 0),
        "BrochureDownloaded": behaviour.get("brochure_downloaded", 0),
        "ChatInitiated": behaviour.get("chat_initiated", 0),
        "PricingPageVisited": behaviour.get("pricing_page_visited", 0),
        "TestimonialVisited": behaviour.get("testimonial_visited", 0),
        "WebinarAttended": behaviour.get("webinar_attended", 0),
        "EmailOpenedCount": 0,
        "CurrentOccupation": profile.get("current_occupation", "Unemployed"),
        "Specialization": profile.get("specialization", "Business"),
        "CourseType": course_title,
        "City": profile.get("city", "Unknown"),
        "Country": profile.get("country", "India"),
        "AgeBracket": profile.get("age_bracket"),
        "HowDidYouHear": profile.get("how_did_you_hear", "Unknown"),
        "DoNotEmail": profile.get("do_not_email", "No"),
        "DoNotCall": profile.get("do_not_call", "No"),
        "WhatsAppOptIn": profile.get("whatsapp_opt_in", 0),
        "cart_abandoned": cart_abandoned,
        "wishlist_count": wishlist_count,
        "enquiry_submitted": enquiry,
        "past_purchases": past_purchases,
    }


def _save_lead(user_id, raw, pred, content, trigger):
    db.execute("""
        INSERT INTO leads (
            user_id, course_type, lead_score, conversion_probability,
            persona, customer_segment, recommended_action,
            email_subject, email_body, whatsapp_message, coupon_code, trigger_reason
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        user_id, raw["CourseType"], pred["lead_score"], pred["conversion_probability"],
        pred["persona"], pred["customer_segment"], pred["recommended_action"],
        content["email_subject"], content["email_body"], content["whatsapp_message"],
        content["coupon_code"], trigger
    ))


# ============================================================
# 🛒 CART ABANDONMENT JOB
# ============================================================
def cart_abandonment_job():
    try:
        carts = db.get_abandoned_carts(CART_ABANDON_MINUTES)
        print(f"[CART JOB] Found {len(carts)} carts")

        for item in carts:
            user_id = item["user_id"]

            # 🛑 COOLDOWN CHECK
            if db.recent_lead_exists(user_id, "cart_abandon", COOLDOWN_CART_HOURS):
                print(f"[CART JOB] Skipping {item['email']} (cooldown)")
                continue

            profile = db.get_profile(user_id) or {}
            behaviour = db.get_behaviour_summary(user_id)
            purchases = db.get_purchases(user_id)

            raw = _build_raw(user_id, profile, behaviour,
                             item["course_title"], cart_abandoned=True,
                             past_purchases=len(purchases))

            pred = predict_lead(raw)

            content = generate_content(
                name=item["name"],
                occupation=profile.get("current_occupation","Professional"),
                specialization=profile.get("specialization","your field"),
                course=item["course_title"],
                action=pred["recommended_action"],
                trigger="cart_abandon",
                past_purchases=len(purchases),
            )

            _save_lead(user_id, raw, pred, content, "cart_abandon")
            send_marketing_email(item["email"], content["email_subject"], content["email_body"])
            db.mark_cart_email_sent(item["cart_id"])

            print(f"[CART JOB] Email sent → {item['email']}")

    except Exception as e:
        print("[CART JOB ERROR]", e)


# ============================================================
# ⏱ SESSION INACTIVE JOB
# ============================================================
def session_end_job():
    try:
        users = db.get_inactive_users(SESSION_INACTIVE_MINUTES)
        print(f"[SESSION JOB] Found {len(users)} users")

        for user in users:
            user_id = user["user_id"]

            # 🛑 COOLDOWN CHECK
            if db.recent_lead_exists(user_id, "session_end", COOLDOWN_SESSION_HOURS):
                print(f"[SESSION JOB] Skipping {user['email']} (cooldown)")
                continue

            profile = db.get_profile(user_id) or {}
            behaviour = db.get_behaviour_summary(user_id)

            raw = _build_raw(user_id, profile, behaviour, "Browsing")
            pred = predict_lead(raw)

            content = generate_content(
                name=user["name"],
                occupation=profile.get("current_occupation","Professional"),
                specialization=profile.get("specialization","your field"),
                course="our programmes",
                action=pred["recommended_action"],
                trigger="session_end",
                past_purchases=0,
            )

            _save_lead(user_id, raw, pred, content, "session_end")
            print(f"[SESSION JOB] Lead created → {user['email']}")

    except Exception as e:
        print("[SESSION JOB ERROR]", e)


# ============================================================
# ⭐ WISHLIST JOB (INSIGHT EMAIL — NO COUPON)
# ============================================================
def wishlist_job():
    try:
        users = db.get_users_with_old_wishlist(WISHLIST_DELAY_MINUTES)
        print(f"[WISHLIST JOB] Found {len(users)} users")

        for user in users:
            user_id = user["user_id"]

            # 🛑 COOLDOWN CHECK
            if db.recent_lead_exists(user_id, "wishlist", COOLDOWN_WISHLIST_HOURS):
                print(f"[WISHLIST JOB] Skipping {user['email']} (cooldown)")
                continue

            profile = db.get_profile(user_id) or {}
            behaviour = db.get_behaviour_summary(user_id)

            raw = _build_raw(user_id, profile, behaviour, "Wishlist Course")
            pred = predict_lead(raw)

            content = generate_content(
                name=user["name"],
                occupation=profile.get("current_occupation","Professional"),
                specialization=profile.get("specialization","your field"),
                course="your shortlisted course",
                action="Nurture via Email/WhatsApp",
                trigger="wishlist",
                past_purchases=0,
            )

            content["coupon_code"] = None  # ❌ No discount email

            _save_lead(user_id, raw, pred, content, "wishlist")
            send_marketing_email(user["email"], content["email_subject"], content["email_body"])

            print(f"[WISHLIST JOB] Email sent → {user['email']}")

    except Exception as e:
        print("[WISHLIST JOB ERROR]", e)


def start_scheduler():
    scheduler.add_job(cart_abandonment_job, "interval", minutes=5)
    scheduler.add_job(session_end_job, "interval", minutes=5)
    scheduler.add_job(wishlist_job, "interval", minutes=5)
    scheduler.start()
    print("[SCHEDULER] All jobs started")