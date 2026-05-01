"""
main.py — X Education User Backend (port 8000)
All API routes for the user-facing website.
"""
import os
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv

import database as db
import auth
from predict         import predict_lead
from genai_mock      import generate_content
from email_service   import send_otp_email, send_marketing_email
from recommendations import get_recommendations
from scheduler       import start_scheduler

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
    if db.get_user_by_email(body.email):
        raise HTTPException(400, "Email already registered. Please login.")
    otp = auth.generate_otp()
    # Store user as unverified
    user_id = db.execute(
        "INSERT INTO users (name, email, password_hash, is_verified) VALUES (?,?,?,0)",
        (body.name, body.email, auth.hash_password(body.password))
    )
    auth.save_otp(body.email, otp)
    ok, msg = send_otp_email(body.email, otp, body.name)
    if not ok:
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
    token = auth.create_token(user["id"], user["email"])
    return {"token": token, "user": {"id": user["id"], "name": user["name"], "email": user["email"]},
            "profile_complete": False, "message": "Email verified! Welcome to X Education."}

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
@app.post("/api/track")
def track_event(body: BehaviourEvent, user=Depends(get_current_user)):
    db.execute("""
        INSERT INTO behaviour_events
        (user_id, session_id, course_slug, event_type, time_spent_sec)
        VALUES (?,?,?,?,?)
    """, (user["id"], body.session_id, body.course_slug, body.event_type, body.time_spent_sec))

    db.execute(
        "UPDATE user_sessions SET last_active=datetime('now','localtime') WHERE id=?",
        (body.session_id,)
    )

    profile   = db.get_profile(user["id"]) or {}
    behaviour = db.get_behaviour_summary(user["id"])

    raw = {
        "LeadOrigin":"Website Interaction",
        "LeadSource":"Direct Traffic",
        "DeviceType":"Desktop",
        "TotalVisits": behaviour["total_visits"],
        "TotalTimeOnWebsite": behaviour["total_time_on_website"],
        "PageViewsPerVisit": behaviour["page_views_per_visit"],
        "SessionsCount": behaviour["sessions_count"],
        "VideoWatched": behaviour["video_watched"],
        "BrochureDownloaded": behaviour["brochure_downloaded"],
        "ChatInitiated": behaviour["chat_initiated"],
        "PricingPageVisited": behaviour["pricing_page_visited"],
        "TestimonialVisited": behaviour["testimonial_visited"],
        "WebinarAttended": behaviour["webinar_attended"],
        "EmailOpenedCount":0,
        "CurrentOccupation":profile.get("current_occupation","Unemployed"),
        "Specialization":profile.get("specialization","Business"),
        "CourseType":"Browsing",
        "City":profile.get("city","Unknown"),
        "Country":profile.get("country","India"),
        "AgeBracket":profile.get("age_bracket"),
        "HowDidYouHear":profile.get("how_did_you_hear","Unknown"),
        "DoNotEmail":profile.get("do_not_email","No"),
        "DoNotCall":profile.get("do_not_call","No"),
        "WhatsAppOptIn":profile.get("whatsapp_opt_in",0),
        "wishlist_count": len(db.get_wishlist(user["id"])),
        "past_purchases": len(db.get_purchases(user["id"])),
    }

    from predict import create_or_update_lead_snapshot
    create_or_update_lead_snapshot(user["id"], raw)

    return {"tracked": True}

