"""
outreach.py — every marketing email the user-backend sends goes through here.

* respects the user's "Do not email" choice (the scheduler used to ignore it)
* the "View Course" button opens the course the person looked at, straight on our website:
  <site>/courses/<slug>?ref=<token>. The course page reports the click itself (POST /api/email/click),
  so no separate tracking server has to be reachable from the phone or laptop that opens the email.
* working one-click unsubscribe link (<site>/unsubscribe?t=<token>, + List-Unsubscribe header)

Where the links point: PUBLIC_SITE_URL in .env (e.g. http://192.168.1.5:5173 so a phone on the same
Wi-Fi can open them); without it, USER_FRONTEND_URL, which is http://localhost:5173 (works on this laptop).
"""
import os
import uuid

import catalog
import database as db
from email_service import send_marketing_email

SITE_URL = (os.getenv("PUBLIC_SITE_URL") or os.getenv("USER_FRONTEND_URL") or "http://localhost:5173").rstrip("/")
FRONTEND_URL = SITE_URL                      # (kept for older imports)


def course_url(slug=None):
    return f"{SITE_URL}/courses/{slug}" if slug and catalog.get_course(slug) else f"{SITE_URL}/courses"


def tracked_link(token, slug=None):
    """The email's button: the course page itself, carrying the email's token."""
    return f"{course_url(slug)}?ref={token}"


def unsubscribe_link(token):
    return f"{SITE_URL}/unsubscribe?t={token}"


def send_tracked_email(user_id, lead_id, to_email, subject, body, course_slug=None,
                       cta_label="View Course", campaign_name=None, adoption=None):
    profile = db.get_profile(user_id) or {}
    if profile.get("do_not_email") == "Yes":
        print(f"[EMAIL] skipped {to_email}: opted out of email")
        return False, "User opted out of emails"
    token = uuid.uuid4().hex
    db.insert_email_send(token, user_id, lead_id=lead_id, subject=subject, body=body)
    if campaign_name:
        db.execute("UPDATE email_sends SET campaign_name=? WHERE token=?", (campaign_name, token))
    if adoption:                                   # (adoption id, 'adopted' | 'check'): see adopted.py
        db.execute("UPDATE email_sends SET adoption_id=?, adoption_arm=? WHERE token=?", (adoption[0], adoption[1], token))
    return send_marketing_email(to_email, subject, body, cta_url=tracked_link(token, course_slug), cta_label=cta_label,
                                unsubscribe_url=unsubscribe_link(token))
