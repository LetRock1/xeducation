"""
scoring.py — the ONE place where a user's data becomes a lead score.

Before this file, main.py and scheduler.py each built their own feature
dict (6 copies) with different hard-coded values: LeadOrigin "Website
Interaction" in one, DeviceType "Mobile" in another, Specialization
"Business" in a third... Every endpoint and job now calls build_raw() and
score_user(), so the model sees the same, correct inputs everywhere.
"""
import json
import threading
from datetime import datetime

import catalog
import database as db
import ml_features as F
import settings
from predict import predict_lead

COUPON_VALID_HOURS = int(settings.S["coupon_valid_hours"])


def last_seen(user_id):
    """When the person was last on the website: their latest tracked event, visit or sign-up."""
    row = db.fetchone("""SELECT MAX(t) AS t FROM (
            SELECT MAX(created_at) AS t FROM behaviour_events WHERE user_id=?
            UNION ALL SELECT MAX(last_active) FROM user_sessions WHERE user_id=?
            UNION ALL SELECT created_at FROM users WHERE id=?)""", (user_id, user_id, user_id))
    return row["t"] if row else None


def days_since(ts, now=None):
    """Days between a 'YYYY-MM-DD HH:MM:SS' timestamp and now (local time, like the database)."""
    if not ts:
        return None
    try:
        t = datetime.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return max(0.0, ((now or datetime.now()) - t).total_seconds() / 86400.0)


def build_raw(user_id, course=None, lead_source=None, whatsapp_opt_in=None, recency=False):
    """Collect everything we know about the user as model features.
    recency=True adds away_days (days since the person was last on the site), which the live score
    uses; the simulated history leaves it out (it scores with simulated timestamps)."""
    profile = db.get_profile(user_id) or {}
    b = db.get_behaviour_summary(user_id)
    e = db.get_email_engagement(user_id)
    extra = {"away_days": days_since(last_seen(user_id))} if recency else {}
    return {
        **extra,
        "LeadOrigin": "Lead Add Form" if b["enquiry_submitted"] else "Landing Page Submission",
        "LeadSource": lead_source or b.get("lead_source") or "Direct Traffic",
        "DeviceType": b.get("device_type") or "Desktop",
        "CurrentOccupation": profile.get("current_occupation"),
        "Specialization": profile.get("specialization"),
        "CourseType": course or b.get("top_course_slug"),
        "City": profile.get("city"),
        "Country": profile.get("country"),
        "AgeBracket": profile.get("age_bracket"),
        "HowDidYouHear": profile.get("how_did_you_hear"),
        "TotalVisits": b["total_visits"],
        "TotalTimeOnWebsite": b["total_time_on_website"],
        "PageViewsPerVisit": b["page_views_per_visit"],
        "EmailOpenedCount": e["opens"] or 0,
        "VideoWatched": b["video_watched"],
        "BrochureDownloaded": b["brochure_downloaded"],
        "ChatInitiated": b["chat_initiated"],
        "PricingPageVisited": b["pricing_page_visited"],
        "TestimonialVisited": b["testimonial_visited"],
        "WebinarAttended": b["webinar_attended"],
        "AddedToWishlist": b["added_to_wishlist"],
        "AddedToCart": b["added_to_cart"],
        "CheckoutStarted": b["checkout_started"],
        "EnquirySubmitted": b["enquiry_submitted"],
        "WhatsAppOptIn": profile.get("whatsapp_opt_in", 0) if whatsapp_opt_in is None else whatsapp_opt_in,
        "DoNotEmail": profile.get("do_not_email") or "No",
        "DoNotCall": profile.get("do_not_call") or "No",
        "past_purchases": len(db.get_purchases(user_id)),
    }


def score_user(user_id, source, course=None, explain=False, snapshot_gap_minutes=0, **kw):
    """Score a user, record a snapshot for closed-loop retraining, update the live score."""
    raw = build_raw(user_id, course=course, recency=True, **kw)
    pred = predict_lead(raw, explain=explain)
    pred["raw"] = raw
    db.add_score_snapshot(user_id, source, pred["features"], pred["conversion_probability"],
                          pred["lead_score"], pred["recommended_action"], pred["model_version"],
                          min_gap_minutes=snapshot_gap_minutes)
    db.execute("""
        INSERT INTO live_user_state (user_id, live_score, persona, updated_at)
        VALUES (?, ?, ?, datetime('now','localtime'))
        ON CONFLICT(user_id) DO UPDATE SET live_score=excluded.live_score,
            persona=excluded.persona, updated_at=excluded.updated_at
    """, (user_id, pred["lead_score"], pred["persona"]))
    return pred


