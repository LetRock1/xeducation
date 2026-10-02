"""
playbook.py — what happens when a trigger fires (cart left, checkout left,
wishlist, inactivity, enquiry).

    score the lead → record a lead touchpoint → next-best-action decides →
    carry it out (email with/without coupon, or a call / WhatsApp task) →
    log everything so outcomes can be learned from.

Before, every trigger sent a tier-template email with a tier coupon. Now the
uplift model decides whether to contact at all, how, and whether a discount
is worth it — and 15% of decisions are randomised so the system keeps
learning which actions really work (see nba.py).
"""
import catalog
import database as db
import nba
from genai_mock import generate_content
from outreach import send_tracked_email
from scoring import save_lead, score_user


def handle_trigger(user_id, name, email, trigger, course_slug=None, allowed=None, always_email=False):
    """Returns (lead_id, prediction, decision)."""
    profile = db.get_profile(user_id) or {}
    pred = score_user(user_id, source=trigger, course=course_slug, explain=True)
    decision = nba.decide(user_id, trigger, pred, course_slug=course_slug, allowed=allowed)
    action = decision["action"]
    title = catalog.title_of(course_slug, "our programmes") if course_slug else "our programmes"
    is_email = action.startswith("email")

    content = generate_content(
        name=name, occupation=profile.get("current_occupation"), specialization=profile.get("specialization"),
        course=title, action=("Target Immediately" if action == "call" else pred["recommended_action"]),
        trigger=trigger, past_purchases=pred["raw"]["past_purchases"], lead_score=pred["lead_score"],
        course_slug=course_slug, offer_pct=nba.offer_pct(action) if is_email else 0,
    )
    lead_id = save_lead(user_id, pred, content, trigger, course_slug=course_slug)
    nba.attach_to_lead(lead_id, decision)

    if is_email or always_email:
        ok, _ = send_tracked_email(user_id, lead_id, email, content["email_subject"], content["email_body"],
                                   course_slug=course_slug)
        if ok and is_email:
            nba.mark_executed(decision["decision_id"])
    if action in ("call", "whatsapp"):
        verb = "Call" if action == "call" else "WhatsApp"
        nba.create_task(user_id, lead_id, decision, f"{verb} {name} about {title}",
                        content.get("call_script") if action == "call" else content.get("whatsapp_message"))
    print(f"[NBA] {email} · {trigger} · score {pred['lead_score']:.0f} → {decision['label']} ({decision['policy']})")
    return lead_id, pred, decision
