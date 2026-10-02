"""
=================================================================
 EXPERIMENT 4 — "How to convert" tips: are they valid, small, actionable — and causal?
=================================================================
 recourse.py proposes, for each lead, the cheapest set of at most 3 realistic
 next steps that the lead model predicts would lift the lead into the next
 tier. This experiment measures the standard counterfactual-explanation
 properties on 3,000 fresh simulated leads below the top tier:

   coverage   share of leads for which a plan reaching the next tier exists
   sparsity   number of steps in the plan;  effort = sum of step efforts
   actionability  share of plans that only use things sales/the learner can
              do. Ours is 100 % by construction; for comparison an
              UNCONSTRAINED search (allowed to "change" occupation, lead
              source, city, age, consent ... at the same cost, like a plain
              distance-based counterfactual) shows how often a generic
              method would give impossible advice.
   one-size   the same plan for everyone (the 3 steps with the largest
              average predicted gain) — what a static playbook does.
   causal gap the simulator knows the TRUE effect of each step (the
              generator's structural equation, holding the person's hidden
              intent fixed). Predicted gain vs true gain shows how much of
              a correlational tip's promise is real — the honest reason the
              system's causal decisions come from the separately learned,
              randomized next-best-action model, not from these tips.

 Run (after train-model.bat):  python ml/experiments/recourse_eval.py   (~2 min)
 Writes ml/results/recourse_eval.{json,md}
=================================================================
"""
import json
import os
import sys
import time
from itertools import combinations

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ML = os.path.dirname(HERE)
BACKEND = os.path.join(ML, "..", "user-backend")
sys.path.insert(0, ML)
sys.path.insert(0, BACKEND)
import generate_dataset as G          # noqa: E402
import ml_features as F               # noqa: E402
import recourse as R                  # noqa: E402
from predict import _probs            # noqa: E402

RESULTS = os.path.join(ML, "results")
N_EVAL, N_UNCONSTRAINED = 3000, 600

# Direct effects on the log-odds of buying in the generator's structural equation
# (ml/generate_dataset.py, section D). Verified against the data below.
TRUE_DIRECT = {"VideoWatched": 0.30, "PricingPageVisited": 0.35, "TestimonialVisited": 0.20,
               "BrochureDownloaded": 0.45, "ChatInitiated": 0.40, "WebinarAttended": 0.60,
               "AddedToWishlist": 0.30, "AddedToCart": 0.75, "CheckoutStarted": 0.95,
               "EnquirySubmitted": 0.85, "WhatsAppOptIn": 0.25}

# attributes a generic counterfactual search could "change" but nobody can act on
IMMUTABLE = ["CurrentOccupation", "LeadSource", "LeadOrigin", "Specialization", "City",
             "AgeBracket", "Country", "HowDidYouHear", "DoNotEmail", "DoNotCall"]


def true_logit_delta(before, after):
    d = sum(c * (after[k] - before[k]) for k, c in TRUE_DIRECT.items())
    d += 0.25 * (np.log(max(after["TotalVisits"], 1)) - np.log(max(before["TotalVisits"], 1)))
    d += 0.18 * (np.log1p(after["TotalTimeOnWebsite"] / 60) - np.log1p(before["TotalTimeOnWebsite"] / 60))
    d += 0.10 * (min(after["EmailOpenedCount"], 4) - min(before["EmailOpenedCount"], 4))
    return d