def interest_slug(user_id, explicit_slug=None):
    """The course this lead is about: explicit > latest cart item > most viewed course."""
    if explicit_slug and catalog.get_course(explicit_slug):
        return explicit_slug
    cart = db.get_cart(user_id)
    if cart:
        return cart[0]["course_slug"]
    return db.get_behaviour_summary(user_id).get("top_course_slug")


def issue_coupon(user_id, code, pct, tier):
    """Give the user a personal coupon (one live copy per code)."""
    if not code or not pct:
        return
    exists = db.fetchone("""SELECT id FROM coupons_issued WHERE user_id=? AND coupon_code=? AND used=0
                            AND (expires_at IS NULL OR expires_at > datetime('now','localtime'))""",
                         (user_id, code))
    if exists:
        return
    db.execute("""INSERT INTO coupons_issued (user_id, coupon_code, discount_pct, tier, expires_at)
                  VALUES (?,?,?,?,datetime('now','localtime',?))""",
               (user_id, code, int(pct), tier, f"+{COUPON_VALID_HOURS} hours"))


def _tips(pred):
    """'How to convert' guidance for sales (see recourse.py)."""
    try:
        import recourse
        return recourse.tips_for(pred["features"], pred["lead_score"])
    except Exception as e:
        print(f"[RECOURSE] skipped: {e}")
        return []


