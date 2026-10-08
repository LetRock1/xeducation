"""
paths.py — WHAT-IF PATHS for one lead: "if the team does this now, the learner will probably do
that in the next 3 days, and then the best next step is ...".

    step 1   every step the team may take now, with the SAME numbers and the SAME pick as the
             lead page's recommendation (nba.recommend_now -> nba.evaluate, the calculation behind
             every automatic decision). So the what-if paths and "Recommended action" always agree.
    react    how learners in the same lifecycle stage reacted to that step in the next 3 days, from
             the CRM's own history (journeys.py, inverse-propensity weighted): bought / cart-
             checkout-enquiry / came back and engaged / clicked / nothing. When there is too little
             history for the stage and step, the page says so instead of showing a guess.
    step 2   for each likely reaction, the best follow-up for the learner as they would then be
             (their features updated by the reaction, re-scored by the same models and rules).

Customers get no paths: the CRM does not try to sell a course someone already owns.
"""
import catalog
import database as db
import journeys as J
import nba
import nba_core as N
from predict import predict_lead

STEP_REACTIONS = ["advanced", "engaged", "clicked", "none"]
MIN_HISTORY = 30            # decisions needed before a reaction mix is shown
STAGE_LABELS = {"Lead": "New lead", "Engaged": "Engaged", "MQL": "Interested (MQL)",
                "SQL": "Ready to buy (SQL)", "Customer": "Customer"}


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


def _reaction_mix(jm, stage, action):
    """(reaction probabilities, evidence) from history, or (None, evidence) when there is too little."""
    st = (jm.get("stages") or {}).get(stage) or {}
    cell = (st.get("actions") or {}).get(action) or {}
    if (cell.get("n") or 0) >= MIN_HISTORY:
        return cell["reactions"], {"decisions": cell["n"], "basis": f"{STAGE_LABELS.get(stage, stage)} leads after this step"}
    if (st.get("n") or 0) >= MIN_HISTORY:
        # this step was rarely taken for this stage: the stage's own mix (all steps), said plainly
        mix = {}
        acts = st.get("actions") or {}
        tot = sum((c.get("n") or 0) for c in acts.values())
        if tot:
            for r in J.REACTIONS:
                mix[r] = sum((c.get("n") or 0) * c["reactions"].get(r, 0) for c in acts.values()) / tot
            return mix, {"decisions": int(tot), "basis": f"{STAGE_LABELS.get(stage, stage)} leads after any step "
                                                         f"(only {cell.get('n') or 0} after this one)"}
    return None, {"decisions": int(cell.get("n") or 0), "basis": "not enough history yet"}


