"""
=================================================================
 LIVE SIMULATION — the simulated learners keep living, in real time
=================================================================
 The starting history (ml/generate_history.py) gives the CRM six months of simulated learners.
 This module keeps those same people — and new ones who sign up every day — using the website
 while the servers run, so the CRM always has live work: it scores them, decides, sends e-mails
 and coupons, creates call tasks, and learns from who buys. They are part of the CRM's one pool of
 learners, next to the real people who sign up on the website.

 How they reach the CRM: through the website's own API over HTTP (http://127.0.0.1:8000/api/...),
 with exactly the requests a browser sends — start a visit, report each page and its seconds (and a
 "still here" every 30 s while reading), video / pricing / brochure / chat / webinar, add to wishlist
 or cart, start checkout, send an enquiry, open the course from the button in an e-mail, pay with
 their best coupon, sign up with the code from their inbox. Nothing in the CRM is written by this file
 directly, and the CRM's decisions have no special code for them: the only thing that marks them is
 their address (…@demo.xeducation.test, a reserved domain that is never e-mailed), shown as a small
 "simulated" tag in the dashboard.

 What the simulator decides — the same documented behaviour as the six-month history:
   who they are     profile, hidden intent and luck (ml/generate_dataset.py), and how much each CRM step
                    changes each person's chance to buy (ml/nba_simulation.py TRUE_EFFECTS + a personal
                    deviation). The history's learners are re-created exactly from the history's seed.
   coming back      chance per day sig(-2.6 + 0.7*intent - 0.05*days away + boost), only within 21 days
                    of the last visit. A call that reached them adds 0.5 for two days, a WhatsApp 0.3;
                    a click on an e-mail brings them back a minute later.
   on the website   pages (1 + Poisson), seconds per page (log-normal) and every first-time step (video,
                    pricing, testimonials, brochure, chat, webinar, wishlist, cart, checkout, enquiry)
                    with its documented chance (EVENTS in ml/generate_history.py).
   e-mails          only the e-mails the CRM really sent them: clicked with chance
                    sig(-1.7 + 0.6*intent, +0.4 with a coupon), 12 minutes to 30 hours after sending.
   buying           the documented buying formula on everything they have done so far, plus the strongest
                    effect of a CRM step in the last 14 days, spread evenly over the day (daily chance
                    1 - (1 - p14)^(1/14)), only while they visited in the last 14 days. They come back,
                    put the course in the cart and pay with their best valid coupon.
   the advisor      call and WhatsApp tasks of simulated learners are done by a simulated advisor 1-24 hours
                    after the CRM creates them (call: reached 60 %, no answer 30 %, not interested 10 %),
                    unless you do them first in Today's actions. Real learners' tasks are never touched.
                    The simulated advisor has its own daily call capacity (nba.py), so simulated learners
                    never use up a real advisor's calls.
   new sign-ups     about 13 a day (the history's recent rate): sign-up -> e-mailed code -> profile -> visit.

 Real time: a second here is a second for the CRM. When the servers are off nobody can use the website,
 so nothing happens then: a visit or click that fell into that time is dropped, not replayed later.
 The hidden traits and the simulator's to-do list live in its own database
 (user-backend/simulation_world.db), never in the CRM's database.

 It runs inside the user-backend (scheduler.py starts it every few seconds); crm_settings.json
 "live_simulation" switches it on or off, and the dashboard can pause it or send a learner to the site now.
 From a terminal (servers running):
     user-backend\\venv\\Scripts\\python.exe ml\\live_simulation.py --status
     user-backend\\venv\\Scripts\\python.exe ml\\live_simulation.py --reset     (forget its to-do list)
=================================================================
"""
import argparse
import contextlib
import hashlib
import json
import os
import re
import sqlite3
import sys
import threading
import time as _time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, time, timedelta

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.normpath(os.path.join(HERE, "..", "user-backend"))
for _p in (HERE, BACKEND):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import catalog                  # noqa: E402  the website's catalogue (titles, prices)
import database as db           # noqa: E402  read only here: the learners' inbox and what they did
import generate_dataset as G    # noqa: E402  who they are, and the buying formula
import generate_history as H    # noqa: E402  the documented behaviour (EVENTS, BASE_SHIFT, WORLD_DRIFT ...)
import ml_features as F         # noqa: E402
import nba_core as N            # noqa: E402
import nba_simulation as S      # noqa: E402  true effects of each CRM step
import settings                 # noqa: E402

TS = "%Y-%m-%d %H:%M:%S"
DOMAIN = H.DEMO_DOMAIN
LIKE = f"%@{DOMAIN}"
HISTORY_SEED = 2026                       # the seed generate_history.py uses (its --seed default)
LIVE_SEED = HISTORY_SEED + 1_000_000      # new sign-ups: learner number k is drawn with seed LIVE_SEED + k
LATE = timedelta(minutes=15)              # a step this late fell into a time the website was off: dropped
ROLL_EVERY = timedelta(seconds=60)        # how often the dice for visits, purchases and sign-ups are rolled
WORLD_PATH = os.getenv("SIM_WORLD_DB", os.path.join(BACKEND, "simulation_world.db"))
API_URL = os.getenv("SIM_API_URL", "http://127.0.0.1:8000").rstrip("/")
CHAT_QUESTIONS = ["What are the fees?", "How long is it?", "What will I learn in this course?",
                  "Is there an EMI option?", "Do I get a certificate?", "Is there placement support?",
                  "Which course suits me?"]          # all answered from the course facts (no AI service needed)
DEFAULTS = {"enabled": True, "new_signups_per_day": 13, "advisor_hours": [1, 24], "tick_seconds": 10}
STEP_TEXT = {"video": "watched the overview video", "pricing": "read the pricing", "testimonial": "read testimonials",
             "brochure": "downloaded the brochure", "chat": "asked the chat assistant", "webinar": "booked a webinar seat",
             "wishlist": "wishlisted {course}", "cart": "put {course} in the cart", "checkout": "started checkout",
             "enquiry": "sent an enquiry"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS learners (
    user_id     INTEGER PRIMARY KEY,     -- users.id in the CRM
    email       TEXT UNIQUE,
    name        TEXT,
    k           INTEGER,                 -- learner number: below the history's size = a history learner
    joined      TEXT,                    -- 'history' | 'live' (signed up while the servers ran)
    intent      REAL,                    -- hidden: how much they want a course (never shown to the CRM)
    luck        REAL,                    -- hidden: timing, budget, mood
    noise_json  TEXT,                    -- hidden: how this person reacts to each CRM step
    slug        TEXT,                    -- the course they are interested in
    device      TEXT, source TEXT, occ TEXT,
    dne INTEGER, dnc INTEGER, wa INTEGER, phone TEXT,
    boost       REAL DEFAULT 0,          -- after a call / WhatsApp that reached them
    boost_until TEXT,
    busy_until  TEXT,                    -- a visit is in progress until then
    session_id  INTEGER,                 -- the website session of the current visit
    bought      INTEGER DEFAULT 0,
    created_at  TEXT
);
CREATE TABLE IF NOT EXISTS effects (       -- each CRM step that reached someone, with its true effect
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, ref TEXT UNIQUE, kind TEXT, effect REAL,
    starts_at TEXT, until TEXT
);
CREATE INDEX IF NOT EXISTS idx_sim_effects_user ON effects(user_id, until);
CREATE TABLE IF NOT EXISTS tasks (         -- call / WhatsApp tasks of simulated learners
    task_id INTEGER PRIMARY KEY, user_id INTEGER, due_at TEXT, handled INTEGER DEFAULT 0,
    outcome TEXT, done_by TEXT
);
CREATE TABLE IF NOT EXISTS queue (         -- what each learner will do next, and when
    id INTEGER PRIMARY KEY AUTOINCREMENT, due_at TEXT, user_id INTEGER, visit TEXT, kind TEXT, payload TEXT
);
CREATE INDEX IF NOT EXISTS idx_sim_queue_due ON queue(due_at);
CREATE TABLE IF NOT EXISTS log (           -- the simulated people's diary (shown on the dashboard)
    id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, user_id INTEGER, kind TEXT, text TEXT
);
CREATE INDEX IF NOT EXISTS idx_sim_log_at ON log(at);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


def conf():
    c = dict(DEFAULTS)
    c.update({k: v for k, v in (settings.S.get("live_simulation") or {}).items() if not str(k).startswith("_")})
    return c


def ts(t):
    return t.strftime(TS)


def parse(s):
    return datetime.strptime(str(s)[:19], TS)


def sig(x):
    return 1.0 / (1.0 + np.exp(-np.asarray(x, dtype=float)))


class Offline(Exception):
    """The website's API did not answer (the user-backend is starting, stopping or down)."""


class Paused(Exception):
    pass


# ── the website's API, called the way a browser calls it ─────────────────────────────────────────
class HttpApi:
    def __init__(self, base=API_URL, internal_key=None, timeout=30):
        self.base = base.rstrip("/")
        self.key = internal_key or os.getenv("INTERNAL_API_KEY", "xedu-internal-dev")
        self.timeout = timeout
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # 127.0.0.1: never via a proxy

    def call(self, method, path, body=None, token=None, internal=False):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if internal:
            headers["X-Internal-Key"] = self.key
        data = json.dumps(body).encode() if body is not None else (b"" if method in ("POST", "PUT") else None)
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with self.opener.open(req, timeout=self.timeout) as r:
                raw = r.read().decode() or "null"
                return r.status, json.loads(raw)
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read().decode() or "null")
            except ValueError:
                detail = None
            return e.code, detail
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
            raise Offline(str(e))


