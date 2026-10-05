"""
outreach.py — every marketing email the user-backend sends goes through here.

* respects the user's "Do not email" choice (the scheduler used to ignore it)
* click-tracked CTA that lands on the real course page (/courses/<slug>;
  the old links pointed to /course/<slug>, which doesn't exist)
* working one-click unsubscribe link (+ List-Unsubscribe header)
"""
import os
import uuid
from urllib.parse import quote

import catalog
import database as db
from email_service import send_marketing_email

MKT_BASE_URL = os.getenv("MKT_PUBLIC_BASE_URL", "http://localhost:8001")
FRONTEND_URL = os.getenv("USER_FRONTEND_URL", "http://localhost:5173")


def course_url(slug=None):
    return f"{FRONTEND_URL}/courses/{slug}" if slug and catalog.get_course(slug) else f"{FRONTEND_URL}/courses"


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
    click_url = f"{MKT_BASE_URL}/api/mkt/track/click/{token}?to={quote(course_url(course_slug), safe='')}"
    unsubscribe_url = f"{MKT_BASE_URL}/api/mkt/unsubscribe/{token}"
    return send_marketing_email(to_email, subject, body, cta_url=click_url, cta_label=cta_label,
                                unsubscribe_url=unsubscribe_url)
