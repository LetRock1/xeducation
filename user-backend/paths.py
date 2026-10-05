"""
paths.py — WHAT-IF PATHS for one lead: "if the team does this, the learner will probably do
that, and then the best next step is ...", two (optionally three) team steps ahead.

    step 1   every action the team may take now (consent, phone, call capacity respected)
    react    how learners in the same lifecycle stage reacted to that action in the next
             3 days, from the CRM's history (journeys.py, inverse-propensity weighted):
             bought / cart-checkout-enquiry / came back and engaged / clicked / nothing
    step 2   for each likely reaction, the best follow-up for the learner as they would
             then be (their features updated by the reaction, re-scored by the lead model)

Chances of buying come from the same models the decision engine uses: the lead model
(P(buy | no action)) and the next-best-action uplift model (P(buy | action)), so the tree
is personal to this lead; the reaction mix is what history shows for similar leads.
The best path maximises expected profit = P(buy) x price x (1 - discount) - costs,
looking at the best follow-up after each likely reaction (a two-step look-ahead).

Honesty: reactions are averages for leads in the same stage, and a path's chance of
buying is an estimate from the models — the paths show where the evidence points, not a
guarantee. Every node says how many past decisions it is based on.
"""
import catalog
import database as db
import journeys as J
import ml_features as F
import nba
import nba_core as N
from predict import predict_lead
from scoring import build_raw, interest_slug

STEP_REACTIONS = ["advanced", "engaged", "clicked", "none"]


def _apply(features: dict, reaction: str) -> dict:
    """The lead as they would be after this reaction (what the tracker would record)."""
    f = dict(features)
    if reaction == "none":
        return f
    f["TotalVisits"] = min(f.get("TotalVisits", 1) + 1, 30)
    if reaction == "clicked":
        f["EmailOpenedCount"] = min(f.get("EmailOpenedCount", 0) + 1, 10)
        f["TotalTimeOnWebsite"] = min(f.get("TotalTimeOnWebsite", 0) + 90, 6000)
    elif reaction == "engaged":
        f["TotalTimeOnWebsite"] = min(f.get("TotalTimeOnWebsite", 0) + 240, 6000)
        for flag in ("VideoWatched", "PricingPageVisited", "BrochureDownloaded", "TestimonialVisited"):
            if not f.get(flag):
                f[flag] = 1
                break
    elif reaction == "advanced":
        f["TotalTimeOnWebsite"] = min(f.get("TotalTimeOnWebsite", 0) + 300, 6000)
        f["PricingPageVisited"] = 1
        f["AddedToCart"] = 1
    return f


def _score(features):
    p = predict_lead(dict(features))
    return p["conversion_probability"], p["lead_score"], p["recommended_action"]


def _blocked(features, has_phone):
    b = N.eligible(features, has_phone)
    if nba._calls_today() >= nba.DAILY_CALL_CAPACITY and not b["call"]:
        b["call"] = "today's call capacity is used up"
    return b


def _value(p, price, discount, cost):
    return p * price * (1 - discount) - cost


