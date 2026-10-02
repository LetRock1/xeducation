"""
assistant.py — the website chat assistant.

Replaces the old widget that pretended to be a human ("Priya — Online now")
and replied with the same four canned lines in order, whatever you typed.

How it works:
  1. Detect the intent of the message with keyword rules (fees, duration,
     syllabus, instructor, level, which course fits me, certificate,
     placement, refund, payment, webinar, callback, ...).
  2. Work out which course the question is about: a course named in the
     message, otherwise the course page the visitor is on.
  3. Answer ONLY from the course catalogue and faq.json — it never invents
     facts. If GEMINI_API_KEY is set, unmatched questions are answered by
     Gemini, grounded on the same catalogue text.
  4. Every message is stored in chat_messages (marketing can read the
     transcript on the lead page), and "talk to a human" opens a real
     callback request that appears on the sales dashboard.
"""
import json
import os
import re

import catalog
from recommendations import get_recommendations

_FAQ_PATH = os.path.join(os.path.dirname(__file__), "faq.json")

INTENTS = [
    ("callback",   r"\b(call( me)?|callback|call back|talk to|speak to|human|agent|advisor|adviser|counsel+or|counsel+ing|phone)\b"),
    ("price",      r"\b(price|prices|fee|fees|cost|costs|how much|emi|instal+ments?|afford|expensive|cheap|discount|coupon|offer)\b"),
    ("duration",   r"\b(how long|duration|months?|weeks?|hours? per|time commitment)\b"),
    ("curriculum", r"\b(syllabus|curriculum|modules?|topics?|cover|what will i learn|content)\b"),
    ("instructor", r"\b(instructor|teacher|faculty|mentor|who teaches|trainer)\b"),
    ("level",      r"\b(beginner|prerequisites?|eligib\w*|background|experience needed|level|difficult|hard)\b"),
    ("recommend",  r"\b(which course|recommend|suggest|best course|right course|confused|for me|should i (take|choose|pick))\b"),
    ("catalogue",  r"\b(courses|programmes|programs|what do you (offer|have)|options|list)\b"),
    ("certificate",r"\b(certificate|certification|certified)\b"),
    ("placement",  r"\b(placement|job|jobs|salary|hike|career support|hiring)\b"),
    ("refund",     r"\b(refund|cancel|money back)\b"),
    ("payment",    r"\b(pay|payment|upi|card|net ?banking)\b"),
    ("schedule",   r"\b(schedule|timings?|weekend|working|part[- ]time|self[- ]paced|live classes?)\b"),
    ("webinar",    r"\b(webinar|live session|demo class|free class|saturday)\b"),
    ("thanks",     r"\b(thanks|thank you|thx|great|ok(ay)?|cool)\b"),
    ("greet",      r"^\s*(hi|hello|hey|namaste|good (morning|afternoon|evening))\b"),
]

DEFAULT_SUGGESTIONS = ["What are the fees?", "Which course suits me?", "How long is it?", "Talk to an advisor"]


