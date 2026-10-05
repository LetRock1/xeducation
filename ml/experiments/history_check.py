"""
history_check.py — what the simulated six-month histories show, read straight from their databases.

A history (ml/generate_history.py --seed S) is the CRM running by itself for 180 days on 2,000
simulated learners. Two things in it are KNOWN, so the CRM's conclusions can be checked:
  * how this business differs from the data the base model was trained on (WORLD_DRIFT:
    WhatsApp opt-in +0.6, mobile -0.5, webinar +0.7 log-odds of buying)
  * the true effect of every A/B test variant (AB_TESTS)

For every history folder given, this reports:
  1. the learning loop, judged on the untouched control group: how many of them each model
     expected to buy vs how many did; log-loss of ours vs a naive retrain; which model the usual
     check (fit on all live data) would have picked; how often the model was swapped
  2. what the loop learned for the three known differences, against the true values
  3. the CRM's total impact: leads it worked on vs the untouched control group (bought within 30 days)
  4. the A/B tests: each verdict against the true effects, and what happened to adopted winners

Usage:  python ml/experiments/history_check.py [FOLDER ...]
        (each FOLDER is a project folder with a finished history; default: this project)
Writes ml/results/history_runs.md
"""
import importlib.util
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ROOT, "ml", "results", "history_runs.md")
TS = "%Y-%m-%d %H:%M:%S"
DOMAIN = "demo.xeducation.test"
sys.path.insert(0, os.path.join(ROOT, "user-backend"))      # for unpickling the lead model


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


GH = _load("generate_history_ref", os.path.join(ROOT, "ml", "generate_history.py"))
X = _load("experiments", os.path.join(ROOT, "marketing-backend", "experiments.py"))
sys.modules["experiments"] = X
AD = _load("adoption_ref", os.path.join(ROOT, "marketing-backend", "adoption.py"))
SETTINGS = json.load(open(os.path.join(ROOT, "crm_settings.json"), encoding="utf-8"))
CONTROL_SHARE = float(SETTINGS["global_control"]["share"])
WINDOW = int(SETTINGS["ab_testing"].get("outcome_window_days", 14))
ALPHA = float(SETTINGS["ab_testing"]["alpha"])
POWER = float(SETTINGS["ab_testing"]["power"])
DRIFT = dict(GH.WORLD_DRIFT)
DRIFT_LABEL = {"WhatsAppOptIn": "Opted in to WhatsApp", "MobileDevice": "Browses on mobile",
               "WebinarAttended": "Joined a webinar"}
import lead_model as LM   # noqa: E402
LABELS = dict(LM.LIVE_LABELS)


def in_control(user_id):
    """Same hash as user-backend/settings.py in_global_control()."""
    import settings
    return settings.in_global_control(user_id)


def truth_of(test):
    """Variants with a truly positive effect vs the test's reference, from the documented effects."""
    by = {v["key"]: v for v in test["variants"]}
    metric = test["metric"]
    if metric == "click":                       # click tests compare variants with variant A
        a = by["A"].get("click", 0.0)
        pos = [k for k, v in by.items() if k != "A" and not callable(v.get("click")) and v.get("click", 0.0) > a]
        return pos, "clicks vs variant A"
    pos = []
    for k, v in by.items():                     # purchase tests compare each variant with sending nothing
        b = v.get("buy", 0.0)
        if b in ("coupon10", "coupon20") or callable(b) or (isinstance(b, (int, float)) and b > 0):
            pos.append(k)
    return pos, "purchases vs no email"


TRUE_TEXT = {
    "10% vs 20% coupon": "both coupons raise buying (20% more); the audience is far below the planned size",
    "Webinar invite vs brochure": "true null: neither email changes buying",
    "Subject line: benefit vs urgency": "urgency subject: +0.8 log-odds on clicks, same buying",
    "Short mobile email vs long email": "short email +1.4 on phones only; long email +0.4 on desktop only",
    "Personalised course pick vs generic newsletter": "personalised +1.2 log-odds on buying; newsletter nothing",
    "EMI message vs refund guarantee": "sent 5 days before the end: cannot be final yet",
}


def judge(test_spec, analysis):
    pos, _ = truth_of(test_spec)
    v = analysis["verdict"]
    st = v.get("status")
    if not analysis.get("final"):
        return "running (correct: not final)" if st == "running" else f"{st}?"
    if st == "winner":
        return "correct" if v.get("winner") in pos else "WRONG (false winner)"
    if st == "loser":
        return "WRONG (false loser)"
    if st == "no_difference":
        return "correct (true null)" if not pos else "missed (too few people)"
    return st


