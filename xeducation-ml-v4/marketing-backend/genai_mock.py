"""
genai_mock.py — Behaviour-aware, tier-specific, course-aware content generator.
Produces personalised email + WhatsApp content based on:
  - User's ML tier (Low Priority / Nurture / Campaign / Target)
  - Specific course they were viewing / added to cart / wishlisted
  - Their occupation + specialization
  - Trigger reason (session_end / cart_abandon / wishlist_viewed / enquiry)

generate_content() calls Gemini automatically when GEMINI_API_KEY is set in
.env (see generate_content_ai() below) and falls back to the deterministic
templates in this file — as mock content, or as a safety net if the Gemini
call fails for any reason (missing key, network error, bad JSON, etc.) so a
demo never breaks on a flaky API call.
"""
import os
from datetime import datetime

YEAR = datetime.now().year

# Plain-English phrase for why we're contacting this lead now, used both as
# extra context fed into the Gemini prompt and as the fallback used
# throughout this file's own mock templates.
TRIGGER_CONTEXT = {
    "cart_abandon":        "they added a course to their cart but did not complete checkout",
    "checkout_abandon":    "they reached checkout and stopped one step short of paying",
    "wishlist_viewed":     "they added a course to their wishlist",
    "wishlist":            "they added a course to their wishlist",
    "session_end":         "they browsed the site and went inactive",
    "enquiry":             "they submitted an enquiry form asking for more information",
    "email_open":          "they opened a previous marketing email",
    "email_click":         "they clicked through a previous marketing email",
    "decay":               "they were engaged before but have gone quiet recently",
    "manual_edit":         "a marketing team member is drafting this email manually",
}


# ── Tier 0: Low Priority — Industry insights, no selling ────────────────────
def _low_priority(name, occupation, specialization, course, trigger):
    first = (name or "there").split()[0]
    month = datetime.now().strftime("%B %Y")
    return {
        "email_subject": f"[{month}] What's happening in {course} right now — for {occupation}s",
        "email_body": f"""Hi {first},

We noticed you recently explored our {course} programme. We thought you'd appreciate staying informed about what's happening in this space — no strings attached.

📊 Industry Snapshot — {course} in {YEAR}:

• Demand for {course} skills among {occupation}s is up 58% year-on-year
• The average salary premium for certified {course} professionals is now 38% above peers
• Companies in {specialization} are actively hiring for {course}-related roles in Q3 {YEAR}

🧠 Why this matters for you:
As someone with a background in {specialization}, {course} gives you a direct edge in your current role — it's not about switching careers, it's about leading in the one you already have.

📚 3 things worth reading this month:
1. How {occupation}s are using {course} to automate the boring parts of their work
2. The {course} skills gap in {specialization} — and who's filling it
3. A {occupation}'s honest review: 6 months after completing {course}

No pressure. No deadlines. Just staying sharp.

See you around,
The X Education Team

P.S. When you're ready, our {course} programme is here. Not before.
""",
        "whatsapp_message": f"Hey {first} 👋 We saw you checking out {course}. Here's a quick insight for {occupation}s in {specialization}: demand for these skills is up 58% this year. No pressure — just keeping you informed. Reply INFO for the full monthly digest!",
        "coupon_code": "",
        "call_script": "",
    }


# ── Tier 1: Nurture — Insights + coupon + soft CTA ──────────────────────────
def _nurture(name, occupation, specialization, course, trigger):
    first = (name or "there").split()[0]
    coupon = "FUTURE_READY_15"
    extra = ""
    if trigger == "cart_abandon":
        extra = f"\n\n🛒 We noticed you had {course} in your cart. Life gets busy — we get it. Your spot is still available."
    elif trigger == "checkout_abandon":
        extra = f"\n\n💳 You made it all the way to checkout for {course} and stopped just short. Whatever came up, your seat is still being held."
    elif trigger in ("wishlist_viewed", "wishlist"):
        extra = f"\n\n❤️ You added {course} to your wishlist. Here's something to make the decision easier."
    return {
        "email_subject": f"{first}, your {course} Success Blueprint is ready — + 15% off inside",
        "email_body": f"""Hi {first},

Being a {occupation} in {specialization} is a strong foundation. Becoming a {course} Specialist is how you get the seat at the table.{extra}

🗺 Your personalised {course} Success Blueprint:

Week 1–4:    Foundation — close the knowledge gap between where you are and where the market is going
Week 5–12:   Applied Projects — real problems, real solutions, your portfolio grows
Week 13–20:  Advanced Track — the 20% of skills that account for 80% of career value
Week 21–24:  Capstone + Placement Prep — industry presentation, mock interviews, offer letters

💼 What {occupation}s in {specialization} typically achieve in 6 months:
✅ 35–45% salary increase in first role change
✅ Promoted internally in 3 of 4 cases
✅ The ability to lead cross-functional projects in {course}

🎁 Because you've been exploring seriously:
Use coupon **{coupon}** at checkout for 15% off.
Valid for the next 72 hours.

Ready when you are,
Kavita Shah
Career Advisor — X Education
""",
        "whatsapp_message": f"Hey {first} 📘 Your {course} Success Blueprint is ready! As a {occupation} in {specialization}, you're closer than you think. Use code {coupon} for 15% off — valid 72 hrs. Reply BLUEPRINT to get started! 🚀",
        "coupon_code": coupon,
        "call_script": "",
    }


