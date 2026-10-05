"""
journeys.py — customer-journey analytics from the CRM's own history (standard CRM practice:
lifecycle stages, funnel, journey map, top converting paths, drop-off points) and the
JOURNEY MODEL used by the what-if paths (paths.py).

Lifecycle stages (crm_settings.json), worked out from what the learner did:
    Lead      signed up
    Engaged   video, brochure, testimonials, webinar, or a 2nd visit
    MQL       pricing, wishlist or chat                     (marketing-qualified)
    SQL       enquiry, callback, cart or checkout           (sales-qualified)
    Customer  bought

A journey step = one next-best-action decision: the stage the lead was in, what the team did,
how the learner reacted in the next 3 days (bought / moved to cart-checkout-enquiry / came back
and engaged / clicked / nothing) and whether they bought within the outcome window.

Honesty: rates per (stage, action) are weighted by 1/probability of the logged decision
(inverse-propensity), so they estimate what happens when the team takes that action — not
just what happened to the leads the model happened to pick for it. Small cells are smoothed
towards the stage average.
"""
import json
import time

import numpy as np
import pandas as pd

import database as db
import nba_core as N
import settings

STAGES = ["Lead", "Engaged", "MQL", "SQL", "Customer"]
REACTIONS = ["bought", "advanced", "engaged", "clicked", "none"]
REACTION_LABELS = {"bought": "Bought", "advanced": "Cart / checkout / enquiry", "engaged": "Came back & engaged",
                   "clicked": "Clicked, no visit", "none": "No response"}
ACTION_GROUP = {"none": "Nothing", "email_info": "Email", "email_coupon_10": "Coupon", "email_coupon_20": "Coupon",
                "call": "Call", "whatsapp": "WhatsApp"}
REACTION_DAYS = 3
WINDOW_DAYS = int(settings.S["outcome_window_days"])
SMOOTH = 50.0             # pseudo-count towards the stage average (chosen out of time: 5 over-fits small cells)
_cache = {"at": 0.0, "model": None}


def stage_of(features: dict, score=None, bought=False) -> str:
    f = features or {}
    if bought:
        return "Customer"
    if f.get("EnquirySubmitted") or f.get("AddedToCart") or f.get("CheckoutStarted"):
        return "SQL"
    if f.get("PricingPageVisited") or f.get("AddedToWishlist") or f.get("ChatInitiated"):
        return "MQL"
    if (f.get("VideoWatched") or f.get("BrochureDownloaded") or f.get("TestimonialVisited") or f.get("WebinarAttended")
            or (f.get("TotalVisits") or 1) >= 2):
        return "Engaged"
    return "Lead"


def _read(sql, params=()):
    con = db.get_conn()
    try:
        return pd.read_sql_query(sql, con, params=params)
    finally:
        con.close()


def _first_after(left_users, left_times, right):
    """First right['t'] strictly after each left time, same user (right: user_id, t)."""
    if right.empty or len(left_users) == 0:
        return np.full(len(left_users), np.datetime64("NaT"), dtype="datetime64[ns]")
    L = pd.DataFrame({"user_id": np.asarray(left_users), "_t": pd.to_datetime(left_times).to_numpy(),
                      "_i": np.arange(len(left_users))}).sort_values("_t")
    R = right[["user_id", "t"]].dropna().sort_values("t").rename(columns={"t": "_r"})
    R["_hit"] = R["_r"]
    m = pd.merge_asof(L, R, left_on="_t", right_on="_r", by="user_id", direction="forward", allow_exact_matches=False)
    return m.sort_values("_i")["_hit"].to_numpy()


