"""
main.py — X Education Marketing Backend (port 8001)
Reads from the shared user DB. Marketing-specific tables stored here too.
"""
import os, csv, io, sqlite3, uuid, random
from urllib.parse import quote
from datetime import datetime
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response, RedirectResponse
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

PUBLIC_BASE_URL   = os.getenv("PUBLIC_BASE_URL", "http://localhost:8001")
USER_FRONTEND_URL = os.getenv("USER_FRONTEND_URL", "http://localhost:5173")
DEMO_MODE         = os.getenv("DEMO_MODE", "true").lower() == "true"
USER_BACKEND_URL  = os.getenv("USER_BACKEND_URL", "http://localhost:8000")
INTERNAL_API_KEY  = os.getenv("INTERNAL_API_KEY", "xedu-internal-dev")
MODEL_CARD_PATH   = os.getenv("MODEL_CARD_PATH", os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "user-backend", "ml_models", "model_card.json"))


def request_rescore(user_id: int, reason: str) -> dict | None:
    """Ask the user-backend to re-run the ML model for this user (closed loop)."""
    import json as _json
    import urllib.request
    req = urllib.request.Request(
        f"{USER_BACKEND_URL}/api/internal/rescore/{user_id}?reason={reason}",
        method="POST", headers={"X-Internal-Key": INTERNAL_API_KEY})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return _json.loads(r.read().decode())
    except Exception as e:
        print(f"[RESCORE] user {user_id} ({reason}) failed: {e}")
        return None

# Engagement tracking is click-only (see track_click below) — no pixel.
AB_TEST_MIN_SAMPLE = int(os.getenv("AB_TEST_MIN_SAMPLE", "1" if DEMO_MODE else "5"))

PLV_TIER_MULTIPLIER = {
    "Target Immediately": 1.5,
    "Nurture via Email/WhatsApp": 1.0,
    "Marketing Campaign": 0.6,
    "Low Priority": 0.2,
}

# ── DB helpers ────────────────────────────────────────────────────────────────
def user_conn():
    c = sqlite3.connect(USER_DB, check_same_thread=False, timeout=30)
    c.row_factory = sqlite3.Row
    return c

def mkt_conn():
    c = sqlite3.connect(MKT_DB, check_same_thread=False, timeout=30)
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

def uex(sql, params=()):
    c = user_conn()
    cur = c.execute(sql, params)
    c.commit()
    lid = cur.lastrowid
    c.close()
    return lid