# ── who the simulated learners are ───────────────────────────────────────────────────────────────
_cache = {}


def course_slugs():
    if "slugs" not in _cache:
        _cache["slugs"] = H.course_slugs(F, catalog)
    return _cache["slugs"]


def history_size():
    hist = settings.S.get("starting_history") or {}
    return int(hist.get("learners", 2000)), int(hist.get("days", 180))


def history_traits():
    """The history's learners exactly as ml/generate_history.py made them (same seed, same draws, same order)."""
    if "history" not in _cache:
        n, days = history_size()
        by_type, all_slugs = course_slugs()
        rng = np.random.default_rng(HISTORY_SEED)
        out = H.learner_traits(n, days, HISTORY_SEED, G, rng, by_type, all_slugs, N.ACTION_LIST, S.EFFECT_NOISE_SD)
        _cache["history"] = {t["email"]: t for t in out}
    return _cache["history"]


def new_traits(k):
    """Learner number k (k >= the history's size): a new person who signs up while the CRM runs. Drawn by the
    same generator as the history's learners, with their own seed (LIVE_SEED + k)."""
    by_type, all_slugs = course_slugs()
    rng = np.random.default_rng(LIVE_SEED + int(k))
    r = G.generate(1, seed=int(rng.integers(2 ** 31 - 1)), return_truth=True).to_dict("records")[0]
    first, last = str(rng.choice(H.FIRST)), str(rng.choice(H.LAST))
    slug = str(rng.choice(by_type.get(r["CourseType"]) or all_slugs))
    luck = float(rng.normal(0, 0.45))
    noise = {a: float(rng.normal(0, S.EFFECT_NOISE_SD)) for a in N.ACTION_LIST}
    phone = f"+91 00000 {int(k) + 1:05d}" if rng.random() < 0.85 else None
    return {"i": int(k), "name": f"{first} {last}", "email": f"{first}.{last}.{int(k) + 1}@{DOMAIN}".lower(),
            "occ": r["CurrentOccupation"], "spec": r["Specialization"], "intent": float(r["_intent"]), "luck": luck,
            "dne": int(r["DoNotEmail"]), "dnc": int(r["DoNotCall"]), "wa": int(r["WhatsAppOptIn"]),
            "device": r["DeviceType"], "source": r["LeadSource"], "slug": slug, "noise": noise, "phone": phone, "raw": r}


def context_of(features):
    """nba_core.context() for one person at base probability 0.5 (as the history's effect_of uses it), without
    building a pandas frame: the same cleaning (ml_features.normalize_raw), the same nine values. A test checks
    it equals nba_core.context(ml_features.to_model_frame([features]), [0.5]) exactly."""
    f = F.normalize_raw(features)
    occ = str(f["CurrentOccupation"])
    cart, checkout, enquiry = f["AddedToCart"] == 1, f["CheckoutStarted"] == 1, f["EnquirySubmitted"] == 1
    return np.array([1.0, 0.0,
                     float(occ in N.PRICE_SENSITIVE_OCC or (cart and not checkout)),
                     float(checkout), float(cart or enquiry), float(occ in N.PROFESSIONAL_OCC),
                     float(f["EmailOpenedCount"] > 0), float(f["WhatsAppOptIn"] == 1),
                     float(f["TotalTimeOnWebsite"] < 120)])


def number_of(email):
    m = re.search(r"\.(\d+)@", email or "")
    return int(m.group(1)) - 1 if m else None


def traits_for(email):
    """(traits, k, joined) for a simulated learner already in the CRM."""
    k = number_of(email)
    hist = history_traits()
    if email in hist:
        return hist[email], k, "history"
    n, _ = history_size()
    if k is not None and k >= n:
        tr = new_traits(k)
        if tr["email"] == email:
            return tr, k, "live"
    # someone this simulator cannot re-create exactly (made with another seed): new hidden traits, same address
    seed_k = 10 ** 7 + int(hashlib.sha256(email.encode()).hexdigest()[:8], 16)
    tr = dict(new_traits(seed_k), email=email)
    return tr, k, "other"


