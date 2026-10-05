import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "xeducation_user.db")


def get_conn():
    # timeout/busy_timeout: wait up to 30s for another writer instead of
    # failing instantly with "database is locked"
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    # ── 1. USERS ────────────────────────────────────────────────────
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        name         TEXT NOT NULL,
        email        TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        is_verified  INTEGER DEFAULT 0,
        created_at   TEXT DEFAULT (datetime('now','localtime'))
    )""")

    # ── 2. OTP TOKENS ───────────────────────────────────────────────
    c.execute("""CREATE TABLE IF NOT EXISTS otp_tokens (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        email      TEXT NOT NULL,
        otp        TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        used       INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )""")

    # ── 3. USER PROFILES ─────────────────────────────────────────────
    c.execute("""CREATE TABLE IF NOT EXISTS user_profiles (
        user_id           INTEGER PRIMARY KEY REFERENCES users(id),
        current_occupation TEXT,
        specialization     TEXT,
        age_bracket        TEXT,
        city               TEXT,
        country            TEXT DEFAULT 'India',
        phone              TEXT,
        whatsapp_opt_in    INTEGER DEFAULT 0,
        do_not_email       TEXT DEFAULT 'No',
        do_not_call        TEXT DEFAULT 'No',
        how_did_you_hear   TEXT,
        profile_complete   INTEGER DEFAULT 0,
        updated_at         TEXT DEFAULT (datetime('now','localtime'))
    )""")

    # ── 4. USER SESSIONS ─────────────────────────────────────────────
    c.execute("""CREATE TABLE IF NOT EXISTS user_sessions (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER REFERENCES users(id),
        login_at     TEXT DEFAULT (datetime('now','localtime')),
        last_active  TEXT DEFAULT (datetime('now','localtime')),
        device_type  TEXT,
        lead_source  TEXT DEFAULT 'Direct Traffic'
    )""")

    # ── 5. BEHAVIOUR EVENTS ──────────────────────────────────────────
    c.execute("""CREATE TABLE IF NOT EXISTS behaviour_events (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id         INTEGER REFERENCES users(id),
        session_id      INTEGER REFERENCES user_sessions(id),
        course_slug     TEXT,
        event_type      TEXT,
        time_spent_sec  INTEGER DEFAULT 0,
        created_at      TEXT DEFAULT (datetime('now','localtime'))
    )""")

    # ── 6. CART ─────────────────────────────────────────────────────
    c.execute("""CREATE TABLE IF NOT EXISTS cart (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER REFERENCES users(id),
        course_slug  TEXT NOT NULL,
        course_title TEXT NOT NULL,
        price        REAL NOT NULL,
        added_at     TEXT DEFAULT (datetime('now','localtime')),
        abandon_email_sent INTEGER DEFAULT 0,
        UNIQUE(user_id, course_slug)
    )""")

    # ── 7. WISHLIST ─────────────────────────────────────────────────
    c.execute("""CREATE TABLE IF NOT EXISTS wishlist (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER REFERENCES users(id),
        course_slug  TEXT NOT NULL,
        course_title TEXT NOT NULL,
        added_at     TEXT DEFAULT (datetime('now','localtime')),
        UNIQUE(user_id, course_slug)
    )""")

    # ── 8. PURCHASES ────────────────────────────────────────────────
    c.execute("""CREATE TABLE IF NOT EXISTS purchases (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id         INTEGER REFERENCES users(id),
        course_slug     TEXT NOT NULL,
        course_title    TEXT NOT NULL,
        price_paid      REAL NOT NULL,
        coupon_used     TEXT,
        discount_amount REAL DEFAULT 0,
        purchased_at    TEXT DEFAULT (datetime('now','localtime'))
    )""")

    # ── 9. LEADS ────────────────────────────────────────────────────
    c.execute("""CREATE TABLE IF NOT EXISTS leads (
        id                    INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id               INTEGER REFERENCES users(id),
        lead_origin           TEXT,
        lead_source           TEXT,
        device_type           TEXT,
        total_visits          INTEGER DEFAULT 1,
        total_time_on_website INTEGER DEFAULT 0,
        page_views_per_visit  REAL DEFAULT 1.0,
        sessions_count        INTEGER DEFAULT 1,
        video_watched         INTEGER DEFAULT 0,
        brochure_downloaded   INTEGER DEFAULT 0,
        chat_initiated        INTEGER DEFAULT 0,
        pricing_page_visited  INTEGER DEFAULT 0,
        testimonial_visited   INTEGER DEFAULT 0,
        webinar_attended      INTEGER DEFAULT 0,
        email_opened_count    INTEGER DEFAULT 0,
        course_type           TEXT,
        lead_score            REAL,
        conversion_probability REAL,
        persona               TEXT,
        customer_segment      TEXT,
        recommended_action    TEXT,
        email_subject         TEXT,
        email_body            TEXT,
        whatsapp_message      TEXT,
        coupon_code           TEXT,
        call_script           TEXT,
        email_sent            INTEGER DEFAULT 0,
        email_sent_at         TEXT,
        trigger_reason        TEXT,
        created_at            TEXT DEFAULT (datetime('now','localtime'))
    )""")

    # ── 10. REVIEWS ─────────────────────────────────────────────────
    c.execute("""CREATE TABLE IF NOT EXISTS reviews (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER REFERENCES users(id),
        course_slug  TEXT NOT NULL,
        rating       INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
        review_text  TEXT,
        created_at   TEXT DEFAULT (datetime('now','localtime')),
        UNIQUE(user_id, course_slug)
    )""")

    # ── 11. Q&A ─────────────────────────────────────────────────────
    c.execute("""CREATE TABLE IF NOT EXISTS qna (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER REFERENCES users(id),
        course_slug  TEXT NOT NULL,
        question     TEXT NOT NULL,
        answer       TEXT,
        answered_by  TEXT DEFAULT 'X Education Team',
        answered_at  TEXT,
        created_at   TEXT DEFAULT (datetime('now','localtime'))
    )""")

    # ── 12. COUPONS ISSUED ──────────────────────────────────────────
    c.execute("""CREATE TABLE IF NOT EXISTS coupons_issued (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER REFERENCES users(id),
        coupon_code  TEXT NOT NULL,
        discount_pct INTEGER NOT NULL,
        tier         TEXT NOT NULL,
        used         INTEGER DEFAULT 0,
        used_at      TEXT,
        expires_at   TEXT,
        created_at   TEXT DEFAULT (datetime('now','localtime'))
    )""")


    c.execute("""CREATE TABLE IF NOT EXISTS live_user_state (
    user_id       INTEGER PRIMARY KEY REFERENCES users(id),
    live_score    REAL,
    persona       TEXT,
    updated_at    TEXT DEFAULT (datetime('now','localtime'))
    )""")

    # ── 14. CHECKOUT SESSIONS ────────────────────────────────────────
    c.execute("""CREATE TABLE IF NOT EXISTS checkout_sessions (
        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id            INTEGER REFERENCES users(id),
        cart_value         REAL DEFAULT 0,
        started_at         TEXT DEFAULT (datetime('now','localtime')),
        completed          INTEGER DEFAULT 0,
        abandon_email_sent INTEGER DEFAULT 0
    )""")

    # ── 15. EMAIL SENDS (open/click tracking log, shared by both services) ──
    c.execute("""CREATE TABLE IF NOT EXISTS email_sends (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id          INTEGER,
        user_id          INTEGER REFERENCES users(id),
        campaign_id      INTEGER,
        ab_test_id       INTEGER,
        variant          TEXT DEFAULT 'A',
        token            TEXT UNIQUE,
        subject          TEXT,
        body             TEXT,
        sent_at          TEXT DEFAULT (datetime('now','localtime')),
        opened_at        TEXT,
        open_count       INTEGER DEFAULT 0,
        first_clicked_at TEXT,
        click_count      INTEGER DEFAULT 0
    )""")

    # ── 16. LEAD SCORE HISTORY (decay / rescoring / email-engagement audit) ──
    c.execute("""CREATE TABLE IF NOT EXISTS lead_score_history (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id    INTEGER,
        user_id    INTEGER REFERENCES users(id),
        old_score  REAL,
        new_score  REAL,
        old_tier   TEXT,
        new_tier   TEXT,
        reason     TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )""")

    # ── 17a. CHAT ASSISTANT TRANSCRIPTS ──────────────────────────────
    c.execute("""CREATE TABLE IF NOT EXISTS chat_messages (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER REFERENCES users(id),
        conversation TEXT NOT NULL,
        role         TEXT NOT NULL,          -- 'user' | 'assistant'
        text         TEXT NOT NULL,
        intent       TEXT,
        course_slug  TEXT,
        created_at   TEXT DEFAULT (datetime('now','localtime'))
    )""")

    # ── 17b. CALLBACK REQUESTS (from chat / course page) ─────────────
    c.execute("""CREATE TABLE IF NOT EXISTS callback_requests (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id        INTEGER REFERENCES users(id),
        phone          TEXT,
        course_slug    TEXT,
        preferred_time TEXT,
        note           TEXT,
        status         TEXT DEFAULT 'open',   -- open | done
        created_at     TEXT DEFAULT (datetime('now','localtime')),
        closed_at      TEXT
    )""")

    # ── 17c. NEXT-BEST-ACTION DECISION LOG (closed loop for the uplift model) ──
    c.execute("""CREATE TABLE IF NOT EXISTS nba_decisions (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id          INTEGER REFERENCES users(id),
        lead_id          INTEGER,
        trigger_reason   TEXT,
        action           TEXT NOT NULL,       -- what was done
        model_best       TEXT,                -- what the model would have done
        policy           TEXT,                -- 'model' | 'explore'
        propensity       REAL,                -- P(this action | logging policy)
        base_probability REAL,
        price            REAL,
        options_json     TEXT,
        features_json    TEXT,
        model_version    TEXT,
        executed_at      TEXT,
        created_at       TEXT DEFAULT (datetime('now','localtime'))
    )""")

    # ── 17d. SALES TASKS (calls / WhatsApp chosen by next-best-action) ──
    c.execute("""CREATE TABLE IF NOT EXISTS sales_tasks (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id       INTEGER REFERENCES users(id),
        lead_id       INTEGER,
        decision_id   INTEGER,
        task_type     TEXT,                   -- 'call' | 'whatsapp'
        title         TEXT,
        detail        TEXT,
        expected_gain REAL,
        status        TEXT DEFAULT 'open',    -- open | done | skipped
        outcome       TEXT,
        created_at    TEXT DEFAULT (datetime('now','localtime')),
        done_at       TEXT
    )""")

    # ── 17. SCORE SNAPSHOTS (closed loop: features + prediction, later
    #        labelled by whether the user actually bought → retraining data) ──
    c.execute("""CREATE TABLE IF NOT EXISTS score_snapshots (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id        INTEGER REFERENCES users(id),
        source         TEXT,
        features_json  TEXT NOT NULL,
        probability    REAL,
        lead_score     REAL,
        tier           TEXT,
        model_version  TEXT,
        created_at     TEXT DEFAULT (datetime('now','localtime'))
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_snap_user ON score_snapshots(user_id, created_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_events_user ON behaviour_events(user_id, event_type)")

    # ── 18. EXPERIMENT ASSIGNMENTS (A/B tests and campaign holdouts) ──
    # Every person in an A/B test or campaign audience, with the arm they were
    # assigned to and the probability of that arm. The learning loop uses every
    # assignment, with the next-best-action log, as a decision point (what the CRM
    # did at that moment); the no-email arms ('control', 'holdout') got nothing.
    c.execute("""CREATE TABLE IF NOT EXISTS experiment_assignments (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        experiment_type TEXT NOT NULL,          -- 'ab' | 'campaign'
        experiment_id   INTEGER NOT NULL,
        user_id         INTEGER REFERENCES users(id),
        lead_id         INTEGER,
        arm             TEXT NOT NULL,          -- 'control' | 'holdout' | 'send' | 'A' | 'B' | 'C'
        probability     REAL NOT NULL,          -- chance of this arm under the assignment rule
        features_json   TEXT,                   -- what the model knew at assignment time
        tier            TEXT,
        occupation      TEXT,
        device          TEXT,
        source          TEXT,
        assigned_at     TEXT DEFAULT (datetime('now','localtime')),
        UNIQUE(experiment_type, experiment_id, user_id)
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_assign_exp ON experiment_assignments(experiment_type, experiment_id)")

    # ── 19. LEARNING RUNS (the automatic learning loop's log) ──
    c.execute("""CREATE TABLE IF NOT EXISTS learning_runs (
        id                       INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at               TEXT DEFAULT (datetime('now','localtime')),
        finished_at              TEXT,
        as_of                    TEXT,
        reason                   TEXT,             -- scheduled | manual | history | cli
        status                   TEXT,             -- done | skipped | error
        outcomes_known           INTEGER,
        new_outcomes             INTEGER,
        random_slice             INTEGER,          -- control-group decision points with a known outcome (5% global control group)
        random_slice_buyers      INTEGER,
        lead_decision            TEXT,             -- swapped | kept | not_enough_data
        lead_prob_better         REAL,
        champion_true_logloss    REAL, challenger_true_logloss REAL, naive_true_logloss REAL,
        champion_true_auc        REAL, challenger_true_auc     REAL, naive_true_auc     REAL,
        champion_live_auc        REAL, challenger_live_auc     REAL, naive_live_auc     REAL,
        challenger_live_logloss  REAL, naive_live_logloss      REAL,
        naive_would_pick         INTEGER,          -- would 'best fit on live data' have chosen the naive model?
        own_effect_share         REAL,             -- share of followed-up leads' buying chance caused by the follow-ups
        learned_json             TEXT,             -- the live layer after the run (points per signal, slope, intercept)
        nba_decision             TEXT,             -- swapped | kept | not_enough_data
        nba_detail_json          TEXT,
        lead_version_before      TEXT, lead_version_after TEXT,
        nba_version_before       TEXT, nba_version_after  TEXT,
        note                     TEXT,
        simulated                INTEGER DEFAULT 0
    )""")

    # ── 20. PIPELINE BOARD: cards moved by hand (otherwise the stage follows the learner's behaviour) ──
    c.execute("""CREATE TABLE IF NOT EXISTS pipeline_overrides (
        user_id    INTEGER PRIMARY KEY REFERENCES users(id),
        stage      TEXT NOT NULL,                 -- Lead | Engaged | MQL | SQL
        note       TEXT,
        moved_at   TEXT DEFAULT (datetime('now','localtime'))
    )""")

    # ── 21. ADOPTED A/B WINNERS: the winning wording becomes the standard information email of its
    #        audience; a small check group keeps getting the old email so the CRM keeps checking it ──
    c.execute("""CREATE TABLE IF NOT EXISTS adopted_emails (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        ab_test_id    INTEGER,                    -- ab_tests.id in the marketing database
        test_name     TEXT,
        audience      TEXT,                       -- a tier name or 'All leads'
        metric        TEXT,                       -- purchase | click
        variant_key   TEXT,
        variant_label TEXT,
        subject       TEXT,
        body          TEXT,
        test_lift     REAL, test_lift_lo REAL, test_lift_hi REAL,
        check_share   REAL,                       -- share of the audience that keeps the old email
        status        TEXT DEFAULT 'active',      -- active | confirmed | reverted
        adopted_at    TEXT,
        decided_at    TEXT,
        reason        TEXT,
        check_json    TEXT,                       -- latest adopted-vs-old comparison
        simulated     INTEGER DEFAULT 0
    )""")

    # ── 22. COPILOT: every question, which data tools answered it, and the answer ──
    c.execute("""CREATE TABLE IF NOT EXISTS copilot_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        asked_at    TEXT DEFAULT (datetime('now','localtime')),
        question    TEXT,
        intent      TEXT,
        tools_json  TEXT,
        answer      TEXT,
        drafts_json TEXT,
        used_gemini INTEGER DEFAULT 0
    )""")

    conn.commit()

    # ── Additive migrations for pre-existing DBs ─────────────────────
    for col_sql in (
        "ALTER TABLE leads ADD COLUMN plv REAL DEFAULT 0",
        "ALTER TABLE leads ADD COLUMN last_active_at TEXT",
        "ALTER TABLE leads ADD COLUMN decayed INTEGER DEFAULT 0",
        "ALTER TABLE email_sends ADD COLUMN ab_test_id INTEGER",
        "ALTER TABLE leads ADD COLUMN score_factors TEXT",
        "ALTER TABLE leads ADD COLUMN model_version TEXT",
        "ALTER TABLE leads ADD COLUMN course_slug TEXT",
        "ALTER TABLE otp_tokens ADD COLUMN attempts INTEGER DEFAULT 0",
        "ALTER TABLE otp_tokens ADD COLUMN purpose TEXT DEFAULT 'signup'",
        "ALTER TABLE email_sends ADD COLUMN campaign_name TEXT",
        "ALTER TABLE leads ADD COLUMN nba_action TEXT",
        "ALTER TABLE leads ADD COLUMN nba_json TEXT",
        "ALTER TABLE leads ADD COLUMN tips_json TEXT",
        "ALTER TABLE wishlist ADD COLUMN reminder_sent INTEGER DEFAULT 0",
        "ALTER TABLE user_sessions ADD COLUMN followed_up INTEGER DEFAULT 0",
        "ALTER TABLE email_sends ADD COLUMN adoption_id INTEGER",
        "ALTER TABLE email_sends ADD COLUMN adoption_arm TEXT",
    ):
        try:
            c.execute(col_sql)
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists

    # ── Indexes for per-person look-ups (lead lists, lead pages, learning loop) ──
    for idx_sql in (
        "CREATE INDEX IF NOT EXISTS idx_leads_user ON leads(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_purchases_user ON purchases(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_sessions_user ON user_sessions(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_emails_user ON email_sends(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_nba_user ON nba_decisions(user_id, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_coupons_user ON coupons_issued(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_tasks_user ON sales_tasks(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_assign_user ON experiment_assignments(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_callbacks_user ON callback_requests(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_profiles_user ON user_profiles(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_history_user ON lead_score_history(user_id)",
    ):
        try:
            c.execute(idx_sql)
        except sqlite3.OperationalError:
            pass  # table from an older version without that column
    conn.commit()

    conn.close()
    print(f"[DB] Initialised -> {DB_PATH}")


# ── HELPER QUERIES ────────────────────────────────────────────────────────────

def fetchone(query, params=()):
    conn = get_conn()
    row = conn.execute(query, params).fetchone()
    conn.close()
    return dict(row) if row else None


def fetchall(query, params=()):
    conn = get_conn()
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def execute(query, params=()):
    conn = get_conn()
    cur = conn.execute(query, params)
    conn.commit()
    last_id = cur.lastrowid
    conn.close()
    return last_id


def get_user_by_email(email):
    return fetchone("SELECT * FROM users WHERE email=?", (email,))


def get_user_by_id(user_id):
    return fetchone("SELECT * FROM users WHERE id=?", (user_id,))


def get_profile(user_id):
    return fetchone("SELECT * FROM user_profiles WHERE user_id=?", (user_id,))


def get_cart(user_id):
    return fetchall("SELECT * FROM cart WHERE user_id=? ORDER BY added_at DESC", (user_id,))


def get_wishlist(user_id):
    return fetchall("SELECT * FROM wishlist WHERE user_id=? ORDER BY added_at DESC", (user_id,))


def get_purchases(user_id):
    return fetchall("SELECT * FROM purchases WHERE user_id=? ORDER BY purchased_at DESC", (user_id,))


def get_reviews(course_slug):
    return fetchall("""
        SELECT r.*, u.name FROM reviews r
        JOIN users u ON r.user_id=u.id
        WHERE r.course_slug=? ORDER BY r.created_at DESC
    """, (course_slug,))


def get_qna(course_slug):
    return fetchall("""
        SELECT q.*, u.name as user_name FROM qna q
        JOIN users u ON q.user_id=u.id
        WHERE q.course_slug=? ORDER BY q.created_at DESC
    """, (course_slug,))


def get_user_lead(user_id):
    return fetchone(
        "SELECT * FROM leads WHERE user_id=? ORDER BY created_at DESC, id DESC LIMIT 1",
        (user_id,)
    )


# ── Behaviour summary → the model's auto-tracked features ───────────────────
def get_behaviour_summary(user_id):
    """
    Aggregates everything the website tracked for this user into the same
    quantities the model was trained on:
      total_visits          distinct sessions that produced at least one event
                            (a new session starts after 30 min of inactivity)
      total_time_on_website seconds summed from page_view events
      page_views_per_visit  page_view events / visits
      flags                 1 if the event ever happened
    """
    conn = get_conn()
    try:
        q = lambda sql, *a: conn.execute(sql, (user_id, *a)).fetchone()

        visits = q("SELECT COUNT(DISTINCT session_id) AS c FROM behaviour_events "
                   "WHERE user_id=? AND session_id IS NOT NULL")["c"] or 0
        visits = max(visits, 1)
        time_total = q("SELECT COALESCE(SUM(time_spent_sec),0) AS t FROM behaviour_events "
                       "WHERE user_id=? AND event_type='page_view'")["t"] or 0
        pv = q("SELECT COUNT(*) AS c FROM behaviour_events "
               "WHERE user_id=? AND event_type='page_view'")["c"] or 0

        counts = {r["event_type"]: r["c"] for r in conn.execute(
            "SELECT event_type, COUNT(*) AS c FROM behaviour_events WHERE user_id=? GROUP BY event_type",
            (user_id,)).fetchall()}
        has = lambda *types: int(any(counts.get(t, 0) > 0 for t in types))

        in_cart = q("SELECT COUNT(*) AS c FROM cart WHERE user_id=?")["c"]
        in_wishlist = q("SELECT COUNT(*) AS c FROM wishlist WHERE user_id=?")["c"]
        checkouts = q("SELECT COUNT(*) AS c FROM checkout_sessions WHERE user_id=?")["c"]
        enquiries = q("SELECT COUNT(*) AS c FROM leads WHERE user_id=? AND trigger_reason='enquiry'")["c"]

        row = q("""SELECT course_slug, COUNT(*) AS cnt FROM behaviour_events
                   WHERE user_id=? AND course_slug IS NOT NULL
                   GROUP BY course_slug ORDER BY cnt DESC LIMIT 1""")
        last_session = q("SELECT device_type FROM user_sessions WHERE user_id=? "
                         "AND device_type IS NOT NULL ORDER BY id DESC LIMIT 1")
        # acquisition source = first visit that came from somewhere specific
        first_source = q("SELECT lead_source FROM user_sessions WHERE user_id=? "
                         "AND lead_source IS NOT NULL AND lead_source != 'Direct Traffic' "
                         "ORDER BY id ASC LIMIT 1")

        return {
            "total_visits":          visits,
            "sessions_count":        visits,
            "total_time_on_website": int(min(time_total, 6000)),
            "page_views_per_visit":  round(pv / visits, 1),
            "video_watched":         has("video_play"),
            "brochure_downloaded":   has("brochure_dl"),
            "chat_initiated":        has("chat"),
            "pricing_page_visited":  has("pricing_view"),
            "testimonial_visited":   has("testimonial_view"),
            "webinar_attended":      has("webinar_view", "webinar_register"),
            "added_to_wishlist":     int(has("wishlist_add") or in_wishlist > 0),
            "added_to_cart":         int(has("cart_add") or in_cart > 0),
            "checkout_started":      int(has("checkout_start") or checkouts > 0),
            "enquiry_submitted":     int(has("enquiry_submit") or enquiries > 0),
            "top_course_slug":       row["course_slug"] if row else None,
            "device_type":           last_session["device_type"] if last_session else None,
            "lead_source":           first_source["lead_source"] if first_source else None,
        }
    finally:
        conn.close()


def add_score_snapshot(user_id, source, features, probability, lead_score, tier,
                       model_version, min_gap_minutes=0):
    """Store what the model saw + what it predicted. Later labelled by purchases."""
    import json
    if min_gap_minutes:
        recent = fetchone("""SELECT id FROM score_snapshots WHERE user_id=? AND source=?
                             AND created_at >= datetime('now','localtime',?)""",
                          (user_id, source, f"-{int(min_gap_minutes)} minutes"))
        if recent:
            return None
    return execute("""INSERT INTO score_snapshots
        (user_id, source, features_json, probability, lead_score, tier, model_version)
        VALUES (?,?,?,?,?,?,?)""",
        (user_id, source, json.dumps(features), probability, lead_score, tier, model_version))


def validate_coupon(user_id, code):
    return fetchone("""
        SELECT * FROM coupons_issued
        WHERE user_id=? AND coupon_code=? AND used=0
          AND (expires_at IS NULL OR expires_at > datetime('now','localtime'))
    """, (user_id, code))


def mark_coupon_used(coupon_id):
    execute("""
        UPDATE coupons_issued SET used=1, used_at=datetime('now','localtime')
        WHERE id=?
    """, (coupon_id,))



# ============================================================
# SCHEDULER SUPPORT FUNCTIONS (NEW)
# ============================================================

def get_abandoned_carts(minutes=60):
    """
    Cart items where user added course but didn't purchase
    within X minutes.
    """
    return fetchall("""
        SELECT 
            c.id as cart_id,
            c.user_id,
            c.course_slug,
            c.course_title,
            c.price,
            c.added_at,
            u.email,
            u.name
        FROM cart c
        JOIN users u ON u.id = c.user_id
        WHERE c.abandon_email_sent = 0
        AND c.added_at <= datetime('now','localtime', ?)
    """, (f"-{minutes} minutes",))


def mark_cart_email_sent(cart_id):
    execute(
        "UPDATE cart SET abandon_email_sent=1 WHERE id=?",
        (cart_id,)
    )


def get_inactive_users(minutes=15, lookback_hours=48):
    """
    Visits that ended (no activity for `minutes`) and have not been handled by
    the inactivity job yet — one decision per visit. Only each user's latest
    visit counts, and only if it happened in the last `lookback_hours`.
    """
    return fetchall("""
        SELECT
            u.id AS user_id,
            u.email,
            u.name,
            s.id AS session_id,
            s.last_active AS last_seen
        FROM user_sessions s
        JOIN users u ON u.id = s.user_id
        WHERE u.is_verified = 1
          AND s.id = (SELECT MAX(s2.id) FROM user_sessions s2 WHERE s2.user_id = s.user_id)
          AND COALESCE(s.followed_up, 0) = 0
          AND s.last_active <= datetime('now','localtime', ?)
          AND s.last_active >= datetime('now','localtime', ?)
    """, (f"-{minutes} minutes", f"-{lookback_hours} hours"))


def mark_visit_handled(user_id, session_id):
    execute("UPDATE user_sessions SET followed_up=1 WHERE user_id=? AND id<=?", (user_id, session_id))


def get_users_with_old_wishlist(minutes=30):
    """
    Users with a wishlisted course (not bought, not reminded yet) that was
    added more than `minutes` ago — one reminder per wishlist item.
    course_slug is the oldest such item (SQLite returns the row of MIN()).
    """
    return fetchall("""
        SELECT
            w.user_id,
            u.email,
            u.name,
            w.course_slug,
            MIN(w.added_at) as first_added
        FROM wishlist w
        JOIN users u ON u.id = w.user_id
        LEFT JOIN purchases p
            ON p.user_id = w.user_id
            AND p.course_slug = w.course_slug
        WHERE p.id IS NULL
          AND COALESCE(w.reminder_sent, 0) = 0
        GROUP BY w.user_id
        HAVING first_added <= datetime('now','localtime', ?)
    """, (f"-{minutes} minutes",))


def mark_wishlist_reminded(user_id):
    execute("UPDATE wishlist SET reminder_sent=1 WHERE user_id=?", (user_id,))


def recent_lead_exists(user_id, trigger, hours=6):
    """
    Prevent duplicate leads within cooldown window.
    trigger may be a single trigger, a list/tuple of triggers, or None (= any).
    """
    if trigger is None:
        triggers = None
    elif isinstance(trigger, (list, tuple)):
        triggers = list(trigger)
    else:
        triggers = [trigger]
    sql = "SELECT id FROM leads WHERE user_id=? AND created_at >= datetime('now','localtime', ?)"
    params = [user_id, f"-{hours} hours"]
    if triggers:
        sql += f" AND trigger_reason IN ({','.join('?' * len(triggers))})"
        params += triggers
    return fetchone(sql + " LIMIT 1", tuple(params)) is not None


def get_attribution_lead(user_id):
    """The latest lead that actually reached the user (email sent or enquiry)."""
    return fetchone("""SELECT * FROM leads WHERE user_id=? AND (email_sent=1 OR trigger_reason='enquiry')
                       ORDER BY created_at DESC, id DESC LIMIT 1""", (user_id,))


# ============================================================
# CHECKOUT ABANDONMENT
# ============================================================

def start_checkout_session(user_id, cart_value):
    return execute(
        "INSERT INTO checkout_sessions (user_id, cart_value) VALUES (?,?)",
        (user_id, cart_value)
    )


def complete_latest_checkout_session(user_id):
    # Close ALL open checkout sessions for this user. If they opened /checkout
    # more than once before paying, the older sessions would otherwise stay
    # "abandoned" and trigger a recovery email AFTER they already bought.
    execute("UPDATE checkout_sessions SET completed=1 WHERE user_id=? AND completed=0", (user_id,))


def get_abandoned_checkouts(minutes=30):
    """
    Checkout sessions started but not completed within X minutes.
    """
    return fetchall("""
        SELECT
            cs.id as checkout_id,
            cs.user_id,
            cs.cart_value,
            cs.started_at,
            u.email,
            u.name
        FROM checkout_sessions cs
        JOIN users u ON u.id = cs.user_id
        WHERE cs.completed = 0
          AND cs.abandon_email_sent = 0
          AND cs.started_at <= datetime('now','localtime', ?)
    """, (f"-{minutes} minutes",))


def mark_checkout_email_sent(checkout_id):
    execute("UPDATE checkout_sessions SET abandon_email_sent=1 WHERE id=?", (checkout_id,))


# ============================================================
# EMAIL SENDS (open/click tracking)
# ============================================================

def insert_email_send(token, user_id, lead_id=None, campaign_id=None, variant="A", subject="", body=""):
    if lead_id:
        execute("UPDATE leads SET email_sent=1, email_sent_at=datetime('now','localtime') WHERE id=?", (lead_id,))
    return execute("""
        INSERT INTO email_sends (lead_id, user_id, campaign_id, variant, token, subject, body)
        VALUES (?,?,?,?,?,?,?)
    """, (lead_id, user_id, campaign_id, variant, token, subject, body))


def get_email_send_by_token(token):
    return fetchone("SELECT * FROM email_sends WHERE token=?", (token,))


def get_email_engagement(user_id):
    """Real opens/clicks for a user — closes the loop between sent emails and pkl scoring."""
    row = fetchone("""
        SELECT COALESCE(SUM(open_count),0)  as opens,
               COALESCE(SUM(click_count),0) as clicks,
               COUNT(*)                     as emails_sent
        FROM email_sends WHERE user_id=?
    """, (user_id,))
    return row or {"opens": 0, "clicks": 0, "emails_sent": 0}


def mark_email_opened(token):
    execute("""
        UPDATE email_sends
        SET open_count = open_count + 1,
            opened_at = COALESCE(opened_at, datetime('now','localtime'))
        WHERE token=?
    """, (token,))


def mark_email_clicked(token):
    execute("""
        UPDATE email_sends
        SET click_count = click_count + 1,
            first_clicked_at = COALESCE(first_clicked_at, datetime('now','localtime'))
        WHERE token=?
    """, (token,))


# ============================================================
# LEAD SCORE HISTORY
# ============================================================

def log_score_change(lead_id, user_id, old_score, new_score, old_tier, new_tier, reason):
    execute("""
        INSERT INTO lead_score_history (lead_id, user_id, old_score, new_score, old_tier, new_tier, reason)
        VALUES (?,?,?,?,?,?,?)
    """, (lead_id, user_id, old_score, new_score, old_tier, new_tier, reason))


def get_score_history(lead_id):
    return fetchall(
        "SELECT * FROM lead_score_history WHERE lead_id=? ORDER BY created_at DESC",
        (lead_id,)
    )


# ============================================================
# PREDICTIVE LIFETIME VALUE (PLV)
# ============================================================

def compute_plv(user_id, recommended_action=None, conversion_probability=0.0, course_slug=None):
    """
    PLV = money already spent + expected value of the next purchase
        = spent + P(convert) × price of the course they are interested in
    (falls back to the catalogue's average price). The old version multiplied
    by a tier factor as well, which counted the probability twice.
    """
    import catalog
    spent = fetchone("SELECT COALESCE(SUM(price_paid),0) as s FROM purchases WHERE user_id=?",
                     (user_id,))["s"]
    price = catalog.price_of(course_slug) or catalog.average_price()
    return round(spent + price * _as_fraction(conversion_probability), 2)


def _as_fraction(p):
    """predict_lead() returns conversion_probability as 0-1; accept 0-100 too."""
    p = float(p or 0)
    return p / 100.0 if p > 1 else p


def update_lead_plv(lead_id, plv):
    execute("UPDATE leads SET plv=? WHERE id=?", (plv, lead_id))


def public_user(user):
    """User row without secrets — never send password_hash to the browser."""
    if not user:
        return None
    return {k: v for k, v in user.items() if k not in ("password_hash",)}
