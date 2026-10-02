import os, uuid
from urllib.parse import quote
from apscheduler.schedulers.background import BackgroundScheduler
import database as db
from scoring import score_user, save_lead
from genai_mock import generate_content
from email_service import send_marketing_email

scheduler = BackgroundScheduler(
    timezone="Asia/Kolkata",
    # coalesce: if runs were missed (PC asleep, DB busy), run once instead of
    # piling up; grace time stops the "was missed by ..." warnings.
    job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300},
)

MKT_BASE_URL  = os.getenv("MKT_PUBLIC_BASE_URL", "http://localhost:8001")
FRONTEND_URL  = os.getenv("USER_FRONTEND_URL", "http://localhost:5173")


def _send_tracked_email(user_id, lead_id, to_email, subject, body, course_slug=None):
    """Sends a marketing email with a click-tracked CTA (engagement is click-only, no pixel)."""
    token = uuid.uuid4().hex
    db.insert_email_send(token, user_id, lead_id=lead_id, subject=subject, body=body)
    dest = f"{FRONTEND_URL}/course/{course_slug}" if course_slug else FRONTEND_URL
    click_url = f"{MKT_BASE_URL}/api/mkt/track/click/{token}?to={quote(dest, safe='')}"
    return send_marketing_email(to_email, subject, body, cta_url=click_url)

# ============================================================
COOLDOWN_SESSION_HOURS = 6
COOLDOWN_CART_HOURS = 12
COOLDOWN_WISHLIST_HOURS = 24

# ============================================================
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"
SESSION_INACTIVE_MINUTES = 1 if DEMO_MODE else 15
CART_ABANDON_MINUTES = 1 if DEMO_MODE else 60
WISHLIST_DELAY_MINUTES = 1 if DEMO_MODE else 30
CHECKOUT_ABANDON_MINUTES = 1 if DEMO_MODE else 30
COOLDOWN_CHECKOUT_HOURS = 12


# ============================================================
# SHARED HELPERS — all scoring goes through scoring.py
# ============================================================
def _profile_text(profile, key, default):
    return (profile or {}).get(key) or default


def _course_label(slug):
    return slug.replace("-", " ").title() if slug else "our programmes"


# ============================================================
# 🛒 CART ABANDONMENT JOB
# ============================================================
def cart_abandonment_job():
    try:
        carts = db.get_abandoned_carts(CART_ABANDON_MINUTES)
        print(f"[CART JOB] Found {len(carts)} carts")
        for item in carts:
            user_id = item["user_id"]
            if db.recent_lead_exists(user_id, ("cart_abandon", "checkout_abandon"), COOLDOWN_CART_HOURS):
                # one recovery email is enough — checkout-abandon already covers this cart
                db.mark_cart_email_sent(item["cart_id"])
                continue
            profile = db.get_profile(user_id) or {}
            purchases = db.get_purchases(user_id)
            pred = score_user(user_id, source="cart_abandon",
                              course=item.get("course_slug"), explain=True)
            content = generate_content(
                name=item["name"],
                occupation=_profile_text(profile, "current_occupation", "Professional"),
                specialization=_profile_text(profile, "specialization", "your field"),
                course=item["course_title"],
                action=pred["recommended_action"],
                trigger="cart_abandon",
                past_purchases=len(purchases),
            )
            lead_id = save_lead(user_id, pred, content, "cart_abandon", course_label=item["course_title"])
            _send_tracked_email(user_id, lead_id, item["email"], content["email_subject"],
                                content["email_body"], course_slug=item.get("course_slug"))
            db.mark_cart_email_sent(item["cart_id"])
            print(f"[CART JOB] {item['email']}: score {pred['lead_score']} -> {pred['recommended_action']}")
    except Exception as e:
        print("[CART JOB ERROR]", e)


