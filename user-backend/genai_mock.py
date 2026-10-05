"""
genai_mock.py — Personalised email / WhatsApp / call-script generator.
(The same file is used by user-backend and marketing-backend.)

Content depends on:
  * the lead's tier (how ready they are) and WHY we are contacting them now
    (cart / checkout / wishlist / enquiry / inactivity / campaign)
  * TRUE facts about the course from the catalogue (duration, level,
    modules, instructor, EMI) — no invented salary figures, placement
    rates, "board-approved scholarships" or fake deadlines. Every claim in
    these messages can be checked on the course page.
  * the offer chosen for this lead (discount % or none). The next-best-action
    engine decides the offer; if it doesn't, a tier default is used.

With GEMINI_API_KEY set in .env, Gemini writes the copy from the same facts
(and is told not to invent any); on any error the templates below are used.
"""
import json as _json
import os
from datetime import datetime

import catalog
import gemini

YEAR = datetime.now().year
COUPON_VALID_HOURS = 72

TRIGGER_CONTEXT = {
    "cart_abandon":     "they added a course to their cart but did not complete checkout",
    "checkout_abandon": "they reached checkout and stopped one step short of paying",
    "wishlist_viewed":  "they added a course to their wishlist",
    "wishlist":         "they added a course to their wishlist",
    "session_end":      "they browsed the site and went inactive",
    "enquiry":          "they submitted an enquiry form asking for more information",
    "email_click":      "they clicked through a previous marketing email",
    "decay":            "they were engaged before but have gone quiet recently",
    "campaign":         "they are part of a scheduled campaign",
    "manual_edit":      "a marketing team member is drafting this email manually",
    "next_best_action": "the system chose this follow-up as the most helpful next step",
    "chat_callback":    "they asked for a callback in the website chat",
}

# Default offer per tier, used only when no next-best-action decision is passed in.
DEFAULT_OFFER_PCT = {
    "Target Immediately": 0,            # very likely to buy anyway — a discount mostly gives money away
    "Nurture via Email/WhatsApp": 15,
    "Marketing Campaign": 10,
    "Low Priority": 0,
}

ADVISOR = {"name": "Kavita Shah", "role": "Admissions Advisor, X Education"}


def coupon_code_for(pct, returning=False):
    """Human-readable code per discount level (each copy is issued to one user in coupons_issued)."""
    if not pct:
        return ""
    if returning:
        return f"LOYAL_{int(pct)}"
    return {10: "EARLY_BIRD_10", 15: "FUTURE_READY_15", 20: "SMART_START_20",
            25: "VIP_URGENT_25", 30: "LAST_CHANCE_30"}.get(int(pct), f"XEDU_{int(pct)}OFF")


def _facts(course, course_slug):
    slug = course_slug or catalog.slug_for_title(course)
    f = catalog.facts(slug) if slug else None
    if f:
        return f
    return {"title": course or "our programme", "duration": None, "level": None, "price": None,
            "emi": None, "modules": None, "outcomes": [], "instructor": None, "instructor_role": None}


def _course_block(f):
    lines = []
    if f["duration"]:
        lines.append(f"• Duration: {f['duration']} · Level: {f['level']}")
    if f["modules"]:
        lines.append(f"• Modules include: {f['modules']}")
    if f["outcomes"]:
        lines.append(f"• What you'll gain: {', '.join(f['outcomes'][:3])}")
    if f["instructor"]:
        lines.append(f"• Taught by {f['instructor']} ({f['instructor_role']})")
    if f["price"]:
        emi = f" or EMI from ₹{f['emi']:,}/month" if f["emi"] else ""
        lines.append(f"• Fee: ₹{f['price']:,}{emi}")
    return "\n".join(lines)


def _offer_line(code, pct):
    if not code:
        return ""
    return (f"\n\n🎁 Use code **{code}** at checkout for {pct}% off. "
            f"It's linked to your account and valid for {COUPON_VALID_HOURS} hours.")


def _trigger_line(trigger, title):
    return {
        "cart_abandon": f"You left {title} in your cart — it's still there whenever you're ready.",
        "checkout_abandon": f"You were one step away from enrolling in {title}. If something went wrong at checkout, just reply and we'll help.",
        "wishlist": f"You saved {title} to your wishlist, so here's a quick summary to help you decide.",
        "wishlist_viewed": f"You saved {title} to your wishlist, so here's a quick summary to help you decide.",
        "enquiry": f"Thanks for your enquiry about {title}. Here are the key details.",
        "session_end": f"Thanks for exploring {title} on our site.",
        "decay": f"It's been a while since you looked at {title} — here's what's new to help you decide.",
        "chat_callback": f"Thanks for asking for a callback about {title}. An advisor will call you shortly.",
    }.get(trigger, f"Here's a quick overview of {title}.")


