import os
from apscheduler.schedulers.background import BackgroundScheduler
import database as db
import settings
from playbook import handle_trigger
from outreach import send_tracked_email

scheduler = BackgroundScheduler(
    timezone="Asia/Kolkata",
    # coalesce: if runs were missed (PC asleep, DB busy), run once instead of
    # piling up; grace time stops the "was missed by ..." warnings.
    job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300},
)



def _send_tracked_email(user_id, lead_id, to_email, subject, body, course_slug=None):
    """Kept for old imports — see outreach.send_tracked_email."""
    return send_tracked_email(user_id, lead_id, to_email, subject, body, course_slug=course_slug)

# ============================================================
_COOL = settings.S["cooldown_hours"]
COOLDOWN_SESSION_HOURS = _COOL["visit"]
COOLDOWN_CART_HOURS = _COOL["cart"]
COOLDOWN_WISHLIST_HOURS = _COOL["wishlist"]
# Touchpoints that count for cooldowns. "signup" is not one: creating the CRM
# contact at signup sends nothing, so it must not block the first follow-up.
TOUCH_TRIGGERS = ("enquiry", "chat_callback", "cart_abandon", "checkout_abandon", "wishlist", "session_end", "manual")

# ============================================================
DEMO_MODE = settings.DEMO_MODE
_MIN = settings.by_mode("automation_minutes")       # crm_settings.json: demo vs live timings
SESSION_INACTIVE_MINUTES = _MIN["visit_ended"]
CART_ABANDON_MINUTES = _MIN["cart_abandoned"]
WISHLIST_DELAY_MINUTES = _MIN["wishlist"]
CHECKOUT_ABANDON_MINUTES = _MIN["checkout_abandoned"]
JOB_EVERY_MINUTES = _MIN["job_every"]
COOLDOWN_CHECKOUT_HOURS = _COOL["checkout"]


# ============================================================
# SHARED HELPERS — all scoring goes through scoring.py
# ============================================================
def _profile_text(profile, key, default):
    return (profile or {}).get(key) or default


def _course_label(slug):
    import catalog
    return catalog.title_of(slug, "our programmes") if slug else "our programmes"


# ============================================================
# 🛒 CART ABANDONMENT
# ============================================================
def cart_abandonment_job():
    try:
        carts = db.get_abandoned_carts(CART_ABANDON_MINUTES)
        print(f"[CART JOB] Found {len(carts)} carts")
        for item in carts:
            user_id = item["user_id"]
            if not db.recent_lead_exists(user_id, ("cart_abandon", "checkout_abandon"), COOLDOWN_CART_HOURS):
                handle_trigger(user_id, item["name"], item["email"], "cart_abandon", item.get("course_slug"))
            db.mark_cart_email_sent(item["cart_id"])   # one follow-up per cart item
    except Exception as e:
        print("[CART JOB ERROR]", e)


# ============================================================
# ⏱ INACTIVITY (left the site) — the NBA decides whether to follow up at all
# ============================================================
def session_end_job():
    try:
        users = db.get_inactive_users(SESSION_INACTIVE_MINUTES)
        print(f"[SESSION JOB] Found {len(users)} ended visit(s)")
        for user in users:
            user_id = user["user_id"]
            try:
                if db.recent_lead_exists(user_id, TOUCH_TRIGGERS, COOLDOWN_SESSION_HOURS):
                    continue   # this visit was already covered by another touchpoint
                if db.get_purchases(user_id) and not db.get_cart(user_id):
                    continue   # customers who just browse their course aren't chased
                slug = db.get_behaviour_summary(user_id).get("top_course_slug")
                if not slug:
                    continue   # nothing they looked at — nothing useful to say
                handle_trigger(user_id, user["name"], user["email"], "session_end", slug)
            finally:
                db.mark_visit_handled(user_id, user["session_id"])   # one decision per visit
    except Exception as e:
        print("[SESSION JOB ERROR]", e)