def steps(since=None, until=None):
    """One row per decision: stage, action, reaction within 3 days, bought within the window, weight."""
    until = until or time.strftime("%Y-%m-%d %H:%M:%S")
    since = since or "0000"
    d = _read("""SELECT id, user_id, action, propensity, base_probability, features_json, created_at AS t, policy
                 FROM nba_decisions WHERE created_at >= ? AND created_at <= ? AND propensity > 0""", (since, until))
    if d.empty:
        return d
    d["t"] = pd.to_datetime(d["t"])
    feats = [json.loads(s) if s else {} for s in d["features_json"]]
    d["stage"] = [stage_of(f, (b or 0) * 100) for f, b in zip(feats, d["base_probability"])]
    d["tier"] = [N_tier((b or 0) * 100) for b in d["base_probability"]]
    buys = _read("SELECT user_id, purchased_at AS t FROM purchases WHERE purchased_at <= ?", (until,))
    buys["t"] = pd.to_datetime(buys["t"])
    adv = _read("""SELECT user_id, created_at AS t FROM behaviour_events WHERE created_at <= ?
                   AND event_type IN ('cart_add','checkout_start','enquiry_submit')""", (until,))
    adv["t"] = pd.to_datetime(adv["t"])
    eng = _read("""SELECT user_id, created_at AS t FROM behaviour_events WHERE created_at <= ?
                   AND event_type IN ('page_view','video_play','brochure_dl','pricing_view','testimonial_view',
                                      'webinar_register','chat','wishlist_add')""", (until,))
    eng["t"] = pd.to_datetime(eng["t"])
    clk = _read("SELECT user_id, first_clicked_at AS t FROM email_sends WHERE first_clicked_at IS NOT NULL AND first_clicked_at <= ?",
                (until,))
    clk["t"] = pd.to_datetime(clk["t"])
    u, t = d["user_id"].to_numpy(), d["t"].to_numpy()
    soon = np.timedelta64(REACTION_DAYS, "D")
    window = np.timedelta64(WINDOW_DAYS, "D")
    fb, fa, fe, fc = (_first_after(u, t, x) for x in (buys, adv, eng, clk))
    with np.errstate(invalid="ignore"):
        b3 = ~pd.isna(fb) & (fb <= t + soon)
        a3 = ~pd.isna(fa) & (fa <= t + soon)
        e3 = ~pd.isna(fe) & (fe <= t + soon)
        c3 = ~pd.isna(fc) & (fc <= t + soon)
        d["bought"] = (~pd.isna(fb) & (fb <= t + window)).astype(int)
        d["matured"] = d["bought"].astype(bool) | (t <= np.datetime64(pd.Timestamp(until)) - window)
    d["reaction"] = np.select([b3, a3, e3, c3], ["bought", "advanced", "engaged", "clicked"], default="none")
    d["w"] = 1.0 / d["propensity"].clip(lower=1e-3)
    d["group"] = d["action"].map(ACTION_GROUP).fillna(d["action"])
    return d.drop(columns=["features_json"])


def N_tier(score):
    import ml_features as F
    return F.tier_for(score)


def model(max_age_seconds=300):
    """The journey model built from all history so far (cached for a few minutes)."""
    if _cache["model"] is not None and time.time() - _cache["at"] < max_age_seconds:
        return _cache["model"]
    out = model_from(steps())
    _cache.update(at=time.time(), model=out)
    return out