def verify_structural_coefficients(raw):
    """Regress logit(p_true) on the generator's terms; the recovered behaviour coefficients must match
    TRUE_DIRECT (residual = the generator's 'luck' noise, sd 0.45)."""
    lp = np.log(raw["_p_true"] / (1 - raw["_p_true"]))
    X = pd.DataFrame({k: raw[k] for k in TRUE_DIRECT})
    X["log_visits"] = np.log(raw["TotalVisits"].clip(lower=1))
    X["log_time"] = np.log1p(raw["TotalTimeOnWebsite"] / 60)
    X["opens4"] = raw["EmailOpenedCount"].clip(upper=4)
    X["intent"] = raw["_intent"]
    X["DoNotEmail"], X["DoNotCall"] = raw["DoNotEmail"], raw["DoNotCall"]
    X = pd.concat([X, pd.get_dummies(raw["CurrentOccupation"], prefix="occ", dtype=float)], axis=1)
    A = np.column_stack([np.ones(len(X)), X.to_numpy(dtype=float)])
    coef, *_ = np.linalg.lstsq(A, lp.to_numpy(), rcond=None)
    got = dict(zip(X.columns, coef[1:]))
    worst = max(abs(got[k] - v) for k, v in TRUE_DIRECT.items())
    resid_sd = float(np.std(lp.to_numpy() - A @ coef))
    return {"max_abs_coef_error": float(worst), "residual_sd": resid_sd,
            "recovered": {k: round(float(got[k]), 3) for k in TRUE_DIRECT}}


def plan_metrics(features, plan_steps, s0, p_true, target):
    after = R._apply(features, plan_steps)
    s1 = float(_probs([after])[0]) * 100
    lt = np.log(p_true / (1 - p_true)) + true_logit_delta(features, after)
    true_gain = (1 / (1 + np.exp(-lt)) - p_true) * 100
    return {"reached": bool(target is not None and s1 >= target), "pred_gain": s1 - s0, "true_gain": float(true_gain),
            "steps": len(plan_steps), "effort": sum(s[2] for s in plan_steps)}


def one_size_plan(sample_features):
    """The 3 steps with the largest average predicted gain on a separate sample (a static playbook)."""
    gains = {}
    base = np.array(_probs(sample_features))
    for step in R.STEPS:
        rows = [R._apply(f, (step,)) for f in sample_features]
        gains[step[0]] = float(np.mean(np.array(_probs(rows)) - base))
    top = sorted(gains, key=lambda k: -gains[k])[:3]
    return [s for s in R.STEPS if s[0] in top], gains


def unconstrained_plan(features, s0, target):
    """Fewest changes (L0) reaching the next tier when ANY attribute may change (cost 1 each)."""
    moves = [("step", s) for s in R.STEPS if s[1] == "+1" or not features.get(s[0])]
    for col in IMMUTABLE:
        if col in ("DoNotEmail", "DoNotCall"):
            if features.get(col):
                moves.append(("attr", (col, 0)))
            continue
        vocab, _ = F.CATEGORICAL[col]
        options = [v for v in vocab if v != features.get(col) and v != "Unknown"]
        if not options:
            continue
        probs = _probs([{**features, col: v} for v in options])
        moves.append(("attr", (col, options[int(np.argmax(probs))])))

    def apply(combo):
        f = dict(features)
        steps = [m[1] for m in combo if m[0] == "step"]
        f = R._apply(f, steps)
        for kind, m in combo:
            if kind == "attr":
                f[m[0]] = m[1]
        return f

    for r in range(1, R.MAX_STEPS + 1):
        combos = list(combinations(moves, r))
        probs = np.array(_probs([apply(c) for c in combos])) * 100
        ok = np.where(probs >= target)[0]
        if len(ok):
            best = combos[int(ok[np.argmax(probs[ok])])]
            n_imm = sum(1 for kind, _ in best if kind == "attr")
            return {"reached": True, "changes": r, "immutable_changes": n_imm,
                    "changed": [m[0] for kind, m in best]}
    return {"reached": False, "changes": None, "immutable_changes": 0, "changed": []}