def save_lead(user_id, pred, content, trigger, course_label=None, course_slug=None):
    """Insert a lead row (with its explanation), issue the coupon, store PLV."""
    f = pred["features"]
    course_slug = course_slug if catalog.get_course(course_slug) else None
    if course_slug and not course_label:
        course_label = catalog.title_of(course_slug)
    lead_id = db.execute("""
        INSERT INTO leads (
            user_id, lead_origin, lead_source, device_type,
            total_visits, total_time_on_website, page_views_per_visit,
            sessions_count, video_watched, brochure_downloaded, chat_initiated,
            pricing_page_visited, testimonial_visited, webinar_attended, email_opened_count,
            course_type, lead_score, conversion_probability, persona,
            customer_segment, recommended_action,
            email_subject, email_body, whatsapp_message, coupon_code, call_script,
            trigger_reason, score_factors, model_version, course_slug, tips_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        user_id, f["LeadOrigin"], f["LeadSource"], f["DeviceType"],
        int(f["TotalVisits"]), int(f["TotalTimeOnWebsite"]), f["PageViewsPerVisit"],
        int(f["TotalVisits"]), f["VideoWatched"], f["BrochureDownloaded"], f["ChatInitiated"],
        f["PricingPageVisited"], f["TestimonialVisited"], f["WebinarAttended"],
        int(f["EmailOpenedCount"]),
        course_label or f["CourseType"],
        pred["lead_score"], pred["conversion_probability"], pred["persona"],
        pred["customer_segment"], pred["recommended_action"],
        content.get("email_subject"), content.get("email_body"), content.get("whatsapp_message"),
        content.get("coupon_code"), content.get("call_script"),
        trigger, json.dumps(pred.get("factors") or []), pred["model_version"], course_slug,
        json.dumps(_tips(pred)),
    ))

    issue_coupon(user_id, content.get("coupon_code"), content.get("offer_pct"), pred["recommended_action"])

    plv = db.compute_plv(user_id, pred["recommended_action"], pred["conversion_probability"], course_slug)
    db.update_lead_plv(lead_id, plv)
    return lead_id


def rescore_latest_lead(user_id, reason, snapshot_gap_minutes=0):
    """Re-run the model and update the user's latest lead row in place
    (activity, email click, purchase, manual). History is logged only for
    meaningful moves, so the audit trail isn't flooded by page views."""
    lead = db.get_user_lead(user_id)
    pred = score_user(user_id, source=reason, explain=True, snapshot_gap_minutes=snapshot_gap_minutes)
    if not lead:
        return None, pred
    slug = lead.get("course_slug") or interest_slug(user_id)
    if slug and not lead.get("course_slug"):
        db.execute("UPDATE leads SET course_slug=?, course_type=? WHERE id=?",
                   (slug, catalog.title_of(slug), lead["id"]))
    plv = db.compute_plv(user_id, pred["recommended_action"], pred["conversion_probability"], slug)
    f = pred["features"]
    db.execute("""
        UPDATE leads SET lead_score=?, conversion_probability=?, recommended_action=?,
               persona=?, customer_segment=?, plv=?, email_opened_count=?,
               total_visits=?, total_time_on_website=?, page_views_per_visit=?, sessions_count=?,
               video_watched=?, brochure_downloaded=?, chat_initiated=?, pricing_page_visited=?,
               testimonial_visited=?, webinar_attended=?, lead_source=?, device_type=?,
               score_factors=?, model_version=?, tips_json=?, decayed=0
        WHERE id=?
    """, (pred["lead_score"], pred["conversion_probability"], pred["recommended_action"],
          pred["persona"], pred["customer_segment"], plv, int(f["EmailOpenedCount"]),
          int(f["TotalVisits"]), int(f["TotalTimeOnWebsite"]), f["PageViewsPerVisit"], int(f["TotalVisits"]),
          f["VideoWatched"], f["BrochureDownloaded"], f["ChatInitiated"], f["PricingPageVisited"],
          f["TestimonialVisited"], f["WebinarAttended"], f["LeadSource"], f["DeviceType"],
          json.dumps(pred.get("factors") or []), pred["model_version"], json.dumps(_tips(pred)), lead["id"]))
    old = lead["lead_score"] or 0
    if lead["recommended_action"] != pred["recommended_action"] or abs(old - pred["lead_score"]) >= 5 \
            or reason in ("purchase_conversion", "email_click", "manual_rescore"):
        db.log_score_change(lead["id"], user_id, old, pred["lead_score"],
                            lead["recommended_action"], pred["recommended_action"], reason)
    return lead, pred


# ── Score refresh: everyone, automatically (replaces the hand-written "lead decay" rule) ─────────
def build_raw_many(user_ids, now=None):
    """build_raw(recency=True) for many people at once, with a dozen grouped queries instead of a
    dozen per person. Same values as build_raw (tests/test_score_refresh.py compares them)."""
    ids = sorted({int(u) for u in user_ids})
    if not ids:
        return {}
    con = db.get_conn()
    try:
        con.execute("DROP TABLE IF EXISTS temp._ids")
        con.execute("CREATE TEMP TABLE _ids (id INTEGER PRIMARY KEY)")
        con.executemany("INSERT INTO temp._ids (id) VALUES (?)", [(u,) for u in ids])

        def grouped(sql):
            return {r[0]: r[1] for r in con.execute(sql).fetchall()}

        IN = "user_id IN (SELECT id FROM temp._ids)"
        profiles = {r["user_id"]: dict(r) for r in con.execute(f"SELECT * FROM user_profiles WHERE {IN}")}
        visits = grouped(f"""SELECT user_id, COUNT(DISTINCT session_id) FROM behaviour_events
                             WHERE {IN} AND session_id IS NOT NULL GROUP BY user_id""")
        time_total = grouped(f"""SELECT user_id, COALESCE(SUM(time_spent_sec),0) FROM behaviour_events
                                 WHERE {IN} AND event_type='page_view' GROUP BY user_id""")
        page_views = grouped(f"""SELECT user_id, COUNT(*) FROM behaviour_events
                                 WHERE {IN} AND event_type='page_view' GROUP BY user_id""")
        counts = {}
        for uid, et, c in con.execute(f"""SELECT user_id, event_type, COUNT(*) FROM behaviour_events
                                          WHERE {IN} GROUP BY user_id, event_type"""):
            counts.setdefault(uid, {})[et] = c
        in_cart = grouped(f"SELECT user_id, COUNT(*) FROM cart WHERE {IN} GROUP BY user_id")
        in_wishlist = grouped(f"SELECT user_id, COUNT(*) FROM wishlist WHERE {IN} GROUP BY user_id")
        checkouts = grouped(f"SELECT user_id, COUNT(*) FROM checkout_sessions WHERE {IN} GROUP BY user_id")
        enquiries = grouped(f"""SELECT user_id, COUNT(*) FROM leads WHERE {IN} AND trigger_reason='enquiry'
                                GROUP BY user_id""")
        top = {}
        for uid, slug, cnt, last_id in con.execute(f"""SELECT user_id, course_slug, COUNT(*), MAX(id) FROM behaviour_events
                                                       WHERE {IN} AND course_slug IS NOT NULL
                                                       GROUP BY user_id, course_slug"""):
            if uid not in top or (cnt, last_id) > top[uid][1:]:
                top[uid] = (slug, cnt, last_id)
        device = grouped(f"""SELECT s.user_id, s.device_type FROM user_sessions s
                             JOIN (SELECT user_id, MAX(id) AS id FROM user_sessions WHERE {IN} AND device_type IS NOT NULL
                                   GROUP BY user_id) m ON m.id = s.id""")
        source = grouped(f"""SELECT s.user_id, s.lead_source FROM user_sessions s
                             JOIN (SELECT user_id, MIN(id) AS id FROM user_sessions WHERE {IN} AND lead_source IS NOT NULL
                                   AND lead_source != 'Direct Traffic' GROUP BY user_id) m ON m.id = s.id""")
        opens = grouped(f"SELECT user_id, COALESCE(SUM(open_count),0) FROM email_sends WHERE {IN} GROUP BY user_id")
        bought = grouped(f"SELECT user_id, COUNT(*) FROM purchases WHERE {IN} GROUP BY user_id")
        last_event = grouped(f"SELECT user_id, MAX(created_at) FROM behaviour_events WHERE {IN} GROUP BY user_id")
        last_visit = grouped(f"SELECT user_id, MAX(last_active) FROM user_sessions WHERE {IN} GROUP BY user_id")
        signed_up = {r[0]: r[1] for r in con.execute("SELECT id, created_at FROM users WHERE id IN (SELECT id FROM temp._ids)")}
        con.execute("DROP TABLE IF EXISTS temp._ids")
    finally:
        con.close()

    out = {}
    for u in ids:
        p = profiles.get(u) or {}
        n_visits = max(visits.get(u) or 0, 1)
        c = counts.get(u, {})
        has = lambda *types: int(any(c.get(t, 0) > 0 for t in types))
        enquiry = int(has("enquiry_submit") or (enquiries.get(u) or 0) > 0)
        seen = max([t for t in (last_event.get(u), last_visit.get(u), signed_up.get(u)) if t] or [None],
                   key=lambda t: t or "")
        out[u] = {
            "away_days": days_since(seen, now),
            "LeadOrigin": "Lead Add Form" if enquiry else "Landing Page Submission",
            "LeadSource": source.get(u) or "Direct Traffic",
            "DeviceType": device.get(u) or "Desktop",
            "CurrentOccupation": p.get("current_occupation"),
            "Specialization": p.get("specialization"),
            "CourseType": (top.get(u) or (None,))[0],
            "City": p.get("city"),
            "Country": p.get("country"),
            "AgeBracket": p.get("age_bracket"),
            "HowDidYouHear": p.get("how_did_you_hear"),
            "TotalVisits": n_visits,
            "TotalTimeOnWebsite": int(min(time_total.get(u) or 0, 6000)),
            "PageViewsPerVisit": round((page_views.get(u) or 0) / n_visits, 1),
            "EmailOpenedCount": opens.get(u) or 0,
            "VideoWatched": has("video_play"),
            "BrochureDownloaded": has("brochure_dl"),
            "ChatInitiated": has("chat"),
            "PricingPageVisited": has("pricing_view"),
            "TestimonialVisited": has("testimonial_view"),
            "WebinarAttended": has("webinar_view", "webinar_register"),
            "AddedToWishlist": int(has("wishlist_add") or (in_wishlist.get(u) or 0) > 0),
            "AddedToCart": int(has("cart_add") or (in_cart.get(u) or 0) > 0),
            "CheckoutStarted": int(has("checkout_start") or (checkouts.get(u) or 0) > 0),
            "EnquirySubmitted": enquiry,
            "WhatsAppOptIn": p.get("whatsapp_opt_in", 0),
            "DoNotEmail": p.get("do_not_email") or "No",
            "DoNotCall": p.get("do_not_call") or "No",
            "past_purchases": bought.get(u) or 0,
            "_top_course_slug": (top.get(u) or (None,))[0],
        }
    return out


_refresh_lock = threading.Lock()
_refresh_state = {"last": None}


def refresh_scores(reason="refresh", user_ids=None, verbose=True):
    """Re-score everyone's latest contact record with the CURRENT model and how long they have been
    away. Runs by itself (scheduler.py: at start-up, every few minutes, and right after the learning
    loop switches models), so no lead keeps a score from an old model and nobody has to press a button.
    History is logged only when someone changes tier."""
    import time
    from predict import model_info, predict_many
    if not _refresh_lock.acquire(blocking=False):
        return {"status": "busy"}
    started = time.perf_counter()
    try:
        leads = db.fetchall("""SELECT l.id, l.user_id, l.lead_score, l.recommended_action, l.model_version,
                                      l.course_slug FROM leads l
                               WHERE l.id IN (SELECT MAX(id) FROM leads GROUP BY user_id)""")
        if user_ids is not None:
            wanted = {int(u) for u in user_ids}
            leads = [l for l in leads if l["user_id"] in wanted]
        if not leads:
            return {"status": "done", "checked": 0, "updated": 0, "tier_changes": 0}
        raws = build_raw_many([l["user_id"] for l in leads])
        preds = predict_many([raws[l["user_id"]] for l in leads])
        version = model_info().get("version", "fallback")
        spent = {r["user_id"]: r["s"] for r in db.fetchall(
            "SELECT user_id, COALESCE(SUM(price_paid),0) AS s FROM purchases GROUP BY user_id")}
        carts = {}
        for r in db.fetchall("SELECT user_id, course_slug FROM cart ORDER BY added_at ASC"):
            carts[r["user_id"]] = r["course_slug"]              # the latest cart item wins
        avg_price = catalog.average_price()
        updates, history, states = [], [], []
        for lead, (p, score, tier, persona) in zip(leads, preds):
            u = lead["user_id"]
            slug = lead["course_slug"] or carts.get(u) or raws[u]["_top_course_slug"]
            plv = round((spent.get(u) or 0) + (catalog.price_of(slug) or avg_price) * p, 2)
            old_score = lead["lead_score"] if lead["lead_score"] is not None else -1.0
            if abs(score - old_score) < 0.05 and tier == lead["recommended_action"] and lead["model_version"] == version:
                continue
            updates.append((score, p, tier, persona, persona, plv, version, lead["id"], lead["lead_score"]))
            states.append((u, score, persona))
            if lead["recommended_action"] and tier != lead["recommended_action"]:
                why = "model_update" if lead["model_version"] != version else "time_away"
                history.append((lead["id"], u, lead["lead_score"], score, lead["recommended_action"], tier, why))
        con = db.get_conn()
        try:
            # only rows nobody changed since we read them (an event may have re-scored someone meanwhile)
            con.executemany("""UPDATE leads SET lead_score=?, conversion_probability=?, recommended_action=?, persona=?,
                                      customer_segment=?, plv=?, model_version=?, decayed=0
                               WHERE id=? AND lead_score IS ?""", updates)
            con.executemany("""INSERT INTO lead_score_history (lead_id, user_id, old_score, new_score, old_tier, new_tier, reason)
                               VALUES (?,?,?,?,?,?,?)""", history)
            con.executemany("""INSERT INTO live_user_state (user_id, live_score, persona, updated_at)
                               VALUES (?, ?, ?, datetime('now','localtime'))
                               ON CONFLICT(user_id) DO UPDATE SET live_score=excluded.live_score, persona=excluded.persona,
                               updated_at=excluded.updated_at""", states)
            con.commit()
        finally:
            con.close()
        res = {"status": "done", "reason": reason, "checked": len(leads), "updated": len(updates),
               "tier_changes": len(history), "model_version": version,
               "seconds": round(time.perf_counter() - started, 2)}
        _refresh_state["last"] = {**res, "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        if verbose and (updates or reason != "scheduled"):
            print(f"[SCORES] {reason}: {len(leads)} people checked, {len(updates)} re-scored with {version}, "
                  f"{len(history)} changed tier ({res['seconds']} s)")
        return res
    finally:
        _refresh_lock.release()


def last_refresh():
    return _refresh_state["last"]
