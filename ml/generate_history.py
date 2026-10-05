"""
=================================================================
 STARTING HISTORY — six months of simulated X Education history
=================================================================
 A new CRM has no history, but everything that learns (the live layer of the lead
 model, next-best-action, the A/B engine, the what-if paths) needs some. This script
 builds a realistic starting history "from scratch", clearly marked as simulated:

   * ~2,000 learners sign up over the last 180 days (profiles and hidden intent from the
     documented generator, ml/generate_dataset.py)
   * day by day they visit the website: page views, course video, pricing, brochure,
     testimonials, webinar, chat, wishlist, cart, checkout, enquiries — the same events
     the tracker records, written to the same tables
   * the CRM reacts exactly as the live system does: every visit re-scores the lead,
     triggers (enquiry, checkout/cart left, wishlist, visit ended) go to next-best-action
     with its 15 % random exploration and logged probabilities, which sends emails and
     coupons or creates call / WhatsApp tasks
   * learners react: they click emails (or not), come back, answer calls (or not), buy
   * a monthly email campaign with a 10 % hold-out group, and six A/B tests with a
     no-email control group (one still running "now"), each with documented effects
     that differ between segments
   * the learning loop (user-backend/learning.py) runs at the end of every month on the
     data known at that time; the following month is scored with what it learned — so
     the dashboard shows six months of the loop learning
 Whether someone buys is drawn from the simulator: the generator's documented buying
 formula on their behaviour so far, plus the documented effect of every email, coupon,
 call or campaign they received in the last 14 days (ml/nba_simulation.py).

 Everything is clearly marked and removable:
   * learner emails end in @demo.xeducation.test (never mailed; the email code refuses it)
   * campaigns, A/B tests and learning runs carry a 'simulated' flag
   * --remove deletes all of it and restores the starting models

 Usage (with the backend venv; servers may be running):
   user-backend\\venv\\Scripts\\python.exe ml\\generate_history.py              (2,000 learners)
   user-backend\\venv\\Scripts\\python.exe ml\\generate_history.py --n 1000
   user-backend\\venv\\Scripts\\python.exe ml\\generate_history.py --remove
=================================================================
"""
import os
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")      # thousands of single-row predictions: thread pools only slow them down
import argparse
import heapq
import importlib.util
import json
import os
import shutil
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timedelta

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.normpath(os.path.join(HERE, "..", "user-backend"))
MKT_DIR = os.path.normpath(os.path.join(HERE, "..", "marketing-backend"))
sys.path.insert(0, HERE)
sys.path.insert(0, BACKEND)

DEMO_DOMAIN = "demo.xeducation.test"
SIM = "(simulated)"
TS = "%Y-%m-%d %H:%M:%S"
FIRST = ["Aarav", "Vivaan", "Aditya", "Arjun", "Rohan", "Karan", "Ishaan", "Kabir", "Rahul", "Siddharth",
         "Ananya", "Diya", "Isha", "Kavya", "Meera", "Nisha", "Pooja", "Riya", "Sneha", "Tanvi",
         "Aditi", "Harsh", "Nikhil", "Pranav", "Varun", "Neha", "Shreya", "Divya", "Simran", "Zoya",
         "Amit", "Deepak", "Gaurav", "Manish", "Rajat", "Sahil", "Tarun", "Vikram", "Yash", "Abhishek",
         "Bhavna", "Charu", "Gauri", "Jaya", "Komal", "Lavanya", "Mansi", "Payal", "Ritika", "Swati",
         "Akash", "Dev", "Kunal", "Mohit", "Naveen", "Om", "Parth", "Sameer", "Uday", "Vivek"]
LAST = ["Sharma", "Verma", "Patel", "Iyer", "Nair", "Reddy", "Gupta", "Mehta", "Joshi", "Kulkarni",
        "Desai", "Rao", "Singh", "Chopra", "Bose", "Menon", "Pillai", "Shah", "Kapoor", "Agarwal",
        "Banerjee", "Chatterjee", "Das", "Dutta", "Ghosh", "Jain", "Khanna", "Malhotra", "Mishra", "Pandey",
        "Saxena", "Sinha", "Srivastava", "Tiwari", "Trivedi", "Bhatt", "Chauhan", "Dubey", "Hegde", "Kamath",
        "Naidu", "Prasad", "Shetty", "Thakur", "Yadav"]          # 60 x 45 = 2,700 different names


# ── documented behaviour of the simulated learners (per visit, log-odds) ──────────────
EVENTS = [  # flag, event_type, base, intent slope
    ("video", "video_play", -1.4, 0.9), ("pricing", "pricing_view", -1.3, 0.9),
    ("testimonial", "testimonial_view", -2.0, 0.6), ("brochure", "brochure_dl", -2.3, 1.0),
    ("chat", "chat", -3.1, 0.7), ("webinar", "webinar_register", -3.6, 0.9),
    ("wishlist", "wishlist_add", -2.8, 0.8), ("cart", "cart_add", -3.0, 1.1),
    ("enquiry", "enquiry_submit", -3.4, 0.9),
]
BASE_SHIFT = float(os.getenv("HISTORY_BASE_SHIFT", "-2.0"))          # calibrated so ~39 % of learners buy within the 6 months (real X Education data: 38.5 %)
# How THIS simulated business differs from the data the base lead model was trained on (log-odds of
# buying). A real business never matches its training data exactly; these three documented
# differences give the learning loop something real to discover (ml/experiments/history_check.py
# compares what it learned with these values). HISTORY_DRIFT=0 switches them off (for comparison runs).
WORLD_DRIFT = {"WhatsAppOptIn": 0.6, "MobileDevice": -0.5, "WebinarAttended": 0.7}
if os.getenv("HISTORY_DRIFT", "1") == "0":
    WORLD_DRIFT = {k: 0.0 for k in WORLD_DRIFT}
