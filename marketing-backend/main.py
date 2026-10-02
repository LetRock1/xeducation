"""
main.py — X Education Marketing Backend (port 8001)

Reads and writes the shared user database (leads, emails, coupons ...) and
keeps marketing-only tables (campaigns, A/B tests, WhatsApp log) in its own
small database.

Background jobs (started on boot):
  * every minute  — send campaigns whose scheduled time has come
  * every 5 min   — lead decay (decay.py)
"""
import csv
import io
import json
import os
import random
import re
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import quote

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from jose import JWTError, jwt
from pydantic import BaseModel

import catalog
import coach
from email_service import send_marketing_email, send_simple_email
from stats_utils import sample_size_per_variant, two_proportion_test

load_dotenv()

USER_DB = os.getenv("USER_DB_PATH", "../user-backend/xeducation_user.db")
MKT_DB = os.path.join(os.path.dirname(__file__), "xeducation_marketing.db")
MKT_EMAIL = os.getenv("MARKETING_EMAIL", "admin@xeducation.in")
MKT_PASSWORD = os.getenv("MARKETING_PASSWORD", "marketing_admin_2025")
JWT_SECRET = os.getenv("JWT_SECRET", "mkt_secret")
JWT_ALGO = "HS256"
TOKEN_HOURS = 12

PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8001")
USER_FRONTEND_URL = os.getenv("USER_FRONTEND_URL", "http://localhost:5173")
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"
USER_BACKEND_URL = os.getenv("USER_BACKEND_URL", "http://localhost:8000")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "xedu-internal-dev")
MODEL_CARD_PATH = os.getenv("MODEL_CARD_PATH", os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "user-backend", "ml_models", "model_card.json"))

CONVERSION_WINDOW_DAYS = 14
TIERS = ["Target Immediately", "Nurture via Email/WhatsApp", "Marketing Campaign", "Low Priority"]
# One row per person: a user gets a new lead row for every enquiry / abandonment,
# so lists, stats, campaigns and A/B tests work on each user's LATEST lead.
LATEST = "(SELECT * FROM leads WHERE id IN (SELECT MAX(id) FROM leads GROUP BY user_id))"


# ── DB helpers ────────────────────────────────────────────────────────────────
def _conn(path):
    c = sqlite3.connect(path, check_same_thread=False, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout=30000")
    return c


def uq(sql, params=()):
    c = _conn(USER_DB)
    try:
        return [dict(r) for r in c.execute(sql, params).fetchall()]
    finally:
        c.close()


def uq1(sql, params=()):
    rows = uq(sql, params)
    return rows[0] if rows else None


def uex(sql, params=()):
    c = _conn(USER_DB)
    try:
        cur = c.execute(sql, params)
        c.commit()
        return cur.lastrowid
    finally:
        c.close()


def mq(sql, params=()):
    c = _conn(MKT_DB)
    try:
        return [dict(r) for r in c.execute(sql, params).fetchall()]
    finally:
        c.close()


def mex(sql, params=()):
    c = _conn(MKT_DB)
    try:
        cur = c.execute(sql, params)
        c.commit()
        return cur.lastrowid
    finally:
        c.close()


def mclaim(sql, params=()):
    """Run a guarded UPDATE and say whether it changed a row — used so that a campaign
    or A/B test can only be sent once, even if the timer and a button press collide."""
    c = _conn(MKT_DB)
    try:
        cur = c.execute(sql, params)
        c.commit()
        return cur.rowcount == 1
    finally:
        c.close()


def request_rescore(user_id: int, reason: str):
    """Ask the user-backend to re-run the ML model for this user (closed loop)."""
    import urllib.request
    req = urllib.request.Request(
        f"{USER_BACKEND_URL}/api/internal/rescore/{user_id}?reason={reason}",
        method="POST", headers={"X-Internal-Key": INTERNAL_API_KEY})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"[RESCORE] user {user_id} ({reason}) failed: {e}")
        return None


# ── Marketing DB ──────────────────────────────────────────────────────────────
def init_mkt_db():
    c = _conn(MKT_DB)
    c.execute("""CREATE TABLE IF NOT EXISTS campaign_schedules (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, tier TEXT, subject TEXT, body TEXT,
        scheduled_at TEXT, sent INTEGER DEFAULT 0, sent_at TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime')))""")
    c.execute("""CREATE TABLE IF NOT EXISTS sms_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, phone TEXT, message TEXT,
        status TEXT DEFAULT 'pending', created_at TEXT DEFAULT (datetime('now','localtime')))""")
    c.execute("""CREATE TABLE IF NOT EXISTS ab_tests (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, tier TEXT, subject_a TEXT, body_a TEXT,
        subject_b TEXT, body_b TEXT, status TEXT DEFAULT 'draft',
        created_at TEXT DEFAULT (datetime('now','localtime')))""")
    for sql in ("ALTER TABLE campaign_schedules ADD COLUMN status TEXT DEFAULT 'scheduled'",
                "ALTER TABLE campaign_schedules ADD COLUMN recipients INTEGER DEFAULT 0",
                "ALTER TABLE campaign_schedules ADD COLUMN error TEXT",
                "ALTER TABLE sms_queue ADD COLUMN channel TEXT DEFAULT 'whatsapp'",
                "ALTER TABLE sms_queue ADD COLUMN lead_id INTEGER",
                "ALTER TABLE ab_tests ADD COLUMN sent_at TEXT"):
        try:
            c.execute(sql)
        except sqlite3.OperationalError:
            pass
    c.commit()
    c.close()
    print(f"[MKT-DB] Initialised -> {MKT_DB}")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="X Education Marketing API", version="3.0.0")