def model_from(d):
    """The journey model: per (stage, action) reaction mix and buy rate, IPS-weighted, smoothed."""
    out = {"stages": {}, "decisions": int(len(d)), "built_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    if not d.empty:
        m = d[d["matured"]]
        glob = {r: float((m["reaction"] == r).mean()) if len(m) else 0.0 for r in REACTIONS}
        glob_buy = float(m["bought"].mean()) if len(m) else 0.0
        for stage in STAGES[:-1]:
            sm = m[m["stage"] == stage]
            if len(sm):
                sw = sm["w"].to_numpy()
                base = {r: float((sw * (sm["reaction"] == r)).sum() / sw.sum()) for r in REACTIONS}
                base_buy = float((sw * sm["bought"]).sum() / sw.sum())
            else:
                base, base_buy = glob, glob_buy
            cells = {}
            for a in N.ACTION_LIST:
                c = sm[sm["action"] == a]
                n = int(len(c))
                if n:
                    w = c["w"].to_numpy()
                    w = w * n / w.sum()                      # effective counts
                    react = {r: float(((w * (c["reaction"] == r)).sum() + SMOOTH * base[r]) / (w.sum() + SMOOTH))
                             for r in REACTIONS}
                    buy = float(((w * c["bought"]).sum() + SMOOTH * base_buy) / (w.sum() + SMOOTH))
                else:
                    react, buy = dict(base), base_buy
                cells[a] = {"n": n, "reactions": react, "buy14": buy}
            out["stages"][stage] = {"n": int(len(sm)), "buy14": base_buy, "actions": cells}
    return out


# ── dashboard: journey map, funnel, top paths, drop-offs ─────────────────────
def summary(days=180, tier=None):
    until = time.strftime("%Y-%m-%d %H:%M:%S")
    since = (pd.Timestamp(until) - pd.Timedelta(days=int(days))).strftime("%Y-%m-%d %H:%M:%S")
    d = steps(since, until)
    out = {"days": days, "tier": tier, "decisions": 0, "sankey": {"nodes": [], "links": []}, "top_paths": [],
           "funnel": funnel(since, until), "dropoffs": [], "reaction_labels": REACTION_LABELS}
    if d.empty:
        return out
    if tier:
        d = d[d["tier"] == tier]
    m = d[d["matured"]].copy()
    out["decisions"] = int(len(d))
    out["with_outcome"] = int(len(m))
    if m.empty:
        return out
    m["outcome"] = np.where(m["bought"] == 1, "Bought", "Not (yet)")
    layers = [("stage", [s for s in STAGES[:-1] if (m["stage"] == s).any()]),
              ("group", [g for g in ["Nothing", "Email", "Coupon", "Call", "WhatsApp"] if (m["group"] == g).any()]),
              ("reaction", [r for r in REACTIONS if (m["reaction"] == r).any()]),
              ("outcome", [o for o in ["Bought", "Not (yet)"] if (m["outcome"] == o).any()])]
    nodes, index = [], {}
    for col, values in layers:
        for v in values:
            index[(col, v)] = len(nodes)
            nodes.append({"name": REACTION_LABELS.get(v, v) if col == "reaction" else v, "layer": col})
    links = []
    for (c1, _), (c2, _) in zip(layers[:-1], layers[1:]):
        g = m.groupby([c1, c2]).agg(n=("id", "size"), bought=("bought", "sum")).reset_index()
        for _, r in g.iterrows():
            links.append({"source": index[(c1, r[c1])], "target": index[(c2, r[c2])], "value": int(r["n"]),
                          "conversion": round(float(r["bought"]) / float(r["n"]), 3)})
    out["sankey"] = {"nodes": nodes, "links": links}
    # top converting paths (stage → action → reaction), honest (IPS-weighted) and raw rates
    paths = []
    for (st, a, rc), g in m.groupby(["stage", "action", "reaction"]):
        if len(g) < 15 or rc == "bought":          # 'bought within 3 days' is the outcome itself, not a path
            continue
        w = g["w"].to_numpy()
        paths.append({"stage": st, "action": a, "action_label": N.ACTIONS[a]["label"], "reaction": rc,
                      "reaction_label": REACTION_LABELS[rc], "n": int(len(g)),
                      "conversion": round(float(g["bought"].mean()), 3),
                      "conversion_weighted": round(float((w * g["bought"]).sum() / w.sum()), 3)})
    paths.sort(key=lambda p: (-p["conversion"], -p["n"]))
    out["top_paths"] = paths[:12]
    # action effect per stage (what the team's step adds over doing nothing, IPS-weighted)
    effects = []
    for st, g in m.groupby("stage"):
        base = g[g["action"] == "none"]
        if len(base) < 10:
            continue
        bw = base["w"].to_numpy()
        b_rate = float((bw * base["bought"]).sum() / bw.sum())
        for a, ga in g.groupby("action"):
            if a == "none" or len(ga) < 10:
                continue
            w = ga["w"].to_numpy()
            rate = float((w * ga["bought"]).sum() / w.sum())
            effects.append({"stage": st, "action": a, "label": N.ACTIONS[a]["label"], "n": int(len(ga)),
                            "rate": round(rate, 3), "nothing_rate": round(b_rate, 3), "lift": round(rate - b_rate, 3)})
    out["action_effects"] = effects
    out["dropoffs"] = dropoffs(out["funnel"])
    return out


def funnel(since, until):
    """How many people reached each lifecycle stage (people who signed up in the period)."""
    users = _read("""SELECT id AS user_id, created_at FROM users WHERE is_verified=1 AND created_at >= ? AND created_at <= ?""",
                  (since, until))
    if users.empty:
        return {"stages": [{"stage": s, "people": 0} for s in STAGES]}
    ids = set(users["user_id"])
    ev = _read("""SELECT user_id, event_type, COUNT(*) AS n, MIN(created_at) AS first FROM behaviour_events
                  WHERE created_at <= ? GROUP BY user_id, event_type""", (until,))
    ev = ev[ev["user_id"].isin(ids)]
    sess = _read("SELECT user_id, COUNT(*) AS visits FROM user_sessions GROUP BY user_id")
    sess = sess[sess["user_id"].isin(ids)].set_index("user_id")["visits"].to_dict()
    bought = set(_read("SELECT DISTINCT user_id FROM purchases WHERE purchased_at <= ?", (until,))["user_id"]) & ids
    by_user = {}
    for r in ev.itertuples():
        by_user.setdefault(r.user_id, set()).add(r.event_type)
    reached = {s: 0 for s in STAGES}
    for uid in ids:
        e = by_user.get(uid, set())
        sql = bool(e & {"enquiry_submit", "cart_add", "checkout_start"})
        mql = sql or bool(e & {"pricing_view", "wishlist_add", "chat"})
        eng = mql or bool(e & {"video_play", "brochure_dl", "testimonial_view", "webinar_register"}) or sess.get(uid, 0) >= 2
        cust = uid in bought
        reached["Lead"] += 1
        reached["Engaged"] += int(eng or cust)
        reached["MQL"] += int(mql or cust)
        reached["SQL"] += int(sql or cust)
        reached["Customer"] += int(cust)
    out = []
    prev = None
    for s in STAGES:
        item = {"stage": s, "people": reached[s]}
        if prev:
            item["from_previous"] = round(reached[s] / prev, 3) if prev else None
        out.append(item)
        prev = reached[s]
    return {"stages": out, "signed_up": len(ids)}


def dropoffs(f):
    st = f.get("stages") or []
    out = []
    for a, b in zip(st[:-1], st[1:]):
        if a["people"]:
            lost = a["people"] - b["people"]
            out.append({"from": a["stage"], "to": b["stage"], "lost": lost, "lost_share": round(lost / a["people"], 3)})
    out.sort(key=lambda x: -x["lost_share"])
    return out


# ── SALES PIPELINE BOARD ─────────────────────────────────────────────────────────
# Every lead in its lifecycle stage, worked out live from what the learner has done (the same rules
# as stage_of()), unless someone on the team moved the card by hand (pipeline_overrides). Purchases
# always win: a buyer is a Customer.
_SQL_EVENTS = ("cart_add", "checkout_start", "enquiry_submit")
_MQL_EVENTS = ("pricing_view", "wishlist_add", "chat")
_ENGAGED_EVENTS = ("video_play", "brochure_dl", "testimonial_view", "webinar_view", "webinar_register")


def _in(xs):
    return "(" + ",".join(f"'{x}'" for x in xs) + ")"


def pipeline(limit=40, search=None, include_simulated=True):
    """Board data: one column per lifecycle stage with its leads (highest score first)."""
    import catalog
    rows = db.fetchall(f"""
        WITH ev AS (
            SELECT user_id,
                   MAX(event_type IN {_in(_SQL_EVENTS)}) AS sq,
                   MAX(event_type IN {_in(_MQL_EVENTS)}) AS mq,
                   MAX(event_type IN {_in(_ENGAGED_EVENTS)}) AS en,
                   COUNT(DISTINCT session_id) AS visits,
                   MAX(created_at) AS last_seen
            FROM behaviour_events GROUP BY user_id),
        nb AS (SELECT user_id, action, created_at FROM nba_decisions
               WHERE id IN (SELECT MAX(id) FROM nba_decisions GROUP BY user_id))
        SELECT l.id AS lead_id, l.user_id, u.name, u.email, l.lead_score, l.recommended_action AS tier,
               l.course_slug, l.course_type, l.created_at AS scored_at,
               COALESCE(ev.sq, 0) AS sq, COALESCE(ev.mq, 0) AS mq, COALESCE(ev.en, 0) AS en,
               COALESCE(ev.visits, 0) AS visits, ev.last_seen,
               c.user_id IS NOT NULL AS in_cart, w.user_id IS NOT NULL AS in_wishlist,
               k.user_id IS NOT NULL AS checkout, e.user_id IS NOT NULL AS enquiry,
               p.user_id IS NOT NULL AS bought, p.first_purchase,
               o.stage AS override_stage, o.moved_at, o.note AS override_note,
               nb.action AS last_action, nb.created_at AS last_action_at
        FROM leads l JOIN users u ON u.id = l.user_id
        LEFT JOIN ev ON ev.user_id = l.user_id
        LEFT JOIN (SELECT DISTINCT user_id FROM cart) c ON c.user_id = l.user_id
        LEFT JOIN (SELECT DISTINCT user_id FROM wishlist) w ON w.user_id = l.user_id
        LEFT JOIN (SELECT DISTINCT user_id FROM checkout_sessions) k ON k.user_id = l.user_id
        LEFT JOIN (SELECT DISTINCT user_id FROM leads WHERE trigger_reason = 'enquiry') e ON e.user_id = l.user_id
        LEFT JOIN (SELECT user_id, MIN(purchased_at) AS first_purchase FROM purchases GROUP BY user_id) p
               ON p.user_id = l.user_id
        LEFT JOIN pipeline_overrides o ON o.user_id = l.user_id
        LEFT JOIN nb ON nb.user_id = l.user_id
        WHERE l.id IN (SELECT MAX(id) FROM leads GROUP BY user_id)""")
    q = (search or "").strip().lower()
    prices = {}
    columns = {s: [] for s in STAGES}
    for r in rows:
        simulated = (r["email"] or "").endswith("@demo.xeducation.test")
        if simulated and not include_simulated:
            continue
        if q and q not in (r["name"] or "").lower() and q not in (r["email"] or "").lower():
            continue
        if r["bought"]:
            auto = "Customer"
        elif r["sq"] or r["in_cart"] or r["checkout"] or r["enquiry"]:
            auto = "SQL"
        elif r["mq"] or r["in_wishlist"]:
            auto = "MQL"
        elif r["en"] or (r["visits"] or 0) >= 2:
            auto = "Engaged"
        else:
            auto = "Lead"
        stage = auto if (auto == "Customer" or not r["override_stage"]) else r["override_stage"]
        slug = r["course_slug"]
        if slug not in prices:
            c = catalog.get_course(slug) if slug else None
            prices[slug] = float(c["price"]) if c else None
        p = max(0.0, min(1.0, (r["lead_score"] or 0) / 100.0))
        card = {"user_id": r["user_id"], "lead_id": r["lead_id"], "name": r["name"], "email": r["email"],
                "course": r["course_type"], "course_slug": slug, "score": round(r["lead_score"] or 0, 1),
                "tier": r["tier"], "stage": stage, "auto_stage": auto,
                "moved_by_hand": bool(r["override_stage"]) and auto != "Customer",
                "override_note": r["override_note"], "moved_at": r["moved_at"],
                "last_seen": r["last_seen"], "last_action": r["last_action"],
                "last_action_label": N.ACTIONS.get(r["last_action"], {}).get("label") if r["last_action"] else None,
                "control_group": settings.in_global_control(r["user_id"]), "simulated": simulated,
                "customer_since": r["first_purchase"],
                "expected_value": round(p * prices[slug], 0) if (prices[slug] and stage != "Customer") else None}
        columns[stage].append(card)
    out = []
    for s in STAGES:
        cards = columns[s]
        cards.sort(key=lambda c: (-(c["score"] or 0), c["user_id"]))
        ev = sum(c["expected_value"] or 0 for c in cards)
        out.append({"stage": s, "about": (settings.S.get("lifecycle_stages") or {}).get(s),
                    "count": len(cards), "expected_value": round(ev, 0), "moved_by_hand": sum(c["moved_by_hand"] for c in cards),
                    "cards": cards[:max(1, int(limit))]})
    return {"columns": out, "stages": STAGES, "generated_at": time.strftime("%Y-%m-%d %H:%M:%S")}
