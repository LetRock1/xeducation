"""
mkt_schema.py — tables of the marketing database (campaigns, A/B tests, WhatsApp log).

Kept separate from main.py so the history generator (ml/generate_history.py) can create
the same tables without starting the web server.
"""
import sqlite3


def init(conn: sqlite3.Connection):
    c = conn
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
                "ALTER TABLE campaign_schedules ADD COLUMN holdout_share REAL DEFAULT 0.1",
                "ALTER TABLE campaign_schedules ADD COLUMN held_out INTEGER DEFAULT 0",
                "ALTER TABLE campaign_schedules ADD COLUMN simulated INTEGER DEFAULT 0",
                "ALTER TABLE sms_queue ADD COLUMN channel TEXT DEFAULT 'whatsapp'",
                "ALTER TABLE sms_queue ADD COLUMN lead_id INTEGER",
                "ALTER TABLE ab_tests ADD COLUMN sent_at TEXT",
                # v6 experiment engine
                "ALTER TABLE ab_tests ADD COLUMN hypothesis TEXT",
                "ALTER TABLE ab_tests ADD COLUMN metric TEXT DEFAULT 'purchase'",
                "ALTER TABLE ab_tests ADD COLUMN control_share REAL DEFAULT 0",
                "ALTER TABLE ab_tests ADD COLUMN variants_json TEXT",
                "ALTER TABLE ab_tests ADD COLUMN mde REAL",
                "ALTER TABLE ab_tests ADD COLUMN planned_per_arm INTEGER",
                "ALTER TABLE ab_tests ADD COLUMN started_at TEXT",
                "ALTER TABLE ab_tests ADD COLUMN simulated INTEGER DEFAULT 0",
                "ALTER TABLE ab_tests ADD COLUMN applied_campaign_id INTEGER"):
        try:
            c.execute(sql)
        except sqlite3.OperationalError:
            pass
    c.commit()