app.add_middleware(CORSMiddleware,
                   allow_origins=["http://localhost:5174", "http://127.0.0.1:5174"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def startup():
    init_mkt_db()
    from apscheduler.schedulers.background import BackgroundScheduler
    from decay import lead_decay_job
    sched = BackgroundScheduler(timezone="Asia/Kolkata",
                                job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300})
    sched.add_job(lead_decay_job, "interval", minutes=5)
    sched.add_job(run_due_campaigns, "interval", minutes=1)
    sched.start()
    print("[SCHEDULER] Lead decay (5 min) and campaign sender (1 min) started")
    print("[API] Marketing Backend running on port 8001")


# ── Auth ──────────────────────────────────────────────────────────────────────
class LoginReq(BaseModel):
    email: str
    password: str


@app.post("/api/mkt/login")
def mkt_login(body: LoginReq):
    if body.email.strip().lower() != MKT_EMAIL.lower() or body.password != MKT_PASSWORD:
        raise HTTPException(401, "Invalid marketing credentials")
    exp = datetime.utcnow() + timedelta(hours=TOKEN_HOURS)
    token = jwt.encode({"sub": "marketing_team", "email": body.email, "exp": exp}, JWT_SECRET, algorithm=JWT_ALGO)
    return {"token": token, "message": "Welcome to the Marketing Dashboard"}


def mkt_auth(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Not authenticated")
    try:
        jwt.decode(authorization.split(" ", 1)[1], JWT_SECRET, algorithms=[JWT_ALGO])
    except JWTError:
        raise HTTPException(401, "Session expired — please log in again")
    return True


# ── Outreach helpers ──────────────────────────────────────────────────────────
def _course_url(slug):
    return f"{USER_FRONTEND_URL}/courses/{slug}" if catalog.get_course(slug) else f"{USER_FRONTEND_URL}/courses"


def _lead_slug(lead):
    return lead.get("course_slug") or catalog.slug_for_title(lead.get("course_type"))


def _personalise(text, name, slug):
    first = (name or "there").split()[0]
    return (text or "").replace("{first_name}", first).replace("{name}", name or first) \
        .replace("{course}", catalog.title_of(slug, "our programmes"))


def tracked_send(user_id, email, subject, body, course_slug=None, lead_id=None,
                 campaign_id=None, campaign_name=None, ab_test_id=None, variant="A"):
    """Every marketing email: honours opt-out, click-tracked CTA, working unsubscribe."""
    pref = uq1("SELECT do_not_email FROM user_profiles WHERE user_id=?", (user_id,)) or {}
    if pref.get("do_not_email") == "Yes":
        return False, "User opted out of emails"
    token = uuid.uuid4().hex
    uex("""INSERT INTO email_sends (lead_id, user_id, campaign_id, campaign_name, ab_test_id, variant, token, subject, body)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (lead_id, user_id, campaign_id, campaign_name, ab_test_id, variant, token, subject, body))
    click = f"{PUBLIC_BASE_URL}/api/mkt/track/click/{token}?to={quote(_course_url(course_slug), safe='')}"
    unsub = f"{PUBLIC_BASE_URL}/api/mkt/unsubscribe/{token}"
    ok, msg = send_marketing_email(email, subject, body, cta_url=click, unsubscribe_url=unsub)
    if ok and lead_id:
        uex("UPDATE leads SET email_sent=1, email_sent_at=datetime('now','localtime') WHERE id=?", (lead_id,))
    return ok, msg


def _conversions_after(sends):
    """How many recipients bought within CONVERSION_WINDOW_DAYS after their email."""
    n = 0
    for s in sends:
        if s.get("user_id") and uq1(
                f"""SELECT 1 AS x FROM purchases WHERE user_id=? AND purchased_at >= ?
                    AND purchased_at <= datetime(?, '+{CONVERSION_WINDOW_DAYS} days') LIMIT 1""",
                (s["user_id"], s["sent_at"], s["sent_at"])):
            n += 1
    return n


# ── RUN AUTOMATIONS NOW (demo button) ─────────────────────────────────────────
@app.post("/api/mkt/run-automations")
def run_automations(_=Depends(mkt_auth)):
    """Asks the user-backend to run its automation jobs now (instead of the 5-minute timer)."""
    import urllib.error
    import urllib.request
    req = urllib.request.Request(f"{USER_BACKEND_URL}/api/debug/trigger-jobs", method="POST",
                                 headers={"X-Internal-Key": INTERNAL_API_KEY})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise HTTPException(e.code, "The user backend refused — check INTERNAL_API_KEY in both .env files.")
    except Exception:
        raise HTTPException(503, "User backend unreachable — is it running on port 8000?")


# ── PIPELINE FORECAST (from calibrated probabilities) ─────────────────────────
@app.get("/api/mkt/forecast")
def pipeline_forecast(_=Depends(mkt_auth)):
    """
    Revenue we can expect from people who have not bought yet. Each lead's
    calibrated probability x the price of the course they are interested in;
    the 90% range comes from simulating who converts (independent outcomes).
    Only meaningful while the model is calibrated — see Model health.
    """
    rows = uq(f"""SELECT l.conversion_probability AS p, l.course_slug, l.course_type, l.recommended_action AS tier
                  FROM {LATEST} l WHERE l.user_id NOT IN (SELECT user_id FROM purchases)""")
    avg_price = catalog.average_price()
    items = []
    for r in rows:
        p = float(r["p"] or 0)
        p = p / 100 if p > 1 else p
        price = catalog.price_of(r["course_slug"] or catalog.slug_for_title(r["course_type"])) or avg_price
        items.append((min(max(p, 0.0), 1.0), float(price), r["tier"]))
    if not items:
        return {"open_leads": 0, "expected_revenue": 0, "expected_customers": 0, "by_tier": [],
                "range_90": [0, 0], "customers_range_90": [0, 0]}
    exp_rev = sum(p * price for p, price, _ in items)
    exp_n = sum(p for p, _, _ in items)
    if len(items) <= 3000:
        rng = random.Random(42)
        draws, buyers = [], []
        for _ in range(2000):
            rev = n = 0
            for p, price, _t in items:
                if rng.random() < p:
                    rev += price
                    n += 1
            draws.append(rev)
            buyers.append(n)
        draws.sort()
        buyers.sort()
        q = lambda xs, f: xs[min(int(f * len(xs)), len(xs) - 1)]
        rev_range, n_range = [q(draws, 0.05), q(draws, 0.95)], [q(buyers, 0.05), q(buyers, 0.95)]
    else:   # many leads: the normal approximation is accurate and much faster
        sd_rev = sum(p * (1 - p) * price ** 2 for p, price, _ in items) ** 0.5
        sd_n = sum(p * (1 - p) for p, _, _ in items) ** 0.5
        rev_range = [max(0, round(exp_rev - 1.645 * sd_rev)), round(exp_rev + 1.645 * sd_rev)]
        n_range = [max(0, round(exp_n - 1.645 * sd_n)), round(exp_n + 1.645 * sd_n)]
    by_tier = []
    for t in TIERS:
        g = [(p, price) for p, price, tier in items if tier == t]
        if g:
            by_tier.append({"tier": t, "leads": len(g), "expected_customers": round(sum(p for p, _ in g), 1),
                            "expected_revenue": round(sum(p * price for p, price in g))})
    return {"open_leads": len(items),
            "expected_revenue": round(exp_rev),
            "range_90": rev_range,
            "expected_customers": round(exp_n, 1),
            "customers_range_90": n_range,
            "by_tier": by_tier,
            "note": "Assumes the scores are calibrated (compare predicted vs actual in Model health)."}


# ── STATS ─────────────────────────────────────────────────────────────────────
@app.get("/api/mkt/stats")
def stats(_=Depends(mkt_auth)):
    by_tier = {r["recommended_action"]: r["cnt"] for r in
               uq(f"SELECT recommended_action, COUNT(*) AS cnt FROM {LATEST} GROUP BY recommended_action")}
    buckets = [("0-20", 0, 20), ("20-40", 20, 40), ("40-60", 40, 60), ("60-80", 60, 80), ("80-100", 80, 101)]
    dist = {name: uq1(f"SELECT COUNT(*) AS c FROM {LATEST} WHERE lead_score>=? AND lead_score<?", (lo, hi))["c"]
            for name, lo, hi in buckets}
    return {
        "total_leads": uq1(f"SELECT COUNT(*) AS c FROM {LATEST}")["c"],
        "by_tier": by_tier,
        "avg_lead_score": uq1(f"SELECT ROUND(AVG(lead_score),1) AS a FROM {LATEST}")["a"] or 0,
        "total_users": uq1("SELECT COUNT(*) AS c FROM users WHERE is_verified=1")["c"],
        "total_purchases": uq1("SELECT COUNT(*) AS c FROM purchases")["c"],
        "revenue": uq1("SELECT COALESCE(SUM(price_paid),0) AS r FROM purchases")["r"],
        "active_carts": uq1("SELECT COUNT(DISTINCT user_id) AS c FROM cart")["c"],
        "emails_sent": uq1("SELECT COUNT(*) AS c FROM email_sends WHERE subject != '[demo seed]'")["c"],
        "email_clicks": uq1("SELECT COUNT(*) AS c FROM email_sends WHERE click_count > 0")["c"],
        "open_callbacks": uq1("SELECT COUNT(*) AS c FROM callback_requests WHERE status='open'")["c"],
        "demo_users": uq1("SELECT COUNT(*) AS c FROM users WHERE email LIKE '%@demo.xeducation.test'")["c"],
        "score_distribution": dist,
    }


# ── LEADS (one row per person) ────────────────────────────────────────────────
@app.get("/api/mkt/leads")
def get_leads(tier: Optional[str] = None, search: Optional[str] = None, sort: Optional[str] = None,
              _=Depends(mkt_auth)):
    sql = f"""
        SELECT l.*, u.name, u.email, up.phone, up.whatsapp_opt_in, up.do_not_email, up.do_not_call,
               up.current_occupation, up.specialization, up.city,
               (SELECT COUNT(*) FROM leads x WHERE x.user_id=l.user_id) AS touches,
               (SELECT COUNT(*) FROM purchases p WHERE p.user_id=l.user_id) AS purchases,
               (SELECT COUNT(*) FROM callback_requests cb WHERE cb.user_id=l.user_id AND cb.status='open') AS open_callbacks
        FROM {LATEST} l
        JOIN users u ON l.user_id=u.id
        LEFT JOIN user_profiles up ON up.user_id=l.user_id
        WHERE 1=1"""
    params = []
    if tier:
        sql += " AND l.recommended_action=?"
        params.append(tier)
    if search:
        sql += " AND (u.name LIKE ? OR u.email LIKE ? OR l.course_type LIKE ?)"
        params += [f"%{search}%"] * 3
    sql += {"plv": " ORDER BY l.plv DESC", "score": " ORDER BY l.lead_score DESC"}.get(sort, " ORDER BY l.created_at DESC")
    return {"leads": uq(sql, params)}


@app.get("/api/mkt/priority-queue")
def priority_queue(limit: int = 20, _=Depends(mkt_auth)):
    """People most worth contacting now: expected value = P(convert) × course price (PLV)."""
    leads = uq(f"""
        SELECT l.*, u.name, u.email, up.current_occupation, up.phone
        FROM {LATEST} l JOIN users u ON l.user_id=u.id
        LEFT JOIN user_profiles up ON up.user_id=l.user_id
        WHERE l.recommended_action != 'Low Priority'
          AND l.user_id NOT IN (SELECT user_id FROM purchases)
    """)
    for lead in leads:
        lead["priority_rank"] = round((lead["plv"] or 0), 2)
    leads.sort(key=lambda x: x["priority_rank"], reverse=True)
    return {"priority_queue": leads[:limit]}


@app.get("/api/mkt/leads/{lead_id}")
def get_lead(lead_id: int, _=Depends(mkt_auth)):
    lead = uq1("""
        SELECT l.*, u.name, u.email, up.phone, up.whatsapp_opt_in, up.do_not_email, up.do_not_call,
               up.current_occupation, up.specialization, up.city, up.age_bracket
        FROM leads l JOIN users u ON l.user_id=u.id
        LEFT JOIN user_profiles up ON up.user_id=l.user_id
        WHERE l.id=?""", (lead_id,))
    if not lead:
        raise HTTPException(404, "Lead not found")
    uid = lead["user_id"]
    lead["course_slug"] = _lead_slug(lead)
    lead["behaviour_events"] = uq("SELECT * FROM behaviour_events WHERE user_id=? ORDER BY id DESC LIMIT 30", (uid,))
    lead["coupons"] = uq("SELECT * FROM coupons_issued WHERE user_id=? ORDER BY created_at DESC", (uid,))
    lead["touches"] = uq("""SELECT id, trigger_reason, lead_score, recommended_action, email_sent, created_at
                            FROM leads WHERE user_id=? ORDER BY id DESC""", (uid,))
    lead["score_history"] = uq("SELECT * FROM lead_score_history WHERE user_id=? ORDER BY id DESC LIMIT 30", (uid,))
    lead["emails"] = uq("""SELECT id, subject, sent_at, click_count, first_clicked_at, campaign_name, ab_test_id, variant
                           FROM email_sends WHERE user_id=? ORDER BY id DESC LIMIT 20""", (uid,))
    lead["purchases"] = uq("SELECT * FROM purchases WHERE user_id=? ORDER BY purchased_at DESC", (uid,))
    lead["chat"] = uq("""SELECT role, text, intent, created_at FROM chat_messages WHERE user_id=?
                         ORDER BY id DESC LIMIT 30""", (uid,))[::-1]
    lead["callbacks"] = uq("SELECT * FROM callback_requests WHERE user_id=? ORDER BY id DESC", (uid,))
    lead["tasks"] = uq("SELECT * FROM sales_tasks WHERE user_id=? ORDER BY id DESC LIMIT 10", (uid,))
    for key, field in (("nba", "nba_json"), ("tips", "tips_json")):
        try:
            lead[key] = json.loads(lead.get(field) or "null")
        except ValueError:
            lead[key] = None
    if not lead.get("nba"):
        # show the latest decision taken for this person, if any
        latest = uq1("SELECT options_json, action, policy, model_version, trigger_reason FROM nba_decisions "
                     "WHERE user_id=? ORDER BY id DESC LIMIT 1", (uid,))
        if latest:
            lead["nba"] = {"action": latest["action"], "label": latest["action"], "policy": latest["policy"],
                           "why": f"Decided at the '{latest['trigger_reason']}' trigger.",
                           "detail": f"model {latest['model_version']}",
                           "options": json.loads(latest["options_json"] or "[]")}
    return lead


# ── ATTRIBUTION ───────────────────────────────────────────────────────────────
@app.get("/api/mkt/leads/{lead_id}/attribution")
def lead_attribution(lead_id: int, _=Depends(mkt_auth)):
    lead = uq1("SELECT * FROM leads WHERE id=?", (lead_id,))
    if not lead:
        raise HTTPException(404, "Lead not found")
    uid = lead["user_id"]
    events = uq("""SELECT 'behaviour' AS kind, event_type AS label, course_slug, created_at
                   FROM behaviour_events WHERE user_id=?""", (uid,))
    emails = uq("""SELECT 'email' AS kind, 'email_sent' AS label, NULL AS course_slug, sent_at AS created_at
                   FROM email_sends WHERE user_id=?""", (uid,))
    clicks = uq("""SELECT 'email' AS kind, 'email_clicked' AS label, NULL AS course_slug, first_clicked_at AS created_at
                   FROM email_sends WHERE user_id=? AND first_clicked_at IS NOT NULL""", (uid,))
    purchases = uq("""SELECT 'purchase' AS kind, course_title AS label, course_slug, purchased_at AS created_at
                      FROM purchases WHERE user_id=?""", (uid,))
    touches = uq("""SELECT 'lead_created' AS kind, trigger_reason AS label, course_slug, created_at
                    FROM leads WHERE user_id=?""", (uid,))
    timeline = sorted([e for e in events + emails + clicks + purchases + touches if e["created_at"]],
                      key=lambda e: e["created_at"])
    first_purchase_at = min((p["created_at"] for p in purchases if p["created_at"]), default=None)
    last_touch = None
    if first_purchase_at:
        before = [e for e in timeline if e["created_at"] < first_purchase_at and e["kind"] != "purchase"]
        last_touch = before[-1] if before else None
    return {"lead_id": lead_id, "user_id": uid, "timeline": timeline,
            "first_touch": timeline[0] if timeline else None,
            "last_touch_before_purchase": last_touch, "converted": first_purchase_at is not None}


@app.get("/api/mkt/campaign-influence")
def campaign_influence(_=Depends(mkt_auth)):
    sends = uq("""SELECT es.*, l.trigger_reason FROM email_sends es LEFT JOIN leads l ON l.id = es.lead_id
                  WHERE es.sent_at IS NOT NULL AND es.user_id IS NOT NULL""")
    influence = {}
    for send in sends:
        reason = ("ab_test" if send.get("ab_test_id") else
                  "campaign" if send.get("campaign_id") or send.get("campaign_name")
                  else send.get("trigger_reason") or "manual_send")
        bucket = influence.setdefault(reason, {"emails_sent": 0, "opens": 0, "clicks": 0, "influenced_conversions": 0})
        bucket["emails_sent"] += 1
        if send["click_count"]:
            bucket["clicks"] += 1
            bucket["opens"] += 1
            if uq1(f"""SELECT 1 AS x FROM purchases WHERE user_id=? AND purchased_at >= ?
                       AND purchased_at <= datetime(?, '+{CONVERSION_WINDOW_DAYS} days') LIMIT 1""",
                   (send["user_id"], send["first_clicked_at"], send["first_clicked_at"])):
                bucket["influenced_conversions"] += 1
    return {"campaign_influence": influence}


# ── EXPLAINABILITY / RESCORE / MODEL HEALTH ───────────────────────────────────
@app.get("/api/mkt/leads/{lead_id}/explain")
def explain_lead_score(lead_id: int, _=Depends(mkt_auth)):
    """Factors are computed by the model at scoring time (points each signal added
    or removed) and stored on the lead."""
    lead = uq1("SELECT * FROM leads WHERE id=?", (lead_id,))
    if not lead:
        raise HTTPException(404, "Lead not found")
    try:
        factors = json.loads(lead.get("score_factors") or "[]") or []
    except ValueError:
        factors = []
    note = None if factors else ("This lead was scored before explanations were stored. "
                                 "Click “Re-score now” to compute them with the current model.")
    return {"lead_id": lead_id, "lead_score": lead["lead_score"],
            "recommended_action": lead["recommended_action"],
            "model_version": lead.get("model_version"), "factors": factors, "note": note}


@app.post("/api/mkt/leads/{lead_id}/rescore")
def rescore_lead(lead_id: int, _=Depends(mkt_auth)):
    lead = uq1("SELECT user_id FROM leads WHERE id=?", (lead_id,))
    if not lead:
        raise HTTPException(404, "Lead not found")
    res = request_rescore(lead["user_id"], "manual_rescore")
    if res is None:
        raise HTTPException(503, "User backend unreachable — is it running on port 8000?")
    return res


@app.get("/api/mkt/model/health")
def model_health(window_days: int = 14, _=Depends(mkt_auth)):
    """Calibration on REAL users: predicted vs actual conversion per tier, using
    score snapshots whose outcome is known (bought, or the window has passed)."""
    card = None
    try:
        with open(MODEL_CARD_PATH, encoding="utf-8") as f:
            card = json.load(f)
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
                             AND p.purchased_at <= s.created_at)""")
    except sqlite3.OperationalError:
        rows = []
    labelled = [r for r in rows if r["converted"] or r["matured"]]
    tiers = []
    for t in TIERS:
        g = [r for r in labelled if r["tier"] == t]
        if g:
            tiers.append({"tier": t, "snapshots": len(g),
                          "predicted_rate": round(sum(r["probability"] or 0 for r in g) / len(g), 3),
                          "actual_rate": round(sum(r["converted"] for r in g) / len(g), 3)})
    return {"model": card, "window_days": window_days, "snapshots_total": len(rows),
            "snapshots_labelled": len(labelled), "by_tier": tiers,
            "retrain_hint": "Run retrain-model.bat once you have 50+ labelled snapshots with some purchases."}


# ── EMAIL ─────────────────────────────────────────────────────────────────────
class SendEmailReq(BaseModel):
    lead_id: int
    subject: str
    body: str


@app.post("/api/mkt/send-email")
def send_email_to_lead(req: SendEmailReq, _=Depends(mkt_auth)):
    lead = uq1("SELECT l.*, u.email, u.name FROM leads l JOIN users u ON l.user_id=u.id WHERE l.id=?", (req.lead_id,))
    if not lead:
        raise HTTPException(404, "Lead not found")
    if not req.subject.strip() or not req.body.strip():
        raise HTTPException(400, "Subject and body are required.")
    slug = _lead_slug(lead)
    ok, msg = tracked_send(lead["user_id"], lead["email"], _personalise(req.subject, lead["name"], slug),
                           _personalise(req.body, lead["name"], slug), course_slug=slug, lead_id=req.lead_id)
    return {"success": ok, "message": msg}


def _safe_redirect(to: str) -> str:
    # Only redirect to our own site — otherwise this public link could bounce people to a phishing page.
    return to if to and to.startswith(USER_FRONTEND_URL) else USER_FRONTEND_URL


@app.get("/api/mkt/track/click/{token}")
def track_click(token: str, to: str = USER_FRONTEND_URL):
    """A click proves the email was opened AND shows intent. It is recorded and the
    lead is re-scored by the model (EmailOpenedCount is a model feature)."""
    to = _safe_redirect(to)
    send = uq1("SELECT * FROM email_sends WHERE token=?", (token,))
    if send:
        uex("""UPDATE email_sends SET click_count = click_count + 1, open_count = open_count + 1,
               opened_at = COALESCE(opened_at, datetime('now','localtime')),
               first_clicked_at = COALESCE(first_clicked_at, datetime('now','localtime'))
               WHERE token=?""", (token,))
        if send["user_id"]:
            request_rescore(send["user_id"], "email_click")
    return RedirectResponse(to)


@app.get("/api/mkt/unsubscribe/{token}", response_class=HTMLResponse)
def unsubscribe(token: str):
    """One-click unsubscribe from the link in every marketing email."""
    send = uq1("SELECT user_id FROM email_sends WHERE token=?", (token,))
    if send and send["user_id"]:
        uex("INSERT OR IGNORE INTO user_profiles (user_id) VALUES (?)", (send["user_id"],))
        uex("UPDATE user_profiles SET do_not_email='Yes' WHERE user_id=?", (send["user_id"],))
        msg = "You've been unsubscribed from X Education marketing emails."
    else:
        msg = "This unsubscribe link is not valid any more."
    return f"""<html><body style="font-family:Segoe UI,sans-serif;background:#f8fafc;display:flex;
      align-items:center;justify-content:center;height:100vh;margin:0"><div style="background:white;padding:32px;
      border-radius:12px;border:1px solid #e2e8f0;max-width:420px;text-align:center">
      <h2 style="color:#0B1426;margin-top:0">X Education</h2><p style="color:#334155">{msg}</p>
      <p style="color:#64748b;font-size:13px">You can turn emails back on any time in Settings on the website.</p>
      <a href="{USER_FRONTEND_URL}" style="color:#0284c7">Back to the website</a></div></body></html>"""


# ── SALES ACTIONS (calls / WhatsApp chosen by next-best-action) ───────────────
class TaskDone(BaseModel):
    outcome: str = "reached"          # reached | no_answer | not_interested | sent


@app.get("/api/mkt/actions")
def sales_actions(status: str = "open", _=Depends(mkt_auth)):
    """Today's action list: who to call / message, ranked by expected extra profit."""
    rows = uq("""
        SELECT t.*, u.name, u.email, up.phone, up.whatsapp_opt_in, l.lead_score, l.recommended_action,
               l.course_type, l.course_slug, l.tips_json
        FROM sales_tasks t JOIN users u ON u.id=t.user_id
        LEFT JOIN user_profiles up ON up.user_id=t.user_id
        LEFT JOIN leads l ON l.id=t.lead_id
        WHERE (?='all' OR t.status=?)
        ORDER BY CASE WHEN t.status='open' THEN 0 ELSE 1 END, t.expected_gain DESC, t.id DESC""", (status, status))
    for r in rows:
        try:
            r["tips"] = json.loads(r.pop("tips_json") or "[]")
        except ValueError:
            r["tips"] = []
    return {"actions": rows}


@app.post("/api/mkt/actions/{task_id}/done")
def complete_action(task_id: int, body: TaskDone, _=Depends(mkt_auth)):
    task = uq1("SELECT * FROM sales_tasks WHERE id=?", (task_id,))
    if not task:
        raise HTTPException(404, "Task not found")
    if body.outcome not in ("reached", "no_answer", "not_interested", "sent"):
        raise HTTPException(400, "Unknown outcome.")
    uex("UPDATE sales_tasks SET status='done', outcome=?, done_at=datetime('now','localtime') WHERE id=?",
        (body.outcome, task_id))
    if task["decision_id"] and body.outcome in ("reached", "sent", "not_interested"):
        uex("UPDATE nba_decisions SET executed_at=COALESCE(executed_at, datetime('now','localtime')) WHERE id=?",
            (task["decision_id"],))
    return {"message": "Saved."}


@app.get("/api/mkt/nba/performance")
def nba_performance(window_days: int = 14, _=Depends(mkt_auth)):
    """
    How well is next-best-action doing on REAL leads? Uses the decision log.
      * randomised slice (policy='explore'): a clean experiment — conversion by action
      * inverse-propensity estimates of the value of 'follow the model' vs 'do nothing'
        (valid because every decision's probability under the logging policy is stored)
    """
    try:
        rows = uq(f"""
            SELECT d.*, EXISTS(SELECT 1 FROM purchases p WHERE p.user_id=d.user_id
                                AND p.purchased_at >= d.created_at
                                AND p.purchased_at <= datetime(d.created_at, '+{int(window_days)} days')) AS converted,
                   (d.created_at <= datetime('now','localtime','-{int(window_days)} days')) AS matured
            FROM nba_decisions d""")
    except sqlite3.OperationalError:
        rows = []
    discount = {"email_coupon_10": 0.10, "email_coupon_20": 0.20}
    cost = {"email_info": 2, "email_coupon_10": 2, "email_coupon_20": 2, "call": 150, "whatsapp": 5}
    by_action = {}
    for r in rows:
        b = by_action.setdefault(r["action"], {"decisions": 0, "explore": 0, "known_outcome": 0, "converted": 0})
        b["decisions"] += 1
        b["explore"] += 1 if r["policy"] == "explore" else 0
        if r["converted"] or r["matured"]:
            b["known_outcome"] += 1
            b["converted"] += r["converted"]
    labelled = [r for r in rows if r["converted"] or r["matured"]]
    explore = {}
    for r in labelled:
        if r["policy"] == "explore":
            e = explore.setdefault(r["action"], {"n": 0, "converted": 0})
            e["n"] += 1
            e["converted"] += r["converted"]
    for e in explore.values():
        e["rate"] = round(e["converted"] / e["n"], 3) if e["n"] else None

    def terms(target):
        """(weight, weighted profit) per labelled decision: weight = 1/propensity when the logged
        action is the one the target policy would have taken, else 0."""
        out = []
        for r in labelled:
            a_star = r["model_best"] if target == "model" else target
            if r["action"] != a_star or not r["propensity"]:
                out.append((0.0, 0.0))
                continue
            w = 1.0 / r["propensity"]
            profit = r["converted"] * (r["price"] or 0) * (1 - discount.get(r["action"], 0)) - cost.get(r["action"], 0)
            out.append((w, w * profit))
        return out

    def ips(target):
        t = terms(target)
        n = len(t)
        num, den = sum(x[1] for x in t), sum(x[0] for x in t)
        matched = sum(1 for x in t if x[0] > 0)
        ci = None
        if den and matched >= 5:            # bootstrap the decisions for a 95% interval
            rng = random.Random(7)
            boots = []
            for _ in range(300):
                sample = [t[rng.randrange(n)] for _ in range(n)]
                d = sum(x[0] for x in sample)
                if d:
                    boots.append(sum(x[1] for x in sample) / d)
            boots.sort()
            if len(boots) >= 20:
                ci = [round(boots[int(0.025 * len(boots))], 1), round(boots[int(0.975 * len(boots)) - 1], 1)]
        return {"ips_profit_per_lead": round(num / n, 1) if n else None,
                "snips_profit_per_lead": round(num / den, 1) if den else None,
                "ci95": ci, "matched_decisions": matched}

    return {"decisions_total": len(rows), "decisions_with_outcome": len(labelled),
            "by_action": by_action, "randomised_slice": explore,
            "policy_estimates": {"follow the model": ips("model"), "do nothing": ips("none"),
                                 "information email to all": ips("email_info")},
            "note": ("Each estimate only uses decisions where the logged action matches what that policy would "
                     "have done, re-weighted by 1/probability — so wide intervals mean too few matching decisions "
                     "yet. Run retrain-model.bat to update the uplift model from these logs.")}


# ── IMPROVE EMAIL (Gemini or rule-based coach) ────────────────────────────────
class ImproveReq(BaseModel):
    draft: str
    subject: Optional[str] = ""
    tier: str
    course: Optional[str] = ""
    course_slug: Optional[str] = None
    occupation: Optional[str] = ""
    name: Optional[str] = ""


@app.post("/api/mkt/ai-improve")
def ai_improve(req: ImproveReq, _=Depends(mkt_auth)):
    slug = req.course_slug or catalog.slug_for_title(req.course)
    out = coach.improve(req.subject, req.draft, req.name, req.tier, slug, req.occupation)
    out["note"] = ("Rewritten by Gemini — review before sending." if out["engine"] == "gemini"
                   else "Checked by the rule-based email coach (set GEMINI_API_KEY in .env for AI rewriting).")
    return out


# ── WHATSAPP (wa.me click-to-chat — works without any paid API) ───────────────
class WhatsAppReq(BaseModel):
    lead_id: int
    message: str


def _wa_number(phone):
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 10:
        digits = "91" + digits          # Indian mobile without country code
    return digits if 11 <= len(digits) <= 15 else None


@app.post("/api/mkt/whatsapp")
def whatsapp_link(req: WhatsAppReq, _=Depends(mkt_auth)):
    lead = uq1("""SELECT l.*, u.name, up.phone, up.whatsapp_opt_in FROM leads l JOIN users u ON l.user_id=u.id
                  LEFT JOIN user_profiles up ON up.user_id=l.user_id WHERE l.id=?""", (req.lead_id,))
    if not lead:
        raise HTTPException(404, "Lead not found")
    if not lead.get("whatsapp_opt_in"):
        raise HTTPException(400, "This lead hasn't opted in to WhatsApp messages.")
    number = _wa_number(lead.get("phone"))
    if not number:
        raise HTTPException(400, "No valid phone number on this lead's profile.")
    text = _personalise(req.message, lead["name"], _lead_slug(lead))
    mex("INSERT INTO sms_queue (user_id, lead_id, phone, message, status, channel) VALUES (?,?,?,?,?,?)",
        (lead["user_id"], req.lead_id, number, text, "opened", "whatsapp"))
    return {"url": f"https://wa.me/{number}?text={quote(text)}",
            "message": "WhatsApp opened with the message — press send there."}


@app.get("/api/mkt/sms-queue")
def get_sms_queue(_=Depends(mkt_auth)):
    return {"messages": mq("SELECT * FROM sms_queue ORDER BY created_at DESC")}


# ── COUPONS ───────────────────────────────────────────────────────────────────
class CouponReq(BaseModel):
    user_id: int
    tier: str
    discount_pct: int
    expires_hours: int = 72


@app.post("/api/mkt/coupons/generate")
def generate_coupon(req: CouponReq, _=Depends(mkt_auth)):
    if not 5 <= req.discount_pct <= 50:
        raise HTTPException(400, "Discount must be between 5% and 50%.")
    if not 1 <= req.expires_hours <= 720:
        raise HTTPException(400, "Expiry must be between 1 hour and 30 days.")
    if not uq1("SELECT id FROM users WHERE id=?", (req.user_id,)):
        raise HTTPException(404, "User not found")
    code = f"XE{req.discount_pct}-{''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(5))}"
    uex("""INSERT INTO coupons_issued (user_id, coupon_code, discount_pct, tier, expires_at)
           VALUES (?,?,?,?,datetime('now','localtime',?))""",
        (req.user_id, code, req.discount_pct, req.tier, f"+{req.expires_hours} hours"))
    return {"coupon_code": code, "discount_pct": req.discount_pct,
            "message": f"Personal coupon {code} ({req.discount_pct}% off, {req.expires_hours} h) assigned."}


@app.get("/api/mkt/coupons")
def all_coupons(_=Depends(mkt_auth)):
    return {"coupons": uq("""SELECT ci.*, u.name, u.email FROM coupons_issued ci
                             JOIN users u ON ci.user_id=u.id ORDER BY ci.created_at DESC""")}


@app.delete("/api/mkt/coupons/{coupon_id}")
def delete_coupon(coupon_id: int, _=Depends(mkt_auth)):
    if not uq1("SELECT id FROM coupons_issued WHERE id=?", (coupon_id,)):
        raise HTTPException(404, "Coupon not found")
    uex("DELETE FROM coupons_issued WHERE id=?", (coupon_id,))
    return {"success": True, "message": "Coupon deleted"}


# ── CAMPAIGNS (scheduled sends that actually go out) ──────────────────────────
class CampaignReq(BaseModel):
    name: str
    tier: str
    subject: str
    body: str
    scheduled_at: str


def _normalise_dt(value):
    """'2026-10-02T10:30' (browser) -> '2026-10-02 10:30:00' (SQLite comparable)."""
    v = (value or "").strip().replace("T", " ")
    try:
        return datetime.strptime(v[:16], "%Y-%m-%d %H:%M").strftime("%Y-%m-%d %H:%M:00")
    except ValueError:
        raise HTTPException(400, "Use a date and time like 2026-10-02 10:30.")


def _campaign_recipients(tier):
    tier_sql = "" if tier == "All leads" else " AND l.recommended_action=?"
    params = () if tier == "All leads" else (tier,)
    return uq(f"""SELECT l.id AS lead_id, l.user_id, l.course_slug, l.course_type, u.email, u.name
                  FROM {LATEST} l JOIN users u ON l.user_id=u.id
                  LEFT JOIN user_profiles up ON up.user_id=l.user_id
                  WHERE COALESCE(up.do_not_email,'No') != 'Yes'{tier_sql}""", params)


def send_campaign(campaign_id):
    camp = (mq("SELECT * FROM campaign_schedules WHERE id=?", (campaign_id,)) or [None])[0]
    if not camp or camp["sent"]:
        return 0
    if not mclaim("""UPDATE campaign_schedules SET status='sending'
                     WHERE id=? AND sent=0 AND COALESCE(status,'scheduled') != 'sending'""", (campaign_id,)):
        return 0                                    # already being sent by someone else
    sent, errors = 0, []
    for r in _campaign_recipients(camp["tier"]):
        slug = _lead_slug(r)
        ok, msg = tracked_send(r["user_id"], r["email"], _personalise(camp["subject"], r["name"], slug),
                               _personalise(camp["body"], r["name"], slug), course_slug=slug,
                               lead_id=r["lead_id"], campaign_id=campaign_id, campaign_name=camp["name"])
        sent += 1 if ok else 0
        if not ok and "opted out" not in msg:
            errors.append(msg)
    mex("""UPDATE campaign_schedules SET sent=1, sent_at=datetime('now','localtime'), status=?,
           recipients=?, error=? WHERE id=?""",
        ("sent" if not errors else "sent_with_errors", sent, "; ".join(errors[:3]) or None, campaign_id))
    print(f"[CAMPAIGN] '{camp['name']}' sent to {sent} recipient(s)")
    return sent


def run_due_campaigns():
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for camp in mq("""SELECT id FROM campaign_schedules WHERE sent=0 AND scheduled_at <= ?
                          AND COALESCE(status,'scheduled') != 'sending'""", (now,)):
            send_campaign(camp["id"])
    except Exception as e:
        print("[CAMPAIGN JOB ERROR]", e)


@app.post("/api/mkt/campaigns")
def schedule_campaign(req: CampaignReq, _=Depends(mkt_auth)):
    if req.tier not in TIERS + ["All leads"]:
        raise HTTPException(400, "Unknown tier.")
    if not req.name.strip() or not req.subject.strip() or not req.body.strip():
        raise HTTPException(400, "Name, subject and body are required.")
    when = _normalise_dt(req.scheduled_at)
    cid = mex("INSERT INTO campaign_schedules (name, tier, subject, body, scheduled_at, status) VALUES (?,?,?,?,?,'scheduled')",
              (req.name.strip(), req.tier, req.subject, req.body, when))
    return {"id": cid, "message": f"Campaign '{req.name}' scheduled for {when} "
                                  f"({len(_campaign_recipients(req.tier))} recipient(s) right now)."}


@app.post("/api/mkt/campaigns/{campaign_id}/send-now")
def send_campaign_now(campaign_id: int, _=Depends(mkt_auth)):
    camp = mq("SELECT * FROM campaign_schedules WHERE id=?", (campaign_id,))
    if not camp:
        raise HTTPException(404, "Campaign not found")
    if camp[0]["sent"] or camp[0].get("status") == "sending":
        raise HTTPException(400, "This campaign was already sent (or is being sent right now).")
    n = send_campaign(campaign_id)
    return {"message": f"Sent to {n} recipient(s)."}


@app.get("/api/mkt/campaigns")
def get_campaigns(_=Depends(mkt_auth)):
    out = []
    for c in mq("SELECT * FROM campaign_schedules ORDER BY scheduled_at DESC"):
        sends = uq("SELECT user_id, sent_at, click_count FROM email_sends WHERE campaign_id=?", (c["id"],))
        c["delivered"] = len(sends)
        c["clicks"] = sum(1 for s in sends if s["click_count"])
        c["conversions"] = _conversions_after(sends)
        c["audience_now"] = len(_campaign_recipients(c["tier"])) if not c["sent"] else None
        out.append(c)
    return {"campaigns": out}


@app.delete("/api/mkt/campaigns/{campaign_id}")
def delete_campaign(campaign_id: int, _=Depends(mkt_auth)):
    if not mq("SELECT id FROM campaign_schedules WHERE id=?", (campaign_id,)):
        raise HTTPException(404, "Campaign not found")
    mex("DELETE FROM campaign_schedules WHERE id=?", (campaign_id,))
    return {"success": True, "message": "Campaign deleted"}


# ── A/B TESTING (one email per person, real statistics) ───────────────────────
class AbTestReq(BaseModel):
    name: str
    tier: str
    subject_a: str
    body_a: str
    subject_b: str
    body_b: str


@app.post("/api/mkt/ab-tests")
def create_ab_test(req: AbTestReq, _=Depends(mkt_auth)):
    if req.tier not in TIERS + ["All leads"]:
        raise HTTPException(400, "Unknown tier.")
    tid = mex("INSERT INTO ab_tests (name, tier, subject_a, body_a, subject_b, body_b) VALUES (?,?,?,?,?,?)",
              (req.name, req.tier, req.subject_a, req.body_a, req.subject_b, req.body_b))
    return {"id": tid, "message": f"A/B test '{req.name}' created."}


@app.get("/api/mkt/ab-tests")
def list_ab_tests(_=Depends(mkt_auth)):
    return {"ab_tests": mq("SELECT * FROM ab_tests ORDER BY created_at DESC")}


@app.post("/api/mkt/ab-tests/{test_id}/send")
def send_ab_test(test_id: int, _=Depends(mkt_auth)):
    test = (mq("SELECT * FROM ab_tests WHERE id=?", (test_id,)) or [None])[0]
    if not test:
        raise HTTPException(404, "A/B test not found")
    if test["status"] in ("sent", "sending") or not mclaim(
            "UPDATE ab_tests SET status='sending' WHERE id=? AND COALESCE(status,'draft') NOT IN ('sent','sending')",
            (test_id,)):
        raise HTTPException(400, "This test was already sent.")
    recipients = _campaign_recipients(test["tier"])
    random.shuffle(recipients)                      # random 50/50 split, balanced
    counts = {"A": 0, "B": 0}
    for i, r in enumerate(recipients):
        v = "A" if i % 2 == 0 else "B"
        slug = _lead_slug(r)
        ok, _msg = tracked_send(r["user_id"], r["email"], _personalise(test[f"subject_{v.lower()}"], r["name"], slug),
                                _personalise(test[f"body_{v.lower()}"], r["name"], slug), course_slug=slug,
                                lead_id=r["lead_id"], ab_test_id=test_id, variant=v)
        counts[v] += 1 if ok else 0
    mex("UPDATE ab_tests SET status='sent', sent_at=datetime('now','localtime') WHERE id=?", (test_id,))
    return {"message": f"A/B test sent — A: {counts['A']}, B: {counts['B']} (one email per person)."}


@app.get("/api/mkt/ab-tests/{test_id}/results")
def ab_test_results(test_id: int, _=Depends(mkt_auth)):
    test = (mq("SELECT * FROM ab_tests WHERE id=?", (test_id,)) or [None])[0]
    if not test:
        raise HTTPException(404, "A/B test not found")

    def variant(v):
        sends = uq("""SELECT user_id, sent_at, click_count FROM email_sends
                      WHERE ab_test_id=? AND variant=? AND subject != '[demo seed]'""", (test_id, v))
        n = len(sends)
        clicks = sum(1 for s in sends if s["click_count"])
        conv = _conversions_after(sends)
        return {"sent": n, "clicked": clicks, "converted": conv,
                "click_rate": round(clicks / n * 100, 1) if n else 0,
                "conversion_rate": round(conv / n * 100, 1) if n else 0,
                # kept for the old UI field names
                "opened": clicks, "open_rate": round(clicks / n * 100, 1) if n else 0}

    a, b = variant("A"), variant("B")
    clicks_test = two_proportion_test(a["clicked"], a["sent"], b["clicked"], b["sent"])
    conv_test = two_proportion_test(a["converted"], a["sent"], b["converted"], b["sent"])
    base = (a["clicked"] + b["clicked"]) / max(a["sent"] + b["sent"], 1) or 0.05
    needed = sample_size_per_variant(base, 0.05)
    winner, verdict = None, f"Not enough evidence yet — about {needed} sends per variant are needed to detect a 5-point difference in click rate."
    if clicks_test["p_value"] is not None and clicks_test["p_value"] < 0.05:
        winner = "B" if clicks_test["diff"] > 0 else "A"
        verdict = (f"Variant {winner} has a significantly higher click rate "
                   f"(p = {clicks_test['p_value']}, difference {abs(clicks_test['diff'])*100:.1f} points).")
    elif a["sent"] + b["sent"] and clicks_test["p_value"] is not None:
        verdict = (f"No significant difference yet (p = {clicks_test['p_value']}). "
                   f"Roughly {needed} sends per variant are needed to detect a 5-point difference.")
    return {"test": test, "variant_a": a, "variant_b": b, "winner": winner, "verdict": verdict,
            "click_test": clicks_test, "conversion_test": conv_test, "sends_needed_per_variant": needed}


# ── Q&A ───────────────────────────────────────────────────────────────────────
class AnswerReq(BaseModel):
    qna_id: int
    answer: str


@app.get("/api/mkt/qna")
def get_unanswered_qna(_=Depends(mkt_auth)):
    return {"questions": uq("""SELECT q.*, u.name AS user_name FROM qna q JOIN users u ON q.user_id=u.id
                               WHERE q.answer IS NULL ORDER BY q.created_at DESC""")}


@app.post("/api/mkt/qna/answer")
def answer_question(req: AnswerReq, _=Depends(mkt_auth)):
    if not req.answer.strip():
        raise HTTPException(400, "Answer can't be empty.")
    q = uq1("""SELECT q.*, u.email, u.name FROM qna q JOIN users u ON q.user_id=u.id WHERE q.id=?""", (req.qna_id,))
    if not q:
        raise HTTPException(404, "Question not found")
    uex("UPDATE qna SET answer=?, answered_at=datetime('now','localtime') WHERE id=?", (req.answer.strip(), req.qna_id))
    send_simple_email(q["email"], f"Your question about {catalog.title_of(q['course_slug'])} was answered",
                      f"Hi {(q['name'] or '').split()[0]},\n\nYou asked: {q['question']}\n\nOur answer: "
                      f"{req.answer.strip()}\n\nSee it on the course page: {_course_url(q['course_slug'])}\n\n"
                      "— X Education Team", title="Your question was answered")
    return {"message": "Answer published and emailed to the learner."}


# ── CALLBACK REQUESTS (from the website chat) ─────────────────────────────────
@app.get("/api/mkt/callbacks")
def list_callbacks(status: str = "open", _=Depends(mkt_auth)):
    return {"callbacks": uq("""
        SELECT cb.*, u.name, u.email,
               (SELECT MAX(id) FROM leads l WHERE l.user_id=cb.user_id) AS lead_id
        FROM callback_requests cb JOIN users u ON u.id=cb.user_id
        WHERE (?='all' OR cb.status=?) ORDER BY cb.id DESC""", (status, status))}


@app.post("/api/mkt/callbacks/{callback_id}/done")
def close_callback(callback_id: int, _=Depends(mkt_auth)):
    if not uq1("SELECT id FROM callback_requests WHERE id=?", (callback_id,)):
        raise HTTPException(404, "Callback not found")
    uex("UPDATE callback_requests SET status='done', closed_at=datetime('now','localtime') WHERE id=?", (callback_id,))
    return {"message": "Marked as done."}


# ── CSV EXPORT (one row per person) ───────────────────────────────────────────
@app.get("/api/mkt/export-csv")
def export_leads(_=Depends(mkt_auth)):
    leads = uq(f"""
        SELECT l.id AS lead_id, u.name, u.email, up.phone, l.course_type, up.current_occupation, up.city,
               l.lead_score, l.conversion_probability, l.recommended_action, l.persona, l.plv,
               l.trigger_reason, l.email_sent, l.model_version, l.created_at
        FROM {LATEST} l JOIN users u ON l.user_id=u.id
        LEFT JOIN user_profiles up ON up.user_id=l.user_id ORDER BY l.lead_score DESC""")
    output = io.StringIO()
    if leads:
        writer = csv.DictWriter(output, fieldnames=leads[0].keys())
        writer.writeheader()
        writer.writerows(leads)
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition":
                                      f"attachment; filename=leads_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"})