# ============================================================
# ⏱ SESSION INACTIVE JOB (records a lead; no email)
# ============================================================
def session_end_job():
    try:
        users = db.get_inactive_users(SESSION_INACTIVE_MINUTES)
        print(f"[SESSION JOB] Found {len(users)} users")
        for user in users:
            user_id = user["user_id"]
            if db.recent_lead_exists(user_id, None, COOLDOWN_SESSION_HOURS):
                continue   # already has a fresh lead from another trigger
            profile = db.get_profile(user_id) or {}
            pred = score_user(user_id, source="session_end", explain=True)
            slug = db.get_behaviour_summary(user_id).get("top_course_slug")
            content = generate_content(
                name=user["name"],
                occupation=_profile_text(profile, "current_occupation", "Professional"),
                specialization=_profile_text(profile, "specialization", "your field"),
                course=_course_label(slug),
                action=pred["recommended_action"],
                trigger="session_end",
                past_purchases=pred["raw"]["past_purchases"],
            )
            save_lead(user_id, pred, content, "session_end", course_label=_course_label(slug))
            print(f"[SESSION JOB] {user['email']}: score {pred['lead_score']} -> {pred['recommended_action']}")
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
            if db.recent_lead_exists(user_id, ("wishlist", "cart_abandon", "checkout_abandon"), COOLDOWN_WISHLIST_HOURS):
                continue
            profile = db.get_profile(user_id) or {}
            wl = db.get_wishlist(user_id)
            slug = wl[0]["course_slug"] if wl else None
            title = wl[0]["course_title"] if wl else "your shortlisted course"
            pred = score_user(user_id, source="wishlist", course=slug, explain=True)
            content = generate_content(
                name=user["name"],
                occupation=_profile_text(profile, "current_occupation", "Professional"),
                specialization=_profile_text(profile, "specialization", "your field"),
                course=title,
                action=pred["recommended_action"],
                trigger="wishlist_viewed",
                past_purchases=pred["raw"]["past_purchases"],
            )
            content["coupon_code"] = None  # insight email, no discount
            lead_id = save_lead(user_id, pred, content, "wishlist", course_label=title)
            _send_tracked_email(user_id, lead_id, user["email"], content["email_subject"],
                                content["email_body"], course_slug=slug)
            print(f"[WISHLIST JOB] {user['email']}: score {pred['lead_score']} -> {pred['recommended_action']}")
    except Exception as e:
        print("[WISHLIST JOB ERROR]", e)


# ============================================================
# 💳 CHECKOUT ABANDONMENT JOB
# ============================================================
def checkout_abandonment_job():
    try:
        sessions = db.get_abandoned_checkouts(CHECKOUT_ABANDON_MINUTES)
        print(f"[CHECKOUT JOB] Found {len(sessions)} abandoned checkouts")
        for item in sessions:
            user_id = item["user_id"]
            if db.recent_lead_exists(user_id, "checkout_abandon", COOLDOWN_CHECKOUT_HOURS):
                db.mark_checkout_email_sent(item["checkout_id"])
                continue
            profile = db.get_profile(user_id) or {}
            cart_items = db.get_cart(user_id)
            slug = cart_items[0]["course_slug"] if cart_items else None
            title = cart_items[0]["course_title"] if cart_items else "your selected course"
            pred = score_user(user_id, source="checkout_abandon", course=slug, explain=True)
            content = generate_content(
                name=item["name"],
                occupation=_profile_text(profile, "current_occupation", "Professional"),
                specialization=_profile_text(profile, "specialization", "your field"),
                course=title,
                action=pred["recommended_action"],
                trigger="checkout_abandon",
                past_purchases=pred["raw"]["past_purchases"],
            )
            lead_id = save_lead(user_id, pred, content, "checkout_abandon", course_label=title)
            _send_tracked_email(user_id, lead_id, item["email"], content["email_subject"],
                                content["email_body"], course_slug=slug)
            db.mark_checkout_email_sent(item["checkout_id"])
            print(f"[CHECKOUT JOB] {item['email']}: score {pred['lead_score']} -> {pred['recommended_action']}")
    except Exception as e:
        print("[CHECKOUT JOB ERROR]", e)


def run_all_jobs():
    """Strongest signal first, so weaker jobs see the fresh lead and skip."""
    checkout_abandonment_job()
    cart_abandonment_job()
    wishlist_job()
    session_end_job()


def start_scheduler():
    scheduler.add_job(run_all_jobs, "interval", minutes=5)
    scheduler.start()
    print("[SCHEDULER] All jobs started")