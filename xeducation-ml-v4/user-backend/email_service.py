"""email_service.py — Gmail SMTP for OTP + marketing emails"""
import smtplib, os, re, html as _html
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()
GMAIL_USER = os.getenv("GMAIL_USER", "")
GMAIL_PASS = os.getenv("GMAIL_APP_PASSWORD", "")

def _send(to: str, subject: str, body: str, html: str = None) -> tuple[bool, str]:
    if not GMAIL_USER or not GMAIL_PASS:
        print(f"[EMAIL MOCK] To: {to} | Subject: {subject}")
        return True, "Mock sent (configure Gmail in .env for real sending)"
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"X Education <{GMAIL_USER}>"
        msg["To"] = to
        msg.attach(MIMEText(body, "plain", "utf-8"))
        if html:
            msg.attach(MIMEText(html, "html", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(GMAIL_USER, GMAIL_PASS)
            s.sendmail(GMAIL_USER, to, msg.as_string())
        return True, f"Sent to {to}"
    except Exception as e:
        return False, str(e)

def send_otp_email(to: str, otp: str, name: str) -> tuple[bool, str]:
    subject = f"Your X Education Verification Code: {otp}"
    body = f"""Hi {name},

Your one-time verification code is:

  {otp}

This code expires in 10 minutes. Do not share it with anyone.

If you did not request this, please ignore this email.

— X Education Team"""
    html = f"""<div style="font-family:'Segoe UI',sans-serif;max-width:480px;margin:auto;padding:32px">
<div style="background:#0B1426;padding:20px 24px;border-radius:12px 12px 0 0;text-align:center">
  <h1 style="color:#38BDF8;margin:0;font-size:22px">X Education</h1>
</div>
<div style="background:#f8fafc;padding:32px;border:1px solid #e2e8f0;border-top:none;border-radius:0 0 12px 12px;text-align:center">
  <p style="color:#475569;margin:0 0 16px">Hi {name}, your verification code is:</p>
  <div style="font-size:42px;font-weight:900;letter-spacing:10px;color:#0B1426;margin:20px 0">{otp}</div>
  <p style="color:#94a3b8;font-size:13px">Expires in 10 minutes. Do not share this code.</p>
</div></div>"""
    return _send(to, subject, body, html)

# Maps a lead's trigger_reason to a human-readable attribution line for
# purchase-confirmation emails ("closed loop" — credits the channel that converted the buyer).
ATTRIBUTION_LABELS = {
    "cart_abandon":       "your cart reminder email",
    "session_end":        "a personalized nudge after your last visit",
    "wishlist":           "your wishlist insight email",
    "checkout_abandon":   "your checkout reminder email",
    "behaviour_snapshot": "your on-site browsing activity",
    "enquiry":            "your course enquiry",
    "email_open":         "an email you opened",
    "email_click":        "an email you clicked",
    "decay":              "your ongoing interest on our site",
    None:                 "your visit to X Education",
}


def send_purchase_confirmation_email(to: str, name: str, courses: list, channel_label: str,
                                      total_paid: float, discount_pct: int = 0) -> tuple[bool, str]:
    course_list = ", ".join(courses)
    subject = f"Enrollment Confirmed: {course_list} — X Education"
    discount_note = f" (after {discount_pct}% discount)" if discount_pct else ""
    body = f"""Hi {name},

Congratulations! Your enrollment is confirmed for:

  {course_list}

Amount paid: Rs.{total_paid:,.2f}{discount_note}

We're glad this reached you through {channel_label} — thank you for trusting X Education
with your learning journey. Our team will be in touch shortly with your course access details.

— X Education Team"""
    discount_html = (
        f' <span style="color:#16a34a">({discount_pct}% discount applied)</span>' if discount_pct else ""
    )
    html = f"""<div style="font-family:'Segoe UI',sans-serif;max-width:600px;margin:auto;padding:24px">
<div style="background:#0B1426;padding:20px 24px;border-radius:8px 8px 0 0">
  <h1 style="color:#38BDF8;margin:0;font-size:20px">X Education</h1>
  <p style="color:#94a3b8;margin:4px 0 0;font-size:13px">Enrollment Confirmed</p>
</div>
<div style="background:#f8fafc;padding:28px 24px;border:1px solid #e2e8f0;border-top:none;border-radius:0 0 8px 8px;color:#334155;line-height:1.7;font-size:14px">
  <p>Hi {name},</p>
  <p>🎉 Congratulations! Your enrollment is confirmed for:</p>
  <p style="font-weight:700;font-size:16px;color:#0B1426">{course_list}</p>
  <p><b>Amount paid:</b> Rs.{total_paid:,.2f}{discount_html}</p>
  <p style="color:#64748b;font-size:13px">Attribution: this enrollment is credited to <b>{channel_label}</b>.</p>
  <p>Our team will be in touch shortly with your course access details.</p>
</div>
<p style="color:#94a3b8;font-size:11px;text-align:center;margin-top:16px">
X Education · Mumbai, India · <a href="#" style="color:#38BDF8">Unsubscribe</a></p></div>"""
    return _send(to, subject, body, html)


def _body_to_html(body: str) -> str:
    """Escape the text, turn **bold** into <b>bold</b>, newlines into <br>.
    (The old .replace('**','<b>').replace('**','</b>') turned EVERY ** into
    an opening <b>, so everything after the first coupon code was bold.)"""
    safe = _html.escape(body or "")
    safe = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", safe, flags=re.S)
    return safe.replace("\n", "<br>")


def send_marketing_email(to: str, subject: str, body: str,
                          cta_url: str = None, cta_label: str = "View Course") -> tuple[bool, str]:
    # Engagement is tracked exclusively via the CTA button click-through
    # (no tracking pixel — most email clients block remote images anyway,
    # so a pixel-based "open" signal was unreliable; a real click is not).
    cta_html = (
        f'<p style="text-align:center;margin-top:20px">'
        f'<a href="{cta_url}" style="background:#38BDF8;color:#0B1426;padding:12px 28px;'
        f'border-radius:8px;text-decoration:none;font-weight:700;display:inline-block">{cta_label}</a></p>'
    ) if cta_url else ""
    html = f"""<div style="font-family:'Segoe UI',sans-serif;max-width:600px;margin:auto;padding:24px">
<div style="background:#0B1426;padding:20px 24px;border-radius:8px 8px 0 0">
  <h1 style="color:#38BDF8;margin:0;font-size:20px">X Education</h1>
  <p style="color:#94a3b8;margin:4px 0 0;font-size:13px">Transform Your Career</p>
</div>
<div style="background:#f8fafc;padding:28px 24px;border:1px solid #e2e8f0;border-top:none;border-radius:0 0 8px 8px;color:#334155;line-height:1.7;font-size:14px">
{_body_to_html(body)}
{cta_html}
</div>
<p style="color:#94a3b8;font-size:11px;text-align:center;margin-top:16px">
X Education · Mumbai, India · <a href="#" style="color:#38BDF8">Unsubscribe</a></p></div>"""
    return _send(to, subject, body, html)
