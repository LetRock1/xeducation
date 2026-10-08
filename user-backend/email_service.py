"""
email_service.py — Gmail SMTP for OTPs, marketing and transactional emails.
(The same file is used by user-backend and marketing-backend.)

Without GMAIL_USER / GMAIL_APP_PASSWORD in .env, emails are printed to the
console instead of sent ("[EMAIL MOCK]"), so the project runs anywhere.
"""
import html as _html
import os
import re
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv

load_dotenv()
GMAIL_USER = os.getenv("GMAIL_USER", "")
GMAIL_PASS = os.getenv("GMAIL_APP_PASSWORD", "")
BRAND_FOOTER = "X Education · Mumbai, India"
SMTP_TIMEOUT_SECONDS = 10          # a dead network used to hang a request for minutes
PAUSE_AFTER_NETWORK_ERROR = 300    # then don't try again for 5 minutes (no 10-second wait per email)
_paused_until = {"t": 0.0}


def _send(to: str, subject: str, body: str, html: str = None, headers: dict = None) -> tuple[bool, str]:
    if (to or "").strip().lower().endswith(".test"):
        # simulated demo learners (…@demo.xeducation.test) — a reserved domain, never mailed
        print(f"[EMAIL DEMO] To: {to} | Subject: {subject} (simulated learner, not sent)")
        return True, "Simulated demo learner — not sent"
    if not GMAIL_USER or not GMAIL_PASS:
        print(f"[EMAIL MOCK] To: {to} | Subject: {subject}")
        return True, "Mock sent (configure Gmail in .env for real sending)"
    if time.time() < _paused_until["t"]:
        print(f"[EMAIL PAUSED] To: {to} | Subject: {subject} (Gmail was unreachable a moment ago; not sent)")
        return False, "Email is paused for a few minutes after a network error"
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"X Education <{GMAIL_USER}>"
        msg["To"] = to
        for k, v in (headers or {}).items():
            msg[k] = v
        msg.attach(MIMEText(body, "plain", "utf-8"))
        if html:
            msg.attach(MIMEText(html, "html", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=SMTP_TIMEOUT_SECONDS) as s:
            s.login(GMAIL_USER, GMAIL_PASS)
            s.sendmail(GMAIL_USER, to, msg.as_string())
        return True, f"Sent to {to}"
    except smtplib.SMTPAuthenticationError:
        print("[EMAIL ERROR] Gmail refused the login: check GMAIL_USER and GMAIL_APP_PASSWORD in .env")
        return False, "Gmail refused the login (check the app password in .env)"
    except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError) as e:
        return _network_error(e)
    except smtplib.SMTPException as e:            # e.g. one address refused: no reason to pause the others
        print(f"[EMAIL ERROR] {type(e).__name__}: {e}")
        return False, str(e)
    except OSError as e:                           # no internet, DNS failure, timeout
        return _network_error(e)
    except Exception as e:
        return False, str(e)


def _network_error(e):
    _paused_until["t"] = time.time() + PAUSE_AFTER_NETWORK_ERROR
    print(f"[EMAIL ERROR] {type(e).__name__}: {e} - emails paused for {PAUSE_AFTER_NETWORK_ERROR // 60} minutes")
    return False, f"Could not reach Gmail ({type(e).__name__})"


def _shell(title: str, inner_html: str, footer_extra: str = "") -> str:
    return f"""<div style="font-family:'Segoe UI',sans-serif;max-width:600px;margin:auto;padding:24px">
<div style="background:#0B1426;padding:20px 24px;border-radius:8px 8px 0 0">
  <h1 style="color:#38BDF8;margin:0;font-size:20px">X Education</h1>
  <p style="color:#94a3b8;margin:4px 0 0;font-size:13px">{_html.escape(title)}</p>
</div>
<div style="background:#f8fafc;padding:28px 24px;border:1px solid #e2e8f0;border-top:none;border-radius:0 0 8px 8px;color:#334155;line-height:1.7;font-size:14px">
{inner_html}
</div>
<p style="color:#94a3b8;font-size:11px;text-align:center;margin-top:16px">{BRAND_FOOTER}{footer_extra}</p></div>"""