def check(folder):
    udb = os.path.join(folder, "user-backend", "xeducation_user.db")
    mdb = os.path.join(folder, "marketing-backend", "xeducation_marketing.db")
    con = sqlite3.connect(udb)
    con.row_factory = sqlite3.Row
    uq = lambda sql, params=(): [dict(r) for r in con.execute(sql, params)]
    base = os.path.basename(os.path.normpath(folder))
    m = re.match(r"^s(?:eed)?(\d+)$", base)
    out = {"folder": folder, "label": f"seed {m.group(1)}" if m else base}

    # 1. learning runs
    runs = uq("SELECT * FROM learning_runs WHERE simulated=1 AND status='done' ORDER BY as_of")
    out["runs"] = []
    for r in runs:
        L = json.loads(r.get("learned_json") or "{}")
        c = L.get("control") or {}
        p = c.get("predicted") or {}
        out["runs"].append({
            "as_of": r["as_of"][:10], "people": c.get("people"), "points": r.get("random_slice"),
            "buyers": r.get("random_slice_buyers"),
            "actual": c.get("actual"), "champion": p.get("champion"), "ours": p.get("challenger"), "naive": p.get("naive"),
            "ll_ours": r.get("challenger_true_logloss"), "ll_naive": r.get("naive_true_logloss"),
            "ll_champion": r.get("champion_true_logloss"), "auc_ours": r.get("challenger_true_auc"),
            "auc_naive": r.get("naive_true_auc"), "naive_would_pick": r.get("naive_would_pick"),
            "decision": r.get("lead_decision"), "prob_better": r.get("lead_prob_better"),
            "naive_prob_better": c.get("naive_prob_better"), "nba": r.get("nba_decision"),
            "own_effect_share": r.get("own_effect_share"),
            "naive_points": {s["signal"]: s for s in (L.get("naive_points") or [])},
            "ours_points": {s["signal"]: s for s in (L.get("challenger_points") or [])}})
    end = datetime.strptime(runs[-1]["as_of"][:19], TS) + timedelta(minutes=5) if runs else datetime.now()
    out["end"] = end

    # 2. what the current model has learned
    import joblib
    b = joblib.load(os.path.join(folder, "user-backend", "ml_models", "lead_model.pkl"))
    live = b.get("live") or {}
    w = dict(zip(live.get("signals", []), live.get("weights", [])))
    out["live"] = {"weights": {k: w.get(k) for k in DRIFT}, "all_weights": w, "slope": live.get("slope"),
                   "intercept": live.get("intercept"), "outcomes_used": live.get("outcomes_used"),
                   "version": b.get("version")}

    # 3. total impact (people who signed up at least 30 days before the end)
    rows = uq(f"""SELECT u.id AS user_id, u.created_at, MIN(p.purchased_at) AS first_buy FROM users u
                  LEFT JOIN purchases p ON p.user_id=u.id WHERE u.email LIKE '%@{DOMAIN}' AND u.created_at <= ?
                  GROUP BY u.id""", ((end - timedelta(days=30)).strftime(TS),))
    g = {"worked_on": [0, 0], "control": [0, 0]}
    for r in rows:
        k = g["control" if in_control(r["user_id"]) else "worked_on"]
        k[1] += 1
        if r["first_buy"] and datetime.strptime(r["first_buy"][:19], TS) <= \
                datetime.strptime(r["created_at"][:19], TS) + timedelta(days=30):
            k[0] += 1
    (x1, n1), (x0, n0) = g["worked_on"], g["control"]
    lo, hi = X.diff_ci(x1, n1, x0, n0)
    out["impact"] = {"worked_on": (x1, n1), "control": (x0, n0), "lift": x1 / n1 - x0 / n0, "ci": (lo, hi),
                     "p": X.two_prop_p(x1, n1, x0, n0)}

    # 4. A/B tests and adoptions
    out["ab"] = []
    specs = {t["name"]: t for t in GH.AB_TESTS}
    if os.path.exists(mdb):
        m = sqlite3.connect(mdb)
        m.row_factory = sqlite3.Row
        tests = [dict(r) for r in m.execute("SELECT * FROM ab_tests WHERE simulated=1 ORDER BY id")]
        m.close()
        for t in tests:
            name = t["name"].replace("(simulated) ", "")
            spec = specs.get(name)
            a = AD.analyse_ab(uq, t, json.loads(t["variants_json"]), end, WINDOW, ALPHA, POWER)
            comp = {c["variant"]: c for c in a["comparisons"]}
            v = a["verdict"]
            best = comp.get(v.get("winner")) if v.get("winner") else (max(a["comparisons"], key=lambda c: c["lift"])
                                                                    if a["comparisons"] else None)
            mob = None
            for seg in a["segments"].get("device", []):
                if seg["value"] == "Mobile":
                    mob = seg
            out["ab"].append({"name": name, "metric": t["metric"], "n": {s["arm"]: s["n"] for s in a["arms"]},
                              "status": v.get("status"), "winner": v.get("winner"), "final": a["final"],
                              "lift": best["lift"] if best else None, "ci": best["lift_ci"] if best else None,
                              "vs": best["vs"] if best else None, "variant": best["variant"] if best else None,
                              "judged": judge(spec, a) if spec else "?", "truth": TRUE_TEXT.get(name, ""),
                              "srm_problem": a["srm_problem"], "mobile_best": mob.get("best") if mob else None})
    out["adoptions"] = uq("SELECT * FROM adopted_emails WHERE simulated=1 ORDER BY id")
    con.close()
    return out