LEARN_DAYS = (30, 60, 90, 120, 150)
CAMPAIGNS = [  # day, name, audience, subject, body
    (20, "October cohort announcement", "All leads", "New {course} batch starts soon, {first_name}",
     "Hi {first_name},\n\nA new batch of {course} starts soon. Have a look at the curriculum and the "
     "instructor, and reserve a seat if it fits your plans."),
    (50, "EMI options explained", "Nurture via Email/WhatsApp", "Pay for {course} from ₹2,200 a month",
     "Hi {first_name},\n\nMany learners spread the fee for {course} over monthly EMIs. Here is how it works."),
    (80, "Free career webinar", "Marketing Campaign", "Free live session this Saturday, {first_name}",
     "Hi {first_name},\n\nJoin our free live session with instructors this Saturday and ask anything about {course}."),
    (110, "Learner stories", "All leads", "How learners like you finished {course}",
     "Hi {first_name},\n\nThree short stories from learners who balanced {course} with work or studies."),
    (140, "Curriculum update", "Target Immediately", "What's new in {course} this term",
     "Hi {first_name},\n\nWe refreshed two modules of {course}. Here is what changed."),
    (170, "Last seats reminder", "All leads", "A few seats left in {course}",
     "Hi {first_name},\n\nA few seats are left in the next {course} batch."),
]
# A/B tests: documented effects. buy/click = extra log-odds for the variant; 'coupon10'/'coupon20' use
# the simulator's coupon effects (bigger for price-sensitive learners); callables depend on the learner.
# Six A/B tests with KNOWN true effects (log-odds; "click" moves clicks, "buy" moves buying once the
# learner is back on the site). They are designed so the history shows every kind of verdict:
#   day  40  too small to tell (the plan warns about it)      day 100  a click winner (urgency subject)
#   day  70  a true null (neither email does anything)        day 130  a winner only on mobile phones
#   day 160  a clear purchase winner (personalised course)    day 175  still running at the end
AB_TESTS = [
    {"day": 40, "name": "10% vs 20% coupon", "audience": "All leads", "metric": "purchase",
     "hypothesis": "A 20% coupon converts more learners than 10%, but may not pay for the extra discount.",
     "variants": [
         {"key": "A", "label": "10% coupon", "offer_pct": 10, "click": 0.2, "buy": "coupon10",
          "subject": "10% off {course} for the next 72 hours",
          "body": "Hi {first_name},\n\nHere is 10% off {course}, valid for 72 hours."},
         {"key": "B", "label": "20% coupon", "offer_pct": 20, "click": 0.35, "buy": "coupon20",
          "subject": "20% off {course} for the next 72 hours",
          "body": "Hi {first_name},\n\nHere is 20% off {course}, valid for 72 hours."}]},
    {"day": 70, "name": "Webinar invite vs brochure", "audience": "Low Priority", "metric": "purchase",
     "hypothesis": "Cold leads respond better to a live webinar than to a brochure.",
     "variants": [
         {"key": "A", "label": "Free webinar invite", "offer_pct": 0, "click": 0.0, "buy": 0.0,
          "subject": "Free live session on {course}",
          "body": "Hi {first_name},\n\nJoin a free live session on {course} this Saturday."},
         {"key": "B", "label": "Course brochure", "offer_pct": 0, "click": 0.0, "buy": 0.0,
          "subject": "The {course} brochure",
          "body": "Hi {first_name},\n\nCurriculum, fees and instructor of {course} on one page."}]},
    {"day": 100, "name": "Subject line: benefit vs urgency", "audience": "All leads", "metric": "click",
     "hypothesis": "An urgency subject line gets more people to click than a benefit-led one.",
     "variants": [
         {"key": "A", "label": "Benefit-led subject", "offer_pct": 0, "click": 0.0, "buy": 0.10,
          "subject": "{first_name}, your next career step: {course}",
          "body": "Hi {first_name},\n\nSee how {course} fits your goals: curriculum, instructor and outcomes."},
         {"key": "B", "label": "Urgency subject", "offer_pct": 0, "click": 0.80, "buy": 0.10,
          "subject": "Last seats in the {course} batch",
          "body": "Hi {first_name},\n\nThe next {course} batch is filling up. Reserve your seat this week."}]},
    {"day": 130, "name": "Short mobile email vs long email", "audience": "All leads", "metric": "purchase",
     "hypothesis": "A short email works better on phones; a long one on desktop.",
     "variants": [
         {"key": "A", "label": "Long email", "offer_pct": 0, "click": 0.0,
          "buy": lambda L: 0.40 if L["device"] != "Mobile" else 0.0,
          "subject": "Everything about {course} in one email",
          "body": "Hi {first_name},\n\nModules, projects, instructor, fees, EMI and outcomes of {course} in detail."},
         {"key": "B", "label": "Short mobile-first email", "offer_pct": 0,
          "click": lambda L: 0.9 if L["device"] == "Mobile" else 0.0,
          "buy": lambda L: 1.4 if L["device"] == "Mobile" else 0.0,
          "subject": "{course} in 30 seconds",
          "body": "Hi {first_name},\n\n{course}: 3 reasons, 1 link."}]},
    {"day": 160, "name": "Personalised course pick vs generic newsletter", "audience": "All leads", "metric": "purchase",
     "hypothesis": "A course picked for the learner's background converts better than a generic newsletter.",
     "variants": [
         {"key": "A", "label": "Generic newsletter", "offer_pct": 0, "click": 0.0, "buy": 0.0,
          "subject": "This month at X Education",
          "body": "Hi {first_name},\n\nNews, new batches and learner stories from X Education."},
         {"key": "B", "label": "Personalised course pick", "offer_pct": 0, "click": 1.0, "buy": 1.2,
          "subject": "{first_name}, {course} fits your background",
          "body": "Hi {first_name},\n\nBased on what you looked at, {course} is the best next step for you."}]},
    {"day": 175, "name": "EMI message vs refund guarantee", "audience": "All leads", "metric": "purchase",
     "hypothesis": "A refund guarantee removes more doubt than an EMI message.",
     "variants": [
         {"key": "A", "label": "EMI from \u20b92,200/month", "offer_pct": 0, "click": 0.1, "buy": 0.20,
          "subject": "{course} from \u20b92,200 a month",
          "body": "Hi {first_name},\n\nSpread the fee of {course} over easy monthly EMIs."},
         {"key": "B", "label": "7-day refund guarantee", "offer_pct": 0, "click": 0.15, "buy": 0.25,
          "subject": "Try {course} risk-free for 7 days",
          "body": "Hi {first_name},\n\nStart {course}; if it isn't for you, get a full refund within 7 days."}]},
]


def ts(t):
    return t.strftime(TS)


def sig(x):
    return 1.0 / (1.0 + np.exp(-x))


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class SharedConn(sqlite3.Connection):
    """One connection for the whole run (database.py opens one per query otherwise)."""
    def close(self):
        pass

    def really_close(self):
        sqlite3.Connection.close(self)


# ── removal ───────────────────────────────────────────────────────────────────
def demo_user_ids(db):
    return [r["id"] for r in db.fetchall("SELECT id FROM users WHERE email LIKE ?", (f"%@{DEMO_DOMAIN}",))]


def _mkt_path():
    return os.path.join(MKT_DIR, "xeducation_marketing.db")


def restore_starting_models():
    import learning
    for name in ("lead_model", "nba_model"):
        start = os.path.join(learning.MODEL_DIR, f"{name}.starter.pkl")
        cur = os.path.join(learning.MODEL_DIR, f"{name}.pkl")
        if os.path.exists(start):
            shutil.copy2(start, cur)
    try:
        import joblib
        import lead_model as LM
        b = joblib.load(learning.LEAD_PATH)
        card = {k: v for k, v in b.items() if k != "starter"}
        card["learned_signals"] = LM.learned_points(b)
        with open(learning.CARD_PATH, "w", encoding="utf-8") as f:
            json.dump(card, f, indent=2, default=str)
        nb = joblib.load(learning.NBA_PATH)
        with open(learning.NBA_CARD_PATH, "w", encoding="utf-8") as f:
            json.dump({k: v for k, v in nb.items() if k != "model"}, f, indent=2, default=str)
    except Exception as e:
        print(f"(model cards not refreshed: {e})")
    try:
        import predict
        predict.reload()
    except Exception:
        pass


