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

    conn.commit()

    # ── Additive migrations for pre-existing DBs ─────────────────────
    for col_sql in (
        "ALTER TABLE leads ADD COLUMN plv REAL DEFAULT 0",
        "ALTER TABLE leads ADD COLUMN last_active_at TEXT",
        "ALTER TABLE leads ADD COLUMN decayed INTEGER DEFAULT 0",
        "ALTER TABLE email_sends ADD COLUMN ab_test_id INTEGER",
    ):
        try:
            c.execute(col_sql)
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists

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
        "SELECT * FROM leads WHERE user_id=? ORDER BY created_at DESC LIMIT 1",
        (user_id,)
    )


# ── FIXED get_behaviour_summary ───────────────────────────────────────────────
def get_behaviour_summary(user_id):
    """Fixed version - No more closed database error"""
    conn = get_conn()
    try:
        # Count sessions
        sessions = conn.execute(
            "SELECT COUNT(*) as cnt FROM user_sessions WHERE user_id=?", 
            (user_id,)
        ).fetchone()["cnt"]

        # Total time
        time_total = conn.execute(
            "SELECT COALESCE(SUM(time_spent_sec),0) as t FROM behaviour_events WHERE user_id=?", 
            (user_id,)
        ).fetchone()["t"]

        # Page views
        pv = conn.execute(
            "SELECT COUNT(*) as c FROM behaviour_events WHERE user_id=? AND event_type='page_view'",
            (user_id,)
        ).fetchone()["c"]

        # Distinct visits
        visits = conn.execute(
            "SELECT COUNT(DISTINCT session_id) as c FROM behaviour_events WHERE user_id=?",
            (user_id,)
        ).fetchone()["c"] or 1

        # Most viewed course
        row = conn.execute("""
            SELECT course_slug, COUNT(*) as cnt 
            FROM behaviour_events
            WHERE user_id=? AND course_slug IS NOT NULL
            GROUP BY course_slug 
            ORDER BY cnt DESC LIMIT 1
        """, (user_id,)).fetchone()
        top_course = dict(row)["course_slug"] if row else None

        # Helper to check if event exists
        def has_event(evt_type):
            count = conn.execute(
                "SELECT COUNT(*) as c FROM behaviour_events WHERE user_id=? AND event_type=?",
                (user_id, evt_type)
            ).fetchone()["c"]
            return int(count > 0)

        return {
            "sessions_count":        max(sessions or 1, 1),
            "total_time_on_website": min(time_total or 0, 4000),
            "page_views_per_visit":  round(pv / visits, 1) if visits > 0 else 1.0,
            "total_visits":          visits,
            "video_watched":         has_event("video_play"),
            "brochure_downloaded":   has_event("brochure_dl"),
            "chat_initiated":        has_event("chat"),
            "pricing_page_visited":  has_event("pricing_view"),
            "testimonial_visited":   has_event("testimonial_view"),
            "webinar_attended":      has_event("webinar_view"),
            "top_course_slug":       top_course,
        }
    finally:
        conn.close()   # ← Always close safely


def get_abandoned_carts():
    return fetchall("""
        SELECT c.*, u.email, u.name, up.whatsapp_opt_in,
               up.current_occupation, up.do_not_email
        FROM cart c
        JOIN users u ON c.user_id=u.id
        LEFT JOIN user_profiles up ON up.user_id=c.user_id
        WHERE c.abandon_email_sent=0
          AND c.added_at <= datetime('now','localtime','-60 minutes')
    """)


def mark_cart_email_sent(cart_id):
    execute("UPDATE cart SET abandon_email_sent=1 WHERE id=?", (cart_id,))


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


def get_inactive_users(minutes=15):
    """
    Users whose last session activity is older than X minutes.
    """
    return fetchall("""
        SELECT 
            u.id as user_id,
            u.email,
            u.name,
            MAX(s.last_active) as last_seen
        FROM users u
        JOIN user_sessions s ON s.user_id = u.id
        GROUP BY u.id
        HAVING last_seen <= datetime('now','localtime', ?)
    """, (f"-{minutes} minutes",))


def get_users_with_old_wishlist(minutes=30):
    """
    Users who added wishlist items but did not purchase.
    """
    return fetchall("""
        SELECT 
            w.user_id,
            u.email,
            u.name,
            MIN(w.added_at) as first_added
        FROM wishlist w
        JOIN users u ON u.id = w.user_id
        LEFT JOIN purchases p 
            ON p.user_id = w.user_id 
            AND p.course_slug = w.course_slug
        WHERE p.id IS NULL
        GROUP BY w.user_id
        HAVING first_added <= datetime('now','localtime', ?)
    """, (f"-{minutes} minutes",))


def recent_lead_exists(user_id, trigger, hours=6):
    """
    Prevent duplicate leads within cooldown window.
    """
    row = fetchone("""
        SELECT id FROM leads
        WHERE user_id=? AND trigger_reason=?
        AND created_at >= datetime('now','localtime', ?)
        LIMIT 1
    """, (user_id, trigger, f"-{hours} hours"))
    return row is not None


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

PLV_TIER_MULTIPLIER = {
    "Target Immediately": 1.5,
    "Nurture via Email/WhatsApp": 1.0,
    "Marketing Campaign": 0.6,
    "Low Priority": 0.2,
}


def compute_plv(user_id, recommended_action, conversion_probability=50.0):
    """
    PLV = money already spent + a heuristic future-value term based on
    average course price, conversion probability and lead tier.
    """
    spent = fetchone(
        "SELECT COALESCE(SUM(price_paid),0) as s FROM purchases WHERE user_id=?",
        (user_id,)
    )["s"]
    avg_price = fetchone(
        "SELECT COALESCE(AVG(price),0) as p FROM cart"
    )["p"] or 5000.0
    multiplier = PLV_TIER_MULTIPLIER.get(recommended_action, 0.3)
    future_value = avg_price * _as_fraction(conversion_probability) * multiplier
    return round(spent + future_value, 2)


def _as_fraction(p):
    """predict_lead() returns conversion_probability as 0-1; accept 0-100 too."""
    p = float(p or 0)
    return p / 100.0 if p > 1 else p


def update_lead_plv(lead_id, plv):
    execute("UPDATE leads SET plv=? WHERE id=?", (plv, lead_id))