# ── Tier 2: Marketing Campaign — FOMO + webinar + urgency ───────────────────
def _marketing_campaign(name, occupation, specialization, course, trigger):
    first = (name or "there").split()[0]
    coupon = "EARLY_BIRD_10"
    extra = ""
    if trigger == "cart_abandon":
        extra = f"\n\n⏳ Your {course} cart is waiting. 400+ professionals enrolled this month alone. Don't let this cohort fill up."
    return {
        "email_subject": f"How {occupation}s are dominating {course} in {YEAR} — are you keeping up?",
        "email_body": f"""Hi {first},

The {course} landscape is shifting faster than most {occupation}s realise.{extra}

📈 What the data says about {specialization} professionals in {YEAR}:
• 400+ professionals in your field enrolled in X Education's {course} programme this quarter
• Companies shortlisting {course}-certified candidates are offering 22% higher starting packages
• The window to get ahead is now — not next year, not next quarter

🎙 Join our next FREE live webinar:
"{course} for {occupation}s — The Competitive Edge in {YEAR}"
Live Q&A · Industry guest speakers · Zero sales pitch

📅 This Saturday, 11 AM IST — only 47 seats left

Register free → Reply WEBINAR to this email

When you're ready to go all-in, use **{coupon}** for 10% off.

See you on the inside,
Rohit Desai
Community Manager — X Education
""",
        "whatsapp_message": f"The {course} space is moving fast in {YEAR}, {first}. As a {occupation} in {specialization}, you're already closer to leading this shift than most. Join our free webinar this Saturday, 11 AM. Reply WEBINAR for the link. 10% off with code {coupon} 🚀",
        "coupon_code": coupon,
        "call_script": "",
    }


# ── Tier 3: Target Immediately — Executive pass, 25% scholarship ────────────
def _target_immediately(name, occupation, specialization, course, trigger):
    first = (name or "there").split()[0]
    coupon = "VIP_URGENT_25"
    checkout_note = ""
    if trigger == "checkout_abandon":
        checkout_note = f"\n⚠️ You were one click from completing your {course} checkout. This is the very last chance to lock in your seat at this rate.\n"
    return {
        "email_subject": f"🎯 {first} — Priority Match for {course} · 25% Scholarship · 6 Hours Only",
        "email_body": f"""Hi {first},
{checkout_note}
Our AI system just flagged your profile as a Priority Match for our upcoming {course} cohort.

Given your background as a {occupation} in {specialization}, here's what the data shows:

💰 Professionals with your profile who complete {course} see:
   → Average ₹8–12 LPA salary increase within 6 months
   → 3 out of 4 receive internal promotions within 1 year
   → Direct applicability to your current role from Week 1

🎓 The Board has authorised a one-time Fast-Track Scholarship of 25%
   Exclusively for profiles like yours — this expires in 6 HOURS.

What you get:
✅ 6-month industry-validated {course} programme
✅ Live mentorship from senior {specialization} professionals
✅ Guaranteed placement assistance
✅ VIP alumni network — the only network that matters in {specialization}

Use coupon **{coupon}** at checkout to activate your 25% scholarship.

This isn't just a course. It's the career move your profile has been pointing toward.

Priya Menon
Senior Admissions Advisor — X Education
📞 +91 98765 43210 (Direct line)
""",
        "whatsapp_message": f"Hi {first} 👋 Our system flagged you as a Priority Match for {course}. As a {occupation} in {specialization}, you qualify for a 25% Fast-Track Scholarship — expires in 6 HOURS. Use code {coupon} at checkout. Reply YES and I'll send the VIP link now.",
        "coupon_code": coupon,
        "call_script": (
            f"Hi {first}, I'm calling because our system just flagged your profile as a Priority Match "
            f"for our {course} cohort. Given your background as a {occupation} in {specialization}, "
            f"the Board has authorised a one-time Fast-Track Scholarship of 25%. "
            f"This course will directly impact your day-to-day work in {specialization} from Week 1. "
            f"I'm sending you the VIP enrollment link right now — it expires in 6 hours. "
            f"Ready to lock this in today, {first}?"
        ),
    }


# ── Public API ────────────────────────────────────────────────────────────────