def compute_plv(user_id, recommended_action, conversion_probability=50.0):
    spent = uq1("SELECT COALESCE(SUM(price_paid),0) as s FROM purchases WHERE user_id=?", (user_id,))["s"]
    avg_price = uq1("SELECT COALESCE(AVG(price),0) as p FROM cart")["p"] or 5000.0
    multiplier = PLV_TIER_MULTIPLIER.get(recommended_action, 0.3)
    p = float(conversion_probability or 0)
    p = p / 100.0 if p > 1 else p          # stored as 0-1 by predict_lead()
    future_value = avg_price * p * multiplier
    return round(spent + future_value, 2)

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
    c.execute("""CREATE TABLE IF NOT EXISTS ab_tests (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        name       TEXT,
        tier       TEXT,
        subject_a  TEXT,
        body_a     TEXT,
        subject_b  TEXT,
        body_b     TEXT,
        status     TEXT DEFAULT 'draft',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )""")
    c.commit(); c.close()
    print(f"[MKT-DB] Initialised -> {MKT_DB}")

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="X Education Marketing API", version="2.0.0")
app.add_middleware(CORSMiddleware,
    allow_origins=["http://localhost:5174","http://127.0.0.1:5174"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def startup():
    init_mkt_db()
    from apscheduler.schedulers.background import BackgroundScheduler
    from decay import lead_decay_job
    sched = BackgroundScheduler(timezone="Asia/Kolkata")
    sched.add_job(lead_decay_job, "interval", minutes=5)
    sched.start()
    print("[SCHEDULER] Lead decay job started")
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
    # one row per person: the latest lead of each user (a user gets a new lead row
    # for every enquiry/abandonment, which used to inflate every count)
    total    = uq1("SELECT COUNT(*) as c FROM (SELECT * FROM leads WHERE id IN (SELECT MAX(id) FROM leads GROUP BY user_id))")["c"]
    by_tier  = {r["recommended_action"]: r["cnt"] for r in
                uq("SELECT recommended_action, COUNT(*) as cnt FROM (SELECT * FROM leads WHERE id IN (SELECT MAX(id) FROM leads GROUP BY user_id)) GROUP BY recommended_action")}
    avg_score= uq1("SELECT ROUND(AVG(lead_score),1) as a FROM (SELECT * FROM leads WHERE id IN (SELECT MAX(id) FROM leads GROUP BY user_id))")["a"] or 0
    total_users = uq1("SELECT COUNT(*) as c FROM users WHERE is_verified=1")["c"]
    purchases   = uq1("SELECT COUNT(*) as c FROM purchases")["c"]
    cart_active = uq1("SELECT COUNT(DISTINCT user_id) as c FROM cart")["c"]
    emails_sent = uq1("SELECT COUNT(*) as c FROM leads WHERE email_sent=1")["c"]

    # Score distribution buckets
    dist = {
        "0-20":  uq1("SELECT COUNT(*) as c FROM (SELECT * FROM leads WHERE id IN (SELECT MAX(id) FROM leads GROUP BY user_id)) WHERE lead_score<20")["c"],
        "20-40": uq1("SELECT COUNT(*) as c FROM (SELECT * FROM leads WHERE id IN (SELECT MAX(id) FROM leads GROUP BY user_id)) WHERE lead_score>=20 AND lead_score<40")["c"],
        "40-60": uq1("SELECT COUNT(*) as c FROM (SELECT * FROM leads WHERE id IN (SELECT MAX(id) FROM leads GROUP BY user_id)) WHERE lead_score>=40 AND lead_score<60")["c"],
        "60-80": uq1("SELECT COUNT(*) as c FROM (SELECT * FROM leads WHERE id IN (SELECT MAX(id) FROM leads GROUP BY user_id)) WHERE lead_score>=60 AND lead_score<80")["c"],
        "80-100":uq1("SELECT COUNT(*) as c FROM (SELECT * FROM leads WHERE id IN (SELECT MAX(id) FROM leads GROUP BY user_id)) WHERE lead_score>=80")["c"],
    }
    return {
        "total_leads": total, "by_tier": by_tier, "avg_lead_score": avg_score,
        "total_users": total_users, "total_purchases": purchases,
        "active_carts": cart_active, "emails_sent": emails_sent,
        "score_distribution": dist,
    }

# ── LEADS ─────────────────────────────────────────────────────────────────────
@app.get("/api/mkt/leads")
def get_leads(tier: Optional[str]=None, search: Optional[str]=None, sort: Optional[str]=None, _=Depends(mkt_auth)):
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
    sql += " ORDER BY l.plv DESC" if sort == "plv" else " ORDER BY l.created_at DESC"
    return {"leads": uq(sql, params)}


# ── PRIORITY QUEUE (hot leads with high PLV) ───────────────────────────────────
@app.get("/api/mkt/priority-queue")
def priority_queue(limit: int = 20, _=Depends(mkt_auth)):
    leads = uq("""
        SELECT l.*, u.name, u.email, up.current_occupation
        FROM leads l JOIN users u ON l.user_id=u.id
        LEFT JOIN user_profiles up ON up.user_id=l.user_id
        WHERE l.recommended_action != 'Low Priority'
    """)
    for l in leads:
        l["priority_rank"] = round((l["lead_score"] or 0) * (l["plv"] or 0), 2)
    leads.sort(key=lambda l: l["priority_rank"], reverse=True)
    return {"priority_queue": leads[:limit]}

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

# ── ATTRIBUTION ───────────────────────────────────────────────────────────────
@app.get("/api/mkt/leads/{lead_id}/attribution")
def lead_attribution(lead_id: int, _=Depends(mkt_auth)):
    lead = uq1("SELECT * FROM leads WHERE id=?", (lead_id,))
    if not lead:
        raise HTTPException(404, "Lead not found")
    user_id = lead["user_id"]

    events = uq("""
        SELECT 'behaviour' as kind, event_type as label, course_slug, created_at
        FROM behaviour_events WHERE user_id=?
    """, (user_id,))
    emails = uq("""
        SELECT 'email' as kind,
               CASE WHEN opened_at IS NOT NULL THEN 'email_opened' ELSE 'email_sent' END as label,
               NULL as course_slug, COALESCE(opened_at, sent_at) as created_at
        FROM email_sends WHERE user_id=?
    """, (user_id,))
    clicks = uq("""
        SELECT 'email' as kind, 'email_clicked' as label, NULL as course_slug, first_clicked_at as created_at
        FROM email_sends WHERE user_id=? AND first_clicked_at IS NOT NULL
    """, (user_id,))
    purchases = uq("""
        SELECT 'purchase' as kind, course_title as label, course_slug, purchased_at as created_at
        FROM purchases WHERE user_id=?
    """, (user_id,))
    lead_touch = [{"kind": "lead_created", "label": lead["trigger_reason"], "course_slug": None, "created_at": lead["created_at"]}]

    timeline = sorted(
        [e for e in (events + emails + clicks + purchases + lead_touch) if e["created_at"]],
        key=lambda e: e["created_at"]
    )

    first_touch = timeline[0] if timeline else None
    last_touch_before_purchase = None
    first_purchase_at = next((p["created_at"] for p in purchases if p["created_at"]), None)
    if first_purchase_at:
        before = [e for e in timeline if e["created_at"] < first_purchase_at and e["kind"] != "purchase"]
        last_touch_before_purchase = before[-1] if before else None

    return {
        "lead_id": lead_id,
        "user_id": user_id,
        "timeline": timeline,
        "first_touch": first_touch,
        "last_touch_before_purchase": last_touch_before_purchase,
        "converted": first_purchase_at is not None,
    }


# ── CAMPAIGN INFLUENCE (dashboard aggregate) ───────────────────────────────────
@app.get("/api/mkt/campaign-influence")
def campaign_influence(_=Depends(mkt_auth)):
    sends = uq("""
        SELECT es.*, l.trigger_reason FROM email_sends es
        LEFT JOIN leads l ON l.id = es.lead_id
        WHERE es.sent_at IS NOT NULL
    """)
    influence = {}
    for send in sends:
        reason = send.get("trigger_reason") or "manual_send"
        bucket = influence.setdefault(reason, {"emails_sent": 0, "opens": 0, "clicks": 0, "influenced_conversions": 0})
        bucket["emails_sent"] += 1
        if send["open_count"]:
            bucket["opens"] += 1
        if send["click_count"]:
            bucket["clicks"] += 1
        touch_time = send.get("first_clicked_at") or send.get("opened_at")
        if touch_time and send["user_id"]:
            purchase = uq1("""
                SELECT id FROM purchases WHERE user_id=? AND purchased_at >= ?
                AND purchased_at <= datetime(?, '+7 days') LIMIT 1
            """, (send["user_id"], touch_time, touch_time))
            if purchase:
                bucket["influenced_conversions"] += 1
    return {"campaign_influence": influence}


# ── EXPLAINABILITY ────────────────────────────────────────────────────────────
@app.get("/api/mkt/leads/{lead_id}/explain")
def explain_lead_score(lead_id: int, _=Depends(mkt_auth)):
    """Factors are computed by the model at scoring time (what each signal added
    or removed, in points) and stored on the lead. Older leads fall back to the
    rule-of-thumb explanation."""
    import json as _json
    lead = uq1("""
        SELECT l.*, up.current_occupation FROM leads l
        LEFT JOIN user_profiles up ON up.user_id=l.user_id
        WHERE l.id=?
    """, (lead_id,))
    if not lead:
        raise HTTPException(404, "Lead not found")
    factors = None
    if lead.get("score_factors"):
        try:
            factors = _json.loads(lead["score_factors"]) or None
        except ValueError:
            factors = None
    if not factors:
        from explain import explain_lead
        lead["past_purchases"] = uq1(
            "SELECT COUNT(*) as n FROM purchases WHERE user_id=?", (lead["user_id"],)
        )["n"]
        factors = explain_lead(lead)
    return {"lead_id": lead_id, "lead_score": lead["lead_score"],
            "recommended_action": lead["recommended_action"],
            "model_version": lead.get("model_version"),
            "factors": factors}


@app.post("/api/mkt/leads/{lead_id}/rescore")
def rescore_lead(lead_id: int, _=Depends(mkt_auth)):
    lead = uq1("SELECT user_id FROM leads WHERE id=?", (lead_id,))
    if not lead:
        raise HTTPException(404, "Lead not found")
    res = request_rescore(lead["user_id"], "manual_rescore")
    if res is None:
        raise HTTPException(503, "User backend unreachable — is it running on port 8000?")
    return res


# ── MODEL HEALTH (closed-loop monitoring) ─────────────────────────────────────
@app.get("/api/mkt/model/health")
def model_health(window_days: int = 14, _=Depends(mkt_auth)):
    """
    Is the model telling the truth on REAL users? For every score snapshot old
    enough to know the outcome (or already followed by a purchase), compare the
    predicted probability with what actually happened, per tier.
    """
    import json as _json
    card = None
    try:
        with open(MODEL_CARD_PATH, encoding="utf-8") as f:
            card = _json.load(f)
    except (OSError, ValueError):
        pass
    window = f"+{int(window_days)} days"
    try:
        rows = uq(f"""
            SELECT s.tier, s.probability,
                   EXISTS(SELECT 1 FROM purchases p WHERE p.user_id=s.user_id
                          AND p.purchased_at >= s.created_at
                          AND p.purchased_at <= datetime(s.created_at, '{window}')) AS converted,
                   (s.created_at <= datetime('now','localtime','-{int(window_days)} days')) AS matured
            FROM score_snapshots s
            WHERE s.source != 'purchase_conversion'
              AND NOT EXISTS(SELECT 1 FROM purchases p WHERE p.user_id=s.user_id
                             AND p.purchased_at <= s.created_at)      -- already a customer
        """)
    except sqlite3.OperationalError:
        rows = []
    labelled = [r for r in rows if r["converted"] or r["matured"]]
    order = ["Target Immediately", "Nurture via Email/WhatsApp", "Marketing Campaign", "Low Priority"]
    tiers = []
    for t in order:
        g = [r for r in labelled if r["tier"] == t]
        if g:
            tiers.append({"tier": t, "snapshots": len(g),
                          "predicted_rate": round(sum(r["probability"] or 0 for r in g) / len(g), 3),
                          "actual_rate": round(sum(r["converted"] for r in g) / len(g), 3)})
    return {"model": card, "window_days": window_days,
            "snapshots_total": len(rows), "snapshots_labelled": len(labelled),
            "by_tier": tiers,
            "retrain_hint": "Run retrain-model.bat once you have 50+ labelled snapshots with some purchases."}


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

    token = uuid.uuid4().hex
    uex("INSERT INTO email_sends (lead_id, user_id, token, subject, body) VALUES (?,?,?,?,?)",
        (req.lead_id, lead["user_id"], token, req.subject, req.body))
    course_slug = (lead.get("course_type") or "").lower().replace(" ", "-")
    dest = f"{USER_FRONTEND_URL}/course/{course_slug}" if course_slug else USER_FRONTEND_URL
    click_url = f"{PUBLIC_BASE_URL}/api/mkt/track/click/{token}?to={quote(dest, safe='')}"

    ok, msg = send_marketing_email(lead["email"], req.subject, req.body, cta_url=click_url)
    if ok:
        uex("UPDATE leads SET email_sent=1, email_sent_at=datetime('now','localtime') WHERE id=?", (req.lead_id,))
    return {"success": ok, "message": msg}

# ── CLICK TRACKING (public, no auth — hit by browsers from the email CTA) ─────
# Engagement is tracked exclusively by this real click-through, not an
# invisible pixel: most email clients block remote images by default, so a
# pixel-based "open" signal was unreliable and often just never fired. A
# click both proves the email was opened AND shows genuine intent; it marks the
# send as opened+clicked and triggers a model rescore of the lead.

def _safe_redirect(to: str) -> str:
    # Only ever redirect to our own site - otherwise anyone could use this
    # public link to bounce people to a phishing page (open redirect).
    return to if to and to.startswith(USER_FRONTEND_URL) else USER_FRONTEND_URL


@app.get("/api/mkt/track/click/{token}")
def track_click(token: str, to: str = USER_FRONTEND_URL):
    """A click proves the email was opened AND shows intent. Instead of adding a
    hand-picked +10 (which changed the score but not the tier), we record the
    click and ask the model to rescore the lead — EmailOpenedCount is a model feature."""
    to = _safe_redirect(to)
    send = uq1("SELECT * FROM email_sends WHERE token=?", (token,))
    if send:
        uex("""UPDATE email_sends SET click_count = click_count + 1,
               open_count = open_count + 1,
               opened_at = COALESCE(opened_at, datetime('now','localtime')),
               first_clicked_at = COALESCE(first_clicked_at, datetime('now','localtime'))
               WHERE token=?""", (token,))
        if send["user_id"]:
            request_rescore(send["user_id"], "email_click")
    return RedirectResponse(to)


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

# ── A/B TESTING ───────────────────────────────────────────────────────────────
class AbTestReq(BaseModel):
    name: str; tier: str
    subject_a: str; body_a: str
    subject_b: str; body_b: str

@app.post("/api/mkt/ab-tests")
def create_ab_test(req: AbTestReq, _=Depends(mkt_auth)):
    test_id = mex("""
        INSERT INTO ab_tests (name, tier, subject_a, body_a, subject_b, body_b)
        VALUES (?,?,?,?,?,?)
    """, (req.name, req.tier, req.subject_a, req.body_a, req.subject_b, req.body_b))
    return {"id": test_id, "message": f"A/B test '{req.name}' created."}

@app.get("/api/mkt/ab-tests")
def list_ab_tests(_=Depends(mkt_auth)):
    return {"ab_tests": mq("SELECT * FROM ab_tests ORDER BY created_at DESC")}

@app.post("/api/mkt/ab-tests/{test_id}/send")
def send_ab_test(test_id: int, _=Depends(mkt_auth)):
    from email_service import send_marketing_email
    test = mq("SELECT * FROM ab_tests WHERE id=?", (test_id,))
    if not test:
        raise HTTPException(404, "A/B test not found")
    test = test[0]

    leads = uq("""
        SELECT l.id as lead_id, l.user_id, l.course_type, u.email, up.do_not_email
        FROM leads l JOIN users u ON l.user_id=u.id
        LEFT JOIN user_profiles up ON up.user_id=l.user_id
        WHERE l.recommended_action=?
    """, (test["tier"],))

    sent_count = {"A": 0, "B": 0}
    for lead in leads:
        if lead.get("do_not_email") == "Yes":
            continue
        variant = random.choice(["A", "B"])
        subject = test["subject_a"] if variant == "A" else test["subject_b"]
        body    = test["body_a"] if variant == "A" else test["body_b"]

        token = uuid.uuid4().hex
        uex("""INSERT INTO email_sends (lead_id, user_id, ab_test_id, variant, token, subject, body)
               VALUES (?,?,?,?,?,?,?)""", (lead["lead_id"], lead["user_id"], test_id, variant, token, subject, body))
        course_slug = (lead.get("course_type") or "").lower().replace(" ", "-")
        dest = f"{USER_FRONTEND_URL}/course/{course_slug}" if course_slug else USER_FRONTEND_URL
        click_url = f"{PUBLIC_BASE_URL}/api/mkt/track/click/{token}?to={quote(dest, safe='')}"

        ok, _msg = send_marketing_email(lead["email"], subject, body, cta_url=click_url)
        if ok:
            sent_count[variant] += 1

    mex("UPDATE ab_tests SET status='sent' WHERE id=?", (test_id,))
    return {"message": f"A/B test sent. A: {sent_count['A']}, B: {sent_count['B']}"}


@app.post("/api/mkt/ab-tests/{test_id}/seed-demo")
def seed_ab_test_demo(test_id: int, per_variant: int = 8, _=Depends(mkt_auth)):
    """
    Demo-only helper: A/B testing needs many real recipients to be
    statistically meaningful, which a classroom demo never has. This
    synthesizes `per_variant` extra sends per variant (capped at 25) with
    randomized open/click outcomes so 'View Results' has enough volume to
    clear AB_TEST_MIN_SAMPLE and declare a winner without waiting on real
    traffic. Only usable on an already-sent test.
    """
    test = mq("SELECT * FROM ab_tests WHERE id=?", (test_id,))
    if not test:
        raise HTTPException(404, "A/B test not found")
    if test[0]["status"] != "sent":
        raise HTTPException(400, "Send the test before seeding demo data")

    per_variant = max(1, min(per_variant, 25))
    # Give the two variants distinct random performance so a winner is
    # visible instead of a coin-flip every time.
    open_rate_a = random.uniform(0.35, 0.65)
    open_rate_b = random.uniform(0.35, 0.65)
    click_share = 0.5  # fraction of opens that also click through

    for variant, open_rate in (("A", open_rate_a), ("B", open_rate_b)):
        for _ in range(per_variant):
            token = uuid.uuid4().hex
            uex("""INSERT INTO email_sends (lead_id, user_id, ab_test_id, variant, token, subject, body)
                   VALUES (NULL, NULL, ?, ?, ?, '[demo seed]', '[demo seed]')""",
                (test_id, variant, token))
            opened = random.random() < open_rate
            clicked = opened and random.random() < click_share
            if opened:
                uex("""UPDATE email_sends SET open_count=1,
                       opened_at=datetime('now','localtime') WHERE token=?""", (token,))
            if clicked:
                uex("""UPDATE email_sends SET click_count=1,
                       first_clicked_at=datetime('now','localtime') WHERE token=?""", (token,))

    return {"message": f"Seeded {per_variant} demo sends per variant.", "min_sample_needed": AB_TEST_MIN_SAMPLE}


@app.get("/api/mkt/ab-tests/{test_id}/results")
def ab_test_results(test_id: int, _=Depends(mkt_auth)):
    test = mq("SELECT * FROM ab_tests WHERE id=?", (test_id,))
    if not test:
        raise HTTPException(404, "A/B test not found")

    def variant_stats(variant):
        sends = uq("""
            SELECT COUNT(*) as sent,
                   SUM(CASE WHEN open_count>0 THEN 1 ELSE 0 END) as opened,
                   SUM(CASE WHEN click_count>0 THEN 1 ELSE 0 END) as clicked
            FROM email_sends WHERE ab_test_id=? AND variant=?
        """, (test_id, variant))[0]
        sent = sends["sent"] or 0
        opened = sends["opened"] or 0
        clicked = sends["clicked"] or 0
        return {
            "sent": sent, "opened": opened, "clicked": clicked,
            "open_rate": round(opened / sent * 100, 1) if sent else 0,
            "click_rate": round(clicked / sent * 100, 1) if sent else 0,
        }

    a_stats = variant_stats("A")
    b_stats = variant_stats("B")
    winner = None
    if a_stats["sent"] >= AB_TEST_MIN_SAMPLE and b_stats["sent"] >= AB_TEST_MIN_SAMPLE:
        winner = "A" if a_stats["open_rate"] >= b_stats["open_rate"] else "B"

    return {"test": test[0], "variant_a": a_stats, "variant_b": b_stats, "winner": winner,
            "min_sample_needed": AB_TEST_MIN_SAMPLE}


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