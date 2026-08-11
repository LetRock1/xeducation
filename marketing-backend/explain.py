"""
explain.py — Deterministic "why this score" explanation for a lead.
Mirrors the business-rule / engineered-feature logic in
user-backend/predict.py (_business_rules, _engineer) without needing
the ML/sklearn dependency stack — pure arithmetic over columns already
persisted on the leads row.
"""

DAMPENED_OCCUPATIONS = ["Student", "Unemployed", "Housewife"]


def explain_lead(lead: dict) -> list[dict]:
    factors = []

    def add(factor, detail, impact):
        factors.append({"factor": factor, "detail": detail, "impact": impact})

    trigger = lead.get("trigger_reason")
    if trigger == "checkout_abandon":
        add("Checkout abandonment", "Reached checkout but did not complete the purchase — the strongest intent signal captured. Business rule floors the score at 62+.", "floor 62")
    elif trigger == "cart_abandon":
        add("Cart abandonment", "Added a course to cart but did not purchase. Business rule floors the score at 62.", "floor 62")
    elif trigger == "enquiry":
        add("Enquiry submitted", "Directly requested more information. Business rule floors the score at 42.", "floor 42")

    if lead.get("video_watched"):
        add("Watched course video", "Engaged with the course overview video.", "+20 engagement")
    if lead.get("brochure_downloaded"):
        add("Downloaded brochure", "Downloaded the course brochure.", "+25 engagement, +3 intent")
    if lead.get("chat_initiated"):
        add("Opened chat", "Initiated a chat conversation with the team.", "+15 engagement, +2 intent")
    if lead.get("pricing_page_visited"):
        add("Viewed pricing", "Visited the pricing page.", "+3 intent")
    if lead.get("testimonial_visited"):
        add("Read testimonials", "Viewed student testimonials.", "+2 intent")
    if lead.get("webinar_attended"):
        add("Attended webinar", "Attended a live webinar.", "+4 intent, +2 motivation")

    total_visits = lead.get("total_visits") or 0
    if total_visits > 1:
        add("Returning visitor", f"Visited the site {total_visits} times across sessions.", "engagement boost")

    email_opens = lead.get("email_opened_count") or 0
    if email_opens > 0:
        add("Opened marketing emails", f"Opened {email_opens} marketing email(s). Each open adds +3, each click adds +7 to the live score.", f"+{email_opens * 3} so far")

    if lead.get("wishlist_count", 0) and lead.get("wishlist_count", 0) > 0:
        add("Wishlist activity", "Has at least one course on their wishlist.", "+5, capped at 100")

    occupation = lead.get("current_occupation")
    if occupation in DAMPENED_OCCUPATIONS and trigger not in ("cart_abandon", "enquiry", "checkout_abandon"):
        add("Occupation dampening", f"Occupation '{occupation}' caps the score at 72 and applies a 15% reduction unless a cart/checkout/enquiry signal is present.", "cap 72, ×0.85")

    if not factors:
        add("Baseline browsing", "No strong engagement signals captured yet — score reflects the baseline model prediction only.", "baseline")

    return factors