def _faq():
    try:
        with open(_FAQ_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def detect_intent(text):
    t = (text or "").lower()
    for name, pattern in INTENTS:
        if re.search(pattern, t):
            return name
    return "unknown"


def find_course(text, page_slug=None):
    t = (text or "").lower()
    best = None
    for c in catalog.all_courses():
        title = c["title"].lower()
        if title in t or c["slug"].replace("-", " ") in t:
            if not best or len(title) > len(best["title"]):
                best = c
    if best:
        return best
    # short forms people actually type
    aliases = {"data science": "data-science-analytics", "mba": "mba-core", "digital marketing": "digital-marketing",
               "ai": "ai-machine-learning", "machine learning": "ai-machine-learning", "hr": "hr-management",
               "finance": "finance-banking", "supply chain": "supply-chain-management",
               "six sigma": "lean-six-sigma", "ecommerce": "e-commerce", "e-commerce": "e-commerce",
               "project management": "project-management", "business analytics": "business-analytics"}
    for alias, slug in sorted(aliases.items(), key=lambda kv: -len(kv[0])):
        if re.search(rf"\b{re.escape(alias)}\b", t):
            return catalog.get_course(slug)
    return catalog.get_course(page_slug) if page_slug else None


def _link(c):
    return {"label": f"Open {c['title']}", "to": f"/courses/{c['slug']}"}


def answer(text, page_slug=None, profile=None, user=None, purchased_slugs=()):
    """Returns {reply, intent, course_slug, suggestions, links, action}."""
    intent = detect_intent(text)
    c = find_course(text, page_slug)
    faq = _faq()
    links, action = [], None
    suggestions = DEFAULT_SUGGESTIONS

    def need_course(question):
        return (f"Happy to help with {question}! Which course are you asking about? "
                "For example: Data Science & Analytics, Digital Marketing or MBA Core.")

    if intent == "greet":
        first = (user or {}).get("name", "").split()[0] if user else ""
        reply = (f"Hi{(' ' + first) if first else ''}! I'm the X Education course assistant (automated). "
                 "I can answer questions about fees, duration, syllabus and instructors, help you pick a course, "
                 "or arrange a call with an advisor.")
    elif intent == "price":
        if c:
            reply = (f"{c['title']} costs ₹{c['price']:,}" + (f", or EMI from ₹{c['emi']:,}/month" if c.get("emi") else "")
                     + f". It runs for {c['duration']}. Discounts are occasionally sent by email to registered learners.")
            links = [_link(c)]
        else:
            lo = min(catalog.all_courses(), key=lambda x: x["price"])
            hi = max(catalog.all_courses(), key=lambda x: x["price"])
            reply = (f"Fees range from ₹{lo['price']:,} ({lo['title']}) to ₹{hi['price']:,} ({hi['title']}), "
                     "and most programmes have a monthly EMI option. Which course are you interested in?")
    elif intent == "duration":
        reply = (f"{c['title']} runs for {c['duration']} ({c['level']} level). " + faq.get("schedule", "")) if c \
            else need_course("course duration")
        links = [_link(c)] if c else []
    elif intent == "curriculum":
        if c:
            mods = "; ".join(f"{m['module']}: {m['title']}" for m in c["curriculum"])
            reply = f"Here's the {c['title']} curriculum — {mods}."
            links = [_link(c)]
        else:
            reply = need_course("the syllabus")
    elif intent == "instructor":
        reply = (f"{c['title']} is taught by {c['instructor']['name']} ({c['instructor']['role']}, "
                 f"{c['instructor']['exp']} of experience).") if c else need_course("instructors")
        links = [_link(c)] if c else []
    elif intent == "level":
        reply = (f"{c['title']} is a {c['level']}-level programme. The course page lists what you'll gain: "
                 f"{', '.join(c['outcomes'])}.") if c else need_course("the level and prerequisites")
        links = [_link(c)] if c else []
    elif intent == "recommend" or (intent == "catalogue" and not c):
        profile = profile or {}
        titles = get_recommendations(profile.get("current_occupation") or "", profile.get("specialization") or "",
                                     [page_slug] if page_slug else [], list(purchased_slugs))
        if intent == "catalogue" or not titles:
            domains = sorted({x["domain"] for x in catalog.all_courses()})
            reply = f"We offer {len(catalog.all_courses())} programmes across {len(domains)} areas: {', '.join(domains)}."
            if intent == "recommend" and not profile.get("current_occupation"):
                reply += " Complete your profile (occupation and specialization) and I can suggest the best fit."
        else:
            reply = ("Based on your profile, these look like a good fit: " + ", ".join(titles[:3])
                     + ". Want the fees or syllabus for any of them?")
            for t in titles[:3]:
                slug = catalog.slug_for_title(t)
                if slug:
                    links.append(_link(catalog.get_course(slug)))
    elif intent in ("certificate", "placement", "refund", "payment", "schedule", "webinar"):
        reply = faq.get(intent, "Let me connect you with an advisor for that.")
        if intent == "webinar":
            links = [{"label": "Reserve a seat", "to": "/#webinar"}]
    elif intent == "callback":
        if user:
            reply = "Sure — leave your number and a good time, and an advisor will call you."
            action = {"type": "callback_form"}
        else:
            reply = "Sure! Please log in or create a free account first, then I can book a callback for you."
            links = [{"label": "Log in", "to": "/login"}]
    elif intent == "thanks":
        reply = "You're welcome! Anything else I can help with?"
    elif intent == "catalogue" and c:
        reply = f"{c['title']}: {c['tagline']}. {c['duration']}, ₹{c['price']:,}."
        links = [_link(c)]
    else:
        reply = _llm_answer(text, c) or (
            "I'm not sure about that one. I can help with fees, duration, syllabus, instructors, "
            "choosing a course, certificates, refunds, or I can arrange a call with an advisor.")

    return {"reply": reply, "intent": intent, "course_slug": c["slug"] if c else page_slug,
            "suggestions": suggestions, "links": links, "action": action}


def _llm_answer(text, course):
    """Optional: Gemini answers questions the rules don't cover, using catalogue text only."""
    if not os.getenv("GEMINI_API_KEY"):
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-1.5-flash"))
        context = json.dumps(course or catalog.all_courses()[:8], ensure_ascii=False)[:6000]
        faq = json.dumps(_faq(), ensure_ascii=False)
        prompt = (f"You are X Education's website assistant. Answer in at most 3 sentences using ONLY this "
                  f"catalogue: {context} and these policies: {faq}. If the answer isn't there, say you don't "
                  f"know and offer a callback. Question: {text}")
        return model.generate_content(prompt).text.strip()
    except Exception as e:
        print(f"[ASSISTANT] Gemini fallback failed: {e}")
        return None
