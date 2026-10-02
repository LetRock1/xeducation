"""
recourse.py — "How to convert this lead": counterfactual guidance.

For a lead, search the smallest set of realistic next steps (watch the
overview, read the brochure, attend the webinar, talk to an advisor ...)
that the model predicts would lift them into the next tier. Only
*actionable* signals are changed — never occupation, city, age or consent —
so every tip is something sales or the learner can actually do.

Search: all combinations of up to 3 not-yet-done steps (a few hundred
candidates), scored in one batch by the live lead model; the cheapest
combination (by effort) that reaches the next tier wins.

Honesty note: these are model-based ("people with these signals buy more
often"), not proof that the step causes a purchase — the next-best-action
uplift model (nba.py) is the causal part of the system.
"""
from itertools import combinations

import catalog
import database as db
import ml_features as F
from predict import _probs, predict_lead

# feature, new value (or +1), effort, what sales should do, what the learner sees
STEPS = [
    ("VideoWatched",       1,  1, "Get them to watch the 35-second course overview", "Watch the {course} overview"),
    ("BrochureDownloaded", 1,  1, "Send / share the course brochure",                "Get the {course} brochure"),
    ("PricingPageVisited", 1,  1, "Walk them through fees and the EMI option",       "See fees & EMI options for {course}"),
    ("TestimonialVisited", 1,  1, "Share reviews from learners like them",           "Read what learners say about {course}"),
    ("AddedToWishlist",    1,  1, "Suggest saving the course to compare later",      "Save {course} to compare later"),
    ("EmailOpenedCount",  "+1", 1, "Send a follow-up email worth clicking",          None),
    ("ChatInitiated",      1,  2, "Invite them to ask questions in chat",            "Ask our assistant about {course}"),
    ("TotalVisits",       "+1", 2, "Give them a reason to come back (new cohort, Q&A answer)", None),
    ("WebinarAttended",    1,  3, "Invite them to Saturday's free live session",     "Join Saturday's free live session"),
    ("EnquirySubmitted",   1,  3, "Book a counselling call / get an enquiry",        "Talk to an advisor about {course}"),
    ("AddedToCart",        1,  3, "Help them pick a start date and add to cart",     None),
]
MAX_STEPS = 3


def _apply(features, combo):
    f = dict(features)
    for feat, val, *_ in combo:
        if val == "+1":
            f[feat] = f[feat] + 1
            if feat == "TotalVisits":   # a typical extra visit adds time on site too
                f["TotalTimeOnWebsite"] = f["TotalTimeOnWebsite"] + 180
        else:
            f[feat] = val
    return f


def _next_cutoff(score):
    ups = [c for c, _ in sorted(F.TIERS) if c > score]
    return ups[0] if ups else None


def tips_for(features, current_score, limit=3):
    """Cheapest step-sets that move the lead into the next tier, plus best single steps."""
    target = _next_cutoff(current_score)
    open_steps = [s for s in STEPS if s[1] == "+1" or not features.get(s[0])]
    if not open_steps:
        return []
    combos = [c for r in range(1, MAX_STEPS + 1) for c in combinations(open_steps, r)]
    probs = _probs([_apply(features, c) for c in combos])
    scored = [(c, p * 100, sum(s[2] for s in c)) for c, p in zip(combos, probs)]
    tips = []
    if target is not None:
        reach = [x for x in scored if x[1] >= target]
        reach.sort(key=lambda x: (x[2], -x[1]))
        for c, s, effort in reach[:limit]:
            tips.append({
                "title": " + ".join(step[3] for step in c),
                "detail": f"Predicted score {current_score:.0f} → {s:.0f} ({F.tier_for(s)}) · effort {effort}",
                "steps": [step[0] for step in c], "new_score": round(s, 1), "effort": effort,
            })
    if not tips:   # nothing reaches the next tier with ≤3 steps: show the best single moves
        singles = sorted([x for x in scored if len(x[0]) == 1], key=lambda x: -x[1])[:limit]
        for c, s, effort in singles:
            if s - current_score >= 1:
                tips.append({"title": c[0][3],
                             "detail": f"Predicted score {current_score:.0f} → {s:.0f} (+{s - current_score:.0f} pts)",
                             "steps": [c[0][0]], "new_score": round(s, 1), "effort": effort})
    return tips


def learner_steps(user_id, limit=4):
    """Personalised 'next steps' for the learner's dashboard, ranked by the model."""
    from scoring import build_raw, interest_slug
    profile = db.get_profile(user_id) or {}
    raw = build_raw(user_id)
    pred = predict_lead(raw)
    features = pred["features"]
    slug = interest_slug(user_id)
    title = catalog.title_of(slug, "a course") if slug else None
    cart = db.get_cart(user_id)
    steps = []
    if not profile.get("profile_complete"):
        steps.append({"label": "Complete your profile", "to": "/settings",
                      "why": "Get course suggestions that fit your background."})
    if cart:
        steps.append({"label": "Finish your enrolment", "to": "/checkout",
                      "why": f"{cart[0]['course_title']} is waiting in your cart."})
    if not slug:
        steps.append({"label": "Explore our courses", "to": "/courses", "why": "24 programmes across 8 areas."})
        return steps[:limit]
    links = {
        "VideoWatched": (f"/courses/{slug}", "A 35-second summary of the programme."),
        "BrochureDownloaded": (f"/courses/{slug}/brochure", "Curriculum, fees and instructor on one page."),
        "PricingPageVisited": (f"/courses/{slug}", "Full fee, EMI and what's included."),
        "TestimonialVisited": (f"/courses/{slug}", "Reviews from people who took it."),
        "AddedToWishlist": (f"/courses/{slug}", "Keep it handy while you decide."),
        "ChatInitiated": (f"/courses/{slug}", "Get instant answers about fees, schedule and syllabus."),
        "WebinarAttended": ("/#webinar", "Ask instructors anything, no obligation."),
        "EnquirySubmitted": (f"/enquiry/{slug}", "An advisor answers your questions personally."),
    }
    candidates = [s for s in STEPS if s[4] and s[0] in links and not features.get(s[0])]
    if candidates:
        probs = _probs([_apply(features, (s,)) for s in candidates])
        ranked = sorted(zip(candidates, probs), key=lambda x: -x[1])
        for s, _ in ranked:
            to, why = links[s[0]]
            steps.append({"label": s[4].format(course=title), "to": to, "why": why})
    return steps[:limit]