def pct(x, d=1):
    return "—" if x is None else f"{x * 100:.{d}f}%"


def pts(x):
    return "—" if x is None else f"{x * 100:+.1f}"


def f4(x):
    return "—" if x is None else f"{x:.4f}"


def over(pred, actual):
    return None if pred is None or not actual else pred / actual - 1


def report(results):
    L = ["# The simulated histories, checked against what is known to be true", "",
         f"{len(results)} histories (different random seeds), each 180 days, 2,000 simulated learners, the CRM running "
         "by itself: scoring, next-best-action with 15% exploration, campaigns with hold-outs, six A/B tests, "
         "auto-adopted winners, and the learning loop at days 30, 60, 90, 120, 150 and the end. "
         f"The untouched control group is {CONTROL_SHARE:.0%} of learners (never contacted). "
         "Made by `ml/experiments/history_check.py` from the history databases.", ""]

    # 1. learning loop
    L += ["## 1. Is the learning loop fooling itself? (judged on the untouched control group)", "",
          "Each row is one learning run. The control group's decision points are the moments the CRM would have "
          "acted on those people (it logged the decision but did nothing). *Expects* = the average predicted chance "
          "to buy within 14 days at those points; *bought* = how often they actually did.", "",
          "| History | Run | Control group: people / decision points | Bought | Model in use expects | Naive retrain expects | Ours expects | Log-loss naive | Log-loss ours | Usual check picks | Decision |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    finals = []
    allruns = []
    for res in results:
        for r in res["runs"]:
            if r["actual"] is None:
                continue
            allruns.append(r)
            L.append(f"| {res['label']} | {r['as_of']} | {r['people']} / {r['points']} | {pct(r['actual'])} | "
                     f"{pct(r['champion'])} | {pct(r['naive'])} | {pct(r['ours'])} | "
                     f"{f4(r['ll_naive'])} | {f4(r['ll_ours'])} | "
                     f"{'naive' if r['naive_would_pick'] else 'ours'} | {r['decision']} |")
        ok = [r for r in res["runs"] if r["actual"] is not None and r["ll_ours"] is not None]
        if ok:
            finals.append(ok[-1])
    scored = [r for r in allruns if r["ll_ours"] is not None and r["ll_naive"] is not None]
    if scored:
        better = sum(r["ll_ours"] < r["ll_naive"] for r in scored)
        champ = [r for r in scored if r["ll_champion"] is not None]
        beat_champ = sum(r["ll_ours"] < r["ll_champion"] for r in champ)
        picks = sum(bool(r["naive_would_pick"]) for r in scored)
        on = [over(r["naive"], r["actual"]) for r in scored]
        oo = [over(r["ours"], r["actual"]) for r in scored]
        oc = [over(r["champion"], r["actual"]) for r in scored]
        L += ["", f"- Runs with a control-group check: **{len(scored)}**. Ours predicted the control group better "
              f"(lower log-loss) than the naive retrain in **{better} of {len(scored)}**, and better than the model "
              f"in use at that time in {beat_champ} of {len(champ)}.",
              f"- The usual check (fit on all live outcomes, which the CRM's own follow-ups shaped) would have picked "
              f"the naive retrain in **{picks} of {len(scored)}** runs.",
              f"- How much each overstated the control group's buying, mean over all runs: naive "
              f"**{np.mean(on) * 100:+.0f}%**, ours **{np.mean(oo) * 100:+.0f}%**, the model in use before the run "
              f"{np.mean(oc) * 100:+.0f}%. (Some overstatement is expected for every model: the score is the chance to "
              "buy if we do nothing *now*, but the control group also gets nothing later.)",
              f"- Final runs only (most data): naive {np.mean([over(r['naive'], r['actual']) for r in finals]) * 100:+.0f}%, "
              f"ours {np.mean([over(r['ours'], r['actual']) for r in finals]) * 100:+.0f}%."]
        swaps = sum(r["decision"] == "swapped" for res in results for r in res["runs"])
        nba_swaps = sum(r["nba"] == "swapped" for res in results for r in res["runs"])
        L += [f"- Lead model swapped {swaps} times over {sum(len(r['runs']) for r in results)} runs "
              f"(only when better on the control group in ≥90% of bootstrap resamples); next-best-action swapped "
              f"{nba_swaps} times.", ""]

    # 2. learned differences
    L += ["## 2. What the loop learned about this business, vs the truth", "",
          "The simulated business differs from the base model's training data in three documented ways (log-odds "
          "of buying, `WORLD_DRIFT` in ml/generate_history.py). Below: what the final learning run of each history "
          "learned (ours), and whether the CRM is using a learned model.", "",
          "| History | " + " | ".join(f"{DRIFT_LABEL[k]} (true {DRIFT[k]:+.1f})" for k in DRIFT) +
          " | Largest other corrections | Model in use at the end |",
          "|---|" + "---|" * len(DRIFT) + "---|---|"]
    gaps, found = [], {k: [] for k in DRIFT}
    for res in results:
        last = res["runs"][-1] if res["runs"] else {}
        w = {k: v["weight"] for k, v in (last.get("ours_points") or {}).items()}
        for k in DRIFT:
            if w.get(k) is not None:
                found[k].append(w[k])
        cells = ["—" if w.get(k) is None else f"{w[k]:+.2f}" for k in DRIFT]
        others = sorted(((k, v) for k, v in w.items() if k not in DRIFT), key=lambda kv: -abs(kv[1]))[:3]
        swaps = [r["as_of"] for r in res["runs"] if r["decision"] == "swapped"]
        in_use = (f"learned model from {swaps[-1]}" if swaps else
                  "the starting model (no new model was confirmed with 90% confidence)")
        L.append(f"| {res['label']} | " + " | ".join(cells) + " | " +
                 ", ".join(f"{LABELS.get(k, k)} {v:+.2f}" for k, v in others) + f" | {in_use} |")
        for r in res["runs"]:
            for k, n in (r.get("naive_points") or {}).items():
                o = (r.get("ours_points") or {}).get(k)
                if o:
                    gaps.append(abs(n["weight"] - o["weight"]))
    if all(found.values()):
        L += ["", "Learned vs true, range over the histories: " + "; ".join(
            f"{DRIFT_LABEL[k]} {min(v):+.2f} to {max(v):+.2f} (true {DRIFT[k]:+.1f}, right sign in "
            f"{sum((x > 0) == (DRIFT[k] > 0) for x in v)} of {len(v)})" for k, v in found.items()) + "."]
    L += ["", "Weights are log-odds added for a lead with the signal. They are ridge-shrunk toward 0 and fitted "
          "together with a recalibration of the base score, so only the sign and rough size should match.",
          "The large negative correction for *Clicked our emails* is not one of the designed differences, and it "
          "is right: in the base model's training data e-mail opens depend only on the learner's interest, but in "
          "a running CRM they also depend on how many e-mails the CRM has already sent (learners it kept e-mailing "
          "without a purchase pile up clicks), so a click says less about interest than the base model assumed.",
          "A learned model is used only once the untouched control group confirms it with 90% confidence. With "
          "about 80 untouched people after six months that bar is high: where no model was confirmed, the CRM "
          "kept the starting model even though the new one was often better (section 1). A larger control "
          "group or a lower bar (crm_settings.json) makes it switch sooner, at the cost of fewer people worked on "
          "or more risk of switching on noise."]
    if gaps:
        L += ["", f"The naive retrain learns similar signal weights to ours (median difference {np.median(gaps):.2f}, "
                  f"largest {max(gaps):.2f} log-odds). Its main mistake is the overall level: most decision points were followed by "
                  "an action of the CRM, and the naive retrain folds the average effect of those actions into every "
                  "lead's baseline — which is what section 1 shows."]
    L.append("")

    # 3. impact
    L += ["## 3. The CRM's total impact (worked-on leads vs the untouched control group)", "",
          "Share of learners who bought within 30 days of signing up (learners who signed up at least 30 days "
          "before the end).", "",
          "| History | Worked on | Control group | Difference (95% interval) | p |", "|---|---|---|---|---|"]
    for res in results:
        i = res["impact"]
        (x1, n1), (x0, n0) = i["worked_on"], i["control"]
        L.append(f"| {res['label']} | {x1}/{n1} = {pct(x1 / n1)} | {x0}/{n0} = {pct(x0 / n0)} | "
                 f"{pts(i['lift'])} pts ({pts(i['ci'][0])} to {pts(i['ci'][1])}) | {i['p']:.3f} |")
    lifts = [r["impact"]["lift"] for r in results]
    sig = sum(r["impact"]["ci"][0] > 0 for r in results)
    L += ["", f"Mean difference {np.mean(lifts) * 100:+.1f} pts, positive in {sum(x > 0 for x in lifts)} of "
          f"{len(results)} histories; the 95% interval is above zero in {sig} of {len(results)} (the control group is "
          f"only ~{CONTROL_SHARE:.0%} of learners, so each single history has a wide interval)."]
    if len(results) > 1:
        X1 = sum(r["impact"]["worked_on"][0] for r in results)
        N1 = sum(r["impact"]["worked_on"][1] for r in results)
        X0 = sum(r["impact"]["control"][0] for r in results)
        N0 = sum(r["impact"]["control"][1] for r in results)
        lo, hi = X.diff_ci(X1, N1, X0, N0)
        L.append(f"All {len(results)} independent histories together: worked on {X1:,}/{N1:,} = {X1 / N1:.1%}, "
                 f"control group {X0}/{N0} = {X0 / N0:.1%}: **{pts(X1 / N1 - X0 / N0)} pts** (95% interval "
                 f"{pts(lo)} to {pts(hi)}, p = {X.two_prop_p(X1, N1, X0, N0):.4f}).")
    L.append("")

    # 4. A/B
    L += ["## 4. A/B test verdicts vs the true effects", "",
          "| History | Test | Metric | People per arm | Verdict | Lift of the best variant (95% interval) | True effect | Judged |",
          "|---|---|---|---|---|---|---|---|"]
    tally = {}
    for res in results:
        for a in res["ab"]:
            judged = a["judged"]
            tally[judged.split(" (")[0]] = tally.get(judged.split(" (")[0], 0) + 1
            lift = "—" if a["lift"] is None else (f"{a['variant']} vs {a['vs']}: {pts(a['lift'])} pts "
                                                  f"({pts(a['ci'][0])} to {pts(a['ci'][1])})")
            verdict = a["status"] + (f" {a['winner']}" if a["winner"] else "")
            if a["name"].startswith("Short mobile") and a["mobile_best"]:
                verdict += f" (on phones: {a['mobile_best']})"
            L.append(f"| {res['label']} | {a['name']} | {a['metric']} | "
                     f"{', '.join(f'{k} {v}' for k, v in a['n'].items())} | {verdict} | {lift} | {a['truth']} | {judged} |")
    wrong = sum(v for k, v in tally.items() if k.startswith("WRONG"))
    L += ["", "Tally: " + ", ".join(f"{k}: {v}" for k, v in sorted(tally.items())) + f". Wrong verdicts (a winner or "
          f"loser that is not true): **{wrong}**. *Missed* = a real effect the test was too small to confirm; the "
          "plan shown before sending warns when the audience is smaller than needed.", ""]
    L += ["### Adopted winners", "",
          "| History | From test | Adopted email | Audience | Status | Last check |", "|---|---|---|---|---|---|"]
    for res in results:
        for a in res["adoptions"]:
            c = json.loads(a.get("check_json") or "{}")
            arms = ", ".join(f"{x.get('label')}: {x.get('n')} people, {pct(x.get('rate'))}" for x in c.get("arms", []))
            L.append(f"| {res['label']} | {str(a['test_name']).replace('(simulated) ', '')} | {a['variant_label']} | "
                     f"{a['audience']} | {a['status']} | {c.get('why', '—')} {('(' + arms + ')') if arms else ''} |")
    L.append("")
    return "\n".join(L)


def main():
    folders = sys.argv[1:] or [ROOT]
    results = []
    for f in folders:
        print(f"reading {f} ...", flush=True)
        results.append(check(f))
    text = report(results)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(text)
    print(f"\nSaved {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