def _templates(first, occupation, specialization, f, action, trigger, code, pct, past_purchases):
    title = f["title"]
    block = _course_block(f)
    offer = _offer_line(code, pct)
    opener = _trigger_line(trigger, title)

    if past_purchases > 0:
        subject = f"{first}, a next step after your first course: {title}"
        body = (f"Hi {first},\n\nGreat to have you learning with X Education. {opener}\n\n{block}"
                f"{offer}\n\nReply to this email if you'd like help planning your next course.\n\n"
                f"— The X Education Team")
        wa = f"Hi {first}! Thinking about {title} next? {f['duration'] or ''} programme. Reply YES for details."
        return subject, body, wa, ""

    if action == "Target Immediately":
        subject = f"{first}, your questions about {title} — answered"
        body = (f"Hi {first},\n\n{opener}\n\nAs a {occupation} with a background in {specialization}, "
                f"here is what {title} covers:\n\n{block}{offer}\n\n"
                f"Would a 10-minute call help? Reply with a good time and I'll call you.\n\n"
                f"{ADVISOR['name']}\n{ADVISOR['role']}")
        wa = (f"Hi {first}, this is {ADVISOR['name']} from X Education. {opener} "
              f"Happy to answer any questions about {title} — reply here or tell me a good time to call.")
        script = (f"Hi {first}, this is {ADVISOR['name']} from X Education. {opener} "
                  f"I'd love to understand what you're hoping to get from {title} as a {occupation} and answer "
                  f"any questions about the curriculum, schedule or fees"
                  + (f" — the programme runs for {f['duration']}" if f["duration"] else "") + ". "
                  "What would make this the right time for you?")
        return subject, body, wa, script

    if action == "Nurture via Email/WhatsApp":
        subject = f"{first}, is {title} right for you? A quick guide"
        body = (f"Hi {first},\n\n{opener}\n\n{block}\n\nA good fit if you're a {occupation} in "
                f"{specialization} who wants hands-on, project-based learning.{offer}\n\n"
                f"Questions? Just reply — a real person reads every email.\n\n{ADVISOR['name']}\n{ADVISOR['role']}")
        wa = (f"Hi {first} 👋 {opener} {title}: {f['duration'] or ''}"
              + (f", code {code} gives {pct}% off for {COUPON_VALID_HOURS}h" if code else "") + ". Reply for the syllabus!")
        return subject, body, wa, ""

    if action == "Marketing Campaign":
        subject = f"Free live session: getting started with {title}"
        body = (f"Hi {first},\n\n{opener}\n\nWe run a free live session every Saturday at 11 AM IST where "
                f"instructors walk through the {title} curriculum and answer questions — no obligation.\n\n"
                f"{block}{offer}\n\nReserve a seat from the home page of our website.\n\n— The X Education Team")
        wa = f"Hi {first}! Free live intro to {title} this Saturday 11 AM IST. Reply WEBINAR to reserve a seat."
        return subject, body, wa, ""

    subject = f"{title}: what you'd learn, in two minutes"
    body = (f"Hi {first},\n\n{opener}\n\nNo pressure — here's a short summary you can come back to:\n\n"
            f"{block}{offer}\n\nWhen you're ready, the full curriculum is on the course page.\n\n— The X Education Team")
    wa = f"Hi {first}, here's a 2-minute summary of {title} whenever you're ready. Reply INFO for it."
    return subject, body, wa, ""


def generate_content(name: str, occupation: str, specialization: str, course: str, action: str,
                     trigger: str = "session_end", past_purchases: int = 0, lead_score: float = 0,
                     course_slug: str = None, offer_pct: int = None) -> dict:
    """
    Returns {email_subject, email_body, whatsapp_message, coupon_code, offer_pct, call_script}.
    offer_pct: discount decided by the next-best-action engine (None = tier default, 0 = no offer).
    """
    first = (name or "there").split()[0]
    occupation = occupation or "professional"
    specialization = specialization or "your field"
    f = _facts(course, course_slug)
    pct = DEFAULT_OFFER_PCT.get(action, 0) if offer_pct is None else int(offer_pct)
    if past_purchases > 0 and offer_pct is None:
        pct = 20
    code = coupon_code_for(pct, returning=past_purchases > 0)

    if gemini.enabled():
        try:
            return generate_content_ai(first, occupation, specialization, f, action, trigger,
                                       lead_score, past_purchases, code, pct)
        except Exception as e:
            print(f"[GEMINI] Falling back to template content — {e}")

    subject, body, wa, script = _templates(first, occupation, specialization, f, action, trigger,
                                           code, pct, past_purchases)
    return {"email_subject": subject, "email_body": body, "whatsapp_message": wa,
            "coupon_code": code, "offer_pct": pct, "call_script": script}


def generate_content_ai(first, occupation, specialization, f, action, trigger, lead_score,
                        past_purchases, code, pct) -> dict:
    """Gemini writes the copy from the catalogue facts only. Raises on any failure."""
    facts = _course_block(f) or f["title"]
    offer = (f"Include the coupon code {code} ({pct}% off, valid {COUPON_VALID_HOURS} hours) once."
             if code else "Do not offer any discount.")
    prompt = f"""You write short, honest follow-up messages for X Education, an Indian online-education company.

Lead: {first}, a {occupation} in {specialization}. Tier: {action}. Lead score: {lead_score}/100.
Why we are writing now: {TRIGGER_CONTEXT.get(trigger, 'they showed interest on the website')}.
{"Returning customer with " + str(past_purchases) + " past purchase(s)." if past_purchases else ""}
Course facts (the ONLY facts you may state):
{facts}

Rules:
- Do NOT invent statistics, salaries, placement guarantees, scholarships, seat limits or deadlines.
- {offer}
- Warm, specific, under 160 words. Mention the course by name and why we're writing now.

Reply with ONLY JSON: {{"email_subject":"...","email_body":"...","whatsapp_message":"...","call_script":"..."}}"""
    content = _json.loads(gemini.generate(prompt, json_mode=True))
    for key in ("email_subject", "email_body", "whatsapp_message"):
        if not content.get(key):
            raise ValueError(f"Gemini response missing {key}")
    content.setdefault("call_script", "")
    content["coupon_code"] = code
    content["offer_pct"] = pct
    return content
