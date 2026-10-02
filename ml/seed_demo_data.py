"""
=================================================================
 DEMO DATA — simulated learners with 6 weeks of history
=================================================================
 A fresh install has an empty dashboard, and the closed loop can only be
 shown once there are decisions whose outcome is known (14+ days old). This
 script adds SIMULATED learners so that Model health, the next-best-action
 report, attribution, Today's actions and retrain-model.bat can be
 demonstrated.

 Everything it creates is clearly marked and removable:
   * every simulated learner's email ends in @demo.xeducation.test — a
     reserved domain that can never receive mail (the email code also refuses
     to send to it), and the dashboard shows a "simulated learners" banner
   * remove-demo-data.bat (or --remove) deletes all of it

 How it is generated (honest about what it shows):
   * profiles and behaviour come from the dataset generator (ml/generate_dataset.py)
     and are written as real website events (sessions, page views, cart ...)
   * each learner is scored by the LIVE lead model, and the LIVE next-best-action
     engine decides what to do at their trigger (cart / checkout / wishlist /
     enquiry / inactivity) — with its 15% random exploration and logged
     propensities, exactly as on the website
   * whether they buy is drawn from the simulator (ml/nba_simulation.py) for the
     action that was taken. So the closed loop demonstrates the MECHANISM;
     its numbers reflect the simulator's documented assumptions, not real
     customers.

 Usage (with the backend venv; the servers may be running):
   user-backend\\venv\\Scripts\\python.exe ml\\seed_demo_data.py            400 learners
   user-backend\\venv\\Scripts\\python.exe ml\\seed_demo_data.py --n 800
   user-backend\\venv\\Scripts\\python.exe ml\\seed_demo_data.py --remove
=================================================================
"""
import argparse
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timedelta

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "user-backend")
sys.path.insert(0, HERE)
sys.path.insert(0, BACKEND)

DEMO_DOMAIN = "demo.xeducation.test"
FIRST = ["Aarav", "Vivaan", "Aditya", "Arjun", "Rohan", "Karan", "Ishaan", "Kabir", "Rahul", "Siddharth",
         "Ananya", "Diya", "Isha", "Kavya", "Meera", "Nisha", "Pooja", "Riya", "Sneha", "Tanvi",
         "Aditi", "Harsh", "Nikhil", "Pranav", "Varun", "Neha", "Shreya", "Divya", "Simran", "Zoya"]
LAST = ["Sharma", "Verma", "Patel", "Iyer", "Nair", "Reddy", "Gupta", "Mehta", "Joshi", "Kulkarni",
        "Desai", "Rao", "Singh", "Chopra", "Bose", "Menon", "Pillai", "Shah", "Kapoor", "Agarwal"]
ALLOWED = {"enquiry": ["email_info", "email_coupon_10", "email_coupon_20", "call"],
           "wishlist": ["none", "email_info", "email_coupon_10", "whatsapp"]}
TRIGGER_DELAY_MIN = {"checkout_abandon": (30, 60), "cart_abandon": (60, 120), "wishlist": (30, 90),
                     "session_end": (15, 40), "enquiry": (0, 1)}


