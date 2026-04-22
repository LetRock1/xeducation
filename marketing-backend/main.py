"""
main.py — X Education Marketing Backend (port 8001)
Reads from the shared user DB. Marketing-specific tables stored here too.
"""
import os, csv, io, sqlite3
from datetime import datetime
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv
from passlib.context import CryptContext
from jose import JWTError, jwt

load_dotenv()

USER_DB      = os.getenv("USER_DB_PATH", "../user-backend/xeducation_user.db")
MKT_DB       = os.path.join(os.path.dirname(__file__), "xeducation_marketing.db")
MKT_EMAIL    = os.getenv("MARKETING_EMAIL", "admin@xeducation.in")
MKT_PASSWORD = os.getenv("MARKETING_PASSWORD", "marketing_admin_2025")
JWT_SECRET   = os.getenv("JWT_SECRET", "mkt_secret")
JWT_ALGO     = "HS256"
pwd_ctx      = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── DB helpers ────────────────────────────────────────────────────────────────
def user_conn():
    c = sqlite3.connect(USER_DB, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c

def mkt_conn():
    c = sqlite3.connect(MKT_DB, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c

def uq(sql, params=()):
    c = user_conn()
    rows = c.execute(sql, params).fetchall()
    c.close()
    return [dict(r) for r in rows]

def uq1(sql, params=()):
    c = user_conn()
    r = c.execute(sql, params).fetchone()
    c.close()
    return dict(r) if r else None

def mq(sql, params=()):
    c = mkt_conn()
    rows = c.execute(sql, params).fetchall()
    c.close()
    return [dict(r) for r in rows]

def mex(sql, params=()):
    c = mkt_conn()
    cur = c.execute(sql, params)
    c.commit()
    lid = cur.lastrowid
    c.close()
    return lid

# ── Init marketing DB ─────────────────────────────────────────────────────────
def init_mkt_db():
    c = mkt_conn()
    c.execute("""CREATE TABLE IF NOT EXISTS campaign_schedules (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT,
        tier        TEXT,
        subject     TEXT,
        body        TEXT,
        scheduled_at TEXT,
        sent        INTEGER DEFAULT 0,
        sent_at     TEXT,
        created_at  TEXT DEFAULT (datetime('now','localtime'))
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS sms_queue (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER,
        phone      TEXT,
        message    TEXT,
        status     TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )""")
    c.commit(); c.close()
    print(f"[MKT-DB] Initialised → {MKT_DB}")

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="X Education Marketing API", version="2.0.0")
app.add_middleware(CORSMiddleware,
    allow_origins=["http://localhost:5174","http://127.0.0.1:5174"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def startup():
    init_mkt_db()
    print("[API] Marketing Backend running on port 8001")

# ── Auth ──────────────────────────────────────────────────────────────────────
class LoginReq(BaseModel):
    email: str; password: str

@app.post("/api/mkt/login")
def mkt_login(body: LoginReq):
    if body.email != MKT_EMAIL or body.password != MKT_PASSWORD:
        raise HTTPException(401, "Invalid marketing credentials")
    token = jwt.encode({"sub": "marketing_team", "email": body.email}, JWT_SECRET, algorithm=JWT_ALGO)
    return {"token": token, "message": "Welcome to the Marketing Dashboard"}

def mkt_auth(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Not authenticated")
    try:
        jwt.decode(authorization.split(" ",1)[1], JWT_SECRET, algorithms=[JWT_ALGO])
    except JWTError:
        raise HTTPException(401, "Invalid token")
    return True

# ── STATS ─────────────────────────────────────────────────────────────────────
@app.get("/api/mkt/stats")
def stats(_=Depends(mkt_auth)):
    total    = uq1("SELECT COUNT(*) as c FROM leads")["c"]
    by_tier  = {r["recommended_action"]: r["cnt"] for r in
                uq("SELECT recommended_action, COUNT(*) as cnt FROM leads GROUP BY recommended_action")}
    avg_score= uq1("SELECT ROUND(AVG(lead_score),1) as a FROM leads")["a"] or 0
    total_users = uq1("SELECT COUNT(*) as c FROM users WHERE is_verified=1")["c"]
    purchases   = uq1("SELECT COUNT(*) as c FROM purchases")["c"]
    cart_active = uq1("SELECT COUNT(DISTINCT user_id) as c FROM cart")["c"]
    emails_sent = uq1("SELECT COUNT(*) as c FROM leads WHERE email_sent=1")["c"]

    # Score distribution buckets
    dist = {
        "0-20":  uq1("SELECT COUNT(*) as c FROM leads WHERE lead_score<20")["c"],
        "20-40": uq1("SELECT COUNT(*) as c FROM leads WHERE lead_score>=20 AND lead_score<40")["c"],
        "40-60": uq1("SELECT COUNT(*) as c FROM leads WHERE lead_score>=40 AND lead_score<60")["c"],
        "60-80": uq1("SELECT COUNT(*) as c FROM leads WHERE lead_score>=60 AND lead_score<80")["c"],
        "80-100":uq1("SELECT COUNT(*) as c FROM leads WHERE lead_score>=80")["c"],
    }
    return {
        "total_leads": total, "by_tier": by_tier, "avg_lead_score": avg_score,
        "total_users": total_users, "total_purchases": purchases,
        "active_carts": cart_active, "emails_sent": emails_sent,
        "score_distribution": dist,
    }

# ── LEADS ─────────────────────────────────────────────────────────────────────
@app.get("/api/mkt/leads")
def get_leads(tier: Optional[str]=None, search: Optional[str]=None, _=Depends(mkt_auth)):
    sql = """
        SELECT l.*, u.name, u.email, up.phone, up.whatsapp_opt_in,
               up.current_occupation, up.specialization, up.city
        FROM leads l
        JOIN users u ON l.user_id=u.id
        LEFT JOIN user_profiles up ON up.user_id=l.user_id
        WHERE 1=1
    """
    params = []
    if tier:
        sql += " AND l.recommended_action=?"; params.append(tier)
    if search:
        sql += " AND (u.name LIKE ? OR u.email LIKE ? OR l.course_type LIKE ?)"
        s = f"%{search}%"; params += [s, s, s]
    sql += " ORDER BY l.created_at DESC"
    return {"leads": uq(sql, params)}

@app.get("/api/mkt/leads/{lead_id}")
def get_lead(lead_id: int, _=Depends(mkt_auth)):
    lead = uq1("""
        SELECT l.*, u.name, u.email, up.phone, up.whatsapp_opt_in,
               up.current_occupation, up.specialization, up.city, up.age_bracket
        FROM leads l JOIN users u ON l.user_id=u.id
        LEFT JOIN user_profiles up ON up.user_id=l.user_id
        WHERE l.id=?
    """, (lead_id,))
    if not lead: raise HTTPException(404, "Lead not found")
    # Add behaviour events
    lead["behaviour_events"] = uq(
        "SELECT * FROM behaviour_events WHERE user_id=? ORDER BY created_at DESC LIMIT 20",
        (lead["user_id"],)
    )
    lead["coupons"] = uq(
        "SELECT * FROM coupons_issued WHERE user_id=? ORDER BY created_at DESC",
        (lead["user_id"],)
    )
    return lead

# ── EMAIL ─────────────────────────────────────────────────────────────────────
class SendEmailReq(BaseModel):
    lead_id: int; subject: str; body: str

@app.post("/api/mkt/send-email")
def send_email_to_lead(req: SendEmailReq, _=Depends(mkt_auth)):
    from email_service import send_marketing_email
    lead = uq1("""
        SELECT l.*, u.email, up.do_not_email FROM leads l
        JOIN users u ON l.user_id=u.id
        LEFT JOIN user_profiles up ON up.user_id=l.user_id
        WHERE l.id=?
    """, (req.lead_id,))
    if not lead: raise HTTPException(404, "Lead not found")
    if lead.get("do_not_email") == "Yes":
        return {"success": False, "message": "User opted out of emails"}
    ok, msg = send_marketing_email(lead["email"], req.subject, req.body)
    if ok:
        c = user_conn()
        c.execute("UPDATE leads SET email_sent=1, email_sent_at=datetime('now','localtime') WHERE id=?", (req.lead_id,))
        c.commit(); c.close()
    return {"success": ok, "message": msg}

# ── AI IMPROVE ────────────────────────────────────────────────────────────────
class ImproveReq(BaseModel):
    draft: str; tier: str; course: str; occupation: str; name: str

@app.post("/api/mkt/ai-improve")
def ai_improve(req: ImproveReq, _=Depends(mkt_auth)):
    """
    Improves a marketing team's email draft using GenAI.
    Currently uses mock templates. Swap for Claude API when key available.
    """
    from genai_mock import generate_content
    content = generate_content(
        name=req.name, occupation=req.occupation, specialization="your field",
        course=req.course, action=req.tier, trigger="manual_edit"
    )
    # Blend: keep team's subject line, improve the body
    improved_body = f"""[AI Enhanced Version]

{content['email_body']}

---
[Your original draft for reference:]
{req.draft}
"""
    return {
        "improved_subject": content["email_subject"],
        "improved_body":    content["email_body"],
        "whatsapp_message": content["whatsapp_message"],
        "note": "AI has enhanced your draft. Review before sending."
    }

# ── SMS QUEUE ─────────────────────────────────────────────────────────────────
class SMSReq(BaseModel):
    user_id: int; phone: str; message: str

@app.post("/api/mkt/sms-queue")
def queue_sms(req: SMSReq, _=Depends(mkt_auth)):
    mex("INSERT INTO sms_queue (user_id, phone, message) VALUES (?,?,?)",
        (req.user_id, req.phone, req.message))
    # Mock: in production, call Fast2SMS/MSG91 API here
    print(f"[SMS MOCK] To: {req.phone} | Message: {req.message[:50]}...")
    return {"success": True, "message": f"SMS queued for {req.phone} (mock mode — configure SMS API in .env to send real messages)"}

@app.get("/api/mkt/sms-queue")
def get_sms_queue(_=Depends(mkt_auth)):
    return {"messages": mq("SELECT * FROM sms_queue ORDER BY created_at DESC")}

# ── COUPON GENERATOR ──────────────────────────────────────────────────────────
class CouponReq(BaseModel):
    user_id: int; tier: str; discount_pct: int; expires_hours: int = 72

@app.post("/api/mkt/coupons/generate")
def generate_coupon(req: CouponReq, _=Depends(mkt_auth)):
    codes = {
        "Target Immediately":          "VIP_URGENT_25",
        "Nurture via Email/WhatsApp":  "FUTURE_READY_15",
        "Marketing Campaign":          "EARLY_BIRD_10",
        "Low Priority":                "",
    }
    code = codes.get(req.tier, f"XEDU_{req.discount_pct}OFF")
    if not code:
        raise HTTPException(400, "Low Priority users do not receive coupons.")
    c = user_conn()
    c.execute("""
        INSERT OR IGNORE INTO coupons_issued
        (user_id, coupon_code, discount_pct, tier, expires_at)
        VALUES (?,?,?,?,datetime('now','localtime',?))
    """, (req.user_id, code, req.discount_pct, req.tier, f"+{req.expires_hours} hours"))
    c.commit(); c.close()
    return {"coupon_code": code, "discount_pct": req.discount_pct, "message": "Coupon generated and assigned to user."}

@app.get("/api/mkt/coupons")
def all_coupons(_=Depends(mkt_auth)):
    c = user_conn()
    rows = c.execute("""
        SELECT ci.*, u.name, u.email FROM coupons_issued ci
        JOIN users u ON ci.user_id=u.id
        ORDER BY ci.created_at DESC
    """).fetchall()
    c.close()
    return {"coupons": [dict(r) for r in rows]}

# ── CAMPAIGN SCHEDULER ────────────────────────────────────────────────────────
class CampaignReq(BaseModel):
    name: str; tier: str; subject: str; body: str; scheduled_at: str

@app.post("/api/mkt/campaigns")
def schedule_campaign(req: CampaignReq, _=Depends(mkt_auth)):
    mex("INSERT INTO campaign_schedules (name,tier,subject,body,scheduled_at) VALUES (?,?,?,?,?)",
        (req.name, req.tier, req.subject, req.body, req.scheduled_at))
    return {"message": f"Campaign '{req.name}' scheduled for {req.scheduled_at}"}

@app.get("/api/mkt/campaigns")
def get_campaigns(_=Depends(mkt_auth)):
    return {"campaigns": mq("SELECT * FROM campaign_schedules ORDER BY scheduled_at DESC")}

# ── Q&A (answer questions) ────────────────────────────────────────────────────
class AnswerReq(BaseModel):
    qna_id: int; answer: str

@app.get("/api/mkt/qna")
def get_unanswered_qna(_=Depends(mkt_auth)):
    return {"questions": uq("""
        SELECT q.*, u.name as user_name FROM qna q
        JOIN users u ON q.user_id=u.id
        WHERE q.answer IS NULL ORDER BY q.created_at DESC
    """)}

@app.post("/api/mkt/qna/answer")
def answer_question(req: AnswerReq, _=Depends(mkt_auth)):
    c = user_conn()
    c.execute(
        "UPDATE qna SET answer=?, answered_at=datetime('now','localtime') WHERE id=?",
        (req.answer, req.qna_id)
    )
    c.commit(); c.close()
    return {"message": "Answer published."}

# ── CSV EXPORT ────────────────────────────────────────────────────────────────
@app.get("/api/mkt/export-csv")
def export_leads(_=Depends(mkt_auth)):
    leads = uq("""
        SELECT l.id, u.name, u.email, up.phone, l.course_type,
               up.current_occupation, up.city, l.lead_score,
               l.recommended_action, l.persona, l.trigger_reason,
               l.email_sent, l.created_at
        FROM leads l JOIN users u ON l.user_id=u.id
        LEFT JOIN user_profiles up ON up.user_id=l.user_id
        ORDER BY l.created_at DESC
    """)
    output = io.StringIO()
    if leads:
        writer = csv.DictWriter(output, fieldnames=leads[0].keys())
        writer.writeheader()
        writer.writerows(leads)
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=leads_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"}
    )


# ── COUPON DELETE ─────────────────────────────────────────────────────────────
@app.delete("/api/mkt/coupons/{coupon_id}")
def delete_coupon(coupon_id: int, _=Depends(mkt_auth)):
    c = user_conn()
    row = c.execute("SELECT id FROM coupons_issued WHERE id=?", (coupon_id,)).fetchone()
    if not row:
        c.close()
        raise HTTPException(404, "Coupon not found")
    c.execute("DELETE FROM coupons_issued WHERE id=?", (coupon_id,))
    c.commit(); c.close()
    return {"success": True, "message": "Coupon deleted"}


# ── CAMPAIGN DELETE ───────────────────────────────────────────────────────────
@app.delete("/api/mkt/campaigns/{campaign_id}")
def delete_campaign(campaign_id: int, _=Depends(mkt_auth)):
    row = mq("SELECT id FROM campaign_schedules WHERE id=?", (campaign_id,))
    if not row:
        raise HTTPException(404, "Campaign not found")
    mex("DELETE FROM campaign_schedules WHERE id=?", (campaign_id,))
    return {"success": True, "message": "Campaign deleted"}