def send_otp_email(to: str, otp: str, name: str, purpose: str = "signup") -> tuple[bool, str]:
    if purpose == "reset":
        subject = f"Your X Education password reset code: {otp}"
        intro = "Use this code to reset your password"
    else:
        subject = f"Your X Education verification code: {otp}"
        intro = "Your verification code is"
    body = f"""Hi {name},

{intro}:

  {otp}

This code expires in 10 minutes. Do not share it with anyone.
If you did not request this, you can ignore this email.

— X Education Team"""
    inner = f"""<div style="text-align:center">
  <p style="color:#475569;margin:0 0 16px">Hi {_html.escape(name)}, {intro.lower()}:</p>
  <div style="font-size:42px;font-weight:900;letter-spacing:10px;color:#0B1426;margin:20px 0">{otp}</div>
  <p style="color:#94a3b8;font-size:13px">Expires in 10 minutes. Do not share this code.</p></div>"""
    return _send(to, subject, body, _shell("Account security", inner))


# Maps a lead's trigger_reason to a human-readable attribution line for
# purchase-confirmation emails (credits the touchpoint that reached the buyer).
ATTRIBUTION_LABELS = {
    "cart_abandon":       "your cart reminder email",
    "session_end":        "a follow-up after your last visit",
    "wishlist":           "your wishlist email",
    "checkout_abandon":   "your checkout reminder email",
    "behaviour_snapshot": "your on-site browsing activity",
    "enquiry":            "your course enquiry",
    "campaign":           "one of our email campaigns",
    "ab_test":            "one of our email campaigns",
    "manual_send":        "an email from our admissions team",
    "next_best_action":   "a personalised follow-up from our team",
    "chat_callback":      "your callback request",
    "manual":             "a personal follow-up from our admissions team",
    "email_click":        "an email you clicked",
    "decay":              "your ongoing interest on our site",
    None:                 "your visit to X Education",
}


def send_purchase_confirmation_email(to: str, name: str, courses: list, channel_label: str,
                                     total_paid: float, discount_pct: int = 0) -> tuple[bool, str]:
    course_list = ", ".join(courses)
    subject = f"Enrollment confirmed: {course_list} — X Education"
    discount_note = f" (after {discount_pct}% discount)" if discount_pct else ""
    body = f"""Hi {name},

Your enrollment is confirmed for:

  {course_list}

Amount paid: Rs.{total_paid:,.2f}{discount_note}

Thank you for choosing X Education. You can see your courses any time under
"My Dashboard" on the website.

— X Education Team"""
    discount_html = (f' <span style="color:#16a34a">({discount_pct}% discount applied)</span>'
                     if discount_pct else "")
    inner = f"""<p>Hi {_html.escape(name)},</p>
  <p>🎉 Your enrollment is confirmed for:</p>
  <p style="font-weight:700;font-size:16px;color:#0B1426">{_html.escape(course_list)}</p>
  <p><b>Amount paid:</b> Rs.{total_paid:,.2f}{discount_html}</p>
  <p style="color:#64748b;font-size:13px">This enrollment is credited to <b>{_html.escape(channel_label)}</b>.</p>
  <p>You can see your courses any time under <b>My Dashboard</b> on the website.</p>"""
    return _send(to, subject, body, _shell("Enrollment confirmed", inner))


def _body_to_html(body: str) -> str:
    """Escape the text, turn **bold** into <b>bold</b>, newlines into <br>."""
    safe = _html.escape(body or "")
    safe = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", safe, flags=re.S)
    return safe.replace("\n", "<br>")


def send_marketing_email(to: str, subject: str, body: str, cta_url: str = None,
                         cta_label: str = "View Course", unsubscribe_url: str = None) -> tuple[bool, str]:
    """Marketing email with a click-tracked CTA and a working one-click unsubscribe."""
    cta_html = (
        f'<p style="text-align:center;margin-top:20px">'
        f'<a href="{_html.escape(cta_url)}" style="background:#38BDF8;color:#0B1426;padding:12px 28px;'
        f'border-radius:8px;text-decoration:none;font-weight:700;display:inline-block">{_html.escape(cta_label)}</a></p>'
    ) if cta_url else ""
    unsub_html = (f' · <a href="{_html.escape(unsubscribe_url)}" style="color:#38BDF8">Unsubscribe</a>'
                  if unsubscribe_url else "")
    text = body
    if cta_url:
        text += f"\n\n{cta_label}: {cta_url}"
    if unsubscribe_url:
        text += f"\n\nDon't want these emails? Unsubscribe: {unsubscribe_url}"
    headers = {}
    if unsubscribe_url:
        headers["List-Unsubscribe"] = f"<{unsubscribe_url}>"
        headers["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    html = _shell("Transform your career", _body_to_html(body) + cta_html, unsub_html)
    return _send(to, subject, text, html, headers)


def send_simple_email(to: str, subject: str, body: str, title: str = "Message from X Education") -> tuple[bool, str]:
    """Transactional notification (e.g. your question was answered)."""
    return _send(to, subject, body, _shell(title, _body_to_html(body)))
