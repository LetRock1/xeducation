"""
main.py — X Education User Backend (port 8000)
All API routes for the user-facing website.
"""
import os
import sqlite3
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
from genai_mock      import generate_content
from email_service   import send_otp_email, send_purchase_confirmation_email, ATTRIBUTION_LABELS
from recommendations import get_recommendations
from scheduler       import start_scheduler, _send_tracked_email

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
    course_slug: str; course_title: str; price: float

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


# ── HEALTH ────────────────────────────────────────────────────────────────────
@app.get("/api/health")
def health(): return {"status": "ok", "service": "user-backend"}


# ── AUTH ROUTES ───────────────────────────────────────────────────────────────
@app.post("/api/auth/signup")
def signup(body: SignupRequest):
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
    if not auth.verify_otp(body.email, body.otp):
        raise HTTPException(400, "Invalid or expired OTP. Please try again.")
    user = db.get_user_by_email(body.email)
    if not user:
        raise HTTPException(404, "User not found")
    db.execute("UPDATE users SET is_verified=1 WHERE email=?", (body.email,))

    # Create empty profile
    db.execute("INSERT OR IGNORE INTO user_profiles (user_id) VALUES (?)", (user["id"],))

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
        "profile_complete": False,
        "message": "Email verified! Welcome to X Education."
    }

@app.post("/api/auth/login")
def login(body: LoginRequest):
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
    return {"user": user, "profile": profile}


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
          phone=excluded.phone, how_did_you_hear=excluded.how_did_you_hear,
          profile_complete=1, updated_at=datetime('now','localtime')
    """, (user["id"], body.current_occupation, body.specialization, body.age_bracket,
          body.city, body.country, body.phone, body.how_did_you_hear))
    return {"message": "Profile saved! Personalised recommendations are now enabled."}

@app.put("/api/profile/preferences")
def update_preferences(body: dict, user=Depends(get_current_user)):
    allowed = ["do_not_email","do_not_call","whatsapp_opt_in","phone"]
    for k, v in body.items():
        if k in allowed:
            db.execute(f"UPDATE user_profiles SET {k}=? WHERE user_id=?", (v, user["id"]))
    return {"message": "Preferences updated."}


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

    # Re-score live. A snapshot for closed-loop retraining is kept at most every 30 min.
    pred = score_user(user["id"], source="activity", snapshot_gap_minutes=30)
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


# ── RECOMMENDATIONS ───────────────────────────────────────────────────────────
@app.get("/api/recommendations")
def recommendations(user=Depends(get_current_user)):
    profile   = db.get_profile(user["id"]) or {}
    behaviour = db.get_behaviour_summary(user["id"])
    purchases = db.get_purchases(user["id"])
    wishlist  = db.get_wishlist(user["id"])

    purchased_slugs = [p["course_slug"] for p in purchases]
    viewed_slugs    = []
    if behaviour.get("top_course_slug"):
        viewed_slugs.append(behaviour["top_course_slug"])
    # Add wishlist to viewed
    viewed_slugs += [w["course_slug"] for w in wishlist]

    recs = get_recommendations(
        occupation     = profile.get("current_occupation",""),
        specialization = profile.get("specialization",""),
        viewed_slugs   = viewed_slugs,
        purchased_slugs= purchased_slugs,
    )
    return {"recommendations": recs}


# ── CART ──────────────────────────────────────────────────────────────────────
@app.get("/api/cart")
def get_cart(user=Depends(get_current_user)):
    return {"cart": db.get_cart(user["id"])}

@app.post("/api/cart")
def add_to_cart(item: CartItem, user=Depends(get_current_user)):
    db.execute(
        "INSERT OR IGNORE INTO cart (user_id,course_slug,course_title,price) VALUES (?,?,?,?)",
        (user["id"], item.course_slug, item.course_title, item.price)
    )
    db.execute(
        "INSERT INTO behaviour_events (user_id,course_slug,event_type) VALUES (?,?,?)",
        (user["id"], item.course_slug, "cart_add")
    )
    return {"message": f"'{item.course_title}' added to cart."}

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
    cart_value = sum(item["price"] for item in cart)
    checkout_id = db.start_checkout_session(user["id"], cart_value)
    return {"checkout_id": checkout_id, "cart_value": cart_value}


@app.post("/api/checkout")
def checkout(body: CheckoutRequest, user=Depends(get_current_user)):
    cart = db.get_cart(user["id"])
    if not cart:
        raise HTTPException(400, "Your cart is empty.")

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
    profile   = db.get_profile(user["id"]) or {}
    purchases = db.get_purchases(user["id"])

    if body.phone:
        db.execute(
            "UPDATE user_profiles SET phone=?, whatsapp_opt_in=? WHERE user_id=?",
            (body.phone, body.whatsapp_opt_in, user["id"])
        )
    db.execute("INSERT INTO behaviour_events (user_id, course_slug, event_type) VALUES (?,?,?)",
               (user["id"], body.course_slug, "enquiry_submit"))

    source = body.lead_source if body.lead_source and body.lead_source != "Direct Traffic" else None
    prediction = score_user(user["id"], source="enquiry", course=body.course_slug, explain=True,
                            lead_source=source, whatsapp_opt_in=body.whatsapp_opt_in or None)

    content = generate_content(
        name           = user["name"],
        occupation     = profile.get("current_occupation") or "Professional",
        specialization = profile.get("specialization") or "your field",
        course         = body.course_type,
        action         = prediction["recommended_action"],
        trigger        = "enquiry",
        past_purchases = len(purchases),
    )
    lead_id = save_lead(user["id"], prediction, content, "enquiry", course_label=body.course_type)

    if profile.get("do_not_email") != "Yes":
        _send_tracked_email(user["id"], lead_id, user["email"], content["email_subject"], content["email_body"])
        db.execute("UPDATE leads SET email_sent=1, email_sent_at=datetime('now','localtime') WHERE id=?", (lead_id,))

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
        "user":      user,
        "profile":   profile,
        "cart":      cart,
        "wishlist":  wishlist,
        "purchases": purchases,
        "coupons":   coupons,
        "lead_score": lead["lead_score"] if lead else None,
        "persona":    lead["persona"]    if lead else None,
    }

@app.get("/api/coupons")
def get_coupons(user=Depends(get_current_user)):
    return {"coupons": db.fetchall(
        "SELECT * FROM coupons_issued WHERE user_id=? ORDER BY created_at DESC", (user["id"],)
    )}


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


# ── DEBUG / DEMO ENDPOINT ─────────────────────────────────────────────────────
# For demo only: manually trigger background jobs without waiting 15 min/1 hr.
# Remove this in production.
@app.post("/api/debug/trigger-jobs")
def trigger_jobs_manually():
    """
    Manually runs cart_abandonment_job + session_end_job + checkout_abandonment_job.
    Use this during your demo instead of waiting 15 minutes.
    Open Postman / curl:
      POST http://localhost:8000/api/debug/trigger-jobs
    """
    from scheduler import run_all_jobs
    run_all_jobs()
    return {"message": "All jobs triggered manually. Check marketing dashboard."}