# ── the world ────────────────────────────────────────────────────────────────────────────────────
class World:
    def __init__(self, api=None, path=None, rng=None, clock=None):
        self.api = api or HttpApi()
        self.path = path or WORLD_PATH
        self.rng = rng or np.random.default_rng()
        self.clock = clock or datetime.now
        self.lock = threading.RLock()
        self._busy = threading.Lock()                # one tick at a time
        self._tokens = {}
        self._con = None
        self._last_sync = None
        self.last_error = None
        self.window = int(settings.S.get("outcome_window_days", 14))
        self._pref = None                            # rows read in bulk at the first start (catch_up)

    # ── storage ──
    def con(self):
        if self._con is None:
            c = sqlite3.connect(self.path, timeout=30, check_same_thread=False, isolation_level=None)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript(SCHEMA)
            self._con = c
        return self._con

    def q(self, sql, params=()):
        return [dict(r) for r in self.con().execute(sql, params).fetchall()]

    def q1(self, sql, params=()):
        r = self.con().execute(sql, params).fetchone()
        return dict(r) if r else None

    def x(self, sql, params=()):
        return self.con().execute(sql, params).lastrowid

    @contextlib.contextmanager
    def tx(self):
        """Many small writes in one transaction (thousands of rows at the first start)."""
        c = self.con()
        if c.in_transaction:
            yield
            return
        c.execute("BEGIN")
        try:
            yield
            c.execute("COMMIT")
        except BaseException:
            c.execute("ROLLBACK")
            raise

    def meta(self, key, default=None):
        r = self.q1("SELECT value FROM meta WHERE key=?", (key,))
        return r["value"] if r else default

    def set_meta(self, key, value):
        self.x("INSERT INTO meta (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
               (key, None if value is None else str(value)))

    def learner(self, user_id):
        L = self.q1("SELECT * FROM learners WHERE user_id=?", (user_id,))
        if L:
            L["noise"] = json.loads(L["noise_json"] or "{}")
        return L

    def log(self, at, L, kind, text):
        self.x("INSERT INTO log (at, user_id, kind, text) VALUES (?,?,?,?)",
               (ts(at), L["user_id"] if L else None, kind, (f"{L['name']} " if L else "") + text))

    def enqueue(self, due, user_id, kind, payload=None, visit=None):
        self.x("INSERT INTO queue (due_at, user_id, visit, kind, payload) VALUES (?,?,?,?,?)",
               (ts(due), user_id, visit, kind, json.dumps(payload or {})))

    # ── switch ──
    def enabled(self):
        v = self.meta("enabled")
        return bool(conf()["enabled"]) if v is None else v == "1"

    def set_enabled(self, on):
        with self.lock:
            self.set_meta("enabled", "1" if on else "0")
            self.log(self.clock(), None, "info", "Simulated learners resumed." if on else "Simulated learners paused.")
        return self.status()

    # ── 1. keep the list of people in step with the CRM ──
    def sync(self, now):
        """Every verified simulated learner in the CRM has a row here (hidden traits); people removed from the
        CRM are forgotten. The first time (or after the history was re-made) the effects of the last 14 days and
        the open call tasks are picked up, so nothing the CRM did recently is lost."""
        with self.tx():
            self._sync(now)
        self._last_sync = now

    def _sync(self, now):
        crm = {r["id"]: r for r in db.fetchall("SELECT id, email, name, created_at FROM users WHERE email LIKE ? "
                                               "AND is_verified=1", (LIKE,))}
        known = {r["user_id"]: r["email"] for r in self.q("SELECT user_id, email FROM learners")}
        gone = [u for u, e in known.items() if u not in crm or crm[u]["email"] != e]
        for u in gone:
            for t in ("learners", "effects", "tasks", "queue"):
                self.x(f"DELETE FROM {t} WHERE user_id=?", (u,))
        missing = [r for u, r in crm.items() if u not in known or u in gone]
        for r in missing:
            tr, k, joined = traits_for(r["email"])
            self.x("""INSERT OR REPLACE INTO learners (user_id, email, name, k, joined, intent, luck, noise_json, slug,
                      device, source, occ, dne, dnc, wa, phone, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                   (r["id"], r["email"], r["name"], k, joined, tr["intent"], tr["luck"], json.dumps(tr["noise"]),
                    tr["slug"], tr["device"], tr["source"], tr["occ"], tr["dne"], tr["dnc"], tr["wa"], tr["phone"],
                    r["created_at"]))
        bought = {r["user_id"] for r in db.fetchall("SELECT DISTINCT p.user_id FROM purchases p JOIN users u "
                                                    "ON u.id=p.user_id WHERE u.email LIKE ?", (LIKE,))}
        if bought:
            self.x(f"UPDATE learners SET bought=1 WHERE user_id IN ({','.join(str(int(u)) for u in bought)})")
        if self.meta("started_at") is None or len(missing) > 100:
            self.catch_up(now)
            if self.meta("started_at") is None:
                self.set_meta("started_at", ts(now))
                self.log(now, None, "info", f"Simulated learners started: {len(crm):,} people "
                                            f"({len(bought):,} of them customers).")
        if self.meta("next_k") is None:
            ks = [number_of(r["email"]) for r in crm.values()]
            self.set_meta("next_k", max([k for k in ks if k is not None] + [history_size()[0] - 1]) + 1)

    def catch_up(self, now):
        """Read what it needs from the CRM in a few queries (not three per e-mail), then pick up the recent past."""
        since = ts(now - timedelta(days=self.window))
        self._pref = {
            "dec": {r["lead_id"]: r for r in db.fetchall(
                """SELECT d.lead_id, d.action, d.features_json FROM nba_decisions d JOIN users u ON u.id=d.user_id
                   WHERE u.email LIKE ? AND d.created_at >= ? ORDER BY d.id""",
                (LIKE, ts(now - timedelta(days=self.window + 1))))},
            "feat": {r["user_id"]: r["features_json"] for r in db.fetchall(
                """SELECT s.user_id, s.features_json FROM score_snapshots s WHERE s.id IN
                   (SELECT MAX(s2.id) FROM score_snapshots s2 JOIN users u ON u.id=s2.user_id
                    WHERE u.email LIKE ? GROUP BY s2.user_id)""", (LIKE,))},
            "learner": {L["user_id"]: L for L in self.q("SELECT * FROM learners")},
        }
        for L in self._pref["learner"].values():
            L["noise"] = json.loads(L["noise_json"] or "{}")
        try:
            self._catch_up(now, since)
        finally:
            self._pref = None

    def _catch_up(self, now, since):
        for e in db.fetchall("""SELECT e.* FROM email_sends e JOIN users u ON u.id=e.user_id
                                WHERE u.email LIKE ? AND e.sent_at >= ? ORDER BY e.id""", (LIKE, since)):
            L = self._pref["learner"].get(e["user_id"])
            if L and not L["bought"]:
                self.email_arrived(L, e, now, click=False)
        for t in db.fetchall("""SELECT t.* FROM sales_tasks t JOIN users u ON u.id=t.user_id
                                WHERE u.email LIKE ? AND (t.status='open' OR t.done_at >= ?)""", (LIKE, since)):
            L = self._pref["learner"].get(t["user_id"])
            if not L:
                continue
            if t["status"] == "open":
                self.track_task(t)
            else:
                self.x("INSERT OR IGNORE INTO tasks (task_id, user_id, due_at, handled, outcome, done_by) "
                       "VALUES (?,?,?,1,?,?)", (t["id"], t["user_id"], t["done_at"], t["outcome"], t.get("done_by")))
                self.task_outcome(L, t)
        self.set_meta("email_wm", (db.fetchone("SELECT COALESCE(MAX(id),0) AS m FROM email_sends") or {}).get("m", 0))
        self.set_meta("task_wm", (db.fetchone("SELECT COALESCE(MAX(id),0) AS m FROM sales_tasks") or {}).get("m", 0))

    # ── 2. what they have done so far (the CRM's own tracking tables) ──
    def behaviour(self, user_ids=None):
        """Per simulated learner: visits, seconds on the site, every first-time step, e-mail clicks, last seen."""
        only = ""
        params = [LIKE]
        if user_ids is not None:
            ids = [int(u) for u in user_ids] or [-1]
            only = f" AND u.id IN ({','.join(map(str, ids))})"
        rows = db.fetchall(f"""
            SELECT e.user_id,
                   COUNT(DISTINCT CASE WHEN e.event_type='page_view' THEN e.session_id END) AS visits,
                   COALESCE(SUM(CASE WHEN e.event_type='page_view' THEN e.time_spent_sec END), 0) AS secs,
                   MAX(e.event_type='video_play') AS video, MAX(e.event_type='pricing_view') AS pricing,
                   MAX(e.event_type='testimonial_view') AS testimonial, MAX(e.event_type='brochure_dl') AS brochure,
                   MAX(e.event_type='chat') AS chat, MAX(e.event_type='webinar_register') AS webinar,
                   MAX(e.event_type='wishlist_add') AS wishlist, MAX(e.event_type='cart_add') AS cart,
                   MAX(e.event_type='checkout_start') AS checkout, MAX(e.event_type='enquiry_submit') AS enquiry,
                   MAX(e.created_at) AS last_event
            FROM behaviour_events e JOIN users u ON u.id = e.user_id
            WHERE u.email LIKE ?{only} GROUP BY e.user_id""", tuple(params))
        out = {r["user_id"]: dict(r) for r in rows}
        for r in db.fetchall(f"""SELECT s.user_id, MAX(COALESCE(s.last_active, s.login_at)) AS seen
                                 FROM user_sessions s JOIN users u ON u.id=s.user_id
                                 WHERE u.email LIKE ?{only} GROUP BY s.user_id""", tuple(params)):
            d = out.setdefault(r["user_id"], {"user_id": r["user_id"], "visits": 0, "secs": 0})
            d["seen"] = r["seen"]
        for r in db.fetchall(f"""SELECT m.user_id, COALESCE(SUM(m.click_count),0) AS clicks
                                 FROM email_sends m JOIN users u ON u.id=m.user_id
                                 WHERE u.email LIKE ?{only} GROUP BY m.user_id""", tuple(params)):
            out.setdefault(r["user_id"], {"user_id": r["user_id"], "visits": 0, "secs": 0})["clicks"] = r["clicks"]
        for d in out.values():
            seen = [x for x in (d.get("seen"), d.get("last_event")) if x]
            d["last_seen"] = max(seen) if seen else None
            for f, *_ in H.EVENTS:
                d[f] = int(d.get(f) or 0)
            d["checkout"] = int(d.get("checkout") or 0)
            d["clicks"] = int(d.get("clicks") or 0)
            d["visits"] = int(d.get("visits") or 0)
            d["secs"] = int(d.get("secs") or 0)
        return out

    # ── 3. the true effect of a CRM step on one person ──
    def effect_of(self, L, action, features=None):
        """ml/nba_simulation.py TRUE_EFFECTS at the person's situation + their own deviation, exactly as in
        the history (generate_history.History.effect_of)."""
        if not features:
            if self._pref is not None:
                raw = self._pref["feat"].get(L["user_id"])
            else:
                row = db.fetchone("SELECT features_json FROM score_snapshots WHERE user_id=? ORDER BY id DESC LIMIT 1",
                                  (L["user_id"],))
                raw = row["features_json"] if row else None
            features = json.loads(raw) if raw else None
        if features:
            ctx = context_of(features)
        else:                                   # nothing scored yet: the same context from what they did
            b = self.behaviour([L["user_id"]]).get(L["user_id"], {})
            occ = L["occ"]
            ctx = np.array([1.0, 0.0, float(occ in N.PRICE_SENSITIVE_OCC or (b.get("cart") and not b.get("checkout"))),
                            float(b.get("checkout", 0)), float(b.get("cart", 0) or b.get("enquiry", 0)),
                            float(occ in N.PROFESSIONAL_OCC), float(b.get("clicks", 0) > 0), float(L["wa"]),
                            float(b.get("secs", 0) < 120)])
        return float(ctx @ np.asarray(S.TRUE_EFFECTS[action])) + float(L["noise"].get(action, 0.0))

    def add_effect(self, L, ref, kind, effect, start):
        self.x("INSERT OR IGNORE INTO effects (user_id, ref, kind, effect, starts_at, until) VALUES (?,?,?,?,?,?)",
               (L["user_id"], ref, kind, float(effect), ts(start), ts(start + timedelta(days=self.window))))

    def adopted_shift(self, adoption_id, arm, L):
        """An adopted A/B winner (the CRM's standard e-mail now) keeps the documented extra effect it had in the
        history's test. A test you ran live has no documented effect: the simulator gives it none."""
        if arm != "adopted" or not adoption_id:
            return 0.0, 0.0
        row = db.fetchone("SELECT test_name, variant_key FROM adopted_emails WHERE id=?", (adoption_id,))
        name = (row or {}).get("test_name") or ""
        if not name.startswith(H.SIM):
            return 0.0, 0.0
        test = next((t for t in H.AB_TESTS if t["name"] == name[len(H.SIM):].strip()), None)
        if not test:
            return 0.0, 0.0
        person = {"device": L["device"]}

        def val(v, key):
            x = v.get(key, 0.0)
            return float(x(person)) if callable(x) else (float(x) if isinstance(x, (int, float)) else 0.0)
        win = next((v for v in test["variants"] if v["key"] == row["variant_key"]), None)
        others = [v for v in test["variants"] if v is not win]
        if not win or not others:
            return 0.0, 0.0
        return (val(win, "click") - max(val(v, "click") for v in others),
                val(win, "buy") - max(val(v, "buy") for v in others))

    def ab_variant(self, ab_test_id, key):
        """The documented variant of one of the history's A/B tests (by the test's name in the marketing
        database); None for a test you created live, whose true effect the simulator does not know."""
        cache = self.__dict__.setdefault("_ab", {})
        if ab_test_id not in cache:
            name = None
            path = os.getenv("MKT_DB_PATH", os.path.join(BACKEND, "..", "marketing-backend", "xeducation_marketing.db"))
            try:
                c = sqlite3.connect(f"file:{os.path.normpath(path)}?mode=ro", uri=True, timeout=10)
                try:
                    row = c.execute("SELECT name FROM ab_tests WHERE id=?", (int(ab_test_id),)).fetchone()
                    name = row[0] if row else None
                finally:
                    c.close()
            except sqlite3.Error:
                name = None
            name = name or ""
            if name.startswith(H.SIM):          # one of the history's tests ("(simulated) ..."): documented effects
                plain = name[len(H.SIM):].strip()
                cache[ab_test_id] = next((t for t in H.AB_TESTS if t["name"] == plain), None)
            else:
                cache[ab_test_id] = None
        test = cache[ab_test_id]
        if not test:
            return None
        return next((v for v in test["variants"] if v["key"] == key), None)

    # ── 4. e-mails the CRM sent them ──
    def handle_emails(self, now):
        wm = int(self.meta("email_wm") or 0)
        rows = db.fetchall("""SELECT e.* FROM email_sends e JOIN users u ON u.id=e.user_id
                              WHERE e.id > ? AND u.email LIKE ? ORDER BY e.id LIMIT 500""", (wm, LIKE))
        for e in rows:
            L = self.learner(e["user_id"])
            if L and not L["bought"]:
                self.email_arrived(L, e, now, click=True)
            wm = max(wm, int(e["id"]))
        if rows:
            self.set_meta("email_wm", wm)

    def email_arrived(self, L, e, now, click=True):
        sent = parse(e["sent_at"])
        effect, kind, click_shift = None, "e-mail", 0.0
        dec = None
        if e.get("lead_id") and self._pref is not None:
            dec = self._pref["dec"].get(e["lead_id"])
        elif e.get("lead_id"):
            dec = db.fetchone("SELECT action, features_json FROM nba_decisions WHERE lead_id=? ORDER BY id DESC LIMIT 1",
                              (e["lead_id"],))
        if e.get("campaign_id"):
            kind, effect = "campaign e-mail", 0.7 * self.effect_of(L, "email_info")
        elif e.get("ab_test_id") and self.ab_variant(e["ab_test_id"], e.get("variant")):
            v = self.ab_variant(e["ab_test_id"], e.get("variant"))
            person = {"device": L["device"]}
            click, buy = v.get("click", 0.0), v.get("buy", 0.0)
            click_shift = float(click(person) if callable(click) else click)
            if buy in ("coupon10", "coupon20"):
                effect = self.effect_of(L, "email_coupon_10" if buy == "coupon10" else "email_coupon_20")
            else:
                effect = float(buy(person) if callable(buy) else buy)
            kind = f"A/B test e-mail ({v.get('label')})"
        elif e.get("ab_test_id"):
            pct = (db.fetchone("""SELECT MAX(discount_pct) AS p FROM coupons_issued WHERE user_id=? AND coupon_code LIKE 'AB%'
                                  AND created_at BETWEEN ? AND ?""",
                               (L["user_id"], ts(sent - timedelta(minutes=5)), ts(sent + timedelta(minutes=5)))) or {}).get("p")
            if pct:
                kind, click_shift = f"A/B e-mail with a {int(pct)}% coupon", 0.4
                effect = self.effect_of(L, "email_coupon_10" if pct <= 10 else "email_coupon_20")
            else:
                kind, effect = "A/B test e-mail", 0.7 * self.effect_of(L, "email_info")
        elif dec and str(dec["action"]).startswith("email"):
            feats = json.loads(dec["features_json"]) if dec.get("features_json") else None
            kind, effect = N.ACTIONS[dec["action"]]["label"].lower(), self.effect_of(L, dec["action"], feats)
            if dec["action"] in ("email_coupon_10", "email_coupon_20"):
                click_shift = 0.4
            if e.get("adoption_id"):
                c, b = self.adopted_shift(e["adoption_id"], e.get("adoption_arm"), L)
                click_shift, effect = click_shift + c, effect + b
        if effect is not None:
            self.add_effect(L, f"email:{e['token']}", kind, effect, sent)
        if click:
            p = float(sig(-1.7 + 0.6 * L["intent"] + click_shift))
            if self.rng.random() < p:
                due = sent + timedelta(hours=float(self.rng.uniform(0.2, 30)))
                self.enqueue(due, L["user_id"], "click", {"token": e["token"], "subject": e.get("subject")})

    # ── 5. call and WhatsApp tasks: the simulated advisor ──
    def track_task(self, t):
        lo, hi = (conf().get("advisor_hours") or [1, 24])[:2]
        due = parse(t["created_at"]) + timedelta(hours=float(self.rng.uniform(float(lo), float(hi))))
        self.x("INSERT OR IGNORE INTO tasks (task_id, user_id, due_at) VALUES (?,?,?)", (t["id"], t["user_id"], ts(due)))

    def handle_tasks(self, now):
        wm = int(self.meta("task_wm") or 0)
        new = db.fetchall("""SELECT t.* FROM sales_tasks t JOIN users u ON u.id=t.user_id
                             WHERE t.id > ? AND u.email LIKE ? ORDER BY t.id""", (wm, LIKE))
        for t in new:
            self.track_task(t)
            wm = max(wm, int(t["id"]))
        if new:
            self.set_meta("task_wm", wm)
        for w in self.q("SELECT * FROM tasks WHERE handled=0"):
            t = db.fetchone("SELECT * FROM sales_tasks WHERE id=?", (w["task_id"],))
            L = self.learner(w["user_id"])
            if not t or not L or t["status"] not in ("open", "done"):
                self.x("UPDATE tasks SET handled=1 WHERE task_id=?", (w["task_id"],))
                continue
            if t["status"] == "open":
                if parse(w["due_at"]) > now:
                    continue
                if t["task_type"] == "call":
                    outcome = str(self.rng.choice(["reached", "no_answer", "not_interested"], p=[0.6, 0.3, 0.1]))
                else:
                    outcome = "sent"
                code, r = self.api.call("POST", f"/api/internal/tasks/{t['id']}/done",
                                        {"outcome": outcome, "done_by": "simulated advisor"}, internal=True)
                if code != 200:
                    self.log(now, L, "error", f"simulated advisor could not close task {t['id']}: {code} {r}")
                    self.x("UPDATE tasks SET handled=1 WHERE task_id=?", (w["task_id"],))
                    continue
                t = db.fetchone("SELECT * FROM sales_tasks WHERE id=?", (w["task_id"],))
                if t["status"] != "done":
                    continue
                verb = {"reached": "called and reached", "no_answer": "called — no answer",
                        "not_interested": "called — not interested", "sent": "sent a WhatsApp message to"}[outcome]
                self.log(now, None, "advisor", f"Simulated advisor {verb} {L['name']}.")
            self.x("UPDATE tasks SET handled=1, outcome=?, done_by=? WHERE task_id=?",
                   (t["outcome"], t.get("done_by"), w["task_id"]))
            self.task_outcome(L, t)

    def task_outcome(self, L, t):
        """A call that reached them or a WhatsApp that was sent changes their chance to buy for 14 days and makes
        them more likely to come back for two days (documented, as in the history)."""
        if L["bought"] or t.get("outcome") not in ("reached", "sent") or not t.get("done_at"):
            return
        action = "call" if t["task_type"] == "call" else "whatsapp"
        dec = db.fetchone("SELECT features_json FROM nba_decisions WHERE id=?", (t["decision_id"],)) if t.get("decision_id") else None
        feats = json.loads(dec["features_json"]) if dec and dec.get("features_json") else None
        done = parse(t["done_at"])
        self.add_effect(L, f"task:{t['id']}", action, self.effect_of(L, action, feats), done)
        until = datetime.combine(done.date() + timedelta(days=3), time.min)
        self.x("UPDATE learners SET boost=?, boost_until=? WHERE user_id=?",
               (0.5 if action == "call" else 0.3, ts(until), L["user_id"]))

    # ── 6. the dice: who comes back, who buys, who signs up ──
    def roll(self, now, dt_days):
        people = [L for L in self.q("SELECT * FROM learners WHERE bought=0")]
        if people:
            beh = self.behaviour()
            eff = {r["user_id"]: r["m"] for r in self.q("SELECT user_id, MAX(effect) AS m FROM effects WHERE starts_at <= ? "
                                                         "AND until > ? GROUP BY user_id", (ts(now), ts(now)))}
            uid = [int(L["user_id"]) for L in people]
            intent = np.array([L["intent"] for L in people], dtype=float)
            luck = np.array([L["luck"] for L in people], dtype=float)
            b = [beh.get(u, {}) for u in uid]
            seen = [x.get("last_seen") or L["created_at"] for x, L in zip(b, people)]
            gap = np.array([(now - parse(s)).total_seconds() / 86400 if s else 999.0 for s in seen])
            busy = np.array([bool(L["busy_until"]) and parse(L["busy_until"]) > now for L in people])
            boost = np.array([((L["boost"] or 0.0) if (L["boost_until"] and parse(L["boost_until"]) > now) else 0.0)
                              for L in people], dtype=float)
            flag = lambda f: np.array([x.get(f, 0) for x in b], dtype=float)
            feats = dict(occ=np.array([L["occ"] for L in people]), visits=np.maximum(flag("visits"), 1),
                         time_on_site=np.minimum(flag("secs"), 6000), video=flag("video"), pricing=flag("pricing"),
                         testimonial=flag("testimonial"), brochure=flag("brochure"), chat=flag("chat"),
                         webinar=flag("webinar"), wishlist=flag("wishlist"), cart=flag("cart"),
                         checkout=flag("checkout"), enquiry=flag("enquiry"), opens=np.minimum(flag("clicks"), 10),
                         whatsapp=np.array([L["wa"] for L in people], dtype=float),
                         dne=np.array([L["dne"] for L in people], dtype=float),
                         dnc=np.array([L["dnc"] for L in people], dtype=float))
            z = np.asarray(G.true_logit(feats, intent, luck), dtype=float) + H.BASE_SHIFT
            z += (H.WORLD_DRIFT["WhatsAppOptIn"] * feats["whatsapp"]
                  + H.WORLD_DRIFT["MobileDevice"] * np.array([L["device"] == "Mobile" for L in people], dtype=float)
                  + H.WORLD_DRIFT["WebinarAttended"] * feats["webinar"])
            z += np.array([float(eff.get(u, 0.0)) for u in uid])   # the strongest step of the last 14 days counts
            p14 = sig(z)
            daily_buy = 1 - (1 - p14) ** (1.0 / self.window)
            p_buy = np.where(gap <= self.window, 1 - (1 - daily_buy) ** dt_days, 0.0)
            daily_visit = sig(-2.6 + 0.7 * intent - 0.05 * gap + boost)
            p_visit = np.where((gap <= 21) & ~busy, 1 - (1 - daily_visit) ** dt_days, 0.0)
            buys = self.rng.random(len(people)) < p_buy
            visits = (self.rng.random(len(people)) < p_visit) & ~buys
            self.set_meta("in_market", int(((gap <= 21)).sum()))
            self.set_meta("expected_visits_per_day", round(float(np.where(gap <= 21, daily_visit, 0).sum()), 1))
            self.set_meta("expected_purchases_per_day", round(float(np.where(gap <= self.window, daily_buy, 0).sum()), 1))
            for j in np.flatnonzero(buys):
                self.plan_purchase(people[j], now, busy[j])
            for j in np.flatnonzero(visits):
                start = now + timedelta(seconds=float(self.rng.uniform(0, dt_days * 86400)))
                self.enqueue(start, people[j]["user_id"], "visit", {})
        rate = float(conf().get("new_signups_per_day") or 0)
        has_people = bool(self.q1("SELECT 1 AS x FROM learners LIMIT 1"))   # no starting history: no invented people
        if has_people and rate > 0 and self.rng.random() < 1 - np.exp(-rate * dt_days):
            self.signup(now)

    # ── 7. a visit, step by step (the requests a browser sends) ──
    def plan_visit(self, L, start, came_from=None, then_buy=False, note=None):
        beh = self.behaviour([L["user_id"]]).get(L["user_id"], {})
        flags = {f: int(beh.get(f, 0)) for f, *_ in H.EVENTS} | {"checkout": int(beh.get("checkout", 0))}
        first = int(beh.get("visits", 0)) == 0
        boost = (L["boost"] or 0.0) if L["boost_until"] and parse(L["boost_until"]) > start else 0.0
        intent = L["intent"] + boost
        n_pages = int(min(10, 1 + self.rng.poisson(np.exp(0.4 + 0.25 * L["intent"]))))
        page_secs = np.maximum(1, np.minimum(600, self.rng.lognormal(np.log(50) + 0.25 * L["intent"], 0.6, n_pages))).astype(int)
        dur = int(page_secs.sum())
        source = L["source"] if first else (came_from or "Direct Traffic")
        vid = uuid.uuid4().hex[:12]
        steps, did = [], []
        clock = start
        for k, secs in enumerate(page_secs):
            for s in range(30, int(secs), 30):           # tracker.js: "still here" every 30 s while reading
                steps.append((clock + timedelta(seconds=s), "ping", {}))
            clock = clock + timedelta(seconds=int(secs))
            slug = L["slug"] if k == 0 or self.rng.random() < 0.7 else None
            steps.append((clock, "page", {"slug": slug, "secs": int(secs)}))
        for flag, etype, a, bslope in H.EVENTS:
            if flags.get(flag):
                continue
            extra = 0.5 * flags["pricing"] if flag == "cart" else 0.0
            if self.rng.random() < float(sig(a + bslope * intent + extra)):
                at = start + timedelta(seconds=int(self.rng.uniform(0.2, 1.0) * max(dur, 30)))
                flags[flag] = 1
                did.append(flag)
                kind = flag if flag in ("wishlist", "cart", "enquiry", "chat") else "event"
                steps.append((at, kind, {"etype": etype, "slug": None if flag == "webinar" else L["slug"]}))
                if flag == "cart" and self.rng.random() < float(sig(-1.0 + 0.9 * intent)):
                    steps.append((at + timedelta(minutes=2), "checkout", {}))
                    flags["checkout"] = 1
                    did.append("checkout")
        end = max(t for t, *_ in steps)
        if then_buy:
            steps.append((end + timedelta(minutes=2), "buy", {}))
            end = end + timedelta(minutes=2)
        title = catalog.title_of(L["slug"]) if catalog.get_course(L["slug"]) else L["slug"]
        doing = ", ".join(STEP_TEXT[f].format(course=title) for f in did)
        how = {"Email Campaign": "came back from an e-mail", None: "came back"}.get(came_from, "came back")
        if first:
            how = "is on the website for the first time"
        summary = f"{how}: {n_pages} page{'s' if n_pages > 1 else ''}, {max(1, round(dur / 60))} min" + \
                  (f"; {doing}" if doing else "") + ("; then buys" if then_buy else "") + (f" ({note})" if note else "")
        self.enqueue(start, L["user_id"], "session", {"source": source, "device": L["device"], "summary": summary}, vid)
        for at, kind, payload in sorted(steps, key=lambda s: s[0]):
            self.enqueue(at, L["user_id"], kind, payload, vid)
        self.x("UPDATE learners SET busy_until=? WHERE user_id=?", (ts(end + timedelta(minutes=1)), L["user_id"]))
        return {"visit": vid, "start": ts(start), "end": ts(end), "summary": summary}

    def plan_purchase(self, L, now, busy=False):
        if busy:                               # on the website right now: buys at the end of this visit
            end = parse(L["busy_until"])
            self.enqueue(end, L["user_id"], "buy", {})
        else:                                  # comes back to buy
            self.plan_visit(L, now + timedelta(seconds=float(self.rng.uniform(0, 60))), "Direct Traffic", then_buy=True)

    # ── 8. carry out what is due ──
    def token(self, L):
        tok = self._tokens.get(L["user_id"])
        if tok and tok[1] > _time.time():
            return tok[0]
        import auth                                # the website's own tokens: they are simply logged in
        t = auth.create_token(L["user_id"], L["email"])
        self._tokens[L["user_id"]] = (t, _time.time() + 6 * 3600)
        return t

    def call(self, method, path, body=None, L=None):
        return self.api.call(method, path, body, token=self.token(L) if L else None)

    def track(self, L, etype, slug=None, secs=0):
        code, r = self.call("POST", "/api/track", {"session_id": int(L["session_id"] or 0), "course_slug": slug,
                                                   "event_type": etype, "time_spent_sec": int(secs)}, L)
        if code != 200:
            raise RuntimeError(f"track {etype}: {code} {r}")
        return r

    def process_queue(self, now):
        steps = self.q("SELECT * FROM queue WHERE due_at <= ? ORDER BY due_at, id LIMIT 300", (ts(now),))
        dropped = set()
        for st in steps:
            self.x("DELETE FROM queue WHERE id=?", (st["id"],))
            if st["visit"] and st["visit"] in dropped:
                continue
            L = self.learner(st["user_id"])
            if not L:
                continue
            if now - parse(st["due_at"]) > LATE:
                if st["visit"]:
                    dropped.add(st["visit"])
                    self.x("DELETE FROM queue WHERE visit=?", (st["visit"],))
                    self.x("UPDATE learners SET busy_until=NULL WHERE user_id=?", (L["user_id"],))
                continue                       # the website was not running then: it did not happen
            if L["bought"]:
                continue
            try:
                self.run_step(L, st, now)
            except Offline:
                self.x("INSERT INTO queue (id, due_at, user_id, visit, kind, payload) VALUES (?,?,?,?,?,?)",
                       (st["id"], st["due_at"], st["user_id"], st["visit"], st["kind"], st["payload"]))
                raise
            except Exception as e:             # one learner's step failing must not stop the others
                self.log(now, L, "error", f"— {st['kind']} failed: {e}")
                if st["kind"] == "session" and st["visit"]:
                    dropped.add(st["visit"])
                    self.x("DELETE FROM queue WHERE visit=?", (st["visit"],))
                    self.x("UPDATE learners SET busy_until=NULL WHERE user_id=?", (L["user_id"],))

    def run_step(self, L, st, now):
        kind, p = st["kind"], json.loads(st["payload"] or "{}")
        slug = L["slug"]
        title = catalog.title_of(slug) if catalog.get_course(slug) else slug
        if kind == "visit":
            if L["busy_until"] and parse(L["busy_until"]) > now:
                return                         # already on the site
            self.plan_visit(L, now, p.get("came_from"), then_buy=bool(p.get("buy")), note=p.get("note"))
        elif kind == "session":                # the browser starts a visit (tracker.js ensureSession)
            code, r = self.call("POST", "/api/session/start", {"device_type": p["device"], "lead_source": p["source"]}, L)
            if code != 200 or not (r or {}).get("session_id"):
                raise RuntimeError(f"session start: {code} {r}")
            self.x("UPDATE learners SET session_id=? WHERE user_id=?", (int(r["session_id"]), L["user_id"]))
            self.log(now, L, "visit", p.get("summary") or "is on the website")
        elif kind == "page":                   # time on a page, sent when they leave it
            self.track(L, "page_view", p.get("slug"), p.get("secs", 0))
        elif kind == "ping":                   # tracker.js: still on the page
            self.call("POST", "/api/session/ping", {"session_id": int(L["session_id"] or 0)}, L)
        elif kind == "event":
            self.track(L, p["etype"], p.get("slug"))
        elif kind == "wishlist":               # CourseDetail.jsx handleWishlist
            code, r = self.call("POST", "/api/wishlist", {"course_slug": slug, "course_title": title}, L)
            if code == 200:
                self.track(L, "wishlist_add", slug)
        elif kind == "cart":                   # CourseDetail.jsx handleCart
            code, r = self.call("POST", "/api/cart", {"course_slug": slug}, L)
            if code == 200:
                self.track(L, "cart_add", slug)
        elif kind == "checkout":               # Checkout.jsx: checkoutStart() + tracker.checkoutStart()
            self.call("POST", "/api/checkout/start", None, L)
            self.track(L, "checkout_start")
        elif kind == "enquiry":                # Enquiry.jsx (phone and WhatsApp choice pre-filled from the profile)
            code, r = self.call("POST", "/api/enquiry", {"course_slug": slug, "course_type": title,
                                                         "phone": L["phone"], "whatsapp_opt_in": int(L["wa"])}, L)
            if code != 200:
                raise RuntimeError(f"enquiry: {code} {r}")
        elif kind == "chat":                   # ChatWidget.jsx: tracker.chat() on the first message, then the question
            self.track(L, "chat")
            self.call("POST", "/api/chat", {"message": str(self.rng.choice(CHAT_QUESTIONS)),
                                            "conversation_id": uuid.uuid4().hex, "course_slug": slug}, L)
        elif kind == "click":                  # the e-mail's button opens the course page with ?ref=<token>
            code, r = self.api.call("POST", "/api/email/click", {"token": p["token"]})
            if code == 200 and (r or {}).get("ok"):
                self.log(now, L, "click", f"clicked the e-mail “{(p.get('subject') or '')[:70]}”")
                if not (L["busy_until"] and parse(L["busy_until"]) > now):
                    self.enqueue(now + timedelta(minutes=1), L["user_id"], "visit", {"came_from": "Email Campaign"})
        elif kind == "buy":
            self.buy(L, now)

    def buy(self, L, now):
        """Cart -> checkout -> pay, with their best valid coupon (Checkout.jsx)."""
        slug = L["slug"]
        code, r = self.call("GET", "/api/cart", None, L)
        if slug not in {c.get("course_slug") for c in ((r or {}).get("cart") or [])}:
            code, r = self.call("POST", "/api/cart", {"course_slug": slug}, L)
            if code == 200:
                self.track(L, "cart_add", slug)
        self.call("POST", "/api/checkout/start", None, L)
        self.track(L, "checkout_start")
        code, r = self.call("GET", "/api/coupons", None, L)
        nowts = ts(now)
        valid = [c for c in ((r or {}).get("coupons") or [])
                 if not c.get("used") and (not c.get("expires_at") or str(c["expires_at"])[:19] > nowts)]
        best = max(valid, key=lambda c: c.get("discount_pct") or 0) if valid else None
        code, r = self.call("POST", "/api/checkout", {"coupon_code": best["coupon_code"] if best else ""}, L)
        if code == 400 and best:               # the coupon ran out a moment ago: pay full price
            best = None
            code, r = self.call("POST", "/api/checkout", {"coupon_code": ""}, L)
        if code != 200:
            raise RuntimeError(f"checkout: {code} {r}")
        self.x("UPDATE learners SET bought=1, busy_until=NULL WHERE user_id=?", (L["user_id"],))
        self.x("DELETE FROM queue WHERE user_id=?", (L["user_id"],))
        title = catalog.title_of(slug) if catalog.get_course(slug) else slug
        self.log(now, L, "buy", f"bought {title}" + (f" with the coupon {best['coupon_code']} ({best['discount_pct']}% off)"
                                                      if best else " at full price"))

    # ── 9. new people sign up (Signup.jsx -> VerifyOtp -> CompleteProfile -> Settings) ──
    def signup(self, now):
        k = int(self.meta("next_k") or history_size()[0])
        for _ in range(20):                     # skip any number already used
            tr = new_traits(k)
            if not db.fetchone("SELECT id FROM users WHERE email=?", (tr["email"],)):
                break
            k += 1
        self.set_meta("next_k", k + 1)
        code, r = self.api.call("POST", "/api/auth/signup", {"name": tr["name"], "email": tr["email"],
                                                             "password": uuid.uuid4().hex})
        if code != 200:
            self.log(now, None, "error", f"Sign-up of {tr['email']} refused: {code} {r}")
            return None
        row = db.fetchone("""SELECT otp FROM otp_tokens WHERE email=? AND COALESCE(purpose,'signup')='signup' AND used=0
                             ORDER BY id DESC LIMIT 1""", (tr["email"],))     # the code from their inbox
        code, r = self.api.call("POST", "/api/auth/verify-otp", {"email": tr["email"], "otp": (row or {}).get("otp", "")})
        if code != 200:
            self.log(now, None, "error", f"Verification of {tr['email']} failed: {code} {r}")
            return None
        uid, token = int(r["user"]["id"]), r["token"]
        raw = tr["raw"]
        known = lambda v: None if v in (None, "Unknown") else v
        if raw["CurrentOccupation"] != "Unknown":
            self.api.call("POST", "/api/profile/complete", {
                "current_occupation": raw["CurrentOccupation"], "specialization": raw["Specialization"],
                "age_bracket": known(raw["AgeBracket"]), "city": raw["City"], "country": raw["Country"],
                "phone": tr["phone"], "how_did_you_hear": raw["HowDidYouHear"]}, token=token)
        self.api.call("PUT", "/api/profile/preferences", {"do_not_email": bool(tr["dne"]), "do_not_call": bool(tr["dnc"]),
                                                         "whatsapp_opt_in": bool(tr["wa"]), "phone": tr["phone"]}, token=token)
        self.x("""INSERT OR REPLACE INTO learners (user_id, email, name, k, joined, intent, luck, noise_json, slug, device,
                  source, occ, dne, dnc, wa, phone, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
               (uid, tr["email"], tr["name"], k, "live", tr["intent"], tr["luck"], json.dumps(tr["noise"]), tr["slug"],
                tr["device"], tr["source"], tr["occ"], tr["dne"], tr["dnc"], tr["wa"], tr["phone"], ts(now)))
        self._tokens[uid] = (token, _time.time() + 6 * 3600)
        L = self.learner(uid)
        occ = tr["occ"] if tr["occ"] != "Unknown" else "no profile"
        self.log(now, L, "signup", f"signed up ({occ}, came from {tr['source']})")
        self.enqueue(now + timedelta(seconds=float(self.rng.uniform(20, 90))), uid, "visit", {"came_from": tr["source"]})
        return L

    # ── the clock ──
    def tick(self):
        """Called every few seconds by the user-backend's scheduler."""
        if not self._busy.acquire(blocking=False):
            return
        try:
            with self.lock:
                if not self.enabled():
                    return
                now = self.clock()
                try:
                    if self._last_sync is None or now - self._last_sync > timedelta(minutes=10):
                        self.sync(now)
                    self.process_queue(now)
                    self.handle_emails(now)
                    self.handle_tasks(now)
                    last = self.meta("last_roll")
                    last = parse(last) if last else None
                    if last is None or now - last >= ROLL_EVERY:
                        gap = (now - last) if last else ROLL_EVERY
                        if gap > 3 * ROLL_EVERY:       # the servers were off: that time is not simulated
                            gap = ROLL_EVERY
                        self.roll(now, gap.total_seconds() / 86400)
                        self.set_meta("last_roll", ts(now))
                    self.process_queue(now)
                    self.set_meta("last_tick", ts(now))
                    self.last_error = None
                    if now.minute == 0 and now.second < 20:          # keep the diary short
                        self.x("DELETE FROM log WHERE id < (SELECT COALESCE(MAX(id),0) - 5000 FROM log)")
                except Offline as e:
                    self.last_error = f"The website's API is not reachable yet ({e}); trying again in a few seconds."
        finally:
            self._busy.release()

    # ── the dashboard ──
    def visit_now(self, kind="returning"):
        """'Send a simulated learner to the website now': instead of waiting for the dice, one learner who is
        still deciding (picked with their own chance of coming back) starts a visit now. What they do there is
        drawn exactly as for any other visit. kind='signup': a new learner signs up now."""
        with self.lock:
            if not self.enabled():
                raise Paused("The simulated learners are paused — resume them first.")
            now = self.clock()
            if self._last_sync is None:
                self.sync(now)
            L = None
            if kind != "signup":
                people = self.q("SELECT * FROM learners WHERE bought=0")
                beh = self.behaviour()
                cand, w = [], []
                for P in people:
                    if P["busy_until"] and parse(P["busy_until"]) > now:
                        continue
                    seen = (beh.get(P["user_id"]) or {}).get("last_seen") or P["created_at"]
                    gap = (now - parse(seen)).total_seconds() / 86400 if seen else 999
                    if gap <= 21:
                        cand.append(P)
                        w.append(float(sig(-2.6 + 0.7 * P["intent"] - 0.05 * gap)))
                if cand:
                    w = np.asarray(w) / np.sum(w)
                    L = cand[int(self.rng.choice(len(cand), p=w))]
                    L["noise"] = json.loads(L["noise_json"] or "{}")
                    self.enqueue(now, L["user_id"], "visit", {"note": "sent to the website from the dashboard"})
            if L is None:
                try:
                    L = self.signup(now)
                except Offline as e:
                    raise Offline(str(e))
                if L is None:
                    raise RuntimeError("The sign-up did not go through — see the user-backend window.")
                kind = "signup"
        threading.Thread(target=self.tick, daemon=True).start()      # start right away, not at the next tick
        lead = db.fetchone("SELECT MAX(id) AS id FROM leads WHERE user_id=?", (L["user_id"],)) or {}
        return {"user_id": L["user_id"], "name": L["name"], "lead_id": lead.get("id"), "kind": kind,
                "message": (f"{L['name']} signed up and will open the website in about a minute." if kind == "signup" else
                            f"{L['name']} is on the website now. Their lead page updates as they go; the CRM decides "
                            f"what to do about a minute after they leave (demo timing).")}

    def status(self):
        now = self.clock()
        with self.lock:
            tot = self.q1("""SELECT COUNT(*) AS n, SUM(bought) AS bought, SUM(joined='live') AS live,
                                    SUM(CASE WHEN busy_until > ? THEN 1 ELSE 0 END) AS busy FROM learners""", (ts(now),)) or {}
            day = ts(now - timedelta(days=1))
            counts = {r["kind"]: r["n"] for r in self.q("SELECT kind, COUNT(*) AS n FROM log WHERE at >= ? GROUP BY kind", (day,))}
            recent = self.q("SELECT at, user_id, kind, text FROM log WHERE kind != 'error' ORDER BY id DESC LIMIT 15")
            errors = self.q("SELECT at, text FROM log WHERE kind='error' ORDER BY id DESC LIMIT 3")
            nxt = self.q1("SELECT MIN(due_at) AS d, COUNT(*) AS n FROM queue") or {}
            out = {
                "enabled": self.enabled(), "started_at": self.meta("started_at"), "last_tick": self.meta("last_tick"),
                "last_error": self.last_error,
                "learners": {"total": int(tot.get("n") or 0), "customers": int(tot.get("bought") or 0),
                             "signed_up_live": int(tot.get("live") or 0), "on_site_now": int(tot.get("busy") or 0),
                             "still_deciding": int(self.meta("in_market") or 0)},
                "expected_per_day": {"visits": float(self.meta("expected_visits_per_day") or 0),
                                     "purchases": float(self.meta("expected_purchases_per_day") or 0),
                                     "signups": float(conf().get("new_signups_per_day") or 0)},
                "last_24h": {"visits": counts.get("visit", 0), "email_clicks": counts.get("click", 0),
                             "purchases": counts.get("buy", 0), "signups": counts.get("signup", 0),
                             "advisor_tasks": counts.get("advisor", 0), "errors": counts.get("error", 0)},
                "recent": recent, "recent_errors": errors,
                "queued_steps": int(nxt.get("n") or 0), "next_step_at": nxt.get("d"),
            }
        return out


_world = {"w": None}
_world_lock = threading.Lock()


def get_world():
    with _world_lock:
        if _world["w"] is None:
            _world["w"] = World()
        return _world["w"]


def tick():
    get_world().tick()


def main():
    ap = argparse.ArgumentParser(description="The simulated learners, living in real time (see the docstring).")
    ap.add_argument("--status", action="store_true", help="what they did recently")
    ap.add_argument("--reset", action="store_true", help="forget the simulator's to-do list (not the CRM's data)")
    args = ap.parse_args()
    w = get_world()
    if args.reset:
        for t in ("effects", "tasks", "queue", "log", "meta", "learners"):
            w.x(f"DELETE FROM {t}")
        print("The simulator's own records were cleared; it re-creates them from the CRM on its next start.")
    else:
        print(json.dumps(w.status(), indent=2, default=str))


if __name__ == "__main__":
    main()
