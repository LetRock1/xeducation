"""email_service.py — Gmail SMTP for OTP + marketing emails"""
import smtplib, os
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

def send_marketing_email(to: str, subject: str, body: str) -> tuple[bool, str]:
    html = f"""<div style="font-family:'Segoe UI',sans-serif;max-width:600px;margin:auto;padding:24px">
<div style="background:#0B1426;padding:20px 24px;border-radius:8px 8px 0 0">
  <h1 style="color:#38BDF8;margin:0;font-size:20px">X Education</h1>
  <p style="color:#94a3b8;margin:4px 0 0;font-size:13px">Transform Your Career</p>
</div>
<div style="background:#f8fafc;padding:28px 24px;border:1px solid #e2e8f0;border-top:none;border-radius:0 0 8px 8px;color:#334155;line-height:1.7;font-size:14px">
{body.replace(chr(10),'<br>').replace('**','<b>').replace('**','</b>')}
</div>
<p style="color:#94a3b8;font-size:11px;text-align:center;margin-top:16px">
X Education · Mumbai, India · <a href="#" style="color:#38BDF8">Unsubscribe</a></p></div>"""
    return _send(to, subject, body, html)