def plan(user_id, depth=2, course_slug=None):
    now = nba.recommend_now(user_id)
    if now is None:
        return None
    lead_info = {"user_id": user_id, "name": now["name"], "customer": now["customer"],
                 "control_group": now["control_group"]}
    if now.get("recommendation") is None:
        return {"lead": lead_info, "customer": True, "steps": [], "best": None, "purchases": now["purchases"],
                "summary": now.get("message"), "note": "What-if paths are for people who have not bought yet."}

    x0 = now["features"]
    price = float(now["course"]["price"])
    stage = J.stage_of(x0)
    jm = J.model()
    profile = db.get_profile(user_id) or {}
    has_phone = bool((profile.get("phone") or "").strip())
    best = now["recommendation"]["action"]
    by_action = {o["action"]: o for o in now["options"]}
    allowed = [o["action"] for o in now["options"] if not o["blocked"]] or ["none"]

    # the learner after each possible reaction, and the best follow-up then (same rules and models)
    after = {}
    for r in STEP_REACTIONS:
        x1 = _apply(x0, r)
        p1 = predict_lead(dict(x1, away_days=0))
        p1["raw"] = {"past_purchases": len(now["purchases"])}
        ev1 = nba.evaluate(user_id, p1, now["course"]["slug"])
        after[r] = {"score": p1["lead_score"], "tier": p1["recommended_action"], "stage": J.stage_of(x1),
                    "ev": ev1, "p_none": ev1["values"]["none"]["p_convert"]}

    def follow_up(r, first_discount):
        """Best next step after reaction r (a second discount is not stacked on the first)."""
        ev1 = after[r]["ev"]
        opts = []
        for o in ev1["options"]:
            if o["blocked"]:
                continue
            disc = max(first_discount, o["discount"])
            value = o["p_convert"] * price * (1 - disc) - o["cost"]
            opts.append({"action": o["action"], "label": o["label"], "p_buy": o["p_convert"],
                         "gain": value - ev1["values"]["none"]["p_convert"] * price * (1 - first_discount)})
        opts.sort(key=lambda x: (-x["gain"], x["action"] != "none"))
        top = opts[0] if opts else {"action": "none", "label": N.ACTIONS["none"]["label"],
                                    "p_buy": after[r]["p_none"], "gain": 0.0}
        if top["gain"] <= 0:
            top = next((o for o in opts if o["action"] == "none"), top)
        return top

    steps = []
    for a1 in allowed:
        o = by_action[a1]
        mix, evidence = _reaction_mix(jm, stage, a1)
        reactions = []
        if mix:
            for r in STEP_REACTIONS + ["bought"]:
                pr = float(mix.get(r, 0.0))
                if r == "clicked" and N.ACTIONS[a1]["channel"] not in ("email", "whatsapp"):
                    pr = 0.0
                if pr <= 0.004:
                    continue
                if r == "bought":
                    reactions.append({"reaction": r, "label": J.REACTION_LABELS[r], "prob": pr, "next": None,
                                      "best_next": None})
                    continue
                nxt = follow_up(r, o["discount"])
                reactions.append({"reaction": r, "label": J.REACTION_LABELS[r], "prob": pr,
                                  "next": {"score": after[r]["score"], "tier": after[r]["tier"],
                                           "stage": after[r]["stage"],
                                           "stage_label": STAGE_LABELS.get(after[r]["stage"], after[r]["stage"])},
                                  "best_next": nxt})
            total = sum(x["prob"] for x in reactions) or 1.0
            for x in reactions:
                x["prob"] = x["prob"] / total
            reactions.sort(key=lambda x: -x["prob"])
        steps.append({"action": a1, "label": o["label"], "cost": o["cost"], "discount": o["discount"],
                      "p_buy_step": o["p_convert"], "uplift": o["uplift"], "extra_profit": o["incremental_profit"],
                      "reactions": reactions, "evidence": {**evidence, "stage": stage,
                                                           "stage_label": STAGE_LABELS.get(stage, stage)}})
    # same order as the recommendation: the pick first, then by extra profit now
    steps.sort(key=lambda s: (s["action"] != best, -s["extra_profit"]))

    rec = now["recommendation"]
    first = steps[0] if steps else None
    summary = f"Recommended now: {rec['label']} — {rec['why']}"
    if first and first["reactions"]:
        likely = [x for x in first["reactions"] if x["reaction"] != "bought"][:2]
        if likely:
            summary += " Then: " + "; ".join(
                f"if they {'come back' if x['reaction'] == 'engaged' else 'add to cart or enquire' if x['reaction'] == 'advanced' else 'click' if x['reaction'] == 'clicked' else 'do nothing'}"
                f" ({x['prob'] * 100:.0f}%): {x['best_next']['label']}" for x in likely) + "."
    blocked = {o["action"]: o["blocked"] for o in now["options"] if o["blocked"]}
    return {"lead": {**lead_info, "score": now["score"], "tier": now["tier"], "stage": stage,
                     "stage_label": STAGE_LABELS.get(stage, stage), "probability": now["probability"],
                     "course": now["course"]["title"], "price": price, "away_days": now.get("away_days")},
            "steps": steps, "blocked": blocked, "best": best, "recommendation": rec, "summary": summary,
            "history": {"decisions": jm.get("decisions", 0),
                        "stage_decisions": ((jm.get("stages") or {}).get(stage) or {}).get("n", 0),
                        "built_at": jm.get("built_at"), "min_history": MIN_HISTORY},
            "note": ("Step 1 uses the same numbers and the same rule as the Recommended action tab (highest extra "
                     "profit now). Reactions are what learners in the same stage did in the next 3 days after the same "
                     "step in the CRM's history, weighted by how likely each logged decision was. Estimates, not "
                     "guarantees.")}