def plan(user_id, depth=2, course_slug=None):
    user = db.get_user_by_id(user_id)
    if not user:
        return None
    slug = course_slug or interest_slug(user_id)
    price = float(catalog.price_of(slug) or catalog.average_price())
    raw = build_raw(user_id, course=slug)
    pred = predict_lead(raw)
    x0 = pred["features"]
    profile = db.get_profile(user_id) or {}
    has_phone = bool((profile.get("phone") or "").strip())
    bought = (raw.get("past_purchases") or 0) > 0
    stage = J.stage_of(x0, bought=bought)
    jm = J.model()
    cells = (jm["stages"].get(stage) or {}).get("actions", {}) if stage != "Customer" else {}
    blocked = _blocked(x0, has_phone)
    allowed = [a for a in N.ACTION_LIST if not blocked[a]] or ["none"]
    p0 = nba.action_probabilities(x0, pred["conversion_probability"])     # P(buy within 14 days | x0, a)

    # the learner after each possible reaction (independent of which action caused it)
    after = {}
    for r in STEP_REACTIONS:
        x1 = _apply(x0, r)
        prob1, score1, tier1 = _score(x1)
        after[r] = {"x": x1, "base": prob1, "score": score1, "tier": tier1, "stage": J.stage_of(x1),
                    "p": nba.action_probabilities(x1, prob1)}

    def best_next(r, first_discount):
        a = after[r]
        allowed2 = [k for k in N.ACTION_LIST if not _blocked(a["x"], has_phone)[k]] or ["none"]
        opts = []
        for k in allowed2:
            spec = N.ACTIONS[k]
            opts.append({"action": k, "label": spec["label"], "p_buy": a["p"][k],
                         "value": _value(a["p"][k], price, max(first_discount, spec["discount"]), spec["cost_inr"])})
        opts.sort(key=lambda o: -o["value"])
        return opts

    steps = []
    for a1 in allowed:
        spec = N.ACTIONS[a1]
        cell = cells.get(a1) or {"n": 0, "reactions": {"bought": 0.0, "advanced": 0.1, "engaged": 0.2,
                                                       "clicked": 0.0, "none": 0.7}, "buy14": p0[a1]}
        react = cell["reactions"]
        share3 = react.get("bought", 0.0) / max(cell["buy14"], 0.01)    # share of purchases in the first 3 days
        q1 = min(p0[a1], p0[a1] * min(share3, 1.0))
        rest = sum(react[r] for r in STEP_REACTIONS) or 1.0
        reactions, exp_profit, p_path = [], q1 * price * (1 - spec["discount"]), q1
        for r in STEP_REACTIONS:
            pr = (1 - q1) * react[r] / rest
            if r == "clicked" and spec["channel"] not in ("email", "whatsapp"):
                pr = 0.0
            opts = best_next(r, spec["discount"])
            nxt = opts[0]
            exp_profit += pr * nxt["value"]
            p_path += pr * nxt["p_buy"]
            reactions.append({"reaction": r, "label": J.REACTION_LABELS[r], "prob": pr,
                              "next": {"score": after[r]["score"], "tier": after[r]["tier"], "stage": after[r]["stage"]},
                              "best_next": nxt, "options": opts[:3]})
        exp_profit -= spec["cost_inr"]
        reactions = [r for r in reactions if r["prob"] > 0.004]
        reactions.sort(key=lambda r: -r["prob"])
        steps.append({"action": a1, "label": spec["label"], "cost": spec["cost_inr"], "discount": spec["discount"],
                      "p_buy_step": p0[a1], "early_buy": q1, "reactions": reactions, "p_buy_path": p_path,
                      "expected_profit": exp_profit,
                      "evidence": {"stage": stage, "decisions": cell["n"], "buy_rate": cell["buy14"]}})
    steps.sort(key=lambda s: -s["expected_profit"])
    base = next((s for s in steps if s["action"] == "none"), None)
    for s in steps:
        s["gain_vs_nothing"] = s["expected_profit"] - base["expected_profit"] if base else None
    best = steps[0] if steps else None
    if best and depth >= 3 and best["reactions"]:
        r = next((x for x in best["reactions"] if x["reaction"] != "none"), best["reactions"][0])
        a2 = r["best_next"]["action"]
        cell2 = ((jm["stages"].get(after[r["reaction"]]["stage"]) or {}).get("actions") or {}).get(a2)
        if cell2:
            r2 = max(STEP_REACTIONS, key=lambda k: cell2["reactions"][k] if k != "none" else -1)
            x2 = _apply(after[r["reaction"]]["x"], r2)
            prob2, score2, tier2 = _score(x2)
            p2 = nba.action_probabilities(x2, prob2)
            allowed3 = [k for k in N.ACTION_LIST if not _blocked(x2, has_phone)[k]] or ["none"]
            a3 = max(allowed3, key=lambda k: _value(p2[k], price, N.ACTIONS[k]["discount"], N.ACTIONS[k]["cost_inr"]))
            best["then"] = {"after": r["reaction"], "step2": a2, "reaction2": r2,
                            "reaction2_label": J.REACTION_LABELS[r2], "step3": a3, "step3_label": N.ACTIONS[a3]["label"],
                            "p_buy": p2[a3], "score": score2, "tier": tier2}
    summary = None
    if best:
        def _reaction_text(r):
            return {"none": "there's no response", "engaged": "they come back", "advanced": "they add to cart or enquire",
                    "clicked": "they click"}.get(r["reaction"], r["label"].lower())
        follow = "; ".join(f"if {_reaction_text(r)} ({r['prob']*100:.0f}%): {r['best_next']['label'].lower()}"
                           for r in best["reactions"][:2])
        if best["action"] == "none":
            summary = (f"Best now: wait — {best['p_buy_step']*100:.0f}% chance they buy without a nudge; no action "
                       f"pays for itself yet. Then {follow}.")
        else:
            gain = best.get("gain_vs_nothing")
            summary = (f"Best path: {best['label'].lower()}, then {follow}. Chance of buying on this path "
                       f"{best['p_buy_path']*100:.0f}%"
                       + (f" (waiting now, then the best next step: {base['p_buy_path']*100:.0f}%; nobody contacting "
                          f"them at all: {pred['conversion_probability']*100:.0f}%)" if base else "")
                       + (f", about ₹{gain:,.0f} more than waiting." if base and gain else "."))
    return {"lead": {"user_id": user_id, "name": user["name"], "score": pred["lead_score"],
                     "tier": pred["recommended_action"], "stage": stage, "probability": pred["conversion_probability"],
                     "course": catalog.title_of(slug) if slug else None, "price": price},
            "steps": steps, "blocked": {a: blocked[a] for a in N.ACTION_LIST if blocked[a]},
            "best": best["action"] if best else None, "summary": summary,
            "history": {"decisions": jm.get("decisions", 0), "stage_decisions": (jm["stages"].get(stage) or {}).get("n", 0),
                        "built_at": jm.get("built_at")},
            "note": ("Chances come from the lead model and the next-best-action model for this person; reactions are "
                     "what history shows for leads in the same stage (weighted by how likely each logged decision "
                     "was). Estimates, not guarantees.")}