# ============================================================
# ⭐ WISHLIST — information or a modest nudge, never the deepest discount
# ============================================================
def wishlist_job():
    try:
        users = db.get_users_with_old_wishlist(WISHLIST_DELAY_MINUTES)
        print(f"[WISHLIST JOB] Found {len(users)} users")
        for user in users:
            user_id = user["user_id"]
            if db.recent_lead_exists(user_id, ("wishlist", "cart_abandon", "checkout_abandon"), COOLDOWN_WISHLIST_HOURS):
                continue   # stays pending; reminded once the cooldown has passed
            handle_trigger(user_id, user["name"], user["email"], "wishlist", user.get("course_slug"),
                           allowed=["none", "email_info", "email_coupon_10", "whatsapp"])
            db.mark_wishlist_reminded(user_id)   # one reminder per wishlist item
    except Exception as e:
        print("[WISHLIST JOB ERROR]", e)


# ============================================================
# 💳 CHECKOUT ABANDONMENT
# ============================================================
def checkout_abandonment_job():
    try:
        sessions = db.get_abandoned_checkouts(CHECKOUT_ABANDON_MINUTES)
        print(f"[CHECKOUT JOB] Found {len(sessions)} abandoned checkouts")
        for item in sessions:
            user_id = item["user_id"]
            if not db.recent_lead_exists(user_id, "checkout_abandon", COOLDOWN_CHECKOUT_HOURS):
                cart_items = db.get_cart(user_id)
                slug = cart_items[0]["course_slug"] if cart_items else None
                handle_trigger(user_id, item["name"], item["email"], "checkout_abandon", slug)
            db.mark_checkout_email_sent(item["checkout_id"])
    except Exception as e:
        print("[CHECKOUT JOB ERROR]", e)


def run_all_jobs():
    """Strongest signal first, so weaker jobs see the fresh lead and skip."""
    checkout_abandonment_job()
    cart_abandonment_job()
    wishlist_job()
    session_end_job()


def refresh_scores_job(reason="scheduled"):
    """Every lead re-scored with the current model and the time since their last visit (scoring.py)."""
    try:
        import scoring
        scoring.refresh_scores(reason)
    except Exception as e:
        print("[SCORES JOB ERROR]", e)


def simulation_module():
    """ml/live_simulation.py: the simulated learners, who keep using the website in real time."""
    import sys
    ml_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ml"))
    if ml_dir not in sys.path:
        sys.path.insert(0, ml_dir)
    import live_simulation
    return live_simulation


def simulation_job():
    try:
        simulation_module().tick()
    except Exception as e:
        print("[SIMULATION ERROR]", e)


def start_scheduler():
    import threading
    import learning
    scheduler.add_job(run_all_jobs, "interval", minutes=JOB_EVERY_MINUTES)
    learn_every = int(settings.S["learning"]["check_every_minutes"][settings.MODE])
    scheduler.add_job(learning.scheduled_job, "interval", minutes=learn_every)
    refresh_every = int(settings.by_mode("score_refresh_minutes"))
    scheduler.add_job(refresh_scores_job, "interval", minutes=refresh_every)
    # once right after start-up: scores saved by an older model are brought up to date by themselves
    threading.Timer(3.0, refresh_scores_job, args=["startup"]).start()
    sim = settings.S.get("live_simulation") or {}
    sim_every = max(3, int(sim.get("tick_seconds", 10)))
    scheduler.add_job(simulation_job, "interval", seconds=sim_every)   # does nothing while paused
    scheduler.start()
    print(f"[SCHEDULER] Automations every {JOB_EVERY_MINUTES} min; learning loop checks every {learn_every} min "
          f"(runs when {settings.S['learning']['min_new_outcomes']}+ new outcomes are known); "
          f"every lead re-scored every {refresh_every} min and at start-up")
    print(f"[SIMULATION] Simulated learners {'live' if sim.get('enabled', True) else 'off (crm_settings.json)'}: "
          f"they keep using the website in real time (checked every {sim_every} s; Dashboard -> Simulated learners)")