def ts(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def demo_user_ids(db):
    return [r["id"] for r in db.fetchall("SELECT id FROM users WHERE email LIKE ?", (f"%@{DEMO_DOMAIN}",))]


def remove(db):
    ids = demo_user_ids(db)
    if not ids:
        print("No simulated demo learners found — nothing to remove.")
        return
    con = db.get_conn()
    try:
        q = ",".join("?" * len(ids))
        tables = [r["name"] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for t in tables:
            cols = [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
            if "user_id" in cols and t != "users":
                con.execute(f"DELETE FROM {t} WHERE user_id IN ({q})", ids)
        con.execute(f"DELETE FROM otp_tokens WHERE email LIKE ?", (f"%@{DEMO_DOMAIN}",))
        con.execute(f"DELETE FROM users WHERE id IN ({q})", ids)
        con.commit()
    finally:
        con.close()
    mkt = os.path.join(BACKEND, "..", "marketing-backend", "xeducation_marketing.db")
    if os.path.exists(mkt):
        c = sqlite3.connect(mkt, timeout=30)
        try:
            c.execute(f"DELETE FROM sms_queue WHERE user_id IN ({','.join('?' * len(ids))})", ids)
            c.commit()
        except sqlite3.OperationalError:
            pass
        finally:
            c.close()
    print(f"Removed {len(ids)} simulated demo learners and everything linked to them.")


def seed(db, n, seed_value):
    import catalog
    import generate_dataset as G
    import ml_features as F
    import nba
    import nba_core as N
    import nba_simulation as S
    import scoring
    from genai_mock import generate_content
    from predict import model_info, predict_lead

    if demo_user_ids(db):
        raise SystemExit("Simulated demo learners are already present — run remove-demo-data.bat first.")
    if model_info().get("version", "fallback") == "fallback":
        raise SystemExit("No trained lead model — run train-model.bat first.")

    rng = np.random.default_rng(seed_value)
    nba._rng = np.random.default_rng(seed_value + 1)        # reproducible exploration
    now = datetime.now()
    raw_df = G.generate(n, seed=seed_value, return_truth=True)
    truth = S.true_probabilities(F.to_model_frame(raw_df), raw_df["_p_true"].to_numpy(), seed=seed_value + 2)
    slugs_by_type = {}
    for slug, ctype in F.COURSE_TYPE_BY_SLUG.items():
        if catalog.get_course(slug):
            slugs_by_type.setdefault(ctype, []).append(slug)
    all_slugs = [s for v in slugs_by_type.values() for s in v]
    stats = {"learners": 0, "decisions": 0, "explore": 0, "purchases": 0, "emails": 0, "tasks_open": 0}

    for i, r in enumerate(raw_df.to_dict("records")):
        first, last = FIRST[int(rng.integers(len(FIRST)))], LAST[int(rng.integers(len(LAST)))]
        name, email = f"{first} {last}", f"{first}.{last}.{i + 1}@{DEMO_DOMAIN}".lower()
        recent = rng.random() < 0.2                              # still in their decision window
        signup = now - timedelta(days=float(rng.uniform(0.3, 3.0) if recent else rng.uniform(18, 42)))
        journey = timedelta(hours=float(rng.uniform(0.2, 6.0 if recent else 72.0)))
        visits = max(1, int(r["TotalVisits"]))
        starts = sorted(signup + journey * float(x) for x in rng.random(visits))
        slug = rng.choice(slugs_by_type.get(r["CourseType"]) or all_slugs)
        course = catalog.get_course(slug)

        uid = db.execute("INSERT INTO users (name, email, password_hash, is_verified, created_at) VALUES (?,?,?,1,?)",
                         (name, email, "!demo-" + uuid.uuid4().hex, ts(signup)))
        has_profile = r["CurrentOccupation"] != "Unknown"
        phone = f"+91 00000 {i + 1:05d}" if rng.random() < 0.85 else None
        db.execute("""INSERT INTO user_profiles (user_id, current_occupation, specialization, age_bracket, city, country,
                      phone, whatsapp_opt_in, do_not_email, do_not_call, how_did_you_hear, profile_complete, updated_at)
                      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                   (uid, r["CurrentOccupation"] if has_profile else None, r["Specialization"] if has_profile else None,
                    r["AgeBracket"] if r["AgeBracket"] != "Unknown" else None,
                    r["City"] if r["City"] != "Unknown" else None, r["Country"], phone,
                    int(r["WhatsAppOptIn"]), "Yes" if r["DoNotEmail"] else "No", "Yes" if r["DoNotCall"] else "No",
                    r["HowDidYouHear"] if r["HowDidYouHear"] != "Unknown" else None, int(has_profile), ts(signup)))

        # ── sessions + page views (the same quantities the tracker records) ──
        per_visit = float(r["TotalTimeOnWebsite"]) / visits
        pages = max(1, int(round(float(r["PageViewsPerVisit"]))))
        last_active, sids = signup, []
        for k, start in enumerate(starts):
            end = start + timedelta(seconds=per_visit)
            sid = db.execute("""INSERT INTO user_sessions (user_id, login_at, last_active, device_type, lead_source,
                                followed_up) VALUES (?,?,?,?,?,1)""",
                             (uid, ts(start), ts(end), r["DeviceType"], r["LeadSource"] if k == 0 else "Direct Traffic"))
            sids.append((sid, start, end))
            for p in range(pages):
                db.execute("""INSERT INTO behaviour_events (user_id, session_id, course_slug, event_type, time_spent_sec,
                              created_at) VALUES (?,?,?,?,?,?)""",
                           (uid, sid, slug if p == 0 or rng.random() < 0.6 else None, "page_view",
                            int(round(per_visit / pages)), ts(start + timedelta(seconds=per_visit * (p + 1) / pages))))
            last_active = max(last_active, end)

        # ── intent signals, in the last visit ──
        sid, s_start, s_end = sids[-1]
        def event(kind, minutes_in=1.0):
            at = min(s_start + timedelta(minutes=minutes_in), s_end + timedelta(minutes=1))
            db.execute("""INSERT INTO behaviour_events (user_id, session_id, course_slug, event_type, created_at)
                          VALUES (?,?,?,?,?)""", (uid, sid, slug, kind, ts(at)))
            return at
        for flag, kind in (("VideoWatched", "video_play"), ("PricingPageVisited", "pricing_view"),
                           ("TestimonialVisited", "testimonial_view"), ("BrochureDownloaded", "brochure_dl"),
                           ("ChatInitiated", "chat"), ("WebinarAttended", "webinar_register")):
            if r[flag]:
                last_active = max(last_active, event(kind, float(rng.uniform(0.5, 3))))
        if r["AddedToWishlist"]:
            at = event("wishlist_add", 2)
            db.execute("""INSERT INTO wishlist (user_id, course_slug, course_title, added_at, reminder_sent)
                          VALUES (?,?,?,?,1)""", (uid, slug, course["title"], ts(at)))
        if r["AddedToCart"]:
            at = event("cart_add", 3)
            db.execute("""INSERT INTO cart (user_id, course_slug, course_title, price, added_at, abandon_email_sent)
                          VALUES (?,?,?,?,?,1)""", (uid, slug, course["title"], course["price"], ts(at)))
            last_active = max(last_active, at)
        checkout_id = None
        if r["CheckoutStarted"]:
            at = event("checkout_start", 4)
            checkout_id = db.execute("""INSERT INTO checkout_sessions (user_id, cart_value, started_at, abandon_email_sent)
                                        VALUES (?,?,?,1)""", (uid, course["price"], ts(at)))
            last_active = max(last_active, at)
        if r["EnquirySubmitted"]:
            last_active = max(last_active, event("enquiry_submit", 2.5))
        clicked_k = int(r["EmailOpenedCount"])                 # newsletters they clicked (+ some they ignored)
        received = 0 if r["DoNotEmail"] else clicked_k + int(rng.poisson(2))
        for k in range(received):
            sent = signup + journey * float(rng.random())
            hit = k < clicked_k
            db.execute("""INSERT INTO email_sends (user_id, token, subject, body, sent_at, opened_at, open_count,
                          first_clicked_at, click_count, campaign_name) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                       (uid, uuid.uuid4().hex, "X Education newsletter", "(simulated newsletter)", ts(sent),
                        ts(sent + timedelta(hours=2)) if hit else None, int(hit),
                        ts(sent + timedelta(hours=2)) if hit else None, int(hit), "Newsletter (simulated)"))

        # ── the live model scores them; a CRM contact exists from signup ──
        raw = scoring.build_raw(uid, course=slug)
        pred = predict_lead(raw, explain=True)
        pred["raw"] = raw
        lead_id = scoring.save_lead(uid, pred, {}, "signup", course_slug=slug)
        db.execute("UPDATE leads SET created_at=? WHERE id=?", (ts(signup), lead_id))

        # ── trigger → live next-best-action decision ──
        trigger = ("checkout_abandon" if r["CheckoutStarted"] else "cart_abandon" if r["AddedToCart"]
                   else "enquiry" if r["EnquirySubmitted"] else "wishlist" if r["AddedToWishlist"]
                   else "session_end" if r["TotalTimeOnWebsite"] >= 60 and rng.random() < 0.7 else None)
        action, decided_at = "none", last_active
        if trigger:
            lo, hi = TRIGGER_DELAY_MIN[trigger]
            decided_at = last_active + timedelta(minutes=float(rng.uniform(lo, hi)))
            decision = nba.decide(uid, trigger, pred, course_slug=slug, allowed=ALLOWED.get(trigger))
            action = decision["action"]
            is_email = action.startswith("email")
            content = generate_content(
                name=name, occupation=raw["CurrentOccupation"], specialization=raw["Specialization"],
                course=course["title"], action=("Target Immediately" if action == "call" else pred["recommended_action"]),
                trigger=trigger, past_purchases=0, lead_score=pred["lead_score"], course_slug=slug,
                offer_pct=nba.offer_pct(action) if is_email else 0)
            lead_id = scoring.save_lead(uid, pred, content, trigger, course_slug=slug)
            nba.attach_to_lead(lead_id, decision)
            db.execute("UPDATE leads SET created_at=? WHERE id=?", (ts(decided_at), lead_id))
            db.execute("UPDATE nba_decisions SET created_at=? WHERE id=?", (ts(decided_at), decision["decision_id"]))
            db.execute("""UPDATE coupons_issued SET created_at=?, expires_at=datetime(?, '+72 hours')
                          WHERE user_id=?""", (ts(decided_at), ts(decided_at), uid))
            stats["decisions"] += 1
            stats["explore"] += decision["policy"] == "explore"
            if (is_email or trigger == "enquiry") and not r["DoNotEmail"]:
                sent = decided_at + timedelta(minutes=1)
                clicked = rng.random() < 0.15 + 0.4 * pred["conversion_probability"]
                click_at = sent + timedelta(hours=float(rng.uniform(0.2, 30)))
                clicked = clicked and click_at < now
                db.execute("""INSERT INTO email_sends (lead_id, user_id, token, subject, body, sent_at, opened_at,
                              open_count, first_clicked_at, click_count) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                           (lead_id, uid, uuid.uuid4().hex, content["email_subject"], content["email_body"], ts(sent),
                            ts(click_at) if clicked else None, int(clicked), ts(click_at) if clicked else None,
                            int(clicked)))
                db.execute("UPDATE leads SET email_sent=1, email_sent_at=? WHERE id=?", (ts(sent), lead_id))
                if is_email:
                    db.execute("UPDATE nba_decisions SET executed_at=? WHERE id=?", (ts(sent), decision["decision_id"]))
                stats["emails"] += 1
            if action in ("call", "whatsapp"):
                verb = "Call" if action == "call" else "WhatsApp"
                task_id = nba.create_task(uid, lead_id, decision, f"{verb} {name} about {course['title']}",
                                          content.get("call_script") if action == "call" else content.get("whatsapp_message"))
                done = not recent
                outcome = ("sent" if action == "whatsapp" else
                           rng.choice(["reached", "no_answer", "not_interested"], p=[0.6, 0.3, 0.1])) if done else None
                done_at = decided_at + timedelta(hours=float(rng.uniform(1, 24)))
                db.execute("UPDATE sales_tasks SET created_at=?, status=?, outcome=?, done_at=? WHERE id=?",
                           (ts(decided_at), "done" if done else "open", outcome, ts(done_at) if done else None, task_id))
                if done and outcome != "no_answer":
                    db.execute("UPDATE nba_decisions SET executed_at=? WHERE id=?", (ts(done_at), decision["decision_id"]))
                stats["tasks_open"] += not done

        # snapshot the model saw at their last activity (what Model health is checked against)
        db.execute("""INSERT INTO score_snapshots (user_id, source, features_json, probability, lead_score, tier,
                      model_version, created_at) VALUES (?,?,?,?,?,?,?,?)""",
                   (uid, trigger or "activity", json.dumps(pred["features"]), pred["conversion_probability"],
                    pred["lead_score"], pred["recommended_action"], pred["model_version"], ts(last_active)))

        # ── outcome, from the simulator's response to the action taken ──
        if rng.random() < truth[action][i]:
            bought = decided_at + timedelta(days=float(rng.uniform(0.05, 10)))
            if bought < now - timedelta(minutes=5):
                disc = N.ACTIONS[action]["discount"]
                code = None
                if disc:
                    c = db.fetchone("SELECT id, coupon_code FROM coupons_issued WHERE user_id=? ORDER BY id DESC LIMIT 1",
                                    (uid,))
                    if c:
                        code = c["coupon_code"]
                        db.execute("UPDATE coupons_issued SET used=1, used_at=? WHERE id=?", (ts(bought), c["id"]))
                    else:
                        disc = 0.0
                paid = round(course["price"] * (1 - disc), 2)
                db.execute("""INSERT INTO purchases (user_id, course_slug, course_title, price_paid, coupon_used,
                              discount_amount, purchased_at) VALUES (?,?,?,?,?,?,?)""",
                           (uid, slug, course["title"], paid, code, round(course["price"] - paid, 2), ts(bought)))
                db.execute("""INSERT INTO behaviour_events (user_id, course_slug, event_type, created_at)
                              VALUES (?,?,?,?)""", (uid, slug, "purchase", ts(bought)))
                db.execute("DELETE FROM cart WHERE user_id=? AND course_slug=?", (uid, slug))
                if checkout_id:
                    db.execute("UPDATE checkout_sessions SET completed=1 WHERE id=?", (checkout_id,))
                scoring.rescore_latest_lead(uid, "purchase_conversion")
                db.execute("""UPDATE lead_score_history SET created_at=? WHERE id=(SELECT MAX(id) FROM lead_score_history
                              WHERE user_id=?)""", (ts(bought), uid))
                db.execute("""UPDATE score_snapshots SET created_at=? WHERE id=(SELECT MAX(id) FROM score_snapshots
                              WHERE user_id=? AND source='purchase_conversion')""", (ts(bought), uid))
                stats["purchases"] += 1
        stats["learners"] += 1
        if (i + 1) % 100 == 0:
            print(f"  {i + 1:,} learners ...")

    print(f"\nAdded {stats['learners']} simulated learners (@{DEMO_DOMAIN}): {stats['decisions']} next-best-action "
          f"decisions ({stats['explore']} random learning samples), {stats['emails']} emails, "
          f"{stats['purchases']} purchases, {stats['tasks_open']} open sales tasks.")
    print("Open the dashboard: Model health, Next-best-action, Pipeline forecast, Today's actions.")
    print("Closed loop: run retrain-model.bat — both models are retrained and swapped only if better.")
    print("Remove it all again with remove-demo-data.bat.")


def main():
    ap = argparse.ArgumentParser(description="Add (or remove) simulated demo learners.")
    ap.add_argument("--n", type=int, default=400)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--remove", action="store_true")
    ap.add_argument("--db", default=None, help="path to xeducation_user.db (default: user-backend/)")
    args = ap.parse_args()
    import database as db
    if args.db:
        db.DB_PATH = args.db
    db.init_db()
    if args.remove:
        remove(db)
    else:
        seed(db, args.n, args.seed)


if __name__ == "__main__":
    main()