def generate_content(
    name: str,
    occupation: str,
    specialization: str,
    course: str,
    action: str,
    trigger: str = "session_end",   # session_end / cart_abandon / wishlist_viewed / enquiry
    past_purchases: int = 0,
    lead_score: float = 0,
) -> dict:
    """
    Generate personalised marketing content for a lead.
    trigger gives GenAI context about WHY we're contacting this user now.
    Tries Gemini first (if GEMINI_API_KEY is configured), falls back to the
    deterministic templates below on any failure.
    """
    name         = name or "Valued Learner"
    occupation   = occupation or "Professional"
    specialization = specialization or "your field"
    course       = course or "our programme"

    if os.getenv("GEMINI_API_KEY"):
        try:
            return generate_content_ai(
                name, occupation, specialization, course, action, trigger,
                lead_score, past_purchases,
            )
        except Exception as e:
            print(f"[GEMINI] Falling back to mock content — {e}")

    # Returning customer gets a softer, more personal tone
    if past_purchases > 0 and action != "Target Immediately":
        subject = f"Welcome back, {name.split()[0]} 👋 — Your next step in {course}"
        body = f"""Hi {name.split()[0]},

You've already taken one great step with X Education. We thought you might be interested in expanding your expertise with {course}.

As a returning learner, you have priority access to our next cohort and a special returning-learner discount is on its way to your email.

Your learning history shows you're serious about growth. {course} is the next logical step.

See you inside,
The X Education Team
"""
        return {
            "email_subject": subject, "email_body": body,
            "whatsapp_message": f"Hey {name.split()[0]} 👋 Great to see you back! We think {course} is your next step. Priority access + a special discount is yours. Reply BACK to know more!",
            "coupon_code": "LOYAL_20", "call_script": "",
        }

    if action == "Target Immediately":
        content = _target_immediately(name, occupation, specialization, course, trigger)
    elif action == "Nurture via Email/WhatsApp":
        content = _nurture(name, occupation, specialization, course, trigger)
    elif action == "Marketing Campaign":
        content = _marketing_campaign(name, occupation, specialization, course, trigger)
    else:
        content = _low_priority(name, occupation, specialization, course, trigger)

    # Checkout abandonment is the strongest possible purchase-intent signal —
    # always give the deepest available discount to recover the sale.
    if trigger == "checkout_abandon" and content["coupon_code"]:
        content["coupon_code"] = "LAST_CHANCE_30"

    return content


# ── Gemini API integration ────────────────────────────────────────────────────
COUPON_BY_TIER = {
    "Low Priority":                "",
    "Nurture via Email/WhatsApp":  "FUTURE_READY_15",
    "Marketing Campaign":          "EARLY_BIRD_10",
    "Target Immediately":          "VIP_URGENT_25",
}


def generate_content_ai(name, occupation, specialization, course, action,
                         trigger, lead_score=0, past_purchases=0) -> dict:
    """
    Real Gemini call. Raises on any failure — the caller (generate_content)
    catches and falls back to the mock templates, so a bad/missing key or a
    transient API error never breaks the demo.
    """
    import google.generativeai as genai
    import json as _json

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-3.6-flash"))

    trigger_note = TRIGGER_CONTEXT.get(trigger, "they showed general interest on the site")
    coupon = COUPON_BY_TIER.get(action, "")
    coupon_rule = (
        f"Include the coupon code **{coupon}** at least once in the email body, at checkout."
        if coupon else "This tier gets NO coupon and NO discount — pure value content only, no selling."
    )
    returning_note = (
        f"This is a RETURNING customer with {past_purchases} past purchase(s) — use a warmer, "
        "loyalty-driven tone instead of an acquisition pitch."
        if past_purchases > 0 else ""
    )

    prompt = f"""You are an expert EdTech marketing copywriter for X Education, an Indian online education platform.

Generate hyper-personalised marketing content for this lead:
- Name: {name}
- Occupation: {occupation}
- Industry/Specialization: {specialization}
- Course they're interested in: {course}
- Lead Score: {lead_score}/100
- Marketing Tier: {action}
- Attribution — why we're contacting them right now: {trigger_note}
{returning_note}

Rules:
- Reference the attribution reason above naturally in the email (e.g. mention the cart/checkout/wishlist/enquiry context) — this email should read as a direct response to that specific action, not a generic blast.
- {coupon_rule}
- Always reference their specific occupation AND specialization AND course by name.
- Sound human and warm. Not robotic, not templated, no purple prose.
- Keep the email body under 220 words.

Respond with ONLY raw JSON, no markdown fences, in exactly this shape:
{{"email_subject":"...","email_body":"...","whatsapp_message":"...","coupon_code":"{coupon}","call_script":"..."}}"""

    response = model.generate_content(
        prompt,
        generation_config={"response_mime_type": "application/json"},
    )
    content = _json.loads(response.text)

    for key in ("email_subject", "email_body", "whatsapp_message"):
        if not content.get(key):
            raise ValueError(f"Gemini response missing required field: {key}")
    content.setdefault("coupon_code", coupon)
    content.setdefault("call_script", "")

    if trigger == "checkout_abandon" and content["coupon_code"]:
        content["coupon_code"] = "LAST_CHANCE_30"

    return content