def remove(db):
    ids = demo_user_ids(db)
    con = db.get_conn()
    try:
        if ids:
            q = ",".join("?" * len(ids))
            tables = [r["name"] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            for t in tables:
                cols = [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
                if "user_id" in cols and t != "users":
                    con.execute(f"DELETE FROM {t} WHERE user_id IN ({q})", ids)
            con.execute("DELETE FROM otp_tokens WHERE email LIKE ?", (f"%@{DEMO_DOMAIN}",))
            con.execute(f"DELETE FROM users WHERE id IN ({q})", ids)
        con.execute("DELETE FROM learning_runs WHERE simulated=1")
        try:
            con.execute("DELETE FROM adopted_emails WHERE simulated=1")
        except sqlite3.OperationalError:          # database from before v6
            pass
        con.commit()
    finally:
        con.close()
    if os.path.exists(_mkt_path()):
        c = sqlite3.connect(_mkt_path(), timeout=30)
        try:
            for sql in ("DELETE FROM campaign_schedules WHERE simulated=1", "DELETE FROM ab_tests WHERE simulated=1"):
                try:
                    c.execute(sql)
                except sqlite3.OperationalError:
                    pass
            if ids:
                try:
                    c.execute(f"DELETE FROM sms_queue WHERE user_id IN ({','.join('?' * len(ids))})", ids)
                except sqlite3.OperationalError:
                    pass
            c.commit()
        finally:
            c.close()
    restore_starting_models()
    print(f"Removed {len(ids)} simulated learners, their history, the simulated campaigns, A/B tests and "
          f"learning runs, and restored the starting models.")


# ── the simulation ────────────────────────────────────────────────────────────
class History:
    def __init__(self, db, n, days, seed, verbose=True):
        import catalog
        import generate_dataset as G
        import learning
        import lead_model as LM
        import ml_features as F
        import nba
        import nba_core as N
        import nba_simulation as S
        import predict
        import scoring
        import settings
        from genai_mock import generate_content
        self.db, self.n, self.days, self.verbose = db, n, days, verbose
        self.G, self.S, self.N, self.F, self.LM = G, S, N, F, LM
        self.nba, self.predict, self.scoring, self.catalog, self.learning = nba, predict, scoring, catalog, learning
        self.generate_content = generate_content
        self.settings = settings
        self.E = _load_module("xcrm_experiments", os.path.join(MKT_DIR, "experiments.py"))
        self.mkt_schema = _load_module("xcrm_mkt_schema", os.path.join(MKT_DIR, "mkt_schema.py"))
        sys.modules.setdefault("experiments", self.E)          # adoption.py imports it by this name
        self.adoption = _load_module("xcrm_adoption", os.path.join(MKT_DIR, "adoption.py"))
        import adopted
        self.adopted = adopted
        self.ab_specs = {}       # ab_tests.id -> the test's documented variants (true effects)
        self.rng = np.random.default_rng(seed)
        self.seed = seed
        self.now = datetime.now().replace(microsecond=0)
        self.start = (self.now - timedelta(days=days)).replace(hour=0, minute=0, second=0)
        self.explore = float(nba.EXPLORE_RATE)
        self.capacity = int(nba.DAILY_CALL_CAPACITY)
        self.window = int(settings.S["outcome_window_days"])
        self.queue = []          # (time, seq, kind, payload) — clicks and call outcomes happen later
        self.seq = 0
        self.calls_today = {}
        self.stats = {k: 0 for k in ("visits", "decisions", "explore", "emails", "clicks", "calls", "whatsapp",
                                     "purchases", "campaign_emails", "ab_people", "runs", "lead_swaps", "nba_swaps")}
        self.slugs_by_type = {}
        for slug, ctype in F.COURSE_TYPE_BY_SLUG.items():
            if catalog.get_course(slug):
                self.slugs_by_type.setdefault(ctype, []).append(slug)
        self.all_slugs = [s for v in self.slugs_by_type.values() for s in v]

    # ── helpers ──
    def say(self, *a):
        if self.verbose:
            print(*a, flush=True)

    def push(self, t, kind, payload):
        self.seq += 1
        heapq.heappush(self.queue, (t, self.seq, kind, payload))

    def ex(self, sql, params=()):
        return self.db.execute(sql, params)

    def course(self, L):
        return self.catalog.get_course(L["slug"])

    # ── learners ──
    def create_learners(self):
        raw = self.G.generate(self.n, seed=self.seed, return_truth=True)
        days = np.arange(self.days)
        p = 1 + 0.6 * days / self.days                  # the site grows: more sign-ups recently
        signup_days = np.sort(self.rng.choice(days, size=self.n, p=p / p.sum()))
        self.learners = []
        pairs = [(f, l) for f in FIRST for l in LAST]                # every learner gets a different name
        order = self.rng.permutation(len(pairs))
        for i, r in enumerate(raw.to_dict("records")):
            first, last = pairs[int(order[i % len(pairs)])]
            d = int(signup_days[i])
            t = self.start + timedelta(days=d, hours=float(self.rng.uniform(8, 22)))
            slug = str(self.rng.choice(self.slugs_by_type.get(r["CourseType"]) or self.all_slugs))
            L = {"i": i, "name": f"{first} {last}", "email": f"{first}.{last}.{i + 1}@{DEMO_DOMAIN}".lower(),
                 "occ": r["CurrentOccupation"], "spec": r["Specialization"], "intent": float(r["_intent"]),
                 "luck": float(self.rng.normal(0, 0.45)), "dne": int(r["DoNotEmail"]), "dnc": int(r["DoNotCall"]),
                 "wa": int(r["WhatsAppOptIn"]), "device": r["DeviceType"], "source": r["LeadSource"],
                 "slug": slug, "signup_day": d, "signup_at": t, "visits": 0, "time": 0, "pv": 0, "clicks": 0,
                 "flags": {f: 0 for f, *_ in EVENTS} | {"checkout": 0}, "last_visit_day": d, "boost": 0.0,
                 "boost_day": -1, "effects": [], "bought": False, "touch": {}, "wish_reminded": False,
                 "noise": {a: float(self.rng.normal(0, self.S.EFFECT_NOISE_SD)) for a in self.N.ACTION_LIST},
                 "phone": (f"+91 00000 {i + 1:05d}" if self.rng.random() < 0.85 else None)}
            L["uid"] = self.ex("INSERT INTO users (name, email, password_hash, is_verified, created_at) VALUES (?,?,?,1,?)",
                               (L["name"], L["email"], "!demo-" + uuid.uuid4().hex, ts(t)))
            has_profile = r["CurrentOccupation"] != "Unknown"
            self.ex("""INSERT INTO user_profiles (user_id, current_occupation, specialization, age_bracket, city, country,
                       phone, whatsapp_opt_in, do_not_email, do_not_call, how_did_you_hear, profile_complete, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (L["uid"], r["CurrentOccupation"] if has_profile else None, r["Specialization"] if has_profile else None,
                     r["AgeBracket"] if r["AgeBracket"] != "Unknown" else None,
                     r["City"] if r["City"] != "Unknown" else None, r["Country"], L["phone"], L["wa"],
                     "Yes" if L["dne"] else "No", "Yes" if L["dnc"] else "No",
                     r["HowDidYouHear"] if r["HowDidYouHear"] != "Unknown" else None, int(has_profile), ts(t)))
            self.learners.append(L)
        self.say(f"  {self.n:,} learners created (sign-ups spread over {self.days} days)")

    # ── scoring (the live model, with simulated timestamps) ──
    def score(self, L, t, source):
        raw = self.scoring.build_raw(L["uid"], course=L["slug"])
        pred = self.predict.predict_lead(raw, explain=False)
        pred["raw"] = raw
        self.ex("""INSERT INTO score_snapshots (user_id, source, features_json, probability, lead_score, tier,
                   model_version, created_at) VALUES (?,?,?,?,?,?,?,?)""",
                (L["uid"], source, json.dumps(pred["features"]), pred["conversion_probability"], pred["lead_score"],
                 pred["recommended_action"], pred["model_version"], ts(t)))
        lead = L.get("lead_id")
        if lead:
            old = L.get("tier")
            f = pred["features"]
            plv = round(self.price(L) * pred["conversion_probability"], 2)
            self.ex("""UPDATE leads SET lead_score=?, conversion_probability=?, recommended_action=?, persona=?,
                       customer_segment=?, plv=?, email_opened_count=?, total_visits=?, total_time_on_website=?,
                       page_views_per_visit=?, sessions_count=?, video_watched=?, brochure_downloaded=?,
                       chat_initiated=?, pricing_page_visited=?, testimonial_visited=?, webinar_attended=?,
                       model_version=?, decayed=0 WHERE id=?""",
                    (pred["lead_score"], pred["conversion_probability"], pred["recommended_action"], pred["persona"],
                     pred["persona"], plv, int(f["EmailOpenedCount"]), int(f["TotalVisits"]),
                     int(f["TotalTimeOnWebsite"]), f["PageViewsPerVisit"], int(f["TotalVisits"]), f["VideoWatched"],
                     f["BrochureDownloaded"], f["ChatInitiated"], f["PricingPageVisited"], f["TestimonialVisited"],
                     f["WebinarAttended"], pred["model_version"], lead))
            if old and old != pred["recommended_action"]:
                self.ex("""INSERT INTO lead_score_history (lead_id, user_id, old_score, new_score, old_tier, new_tier,
                           reason, created_at) VALUES (?,?,?,?,?,?,?,?)""",
                        (lead, L["uid"], L.get("score"), pred["lead_score"], old, pred["recommended_action"],
                         source, ts(t)))
        self.ex("""INSERT INTO live_user_state (user_id, live_score, persona, updated_at) VALUES (?,?,?,?)
                   ON CONFLICT(user_id) DO UPDATE SET live_score=excluded.live_score, persona=excluded.persona,
                   updated_at=excluded.updated_at""", (L["uid"], pred["lead_score"], pred["persona"], ts(t)))
        L.update(score=pred["lead_score"], tier=pred["recommended_action"], features=pred["features"], pred=pred)
        return pred

    def price(self, L):
        return float(self.catalog.price_of(L["slug"]) or self.catalog.average_price())

    def insert_lead(self, L, pred, content, trigger, t):
        f = pred["features"]
        lead_id = self.ex("""
            INSERT INTO leads (user_id, lead_origin, lead_source, device_type, total_visits, total_time_on_website,
                page_views_per_visit, sessions_count, video_watched, brochure_downloaded, chat_initiated,
                pricing_page_visited, testimonial_visited, webinar_attended, email_opened_count, course_type,
                lead_score, conversion_probability, persona, customer_segment, recommended_action, email_subject,
                email_body, whatsapp_message, coupon_code, call_script, trigger_reason, score_factors, model_version,
                course_slug, tips_json, plv, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (L["uid"], f["LeadOrigin"], f["LeadSource"], f["DeviceType"], int(f["TotalVisits"]),
             int(f["TotalTimeOnWebsite"]), f["PageViewsPerVisit"], int(f["TotalVisits"]), f["VideoWatched"],
             f["BrochureDownloaded"], f["ChatInitiated"], f["PricingPageVisited"], f["TestimonialVisited"],
             f["WebinarAttended"], int(f["EmailOpenedCount"]), self.catalog.title_of(L["slug"]), pred["lead_score"],
             pred["conversion_probability"], pred["persona"], pred["persona"], pred["recommended_action"],
             content.get("email_subject"), content.get("email_body"), content.get("whatsapp_message"),
             content.get("coupon_code"), content.get("call_script"), trigger, "[]", pred["model_version"],
             L["slug"], "[]", round(self.price(L) * pred["conversion_probability"], 2), ts(t)))
        L["lead_id"] = lead_id
        return lead_id

    # ── visits ──
    def visit(self, L, d, t, came_from=None):
        intent = L["intent"] + (L["boost"] if L["boost_day"] >= d else 0.0)
        first = L["visits"] == 0
        n_pages = int(min(10, 1 + self.rng.poisson(np.exp(0.4 + 0.25 * L["intent"]))))
        page_secs = np.minimum(600, self.rng.lognormal(np.log(50) + 0.25 * L["intent"], 0.6, n_pages)).astype(int)
        dur = int(page_secs.sum())
        source = L["source"] if first else (came_from or "Direct Traffic")
        sid = self.ex("""INSERT INTO user_sessions (user_id, login_at, last_active, device_type, lead_source, followed_up)
                         VALUES (?,?,?,?,?,1)""", (L["uid"], ts(t), ts(t + timedelta(seconds=dur)), L["device"], source))
        clock = t
        for k, secs in enumerate(page_secs):
            clock = clock + timedelta(seconds=int(secs))
            self.ex("""INSERT INTO behaviour_events (user_id, session_id, course_slug, event_type, time_spent_sec, created_at)
                       VALUES (?,?,?,?,?,?)""", (L["uid"], sid, L["slug"] if k == 0 or self.rng.random() < 0.7 else None,
                                                 "page_view", int(secs), ts(clock)))
        L["visits"] += 1
        L["time"] += dur
        L["pv"] += n_pages
        L["last_visit_day"] = d
        self.stats["visits"] += 1
        happened = []
        for flag, etype, a, b in EVENTS:
            if L["flags"][flag]:
                continue
            extra = 0.5 * L["flags"]["pricing"] if flag == "cart" else 0.0
            if self.rng.random() < sig(a + b * intent + extra):
                at = t + timedelta(seconds=int(self.rng.uniform(0.2, 1.0) * max(dur, 30)))
                self.event(L, sid, etype, at)
                L["flags"][flag] = 1
                happened.append(flag)
                if flag == "cart" and self.rng.random() < sig(-1.0 + 0.9 * intent):
                    self.event(L, sid, "checkout_start", at + timedelta(minutes=2))
                    L["flags"]["checkout"] = 1
                    L["checkout_id"] = self.ex("""INSERT INTO checkout_sessions (user_id, cart_value, started_at,
                                                  abandon_email_sent) VALUES (?,?,?,1)""",
                                               (L["uid"], self.price(L), ts(at + timedelta(minutes=2))))
                    happened.append("checkout")
        end = t + timedelta(seconds=dur + 30)
        self.score(L, end, "activity")
        return end, happened

    def event(self, L, sid, etype, at):
        self.ex("""INSERT INTO behaviour_events (user_id, session_id, course_slug, event_type, created_at)
                   VALUES (?,?,?,?,?)""", (L["uid"], sid, L["slug"], etype, ts(at)))
        c = self.course(L)
        if etype == "wishlist_add":
            self.ex("""INSERT OR IGNORE INTO wishlist (user_id, course_slug, course_title, added_at, reminder_sent)
                       VALUES (?,?,?,?,1)""", (L["uid"], L["slug"], c["title"], ts(at)))
        elif etype == "cart_add":
            self.ex("""INSERT OR IGNORE INTO cart (user_id, course_slug, course_title, price, added_at, abandon_email_sent)
                       VALUES (?,?,?,?,?,1)""", (L["uid"], L["slug"], c["title"], c["price"], ts(at)))

    # ── next-best-action at a trigger ──
    def touched_within(self, L, t, triggers, hours):
        return any(L["touch"].get(tr) and t - L["touch"][tr] < timedelta(hours=hours) for tr in triggers)

    def effect_of(self, L, action, features):
        frame = self.F.to_model_frame([features])
        ctx = self.N.context(frame, np.array([0.5]))[0]
        eff = float(ctx @ np.asarray(self.S.TRUE_EFFECTS[action])) + L["noise"].get(action, 0.0)
        return eff

    def decide(self, L, trigger, t, allowed=None, always_email=False):
        N, nba = self.N, self.nba
        pred = self.score(L, t, trigger)
        features, base_p = pred["features"], float(pred["conversion_probability"])
        price = self.price(L)
        probs = nba.action_probabilities(features, base_p)
        values = N.expected_values(probs, price)
        blocked = N.eligible(features, bool(L["phone"]))
        day = t.date()
        if self.calls_today.get(day, 0) >= self.capacity and not blocked["call"]:
            blocked["call"] = "today's call capacity is used up"
        if allowed is not None:
            for a in N.ACTION_LIST:
                if a not in allowed and not blocked[a]:
                    blocked[a] = f"not used for {trigger}"
        if all(blocked[a] for a in N.ACTION_LIST):
            blocked["none"] = None
        action, policy, propensity, best = N.choose(values, blocked, self.explore, self.rng)
        holdout = self.settings.in_global_control(L["uid"])
        if holdout:                      # the untouched control group: decided for the record, never acted on
            action, policy, propensity = "none", "holdout", 1.0
        is_email = action.startswith("email")
        content = self.generate_content(
            name=L["name"], occupation=L["occ"] if L["occ"] != "Unknown" else None, specialization=L["spec"],
            course=self.catalog.title_of(L["slug"]), action=("Target Immediately" if action == "call" else pred["recommended_action"]),
            trigger=trigger, past_purchases=0, lead_score=pred["lead_score"], course_slug=L["slug"],
            offer_pct=nba.offer_pct(action) if is_email else 0)
        adoption, arm, arm_p, shift = None, None, None, (0.0, 0.0)
        if action == "email_info" and not holdout:          # an adopted A/B winner replaces the standard email
            adoption = self.adopted.current_for(pred["recommended_action"])
            if adoption:
                arm, arm_p = self.adopted.arm(adoption, L["uid"])
                if arm == "adopted":
                    title = self.catalog.title_of(L["slug"])
                    content["email_subject"] = self.adopted.personalise(adoption["subject"], L["name"].split()[0], title)
                    content["email_body"] = self.adopted.personalise(adoption["body"], L["name"].split()[0], title)
                    shift = self.adopted_shift(adoption, L)
        lead_id = self.insert_lead(L, pred, content, trigger, t)
        if adoption:
            self.adopted.record(adoption, L["uid"], lead_id, arm, arm_p, tier=pred["recommended_action"],
                                occupation=L["occ"], device=L["device"], source=L["source"], at=ts(t))
        options = [{"action": a, "label": N.ACTIONS[a]["label"], "blocked": blocked[a], **values[a]} for a in N.ACTION_LIST]
        why = (f"In the control group: the CRM never contacts this lead automatically. (The model would have chosen: "
               f"{N.ACTIONS[best]['label'].lower()}.)") if holdout else nba._why(action, values, base_p, price)
        nb = nba._load()
        version = nb["version"] if nb else "prior"
        dec = {"action": action, "label": N.ACTIONS[action]["label"], "policy": policy, "propensity": propensity,
               "model_best": best, "trigger": trigger, "why": why, "options": options, "model_version": version,
               "price": price, "detail": f"Course price ₹{price:,.0f} · model {version} · trigger {trigger}"}
        dec_id = self.ex("""INSERT INTO nba_decisions (user_id, lead_id, trigger_reason, action, model_best, policy,
                            propensity, base_probability, price, options_json, features_json, model_version, created_at)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                         (L["uid"], lead_id, trigger, action, best, policy, propensity, base_p, price,
                          json.dumps(options), json.dumps(features), version, ts(t)))
        dec["decision_id"] = dec_id
        self.ex("UPDATE leads SET nba_action=?, nba_json=? WHERE id=?", (action, json.dumps(dec), lead_id))
        self.stats["decisions"] += 1
        self.stats["explore"] += policy == "explore"
        L["touch"][trigger] = t
        sent = t + timedelta(minutes=1)
        if (is_email or always_email) and not L["dne"]:
            token = self.send_email(L, lead_id, content["email_subject"], content["email_body"], sent,
                                    click_shift=(0.4 if action in ("email_coupon_10", "email_coupon_20") else 0.0) + shift[0])
            if adoption:
                self.ex("UPDATE email_sends SET adoption_id=?, adoption_arm=? WHERE token=?", (adoption["id"], arm, token))
            if is_email:
                self.ex("UPDATE nba_decisions SET executed_at=? WHERE id=?", (ts(sent), dec_id))
            if action in ("email_coupon_10", "email_coupon_20"):
                pct = nba.offer_pct(action)
                self.ex("""INSERT INTO coupons_issued (user_id, coupon_code, discount_pct, tier, created_at, expires_at)
                           VALUES (?,?,?,?,?,?)""", (L["uid"], content.get("coupon_code") or f"XEDU_{pct}OFF", pct,
                                                     pred["recommended_action"], ts(sent), ts(sent + timedelta(hours=72))))
            if is_email:
                L["effects"].append((sent + timedelta(days=self.window), self.effect_of(L, action, features) + shift[1]))
        if action in ("call", "whatsapp"):
            verb = "Call" if action == "call" else "WhatsApp"
            title = f"{verb} {L['name']} about {self.catalog.title_of(L['slug'])}"
            detail = content.get("call_script") if action == "call" else content.get("whatsapp_message")
            gain = values[action]["incremental_profit"]
            task = self.ex("""INSERT INTO sales_tasks (user_id, lead_id, decision_id, task_type, title, detail,
                              expected_gain, status, created_at) VALUES (?,?,?,?,?,?,?,'open',?)""",
                           (L["uid"], lead_id, dec_id, "call" if action == "call" else "whatsapp", title, detail, gain, ts(t)))
            if action == "call":
                self.calls_today[day] = self.calls_today.get(day, 0) + 1
                self.stats["calls"] += 1
            else:
                self.stats["whatsapp"] += 1
            done = t + timedelta(hours=float(self.rng.uniform(1, 24)))
            if done < self.now - timedelta(hours=12):              # recent tasks stay open for the demo
                if action == "call":
                    outcome = str(self.rng.choice(["reached", "no_answer", "not_interested"], p=[0.6, 0.3, 0.1]))
                else:
                    outcome = "sent"
                self.push(done, "task_done", {"task": task, "dec": dec_id, "outcome": outcome, "uid": L["i"],
                                              "action": action, "features": features})
        return action

    def adopted_shift(self, adoption, L):
        """True extra (click, buy) log-odds of an adopted email over the standard one, in this simulation:
        the winning variant's documented effects minus those of the variant it beat."""
        test = self.ab_specs.get(adoption["ab_test_id"])
        if not test:
            return 0.0, 0.0
        val = lambda v, k: (lambda x: float(x(L)) if callable(x) else (float(x) if isinstance(x, (int, float)) else 0.0))(v.get(k, 0.0))
        win = next((v for v in test["variants"] if v["key"] == adoption["variant_key"]), None)
        other = [v for v in test["variants"] if v is not win]
        if not win or not other:
            return 0.0, 0.0
        return (val(win, "click") - max(val(v, "click") for v in other), val(win, "buy") - max(val(v, "buy") for v in other))

    def adoption_checks(self, mkt, t):
        """Once a simulated day: the dashboard's adoption job (marketing-backend/adoption.py) at time t."""
        conf = self.settings.S["ab_testing"]
        mkt.row_factory = sqlite3.Row
        tests = [dict(r) for r in mkt.execute("SELECT * FROM ab_tests WHERE sent_at IS NOT NULL AND simulated=1")]
        mkt.row_factory = None
        if not tests:
            return
        uq = lambda sql, params=(): self.db.fetchall(sql, params)
        uex = lambda sql, params=(): self.ex(sql, params)
        self.adoption.run_checks(
            uq, uex, tests,
            lambda tt, at: self.adoption.analyse_ab(uq, tt, json.loads(tt["variants_json"]), at, self.window,
                                                   float(conf["alpha"]), float(conf["power"])),
            lambda tt: json.loads(tt["variants_json"]), t, float(conf.get("adoption_check_share", 0.10)),
            window_days=self.window, alpha=float(conf["alpha"]), auto_adopt=bool(conf.get("auto_adopt", True)),
            log=lambda m: self.say("  " + m.replace("[ADOPT] ", f"day {(t - self.start).days:3d}: adoption: ")))

    def send_email(self, L, lead_id, subject, body, at, click_shift=0.0, campaign=None, ab=None, variant="A"):
        token = uuid.uuid4().hex
        self.ex("""INSERT INTO email_sends (lead_id, user_id, campaign_id, campaign_name, ab_test_id, variant, token,
                   subject, body, sent_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (lead_id, L["uid"], campaign[0] if campaign else None, campaign[1] if campaign else None,
                 ab, variant, token, subject, body, ts(at)))
        if lead_id:
            self.ex("UPDATE leads SET email_sent=1, email_sent_at=? WHERE id=?", (ts(at), lead_id))
        self.stats["emails" if not (campaign or ab) else "campaign_emails"] += 1
        p_click = sig(-1.7 + 0.6 * L["intent"] + click_shift)
        if self.rng.random() < p_click:
            click_at = at + timedelta(hours=float(self.rng.uniform(0.2, 30)))
            if click_at < self.now:
                self.push(click_at, "click", {"token": token, "uid": L["i"]})
        return token

    # ── purchases ──
    def buy(self, L, t):
        c = self.course(L)
        coupon = self.db.fetchone("""SELECT id, coupon_code, discount_pct FROM coupons_issued WHERE user_id=? AND used=0
                                     AND created_at <= ? AND (expires_at IS NULL OR expires_at > ?)
                                     ORDER BY discount_pct DESC LIMIT 1""", (L["uid"], ts(t), ts(t)))
        pct = coupon["discount_pct"] if coupon else 0
        paid = round(c["price"] * (1 - pct / 100), 2)
        if not L["flags"]["cart"]:
            self.ex("""INSERT INTO behaviour_events (user_id, course_slug, event_type, created_at) VALUES (?,?,?,?)""",
                    (L["uid"], L["slug"], "cart_add", ts(t - timedelta(minutes=3))))
            L["flags"]["cart"] = 1
        self.ex("""INSERT INTO purchases (user_id, course_slug, course_title, price_paid, coupon_used, discount_amount,
                   purchased_at) VALUES (?,?,?,?,?,?,?)""",
                (L["uid"], L["slug"], c["title"], paid, coupon["coupon_code"] if coupon else None,
                 round(c["price"] - paid, 2), ts(t)))
        self.ex("INSERT INTO behaviour_events (user_id, course_slug, event_type, created_at) VALUES (?,?,?,?)",
                (L["uid"], L["slug"], "purchase", ts(t)))
        if coupon:
            self.ex("UPDATE coupons_issued SET used=1, used_at=? WHERE id=?", (ts(t), coupon["id"]))
        self.ex("DELETE FROM cart WHERE user_id=?", (L["uid"],))
        self.ex("UPDATE checkout_sessions SET completed=1 WHERE user_id=? AND completed=0", (L["uid"],))
        L["bought"] = True
        self.stats["purchases"] += 1
        self.score(L, t, "purchase_conversion")

    def buy_probability_today(self, L, d, t):
        """Daily purchase hazard from the simulator's buying formula + effects active now."""
        f = L["flags"]
        b = dict(occ=L["occ"], visits=max(L["visits"], 1), time_on_site=min(L["time"], 6000), video=f["video"],
                 pricing=f["pricing"], testimonial=f["testimonial"], brochure=f["brochure"], chat=f["chat"],
                 webinar=f["webinar"], wishlist=f["wishlist"], cart=f["cart"], checkout=f["checkout"],
                 enquiry=f["enquiry"], opens=min(L["clicks"], 10), whatsapp=L["wa"], dne=L["dne"], dnc=L["dnc"])
        z = float(self.G.true_logit(b, L["intent"], L["luck"])[0]) + BASE_SHIFT
        z += (WORLD_DRIFT["WhatsAppOptIn"] * L["wa"] + WORLD_DRIFT["MobileDevice"] * (L["device"] == "Mobile")
              + WORLD_DRIFT["WebinarAttended"] * f["webinar"])
        L["effects"] = [(until, e) for until, e in L["effects"] if until > t]
        if L["effects"]:                       # the strongest nudge of the last 14 days counts (no stacking)
            z += max(e for _, e in L["effects"])
        p14 = sig(z)
        return 1 - (1 - p14) ** (1 / self.window)

    # ── delayed events (clicks, call outcomes) ──
    def process_queue(self, until):
        while self.queue and self.queue[0][0] <= until:
            t, _, kind, p = heapq.heappop(self.queue)
            L = self.learners[p["uid"]]
            if kind == "click":
                self.ex("""UPDATE email_sends SET click_count=click_count+1, open_count=open_count+1,
                           opened_at=COALESCE(opened_at, ?), first_clicked_at=COALESCE(first_clicked_at, ?)
                           WHERE token=?""", (ts(t), ts(t), p["token"]))
                L["clicks"] += 1
                self.stats["clicks"] += 1
                if not L["bought"]:                       # a click brings them back to the site
                    L["pending_visit"] = (t + timedelta(minutes=1), "Email Campaign")
            elif kind == "task_done":
                self.ex("UPDATE sales_tasks SET status='done', outcome=?, done_at=? WHERE id=?",
                        (p["outcome"], ts(t), p["task"]))
                if p["outcome"] in ("reached", "sent", "not_interested"):
                    self.ex("UPDATE nba_decisions SET executed_at=? WHERE id=?", (ts(t), p["dec"]))
                if p["outcome"] in ("reached", "sent") and not L["bought"]:
                    L["effects"].append((t + timedelta(days=self.window), self.effect_of(L, p["action"], p["features"])))
                    L["boost"], L["boost_day"] = (0.5 if p["action"] == "call" else 0.3), (t.date() - self.start.date()).days + 2

    # ── campaigns and A/B tests ──
    def audience(self, tier, t):
        out = []
        for L in self.learners:
            if L["signup_at"] > t or L["bought"] or L["dne"] or not L.get("lead_id"):
                continue
            if self.settings.in_global_control(L["uid"]):      # never in campaigns or A/B tests
                continue
            if tier != "All leads" and L.get("tier") != tier:
                continue
            out.append(L)
        return out

    def assign_row(self, kind, exp_id, L, arm, prob, t):
        f = L.get("features") or {}
        self.ex("""INSERT OR IGNORE INTO experiment_assignments (experiment_type, experiment_id, user_id, lead_id, arm,
                   probability, features_json, tier, occupation, device, source, assigned_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (kind, exp_id, L["uid"], L.get("lead_id"), arm, prob, json.dumps(f), L.get("tier"),
                 f.get("CurrentOccupation") or L["occ"], L["device"], f.get("LeadSource") or L["source"], ts(t)))

    def personalise(self, text, L):
        first = L["name"].split()[0]
        return (text or "").replace("{first_name}", first).replace("{name}", L["name"]).replace(
            "{course}", self.catalog.title_of(L["slug"]))

    def run_campaign(self, mkt, d, name, tier, subject, body):
        t = self.start + timedelta(days=d, hours=10)
        people = self.audience(tier, t)
        share = float(self.settings.S["campaigns"]["holdout_share"])
        cid = mkt.execute("""INSERT INTO campaign_schedules (name, tier, subject, body, scheduled_at, sent, sent_at,
                             status, recipients, holdout_share, held_out, simulated, created_at)
                             VALUES (?,?,?,?,?,1,?,'sent',0,?,0,1,?)""",
                          (f"{SIM} {name}", tier, subject, body, ts(t), ts(t), share, ts(t - timedelta(days=2)))).lastrowid
        mkt.commit()
        sent = held = 0
        for L in people:
            arm, prob = self.E.arm_for("campaign", cid, L["uid"], self.E.campaign_arms(share))
            self.assign_row("campaign", cid, L, arm, prob, t)
            if arm == "holdout":
                held += 1
                continue
            self.send_email(L, L.get("lead_id"), self.personalise(subject, L), self.personalise(body, L), t,
                            campaign=(cid, f"{SIM} {name}"))
            L["effects"].append((t + timedelta(days=self.window), 0.7 * self.effect_of(L, "email_info", L["features"])))
            sent += 1
        mkt.execute("UPDATE campaign_schedules SET recipients=?, held_out=? WHERE id=?", (sent, held, cid))
        mkt.commit()
        self.say(f"  day {d:3d}: campaign '{name}' -> {sent} emails, {held} held out")

    def run_ab(self, mkt, test):
        d = test["day"]
        t = self.start + timedelta(days=d, hours=11)
        people = self.audience(test["audience"], t)
        control = float(self.settings.S["ab_testing"]["control_share"]) if test["metric"] == "purchase" else 0.0
        keys = [v["key"] for v in test["variants"]]
        base_guess = 0.08 if test["metric"] == "purchase" else 0.15
        mde = float(self.settings.S["ab_testing"]["min_detectable_effect"])
        planned = self.E.sample_size(base_guess, mde, comparisons=self.E.n_comparisons(len(keys), control > 0))
        variants_public = [{k: v for k, v in var.items() if k in ("key", "label", "subject", "body", "offer_pct")}
                           for var in test["variants"]]
        tid = mkt.execute("""INSERT INTO ab_tests (name, tier, subject_a, body_a, subject_b, body_b, status, created_at,
                             sent_at, hypothesis, metric, control_share, variants_json, mde, planned_per_arm, started_at,
                             simulated) VALUES (?,?,?,?,?,?,'sent',?,?,?,?,?,?,?,?,?,1)""",
                          (f"{SIM} {test['name']}", test["audience"], test["variants"][0]["subject"],
                           test["variants"][0]["body"], test["variants"][1]["subject"], test["variants"][1]["body"],
                           ts(t - timedelta(days=1)), ts(t), test["hypothesis"], test["metric"], control,
                           json.dumps(variants_public), mde, planned, ts(t))).lastrowid
        mkt.commit()
        arms = self.E.arms_for_test(control, keys)
        counts = {k: 0 for k, _ in arms}
        spec = {v["key"]: v for v in test["variants"]}
        self.ab_specs[tid] = test
        for L in people:
            arm, prob = self.E.arm_for("ab", tid, L["uid"], arms)
            self.assign_row("ab", tid, L, arm, prob, t)
            counts[arm] += 1
            self.stats["ab_people"] += 1
            if arm == "control":
                continue
            v = spec[arm]
            click = v.get("click", 0.0)
            self.send_email(L, L.get("lead_id"), self.personalise(v["subject"], L), self.personalise(v["body"], L), t,
                            click_shift=float(click(L) if callable(click) else click), ab=tid, variant=arm)
            if v.get("offer_pct"):
                pct = int(v["offer_pct"])
                self.ex("""INSERT INTO coupons_issued (user_id, coupon_code, discount_pct, tier, created_at, expires_at)
                           VALUES (?,?,?,?,?,?)""", (L["uid"], f"AB{tid}_{pct}OFF", pct, L.get("tier") or "",
                                                     ts(t), ts(t + timedelta(hours=72))))
            buy = v.get("buy", 0.0)
            if buy == "coupon10":
                eff = self.effect_of(L, "email_coupon_10", L["features"])
            elif buy == "coupon20":
                eff = self.effect_of(L, "email_coupon_20", L["features"])
            elif callable(buy):
                eff = float(buy(L))
            else:
                eff = float(buy)
            L["effects"].append((t + timedelta(days=self.window), eff))
        self.say(f"  day {d:3d}: A/B test '{test['name']}' -> " + ", ".join(f"{k} {n}" for k, n in counts.items()))

    # ── main loop ──
    def run(self):
        t0 = time.time()
        mkt = sqlite3.connect(_mkt_path(), timeout=30)
        self.mkt_schema.init(mkt)
        self.create_learners()
        by_day = {}
        for L in self.learners:
            by_day.setdefault(L["signup_day"], []).append(L)
        campaigns = {c[0]: c for c in CAMPAIGNS}
        tests = {tst["day"]: tst for tst in AB_TESTS}
        for d in range(self.days):
            day_start = self.start + timedelta(days=d)
            self.process_queue(day_start)
            if d in LEARN_DAYS:
                self.learn(day_start)
            if d in campaigns:
                c = campaigns[d]
                self.run_campaign(mkt, d, c[1], c[2], c[3], c[4])
            if d in tests:
                self.run_ab(mkt, tests[d])
            self.adoption_checks(mkt, day_start)
            for L in by_day.get(d, []):                     # new sign-ups: their first contact record
                pred = self.score(L, L["signup_at"], "signup")
                self.insert_lead(L, pred, {}, "signup", L["signup_at"])
            active = [L for L in self.learners if L["signup_day"] <= d and not L["bought"]]
            order = self.rng.permutation(len(active))
            for j in order:
                L = active[j]
                self.day_for(L, d, day_start)
            if d % 15 == 14:
                self.db.get_conn().commit()
                self.say(f"  day {d + 1:3d}/{self.days}: {self.stats['visits']:,} visits, {self.stats['decisions']:,} "
                         f"decisions, {self.stats['purchases']:,} purchases ({time.time() - t0:,.0f} s)")
        self.process_queue(self.now)
        self.learn(self.now - timedelta(minutes=5))
        self.finish()
        mkt.close()
        return time.time() - t0

    def day_for(self, L, d, day_start):
        visit_times = []
        if d == L["signup_day"] and L["visits"] == 0:
            visit_times.append((L["signup_at"], None))
        pend = L.pop("pending_visit", None)
        if pend and pend[0] < day_start + timedelta(days=1):
            visit_times.append(pend)
        elif pend:
            L["pending_visit"] = pend
        if not visit_times and d > L["signup_day"]:
            gap = d - L["last_visit_day"]
            boost = L["boost"] if L["boost_day"] >= d else 0.0
            if gap <= 21 and self.rng.random() < sig(-2.6 + 0.7 * L["intent"] - 0.05 * gap + boost):
                visit_times.append((day_start + timedelta(hours=float(self.rng.uniform(8, 23))), None))
        happened_all, last_end = [], None
        for vt, came in sorted(visit_times, key=lambda x: x[0]):
            if vt >= self.now:
                continue
            end, happened = self.visit(L, d, vt, came_from=came)
            happened_all += happened
            last_end = end
            if "enquiry" in happened:
                self.decide(L, "enquiry", end - timedelta(seconds=20),
                            allowed=["email_info", "email_coupon_10", "email_coupon_20", "call"], always_email=True)
        # purchase today? (only while they are still "in the market": visited in the last 14 days)
        active = d - L["last_visit_day"] <= self.window
        if active and not L["bought"]:
            when = (last_end or day_start + timedelta(hours=float(self.rng.uniform(9, 23)))) + timedelta(minutes=2)
            if when < self.now and self.rng.random() < self.buy_probability_today(L, d, when):
                if last_end is None:                           # they come back to buy
                    last_end, _ = self.visit(L, d, when - timedelta(minutes=10), came_from="Direct Traffic")
                self.buy(L, when)
                return
        if last_end is None or L["bought"]:
            return
        # triggers after the visit (same order and cool-downs as the live scheduler)
        if L["flags"]["checkout"] and "checkout" in happened_all and not self.touched_within(L, last_end, ("checkout_abandon",), 12):
            self.decide(L, "checkout_abandon", last_end + timedelta(minutes=float(self.rng.uniform(30, 60))))
        elif "cart" in happened_all and not self.touched_within(L, last_end, ("cart_abandon", "checkout_abandon"), 12):
            self.decide(L, "cart_abandon", last_end + timedelta(minutes=float(self.rng.uniform(60, 120))))
        elif "wishlist" in happened_all and not L["wish_reminded"] and \
                not self.touched_within(L, last_end, ("wishlist", "cart_abandon", "checkout_abandon"), 24):
            L["wish_reminded"] = True
            self.decide(L, "wishlist", last_end + timedelta(minutes=float(self.rng.uniform(30, 90))),
                        allowed=["none", "email_info", "email_coupon_10", "whatsapp"])
        elif L["time"] >= 60 and not self.touched_within(
                L, last_end, ("enquiry", "chat_callback", "cart_abandon", "checkout_abandon", "wishlist", "session_end"), 6):
            self.decide(L, "session_end", last_end + timedelta(minutes=float(self.rng.uniform(15, 40))))

    def learn(self, at):
        self.db.get_conn().commit()
        res = self.learning.run(as_of=ts(at), reason="history", simulated=True, verbose=False)
        self.stats["runs"] += 1
        self.stats["lead_swaps"] += res.get("lead_decision") == "swapped"
        self.stats["nba_swaps"] += (res.get("nba") or {}).get("decision") == "swapped"
        cl, nl, ta = res.get("challenger_true_logloss"), res.get("naive_true_logloss"), res.get("challenger_true_auc")
        self.say(f"  {ts(at)[:10]}: learning run — {res.get('outcomes_known', 0):,} decisions with an outcome, "
                 f"{res.get('control_people', 0)} control-group people · lead model {res.get('lead_decision')}"
                 + (f" (control group: log-loss ours {cl:.3f} vs naive {nl:.3f}, AUC {ta:.3f})" if cl and nl and ta else "")
                 + f" · next-best-action {(res.get('nba') or {}).get('decision')}")

    def finish(self):
        # nothing in the simulated history is left for the live automation jobs
        self.ex("UPDATE cart SET abandon_email_sent=1 WHERE user_id IN (SELECT id FROM users WHERE email LIKE ?)",
                (f"%@{DEMO_DOMAIN}",))
        self.ex("UPDATE wishlist SET reminder_sent=1 WHERE user_id IN (SELECT id FROM users WHERE email LIKE ?)",
                (f"%@{DEMO_DOMAIN}",))
        self.ex("""UPDATE checkout_sessions SET abandon_email_sent=1 WHERE user_id IN
                   (SELECT id FROM users WHERE email LIKE ?)""", (f"%@{DEMO_DOMAIN}",))
        self.ex("UPDATE user_sessions SET followed_up=1 WHERE user_id IN (SELECT id FROM users WHERE email LIKE ?)",
                (f"%@{DEMO_DOMAIN}",))
        # 'Why this score?' and tips for everyone's latest contact record, with the final model
        import recourse
        for L in self.learners:
            if not L.get("lead_id"):
                continue
            raw = self.scoring.build_raw(L["uid"], course=L["slug"])
            pred = self.predict.predict_lead(raw, explain=True)
            tips = recourse.tips_for(pred["features"], pred["lead_score"]) if not L["bought"] else []
            self.ex("UPDATE leads SET score_factors=?, tips_json=? WHERE id=?",
                    (json.dumps(pred.get("factors") or []), json.dumps(tips), L["lead_id"]))
        self.db.get_conn().commit()


def generate(db, n, days, seed, verbose=True):
    import learning
    if demo_user_ids(db):
        raise SystemExit("Simulated history is already present — remove it first: python ml/generate_history.py --remove")
    for name in ("lead_model", "nba_model"):
        cur = os.path.join(learning.MODEL_DIR, f"{name}.pkl")
        start = os.path.join(learning.MODEL_DIR, f"{name}.starter.pkl")
        if not os.path.exists(cur):
            raise SystemExit(f"{name}.pkl not found — run python ml/train_model.py and ml/train_uplift.py first (start-all.bat does this).")
        if not os.path.exists(start):
            shutil.copy2(cur, start)
    restore_starting_models()                   # the history starts from the starting models
    os.environ.pop("GEMINI_API_KEY", None)      # templates only: no API calls for simulated emails
    h = History(db, n, days, seed, verbose)
    print(f"Simulating {days} days of history for {n:,} learners (this takes a few minutes) ...")
    secs = h.run()
    s = h.stats
    buyers = s["purchases"]
    print(f"\nDone in {secs / 60:.1f} min. {n:,} simulated learners (@{DEMO_DOMAIN}): {s['visits']:,} visits, "
          f"{s['decisions']:,} next-best-action decisions ({s['explore']:,} random learning samples), "
          f"{s['emails']:,} follow-up emails ({s['clicks']:,} clicks in total), {s['calls']:,} calls, "
          f"{s['whatsapp']:,} WhatsApp tasks, {s['campaign_emails']:,} campaign/A-B emails, "
          f"{buyers:,} purchases ({buyers / n * 100:.1f}% of learners).")
    print(f"Learning loop: {s['runs']} runs, lead model swapped {s['lead_swaps']}x, next-best-action swapped "
          f"{s['nba_swaps']}x — see the dashboard's Learning loop page.")
    print("Remove it all with: python ml/generate_history.py --remove (restores the starting models).")
    return s


def main():
    ap = argparse.ArgumentParser(description="Create (or remove) six months of simulated history.")
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--days", type=int, default=180)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--remove", action="store_true")
    ap.add_argument("--db", default=None, help="path to xeducation_user.db (default: user-backend/)")
    args = ap.parse_args()
    import database as db
    if args.db:
        db.DB_PATH = args.db
    db.init_db()
    shared = sqlite3.connect(db.DB_PATH, timeout=60, check_same_thread=False, factory=SharedConn)
    shared.row_factory = sqlite3.Row
    shared.execute("PRAGMA journal_mode=WAL")
    shared.execute("PRAGMA synchronous=OFF")
    shared.execute("PRAGMA busy_timeout=60000")
    original = db.get_conn
    db.get_conn = lambda: shared
    try:
        if args.remove:
            remove(db)
        else:
            generate(db, args.n, args.days, args.seed)
    finally:
        shared.commit()
        db.get_conn = original
        shared.really_close()


if __name__ == "__main__":
    main()
