"""
main.py — X Education User Backend (port 8000)
All API routes for the user-facing website.
"""
import os
import re
import sqlite3
import uuid
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv

import database as db
import auth
from predict         import predict_lead, model_info
from scoring         import score_user, save_lead, rescore_latest_lead
import ml_features   as F
import catalog
import assistant
from genai_mock      import generate_content
from email_service   import send_otp_email, send_purchase_confirmation_email, ATTRIBUTION_LABELS
from recommendations import recommend
from scheduler       import start_scheduler
from outreach        import send_tracked_email
from playbook        import handle_trigger

load_dotenv()
app = FastAPI(title="X Education User API", version="2.0.0")

app.add_middleware(CORSMiddleware,
    allow_origins=["http://localhost:5173","http://127.0.0.1:5173"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def startup():
    db.init_db()
    start_scheduler()
    print("[API] X Education User Backend running on port 8000")


# ── AUTH DEPENDENCY ───────────────────────────────────────────────────────────
def get_current_user(authorization: str = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Not authenticated")
    token = authorization.split(" ", 1)[1]
    payload = auth.decode_token(token)
    if not payload:
        raise HTTPException(401, "Invalid or expired token")
    user = db.get_user_by_id(int(payload["sub"]))
    if not user:
        raise HTTPException(401, "User not found")
    return user

def optional_user(authorization: str = Header(None)) -> Optional[dict]:
    try:
        return get_current_user(authorization)
    except:
        return None


# ── PYDANTIC MODELS ───────────────────────────────────────────────────────────
class SignupRequest(BaseModel):
    name: str; email: str; password: str

class OTPVerifyRequest(BaseModel):
    email: str; otp: str

class LoginRequest(BaseModel):
    email: str; password: str

class ProfileRequest(BaseModel):
    current_occupation: str
    specialization: str
    age_bracket: Optional[str] = None
    city: Optional[str] = "Unknown"
    country: Optional[str] = "India"
    phone: Optional[str] = None
    how_did_you_hear: Optional[str] = "Unknown"

class BehaviourEvent(BaseModel):
    session_id: int
    course_slug: Optional[str] = None
    event_type: str
    time_spent_sec: Optional[int] = 0

class CartItem(BaseModel):
    course_slug: str
    course_title: Optional[str] = None   # ignored — title and price come from the catalogue
    price: Optional[float] = None

class WishlistItem(BaseModel):
    course_slug: str; course_title: str

class EnquiryRequest(BaseModel):
    course_slug: str
    course_type: str
    phone: Optional[str] = None
    whatsapp_opt_in: int = 0
    lead_source: Optional[str] = "Direct Traffic"

class ReviewRequest(BaseModel):
    course_slug: str; rating: int; review_text: Optional[str] = ""

class QnARequest(BaseModel):
    course_slug: str; question: str

class CheckoutRequest(BaseModel):
    coupon_code: Optional[str] = ""

class EmailOnly(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    email: str; otp: str; new_password: str

class ChangePasswordRequest(BaseModel):
    current_password: str; new_password: str

class PreferencesRequest(BaseModel):
    do_not_email: Optional[bool] = None
    do_not_call: Optional[bool] = None
    whatsapp_opt_in: Optional[bool] = None
    phone: Optional[str] = None

class CouponCheck(BaseModel):
    code: str

class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    course_slug: Optional[str] = None

class CallbackRequest(BaseModel):
    phone: str
    preferred_time: Optional[str] = None
    note: Optional[str] = None
    course_slug: Optional[str] = None


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+?[0-9][0-9 -]{8,14}$")
OTP_RESEND_SECONDS = 60


def _check_password(pw):
    if len(pw or "") < 6:
        raise HTTPException(400, "Password must be at least 6 characters.")


# ── HEALTH ────────────────────────────────────────────────────────────────────
@app.get("/api/health")
def health(): return {"status": "ok", "service": "user-backend"}


# ── AUTH ROUTES ───────────────────────────────────────────────────────────────
@app.post("/api/auth/signup")
def signup(body: SignupRequest):
    body.email = (body.email or "").strip().lower()
    body.name = (body.name or "").strip()
    if not body.name:
        raise HTTPException(400, "Please enter your name.")
    if not EMAIL_RE.match(body.email):
        raise HTTPException(400, "Please enter a valid email address.")
    _check_password(body.password)
    existing = db.get_user_by_email(body.email)
    if existing and existing["is_verified"]:
        raise HTTPException(400, "Email already registered. Please login.")

    otp = auth.generate_otp()
    created = False
    if existing:
        # Unfinished signup (never verified): refresh details and resend a new OTP
        # instead of leaving the email permanently stuck.
        db.execute("UPDATE users SET name=?, password_hash=? WHERE id=?",
                   (body.name, auth.hash_password(body.password), existing["id"]))
        user_id = existing["id"]
    else:
        try:
            user_id = db.execute(
                "INSERT INTO users (name, email, password_hash, is_verified) VALUES (?,?,?,0)",
                (body.name, body.email, auth.hash_password(body.password))
            )
            created = True
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Signup already in progress for this email. Check your inbox for the OTP.")

    auth.save_otp(body.email, otp)
    ok, msg = send_otp_email(body.email, otp, body.name)
    if not ok:
        if created:
            db.execute("DELETE FROM users WHERE id=?", (user_id,))
        raise HTTPException(500, f"Could not send OTP: {msg}")
    return {"message": f"OTP sent to {body.email}. Please verify to complete registration."}

@app.post("/api/auth/verify-otp")
def verify_otp(body: OTPVerifyRequest):
    body.email = (body.email or "").strip().lower()
    if not auth.verify_otp(body.email, body.otp):
        raise HTTPException(400, "Invalid or expired OTP. Please try again.")
    user = db.get_user_by_email(body.email)
    if not user:
        raise HTTPException(404, "User not found")
    db.execute("UPDATE users SET is_verified=1 WHERE email=?", (body.email,))

    # Create empty profile
    db.execute("INSERT OR IGNORE INTO user_profiles (user_id) VALUES (?)", (user["id"],))
    # Every verified user becomes a lead (contact) in the CRM straight away
    if not db.get_user_lead(user["id"]):
        save_lead(user["id"], score_user(user["id"], source="signup", explain=True), {}, "signup")

    # Create a session immediately so tracking works after signup
    session_id = db.execute(
        "INSERT INTO user_sessions (user_id, device_type) VALUES (?,?)",
        (user["id"], "Desktop")
    )

    token = auth.create_token(user["id"], user["email"])
    return {
        "token": token,
        "session_id": session_id,   # NEW: send session id
        "user": {"id": user["id"], "name": user["name"], "email": user["email"]},
        "profile_complete": bool((db.get_profile(user["id"]) or {}).get("profile_complete")),
        "message": "Email verified! Welcome to X Education."
    }

@app.post("/api/auth/login")
def login(body: LoginRequest):
    body.email = (body.email or "").strip().lower()
    user = db.get_user_by_email(body.email)
    if not user or not auth.verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Incorrect email or password.")
    if not user["is_verified"]:
        raise HTTPException(403, "Please verify your email first. Check your inbox for the OTP.")
    profile = db.get_profile(user["id"])
    token = auth.create_token(user["id"], user["email"])
    # Start session
    session_id = db.execute(
        "INSERT INTO user_sessions (user_id, device_type) VALUES (?,?)",
        (user["id"], "Desktop")
    )
    return {
        "token": token, "session_id": session_id,
        "user": {"id": user["id"], "name": user["name"], "email": user["email"]},
        "profile_complete": bool(profile and profile.get("profile_complete")),
    }

@app.get("/api/auth/me")
def me(user=Depends(get_current_user)):
    profile = db.get_profile(user["id"])
    return {"user": db.public_user(user), "profile": profile}


@app.post("/api/auth/resend-otp")
def resend_otp(body: EmailOnly):
    email = (body.email or "").strip().lower()
    user = db.get_user_by_email(email)
    if not user or user["is_verified"]:
        return {"message": "If that account is waiting for verification, a new code has been sent."}
    age = auth.last_otp_age_seconds(email, "signup")
    if age is not None and age < OTP_RESEND_SECONDS:
        raise HTTPException(429, f"Please wait {int(OTP_RESEND_SECONDS - age)} seconds before requesting a new code.")
    otp = auth.generate_otp()
    auth.save_otp(email, otp, "signup")
    ok, msg = send_otp_email(email, otp, user["name"])
    if not ok:
        raise HTTPException(500, f"Could not send OTP: {msg}")
    return {"message": f"A new code has been sent to {email}."}


@app.post("/api/auth/forgot-password")
def forgot_password(body: EmailOnly):
    email = (body.email or "").strip().lower()
    generic = {"message": "If an account exists for that email, a reset code has been sent."}
    user = db.get_user_by_email(email)
    if not user or not user["is_verified"]:
        return generic            # don't reveal which emails are registered
    age = auth.last_otp_age_seconds(email, "reset")
    if age is not None and age < OTP_RESEND_SECONDS:
        raise HTTPException(429, f"Please wait {int(OTP_RESEND_SECONDS - age)} seconds before requesting a new code.")
    otp = auth.generate_otp()
    auth.save_otp(email, otp, "reset")
    send_otp_email(email, otp, user["name"], purpose="reset")
    return generic


@app.post("/api/auth/reset-password")
def reset_password(body: ResetPasswordRequest):
    email = (body.email or "").strip().lower()
    _check_password(body.new_password)
    if not auth.verify_otp(email, body.otp, "reset"):
        raise HTTPException(400, "Invalid or expired code.")
    db.execute("UPDATE users SET password_hash=? WHERE email=?", (auth.hash_password(body.new_password), email))
    return {"message": "Password updated. You can now log in."}


@app.post("/api/auth/change-password")
def change_password(body: ChangePasswordRequest, user=Depends(get_current_user)):
    if not auth.verify_password(body.current_password, user["password_hash"]):
        raise HTTPException(400, "Your current password is incorrect.")
    _check_password(body.new_password)
    db.execute("UPDATE users SET password_hash=? WHERE id=?", (auth.hash_password(body.new_password), user["id"]))
    return {"message": "Password changed."}


# ── PROFILE ───────────────────────────────────────────────────────────────────
@app.post("/api/profile/complete")
def complete_profile(body: ProfileRequest, user=Depends(get_current_user)):
    db.execute("""
        INSERT INTO user_profiles
        (user_id, current_occupation, specialization, age_bracket, city, country,
         phone, how_did_you_hear, profile_complete)
        VALUES (?,?,?,?,?,?,?,?,1)
        ON CONFLICT(user_id) DO UPDATE SET
          current_occupation=excluded.current_occupation,
          specialization=excluded.specialization,
          age_bracket=excluded.age_bracket,
          city=excluded.city, country=excluded.country,
          phone=COALESCE(excluded.phone, user_profiles.phone), how_did_you_hear=excluded.how_did_you_hear,
          profile_complete=1, updated_at=datetime('now','localtime')
    """, (user["id"], body.current_occupation, body.specialization, body.age_bracket,
          body.city, body.country, body.phone, body.how_did_you_hear))
    return {"message": "Profile saved! Personalised recommendations are now enabled."}

@app.put("/api/profile/preferences")
def update_preferences(body: PreferencesRequest, user=Depends(get_current_user)):
    """Communication consent: email / calls / WhatsApp, and phone number."""
    db.execute("INSERT OR IGNORE INTO user_profiles (user_id) VALUES (?)", (user["id"],))
    if body.do_not_email is not None:
        db.execute("UPDATE user_profiles SET do_not_email=? WHERE user_id=?",
                   ("Yes" if body.do_not_email else "No", user["id"]))
    if body.do_not_call is not None:
        db.execute("UPDATE user_profiles SET do_not_call=? WHERE user_id=?",
                   ("Yes" if body.do_not_call else "No", user["id"]))
    if body.whatsapp_opt_in is not None:
        db.execute("UPDATE user_profiles SET whatsapp_opt_in=? WHERE user_id=?",
                   (1 if body.whatsapp_opt_in else 0, user["id"]))
    if body.phone is not None:
        phone = body.phone.strip()
        if phone and not PHONE_RE.match(phone):
            raise HTTPException(400, "Please enter a valid phone number.")
        db.execute("UPDATE user_profiles SET phone=? WHERE user_id=?", (phone or None, user["id"]))
    return {"message": "Preferences updated.", "profile": db.get_profile(user["id"])}


# ── BEHAVIOUR TRACKING ────────────────────────────────────────────────────────
TRACKED_EVENTS = {
    "page_view", "video_play", "brochure_dl", "chat", "pricing_view",
    "testimonial_view", "webinar_view", "webinar_register", "cart_add",
    "wishlist_add", "checkout_start", "enquiry_submit",
}

@app.post("/api/track")
def track_event(body: BehaviourEvent, user=Depends(get_current_user)):
    if body.event_type not in TRACKED_EVENTS:
        raise HTTPException(400, f"Unknown event type '{body.event_type}'")
    # A session id from another user (stale localStorage) must not be counted
    sess = db.fetchone("SELECT id FROM user_sessions WHERE id=? AND user_id=?",
                       (body.session_id, user["id"]))
    session_id = sess["id"] if sess else None
    seconds = max(0, min(int(body.time_spent_sec or 0), 1800))   # cap 30 min per page
    db.execute("""
        INSERT INTO behaviour_events (user_id, session_id, course_slug, event_type, time_spent_sec)
        VALUES (?,?,?,?,?)
    """, (user["id"], session_id, body.course_slug, body.event_type, seconds))
    if session_id:
        db.execute("UPDATE user_sessions SET last_active=datetime('now','localtime') WHERE id=?",
                   (session_id,))

    # Re-score live and keep the person's lead row current. A snapshot for
    # closed-loop retraining is kept at most every 30 min.
    _, pred = rescore_latest_lead(user["id"], "activity", snapshot_gap_minutes=30)
    return {"tracked": True, "live_score": pred["lead_score"], "persona": pred["persona"],
            "tier": pred["recommended_action"]}


@app.get("/api/live-score")
def get_live_score(user=Depends(get_current_user)):
    row = db.fetchone("SELECT live_score, persona FROM live_user_state WHERE user_id=?", (user["id"],))
    if row and row["live_score"] is not None:
        return {"lead_score": row["live_score"], "persona": row["persona"]}
    pred = score_user(user["id"], source="live_score", snapshot_gap_minutes=60)
    return {"lead_score": pred["lead_score"], "persona": pred["persona"]}


@app.post("/api/session/start")
def start_session(body: dict, user=Depends(get_current_user)):
    """Called by the website at the start of every visit (new tab, or after 30 min idle)."""
    device = body.get("device_type") if body.get("device_type") in F.DEVICE_TYPES else "Desktop"
    source = body.get("lead_source") if body.get("lead_source") in F.LEAD_SOURCES else "Direct Traffic"
    sid = db.execute(
        "INSERT INTO user_sessions (user_id, device_type, lead_source) VALUES (?,?,?)",
        (user["id"], device, source)
    )
    return {"session_id": sid}


# ── COURSE CATALOGUE ──────────────────────────────────────────────────────────
@app.get("/api/courses")
def list_courses():
    return {"courses": catalog.all_courses()}

@app.get("/api/courses/{slug}")
def course_detail(slug: str):
    c = catalog.get_course(slug)
    if not c:
        raise HTTPException(404, "Course not found")
    return c


# ── RECOMMENDATIONS ───────────────────────────────────────────────────────────
@app.get("/api/recommendations")
def recommendations(user=Depends(get_current_user)):
    profile   = db.get_profile(user["id"]) or {}
    behaviour = db.get_behaviour_summary(user["id"])
    purchases = db.get_purchases(user["id"])
    wishlist  = db.get_wishlist(user["id"])
    cart      = db.get_cart(user["id"])

    purchased = [p["course_slug"] for p in purchases]
    viewed = ([behaviour["top_course_slug"]] if behaviour.get("top_course_slug") else []) \
        + [w["course_slug"] for w in wishlist]
    # collaborative signal: what else did buyers of my courses buy?
    co = {}
    if purchased:
        q = ",".join("?" * len(purchased))
        for r in db.fetchall(f"""SELECT p2.course_slug, COUNT(DISTINCT p2.user_id) AS n
                                 FROM purchases p1 JOIN purchases p2 ON p1.user_id=p2.user_id
                                 WHERE p1.course_slug IN ({q}) AND p2.course_slug NOT IN ({q})
                                   AND p1.user_id != ?
                                 GROUP BY p2.course_slug""", (*purchased, *purchased, user["id"])):
            co[r["course_slug"]] = r["n"]
    items = recommend(profile.get("current_occupation"), profile.get("specialization"), viewed,
                      purchased, co_purchase=co, cart_slugs=[c["course_slug"] for c in cart])
    return {"recommendations": [i["title"] for i in items], "items": items}


# ── CART ──────────────────────────────────────────────────────────────────────
@app.get("/api/cart")
def get_cart(user=Depends(get_current_user)):
    return {"cart": db.get_cart(user["id"])}

@app.post("/api/cart")
def add_to_cart(item: CartItem, user=Depends(get_current_user)):
    course = catalog.get_course(item.course_slug)
    if not course:
        raise HTTPException(404, "Course not found.")
    if db.fetchone("SELECT id FROM purchases WHERE user_id=? AND course_slug=?", (user["id"], item.course_slug)):
        raise HTTPException(400, "You're already enrolled in this course.")
    db.execute(
        "INSERT OR IGNORE INTO cart (user_id,course_slug,course_title,price) VALUES (?,?,?,?)",
        (user["id"], course["slug"], course["title"], course["price"])
    )
    db.execute(
        "INSERT INTO behaviour_events (user_id,course_slug,event_type) VALUES (?,?,?)",
        (user["id"], item.course_slug, "cart_add")
    )
    return {"message": f"'{course['title']}' added to cart."}

@app.delete("/api/cart/{course_slug}")
def remove_from_cart(course_slug: str, user=Depends(get_current_user)):
    db.execute("DELETE FROM cart WHERE user_id=? AND course_slug=?", (user["id"], course_slug))
    return {"message": "Removed from cart."}


# ── WISHLIST ──────────────────────────────────────────────────────────────────
@app.get("/api/wishlist")
def get_wishlist(user=Depends(get_current_user)):
    return {"wishlist": db.get_wishlist(user["id"])}

@app.post("/api/wishlist")
def add_to_wishlist(item: WishlistItem, user=Depends(get_current_user)):
    course = catalog.get_course(item.course_slug)
    if not course:
        raise HTTPException(404, "Course not found.")
    item.course_title = course["title"]
    db.execute(
        "INSERT OR IGNORE INTO wishlist (user_id,course_slug,course_title) VALUES (?,?,?)",
        (user["id"], item.course_slug, item.course_title)
    )
    db.execute(
        "INSERT INTO behaviour_events (user_id,course_slug,event_type) VALUES (?,?,?)",
        (user["id"], item.course_slug, "wishlist_add")
    )
    return {"message": f"'{item.course_title}' added to wishlist."}

@app.delete("/api/wishlist/{course_slug}")
def remove_from_wishlist(course_slug: str, user=Depends(get_current_user)):
    db.execute("DELETE FROM wishlist WHERE user_id=? AND course_slug=?", (user["id"], course_slug))
    return {"message": "Removed from wishlist."}


# ── CHECKOUT (simulated purchase) ─────────────────────────────────────────────
@app.post("/api/checkout/start")
def checkout_start(user=Depends(get_current_user)):
    cart = db.get_cart(user["id"])
    if not cart:
        return {"checkout_id": None, "cart_value": 0}     # nothing to abandon
    cart_value = sum(catalog.price_of(i["course_slug"]) or i["price"] for i in cart)
    checkout_id = db.start_checkout_session(user["id"], cart_value)
    return {"checkout_id": checkout_id, "cart_value": cart_value}


@app.post("/api/coupons/check")
def check_coupon(body: CouponCheck, user=Depends(get_current_user)):
    """Preview a coupon before paying: valid? how much off? new total?"""
    code = (body.code or "").strip().upper()
    coupon = db.validate_coupon(user["id"], code)
    if not coupon:
        raise HTTPException(400, "This code isn't valid for your account, has expired or was already used.")
    total = sum(catalog.price_of(i["course_slug"]) or i["price"] for i in db.get_cart(user["id"]))
    pct = coupon["discount_pct"]
    return {"code": code, "discount_pct": pct, "expires_at": coupon["expires_at"],
            "subtotal": total, "discount": round(total * pct / 100, 2),
            "total": round(total * (1 - pct / 100), 2)}


@app.post("/api/checkout")
def checkout(body: CheckoutRequest, user=Depends(get_current_user)):
    cart = db.get_cart(user["id"])
    if not cart:
        raise HTTPException(400, "Your cart is empty.")
    # price every item from the catalogue at the moment of purchase
    for item in cart:
        item["price"] = catalog.price_of(item["course_slug"]) or item["price"]
    body.coupon_code = (body.coupon_code or "").strip().upper()

    discount_pct = 0
    coupon_id    = None
    if body.coupon_code:
        coupon = db.validate_coupon(user["id"], body.coupon_code)
        if coupon:
            discount_pct = coupon["discount_pct"]
            coupon_id    = coupon["id"]
        else:
            raise HTTPException(400, "Invalid or expired coupon code.")

    # Credit the last touch that actually reached the user (an email or their enquiry)
    prior_lead = db.get_attribution_lead(user["id"])

    purchased  = []
    total_paid = 0.0
    for item in cart:
        original   = item["price"]
        discounted = round(original * (1 - discount_pct/100), 2)
        db.execute("""
            INSERT INTO purchases (user_id, course_slug, course_title, price_paid, coupon_used, discount_amount)
            VALUES (?,?,?,?,?,?)
        """, (user["id"], item["course_slug"], item["course_title"],
              discounted, body.coupon_code or None, round(original - discounted, 2)))
        db.execute(
            "INSERT INTO behaviour_events (user_id, course_slug, event_type) VALUES (?,?,?)",
            (user["id"], item["course_slug"], "purchase")
        )
        purchased.append(item["course_title"])
        total_paid += discounted

    # Clear cart
    db.execute("DELETE FROM cart WHERE user_id=?", (user["id"],))

    if coupon_id:
        db.mark_coupon_used(coupon_id)

    db.complete_latest_checkout_session(user["id"])

    # ── CLOSED LOOP: the purchase is the real outcome. Rescore the lead with the
    # model (so the dashboard shows it), and the score_snapshots taken before
    # this moment now get labelled "converted" for retraining (ml/retrain_from_live.py).
    _, pred = rescore_latest_lead(user["id"], "purchase_conversion")

    # ── Attributed, properly-branded purchase confirmation email ──
    channel = prior_lead["trigger_reason"] if prior_lead else None
    channel_label = ATTRIBUTION_LABELS.get(channel, ATTRIBUTION_LABELS[None])
    send_purchase_confirmation_email(
        user["email"], user["name"], purchased, channel_label, total_paid, discount_pct
    )

    return {
        "message": "Purchase successful! Great! Welcome to X Education.",
        "courses_purchased": purchased,
        "discount_applied": f"{discount_pct}%" if discount_pct else "None",
        "attributed_to": channel_label,
        "updated_lead_score": pred["lead_score"],
    }

@app.get("/api/purchases")
def get_purchases(user=Depends(get_current_user)):
    return {"purchases": db.get_purchases(user["id"])}


# ── ENQUIRY ───────────────────────────────────────────────────────────────────
@app.post("/api/enquiry")
def submit_enquiry(body: EnquiryRequest, user=Depends(get_current_user)):
    """An enquiry always gets a confirmation email; the next-best-action engine decides
    whether it includes a coupon, or whether an advisor should call."""
    course = catalog.get_course(body.course_slug)
    if not course:
        raise HTTPException(404, "Course not found.")
    if body.phone:
        if not PHONE_RE.match(body.phone.strip()):
            raise HTTPException(400, "Please enter a valid phone number.")
        db.execute("INSERT OR IGNORE INTO user_profiles (user_id) VALUES (?)", (user["id"],))
        db.execute("UPDATE user_profiles SET phone=?, whatsapp_opt_in=? WHERE user_id=?",
                   (body.phone.strip(), 1 if body.whatsapp_opt_in else 0, user["id"]))
    if body.lead_source and body.lead_source != "Direct Traffic" and body.lead_source in F.LEAD_SOURCES:
        db.execute("UPDATE user_sessions SET lead_source=? WHERE id=(SELECT MAX(id) FROM user_sessions WHERE user_id=?)",
                   (body.lead_source, user["id"]))
    db.execute("INSERT INTO behaviour_events (user_id, course_slug, event_type) VALUES (?,?,?)",
               (user["id"], body.course_slug, "enquiry_submit"))

    lead_id, prediction, decision = handle_trigger(
        user["id"], user["name"], user["email"], "enquiry", course["slug"],
        allowed=["email_info", "email_coupon_10", "email_coupon_20", "call"], always_email=True)
    return {
        "lead_id":    lead_id,
        "lead_score": prediction["lead_score"],
        "persona":    prediction["persona"],
        "action":     prediction["recommended_action"],
        "message":    "Enquiry submitted! Check your email for next steps.",
    }


# ── REVIEWS ───────────────────────────────────────────────────────────────────
@app.get("/api/reviews/{course_slug}")
def get_reviews(course_slug: str):
    return {"reviews": db.get_reviews(course_slug)}

@app.post("/api/reviews")
def add_review(body: ReviewRequest, user=Depends(get_current_user)):
    if not 1 <= body.rating <= 5:
        raise HTTPException(400, "Rating must be between 1 and 5.")
    if not db.fetchone("SELECT id FROM purchases WHERE user_id=? AND course_slug=?",
                       (user["id"], body.course_slug)):
        raise HTTPException(403, "Only learners enrolled in this course can review it.")
    db.execute("""
        INSERT INTO reviews (user_id, course_slug, rating, review_text)
        VALUES (?,?,?,?)
        ON CONFLICT(user_id, course_slug) DO UPDATE SET
          rating=excluded.rating, review_text=excluded.review_text
    """, (user["id"], body.course_slug, body.rating, body.review_text))
    db.execute(
        "INSERT INTO behaviour_events (user_id, course_slug, event_type) VALUES (?,?,?)",
        (user["id"], body.course_slug, "review_submit")
    )
    return {"message": "Review submitted. Thank you!"}


# ── Q&A ───────────────────────────────────────────────────────────────────────
@app.get("/api/qna/{course_slug}")
def get_qna(course_slug: str):
    return {"questions": db.get_qna(course_slug)}

@app.post("/api/qna")
def ask_question(body: QnARequest, user=Depends(get_current_user)):
    if len((body.question or "").strip()) < 5:
        raise HTTPException(400, "Please write a question (at least 5 characters).")
    db.execute(
        "INSERT INTO qna (user_id, course_slug, question) VALUES (?,?,?)",
        (user["id"], body.course_slug, body.question)
    )
    return {"message": "Question submitted. Our team will answer shortly."}


# ── USER DASHBOARD DATA ───────────────────────────────────────────────────────
@app.get("/api/dashboard")
def user_dashboard(user=Depends(get_current_user)):
    profile   = db.get_profile(user["id"])
    cart      = db.get_cart(user["id"])
    wishlist  = db.get_wishlist(user["id"])
    purchases = db.get_purchases(user["id"])
    coupons   = db.fetchall(
        "SELECT * FROM coupons_issued WHERE user_id=? AND used=0", (user["id"],)
    )
    lead      = db.get_user_lead(user["id"])
    return {
        "user":      db.public_user(user),
        "profile":   profile,
        "cart":      cart,
        "wishlist":  wishlist,
        "purchases": purchases,
        "coupons":   coupons,
        "lead_score": lead["lead_score"] if lead else None,
        "persona":    lead["persona"]    if lead else None,
        "next_steps": next_steps_for(user["id"], profile, cart, purchases),
    }


def next_steps_for(user_id, profile, cart, purchases):
    """Helpful next actions for the learner (replaced by model-ranked tips in recourse.py)."""
    try:
        import recourse
        return recourse.learner_steps(user_id)
    except ImportError:
        pass
    steps = []
    if not (profile or {}).get("profile_complete"):
        steps.append({"label": "Complete your profile", "to": "/settings",
                      "why": "Get course suggestions that fit your background."})
    if cart:
        steps.append({"label": "Finish your enrolment", "to": "/checkout",
                      "why": f"{cart[0]['course_title']} is waiting in your cart."})
    b = db.get_behaviour_summary(user_id)
    slug = b.get("top_course_slug")
    if slug and catalog.get_course(slug):
        title = catalog.title_of(slug)
        if not b["video_watched"]:
            steps.append({"label": f"Watch the {title} overview", "to": f"/courses/{slug}",
                          "why": "A 35-second summary of the programme."})
        if not b["brochure_downloaded"]:
            steps.append({"label": f"Get the {title} brochure", "to": f"/courses/{slug}/brochure",
                          "why": "Curriculum, fees and instructor on one page."})
    elif not purchases:
        steps.append({"label": "Explore our courses", "to": "/courses", "why": "24 programmes across 8 areas."})
    if not b["webinar_attended"]:
        steps.append({"label": "Join Saturday's free live session", "to": "/#webinar",
                      "why": "Ask instructors anything, no obligation."})
    return steps[:4]

@app.get("/api/coupons")
def get_coupons(user=Depends(get_current_user)):
    return {"coupons": db.fetchall(
        "SELECT * FROM coupons_issued WHERE user_id=? ORDER BY created_at DESC", (user["id"],)
    )}


# ── CHAT ASSISTANT + CALLBACKS ────────────────────────────────────────────────
@app.post("/api/chat")
def chat(body: ChatRequest, authorization: str = Header(None)):
    user = optional_user(authorization)
    text = (body.message or "").strip()[:1000]
    if not text:
        raise HTTPException(400, "Empty message.")
    conv = body.conversation_id or uuid.uuid4().hex
    profile = db.get_profile(user["id"]) if user else None
    purchased = [p["course_slug"] for p in db.get_purchases(user["id"])] if user else []
    res = assistant.answer(text, page_slug=body.course_slug, profile=profile, user=user,
                           purchased_slugs=purchased)
    uid = user["id"] if user else None
    db.execute("INSERT INTO chat_messages (user_id, conversation, role, text, intent, course_slug) VALUES (?,?,?,?,?,?)",
               (uid, conv, "user", text, res["intent"], res["course_slug"]))
    db.execute("INSERT INTO chat_messages (user_id, conversation, role, text, intent, course_slug) VALUES (?,?,?,?,?,?)",
               (uid, conv, "assistant", res["reply"], res["intent"], res["course_slug"]))
    return {"conversation_id": conv, **res}


@app.post("/api/callback")
def request_callback(body: CallbackRequest, user=Depends(get_current_user)):
    phone = (body.phone or "").strip()
    if not PHONE_RE.match(phone):
        raise HTTPException(400, "Please enter a valid phone number.")
    slug = body.course_slug if catalog.get_course(body.course_slug) else None
    db.execute("INSERT OR IGNORE INTO user_profiles (user_id) VALUES (?)", (user["id"],))
    db.execute("UPDATE user_profiles SET phone=COALESCE(phone, ?), do_not_call='No' WHERE user_id=?",
               (phone, user["id"]))
    cb_id = db.execute("""INSERT INTO callback_requests (user_id, phone, course_slug, preferred_time, note)
                          VALUES (?,?,?,?,?)""",
                       (user["id"], phone, slug, (body.preferred_time or "")[:60], (body.note or "")[:300]))
    # asking for a call is a strong, explicit signal — record it as an enquiry-type lead
    db.execute("INSERT INTO behaviour_events (user_id, course_slug, event_type) VALUES (?,?,?)",
               (user["id"], slug, "enquiry_submit"))
    pred = score_user(user["id"], source="chat_callback", course=slug, explain=True)
    profile = db.get_profile(user["id"]) or {}
    content = generate_content(user["name"], profile.get("current_occupation"), profile.get("specialization"),
                               catalog.title_of(slug, "our programmes"), pred["recommended_action"],
                               trigger="chat_callback", lead_score=pred["lead_score"], course_slug=slug,
                               offer_pct=0)
    save_lead(user["id"], pred, content, "chat_callback", course_slug=slug)
    return {"callback_id": cb_id, "message": "Thanks! An advisor will call you soon."}


@app.get("/api/me/insights")
def my_insights(user=Depends(get_current_user)):
    """What the AI currently thinks about this visitor (shown on the dashboard in demo mode)."""
    pred = score_user(user["id"], source="insights", explain=True, snapshot_gap_minutes=60)
    import recourse
    return {"lead_score": pred["lead_score"], "persona": pred["persona"],
            "tier": pred["recommended_action"], "probability": pred["conversion_probability"],
            "factors": pred.get("factors", []), "model_version": pred["model_version"],
            "tips": recourse.tips_for(pred["features"], pred["lead_score"])}


# ── MODEL / INTERNAL ──────────────────────────────────────────────────────────
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "xedu-internal-dev")

@app.get("/api/model/info")
def get_model_info():
    """Which model is live, when it was trained and how well it scored."""
    return model_info()

@app.post("/api/internal/rescore/{user_id}")
def internal_rescore(user_id: int, reason: str = "email_click",
                     x_internal_key: str = Header(None)):
    """Called by the marketing backend (e.g. after an email click) to re-run the model."""
    if x_internal_key != INTERNAL_API_KEY:
        raise HTTPException(403, "Forbidden")
    if not db.get_user_by_id(user_id):
        raise HTTPException(404, "User not found")
    lead, pred = rescore_latest_lead(user_id, reason)
    return {"user_id": user_id, "lead_id": lead["id"] if lead else None,
            "lead_score": pred["lead_score"], "tier": pred["recommended_action"]}


# ── RUN AUTOMATIONS NOW (demo) ────────────────────────────────────────────────
@app.post("/api/debug/trigger-jobs")
def trigger_jobs_manually(x_internal_key: str = Header(None)):
    """
    Runs every automation job now (checkout, cart, wishlist, inactivity) instead of
    waiting for the 5-minute timer, and lists the next-best-action decisions made.
    Open while DEMO_MODE=true; otherwise it needs the internal key (the marketing
    dashboard's "Run automations now" button sends it).
    """
    import scheduler
    if not scheduler.DEMO_MODE and x_internal_key != INTERNAL_API_KEY:
        raise HTTPException(403, "Only available in DEMO_MODE or with the internal key.")
    last = db.fetchone("SELECT COALESCE(MAX(id), 0) AS m FROM nba_decisions")["m"]
    scheduler.run_all_jobs()
    made = db.fetchall("""SELECT d.trigger_reason, d.action, d.policy, u.name
                          FROM nba_decisions d JOIN users u ON u.id = d.user_id
                          WHERE d.id > ? ORDER BY d.id""", (last,))
    return {"message": f"Automations ran: {len(made)} new decision(s).", "decisions": made}