def main():
    t0 = time.time()
    os.makedirs(RESULTS, exist_ok=True)
    raw = G.generate(N_EVAL * 2, seed=4242, return_truth=True)
    check = verify_structural_coefficients(G.generate(60000, seed=99, return_truth=True))
    print(f"Structural-equation check: max |coef error| {check['max_abs_coef_error']:.3f}, "
          f"residual sd {check['residual_sd']:.3f} (generator noise 0.45)")

    feats = [F.normalize_raw(r) for r in raw.to_dict("records")]
    scores = np.array(_probs(feats)) * 100
    keep = [i for i in range(len(feats)) if scores[i] < 80][:N_EVAL]
    print(f"Evaluating {len(keep):,} leads below the top tier ...")
    plan_fixed, avg_gains = one_size_plan([F.normalize_raw(r) for r in
                                           G.generate(2000, seed=4343).to_dict("records")])
    print("One-size plan: " + " + ".join(s[0] for s in plan_fixed))

    rows = []
    for j, i in enumerate(keep):
        f, s0, pt = feats[i], scores[i], float(raw["_p_true"].iloc[i])
        target = R._next_cutoff(s0)
        tips = R.tips_for(f, s0, limit=1)
        step_by_name = {s[0]: s for s in R.STEPS}
        ours = plan_metrics(f, [step_by_name[k] for k in tips[0]["steps"]], s0, pt, target) if tips else \
            {"reached": False, "pred_gain": 0.0, "true_gain": 0.0, "steps": 0, "effort": 0}
        todo = [s for s in plan_fixed if s[1] == "+1" or not f.get(s[0])]
        fixed = plan_metrics(f, todo, s0, pt, target) if todo else \
            {"reached": False, "pred_gain": 0.0, "true_gain": 0.0, "steps": 0, "effort": 0}
        rec = {"tier": F.tier_for(s0), "score": s0, "ours": ours, "fixed": fixed}
        if j < N_UNCONSTRAINED:
            rec["unconstrained"] = unconstrained_plan(f, s0, target)
        rows.append(rec)
        if (j + 1) % 500 == 0:
            print(f"  {j + 1:,} leads ({time.time() - t0:,.0f}s)")

    def summarise(sel, key):
        r = [x[key] for x in sel]
        reached = [x for x in r if x["reached"]]
        pg = np.array([x["pred_gain"] for x in reached]) if reached else np.array([np.nan])
        tg = np.array([x["true_gain"] for x in reached]) if reached else np.array([np.nan])
        return {"leads": len(r), "coverage": float(np.mean([x["reached"] for x in r])),
                "mean_steps_when_reached": float(np.mean([x["steps"] for x in reached])) if reached else None,
                "mean_effort_when_reached": float(np.mean([x["effort"] for x in reached])) if reached else None,
                "mean_effort_all": float(np.mean([x["effort"] for x in r])),
                "mean_predicted_gain_pts": float(np.nanmean(pg)), "mean_true_gain_pts": float(np.nanmean(tg)),
                "true_over_predicted": float(np.nanmean(tg) / np.nanmean(pg)) if reached else None,
                "true_gain_per_effort": float(np.nanmean(tg) / np.mean([x["effort"] for x in reached])) if reached else None}

    tiers = ["Low Priority", "Marketing Campaign", "Nurture via Email/WhatsApp"]
    summary = {"all": {k: summarise(rows, k) for k in ("ours", "fixed")}}
    for t in tiers:
        sel = [x for x in rows if x["tier"] == t]
        if sel:
            summary[t] = {k: summarise(sel, k) for k in ("ours", "fixed")}
    un = [x["unconstrained"] for x in rows if "unconstrained" in x]
    un_reached = [u for u in un if u["reached"]]
    imm_counts = {}
    for u in un_reached:
        for c in u["changed"]:
            if c in IMMUTABLE:
                imm_counts[c] = imm_counts.get(c, 0) + 1
    unconstrained = {
        "leads": len(un), "coverage": float(np.mean([u["reached"] for u in un])),
        "share_of_plans_needing_an_immutable_change": float(np.mean([u["immutable_changes"] > 0 for u in un_reached]))
        if un_reached else None,
        "mean_changes": float(np.mean([u["changes"] for u in un_reached])) if un_reached else None,
        "most_changed_immutables": dict(sorted(imm_counts.items(), key=lambda kv: -kv[1])[:5]),
        "ours_coverage_same_leads": float(np.mean([x["ours"]["reached"] for x in rows if "unconstrained" in x])),
    }
    out = {"design": {"leads": len(rows), "unconstrained_leads": len(un), "max_steps": R.MAX_STEPS},
           "structural_check": check, "one_size_plan": [s[0] for s in plan_fixed],
           "average_single_step_gain_pts": {k: round(v * 100, 2) for k, v in avg_gains.items()},
           "summary": summary, "unconstrained": unconstrained, "runtime_s": round(time.time() - t0, 1)}
    with open(os.path.join(RESULTS, "recourse_eval.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    write_markdown(out)
    a = summary["all"]
    print(f"\nOurs: coverage {a['ours']['coverage'] * 100:.1f}% · {a['ours']['mean_steps_when_reached']:.2f} steps · "
          f"effort {a['ours']['mean_effort_when_reached']:.2f} · predicted +{a['ours']['mean_predicted_gain_pts']:.1f} pts "
          f"vs true +{a['ours']['mean_true_gain_pts']:.1f} pts")
    print(f"One-size: coverage {a['fixed']['coverage'] * 100:.1f}% · effort {a['fixed']['mean_effort_all']:.2f}")
    print(f"Unconstrained: {unconstrained['share_of_plans_needing_an_immutable_change'] * 100:.1f}% of plans need an "
          f"impossible change")
    print(f"Saved {os.path.relpath(RESULTS)}/recourse_eval.json and .md  ({time.time() - t0:,.0f}s)")


def write_markdown(o):
    L = ["# “How to convert” tips — counterfactual quality", "",
         f"{o['design']['leads']:,} fresh simulated leads below the top tier. Plans use at most "
         f"{o['design']['max_steps']} steps. *Predicted gain* = lead-model score change; *true gain* = change in the "
         "simulator's true purchase probability for the same person (hidden intent held fixed), averaged over plans "
         "that reach the next tier.", "",
         f"Structural check: behaviour coefficients recovered from the generated data within "
         f"{o['structural_check']['max_abs_coef_error']:.3f} (residual sd {o['structural_check']['residual_sd']:.2f}).", "",
         f"One-size plan (same for everyone): {' + '.join(o['one_size_plan'])}.", "",
         "| Leads | Method | Coverage (reaches next tier) | Steps | Effort (reached) | Effort (all) | Predicted gain (pts) | True gain (pts) | True / predicted | True gain per effort |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    names = {"ours": "Ours (cheapest personalised plan)", "fixed": "One-size plan"}
    for group, d in o["summary"].items():
        for k, v in d.items():
            f = lambda x, p=2: "—" if x is None else f"{x:.{p}f}"
            L.append(f"| {group} ({v['leads']:,}) | {names[k]} | {v['coverage'] * 100:.1f}% | {f(v['mean_steps_when_reached'])} | "
                     f"{f(v['mean_effort_when_reached'])} | {f(v['mean_effort_all'])} | {f(v['mean_predicted_gain_pts'], 1)} | "
                     f"{f(v['mean_true_gain_pts'], 1)} | {f(v['true_over_predicted'])} | {f(v['true_gain_per_effort'])} |")
    u = o["unconstrained"]
    L += ["", "## Why actionability constraints matter", "",
          f"On {u['leads']:,} of the leads, an unconstrained search (any attribute may change, cost 1 each) reaches the next "
          f"tier for {u['coverage'] * 100:.1f}% (ours: {u['ours_coverage_same_leads'] * 100:.1f}% on the same leads) — but "
          f"**{(u['share_of_plans_needing_an_immutable_change'] or 0) * 100:.1f}%** of its plans require changing something "
          f"no one can act on (most often: " + ", ".join(f"{k} ×{v}" for k, v in u["most_changed_immutables"].items()) + ").",
          "", "## Average predicted gain of each single step (pts)", "",
          "| Step | Gain |", "|---|---|"]
    for k, v in sorted(o["average_single_step_gain_pts"].items(), key=lambda kv: -kv[1]):
        L.append(f"| {k} | {v:+.2f} |")
    with open(os.path.join(RESULTS, "recourse_eval.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