@app.post("/api/session/start")
def start_session(body: dict, user=Depends(get_current_user)):
    sid = db.execute(
        "INSERT INTO user_sessions (user_id, device_type, lead_source) VALUES (?,?,?)",
        (user["id"], body.get("device_type","Desktop"), body.get("lead_source","Direct Traffic"))
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

    purchased = []
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

    # Clear cart
    db.execute("DELETE FROM cart WHERE user_id=?", (user["id"],))

    if coupon_id:
        db.mark_coupon_used(coupon_id)

    return {
        "message": "Purchase successful! Great! Welcome to X Education.",
        "courses_purchased": purchased,
        "discount_applied": f"{discount_pct}%" if discount_pct else "None",
    }

@app.get("/api/purchases")
def get_purchases(user=Depends(get_current_user)):
    return {"purchases": db.get_purchases(user["id"])}


# ── ENQUIRY ───────────────────────────────────────────────────────────────────
@app.post("/api/enquiry")
def submit_enquiry(body: EnquiryRequest, user=Depends(get_current_user)):
    profile   = db.get_profile(user["id"]) or {}
    behaviour = db.get_behaviour_summary(user["id"])
    purchases = db.get_purchases(user["id"])

    # Update phone + whatsapp if provided
    if body.phone:
        db.execute(
            "UPDATE user_profiles SET phone=?, whatsapp_opt_in=? WHERE user_id=?",
            (body.phone, body.whatsapp_opt_in, user["id"])
        )

    raw = {
        "LeadOrigin":         "Landing Page Submission",
        "LeadSource":          body.lead_source or "Direct Traffic",
        "DeviceType":          "Desktop",
        "TotalVisits":         behaviour["total_visits"],
        "TotalTimeOnWebsite":  behaviour["total_time_on_website"],
        "PageViewsPerVisit":   behaviour["page_views_per_visit"],
        "SessionsCount":       behaviour["sessions_count"],
        "VideoWatched":        behaviour["video_watched"],
        "BrochureDownloaded":  behaviour["brochure_downloaded"],
        "ChatInitiated":       behaviour["chat_initiated"],
        "PricingPageVisited":  behaviour["pricing_page_visited"],
        "TestimonialVisited":  behaviour["testimonial_visited"],
        "WebinarAttended":     behaviour["webinar_attended"],
        "EmailOpenedCount":    0,
        "CurrentOccupation":   profile.get("current_occupation","Unemployed"),
        "Specialization":      profile.get("specialization","Business Administration"),
        "CourseType":          body.course_type,
        "City":                profile.get("city","Unknown"),
        "Country":             profile.get("country","India"),
        "AgeBracket":          profile.get("age_bracket"),
        "HowDidYouHear":       profile.get("how_did_you_hear","Unknown"),
        "DoNotEmail":          profile.get("do_not_email","No"),
        "DoNotCall":           profile.get("do_not_call","No"),
        "WhatsAppOptIn":       body.whatsapp_opt_in or profile.get("whatsapp_opt_in",0),
        "enquiry_submitted":   True,
        "cart_abandoned":      False,
        "wishlist_count":      len(db.get_wishlist(user["id"])),
        "past_purchases":      len(purchases),
    }

    prediction = predict_lead(raw)
    content    = generate_content(
        name           = user["name"],
        occupation     = profile.get("current_occupation","Professional"),
        specialization = profile.get("specialization","your field"),
        course         = body.course_type,
        action         = prediction["recommended_action"],
        trigger        = "enquiry",
        past_purchases = len(purchases),
    )

    lead_id = db.execute("""
        INSERT INTO leads (
            user_id, lead_origin, lead_source, device_type,
            total_visits, total_time_on_website, page_views_per_visit,
            sessions_count, video_watched, brochure_downloaded, chat_initiated,
            pricing_page_visited, testimonial_visited, webinar_attended, email_opened_count,
            course_type, lead_score, conversion_probability, persona,
            customer_segment, recommended_action,
            email_subject, email_body, whatsapp_message, coupon_code, call_script,
            trigger_reason
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        user["id"], raw["LeadOrigin"], raw["LeadSource"], raw["DeviceType"],
        raw["TotalVisits"], raw["TotalTimeOnWebsite"], raw["PageViewsPerVisit"],
        raw["SessionsCount"], raw["VideoWatched"], raw["BrochureDownloaded"],
        raw["ChatInitiated"], raw["PricingPageVisited"], raw["TestimonialVisited"],
        raw["WebinarAttended"], raw["EmailOpenedCount"], body.course_type,
        prediction["lead_score"], prediction["conversion_probability"],
        prediction["persona"], prediction["customer_segment"], prediction["recommended_action"],
        content["email_subject"], content["email_body"], content["whatsapp_message"],
        content["coupon_code"], content["call_script"], "enquiry"
    ))

    # Issue coupon if applicable
    if content["coupon_code"]:
        _DISCOUNTS = {"VIP_URGENT_25": 25, "FUTURE_READY_15": 15, "EARLY_BIRD_10": 10, "LOYAL_20": 20}
        discount = _DISCOUNTS.get(content["coupon_code"], 0)
        if discount > 0:
            db.execute("""
                INSERT OR IGNORE INTO coupons_issued
                (user_id, coupon_code, discount_pct, tier, expires_at)
                VALUES (?,?,?,?,datetime('now','localtime','+72 hours'))
            """, (user["id"], content["coupon_code"], discount, prediction["recommended_action"]))

    # Send confirmation email
    if profile.get("do_not_email") != "Yes":
        send_marketing_email(user["email"], content["email_subject"], content["email_body"])
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


# ── DEBUG / DEMO ENDPOINT ─────────────────────────────────────────────────────
# For demo only: manually trigger background jobs without waiting 15 min/1 hr.
# Remove this in production.
@app.post("/api/debug/trigger-jobs")
def trigger_jobs_manually():
    """
    Manually runs cart_abandonment_job + session_end_job.
    Use this during your demo instead of waiting 15 minutes.
    Open Postman / curl:
      POST http://localhost:8000/api/debug/trigger-jobs
    """
    from scheduler import cart_abandonment_job, session_end_job
    cart_abandonment_job()
    session_end_job()
    return {"message": "Both jobs triggered manually. Check marketing dashboard."}