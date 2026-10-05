"""
Does a CRM that retrains on its own results fool itself — and does our learning loop avoid it?
Real randomized data: Hillstrom e-mail experiment (64,000 customers; men's e-mail vs no e-mail;
outcome = visited the website within two weeks).

How a CRM is emulated on real data (no simulator):
  The experiment gave each customer the e-mail with probability 1/2. A CRM policy "e-mail the top 30%
  by the current score (15% of choices random)" is emulated by keeping each customer with the
  probability the policy would have chosen the arm they really got. What remains is exactly the data
  that policy would have logged, with REAL outcomes.

  Round 0  the CRM starts with a recency/spend rule (how CRMs usually start) and e-mails by it.
  Round 1  it retrains on what it logged; the new score decides the next round's e-mails.
  Round 2  it retrains again on everything logged.

Ways to retrain (same learner, gradient boosting):
  naive          fit "who visited" on the logged data — how CRMs usually retrain
  ours           told what the CRM did: the e-mail is an input, and the score is read with it off
  left-alone     fit only on customers who got no e-mail, weighted by 1/probability
  reference      the same learner on the randomized no-email customers (no loop at all — best case)

Judged on held-out customers who were NOT e-mailed in the real experiment (the truth: what they do
when left alone):
  overstatement  predicted vs actual visit rate among the 30% each score would target
  honest AUC / log-loss on the left-alone truth
  live log-loss  fit on data logged by the CRM — the check a normal CRM uses to pick a model

Run:  python ml/experiments/learning_loop.py [repeats=20] [exploration=0.15]     (a few minutes)
Writes ml/results/learning_loop.md and .json
"""
import json
import os
import sys
import time

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import log_loss, roc_auc_score

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hillstrom_uplift as H  # noqa: E402

RESULTS = os.path.normpath(os.path.join(HERE, "..", "results"))
TARGET_SHARE = 0.30
REPEATS = int(sys.argv[1]) if len(sys.argv) > 1 else 20
EPS = float(sys.argv[2]) if len(sys.argv) > 2 else 0.15

h, Xall, arm = H.load()
keep = np.isin(arm, ["none", "mens"])
X = Xall[keep].reset_index(drop=True)
T = (arm[keep] == "mens").astype(int)
Y = h.loc[keep, "visit"].to_numpy().astype(int)
XN = X.to_numpy(dtype=float)
N = len(Y)


def gbm(seed):
    return HistGradientBoostingClassifier(random_state=seed, **H.GBM)


def p_email(score_values, threshold):
    """Probability the CRM policy e-mails each customer: top 30% by score, EPS of choices random."""
    return np.where(score_values >= threshold, 1 - EPS / 2, EPS / 2)


def log_round(idx, score_fn, rng):
    """One deployment round on customers idx: rows the policy would have logged (and their probability)."""
    s = score_fn(XN[idx])
    p1 = p_email(s, np.quantile(s, 1 - TARGET_SHARE))
    p_got = np.where(T[idx] == 1, p1, 1 - p1)
    kept = rng.random(len(idx)) < p_got                    # both arms had probability 1/2
    return idx[kept], p_got[kept]


def fit_naive(rows, seed):
    m = gbm(seed).fit(XN[rows], Y[rows])
    return lambda Z: m.predict_proba(Z)[:, 1]


def fit_left_alone(rows, probs, seed):
    none = T[rows] == 0
    m = gbm(seed).fit(XN[rows][none], Y[rows][none], sample_weight=1 / probs[none])
    return lambda Z: m.predict_proba(Z)[:, 1]


def fit_ours(rows, seed):
    m = gbm(seed).fit(np.column_stack([XN[rows], T[rows]]), Y[rows])
    return lambda Z: m.predict_proba(np.column_stack([Z, np.zeros(len(Z))]))[:, 1]


def judge(score_fn, C, live_rows, rng):
    s = score_fn(XN[C])
    alone = T[C] == 0
    top = s >= np.quantile(s, 1 - TARGET_SHARE)
    pred, actual = s[top & alone].mean(), Y[C][top & alone].mean()
    logged, _ = log_round(C, score_fn, rng)
    return {"honest_auc": roc_auc_score(Y[C][alone], s[alone]),
            "apparent_auc": roc_auc_score(Y[logged], score_fn(XN[logged])),
            "honest_logloss": log_loss(Y[C][alone], np.clip(s[alone], 1e-4, 1 - 1e-4)),
            "live_logloss": log_loss(Y[live_rows], np.clip(score_fn(XN[live_rows]), 1e-4, 1 - 1e-4)),
            "predicted_top": pred, "actual_top": actual, "overstatement_pct": 100 * (pred - actual) / actual}


def main():
    t0 = time.time()
    rows_out = []
    for seed in range(REPEATS):
        rng = np.random.default_rng(seed)
        perm = rng.permutation(N)
        before, B1, B2, C = np.split(perm, [int(.10 * N), int(.40 * N), int(.70 * N)])
        hist = before[T[before] == 0]                      # before the CRM: nobody was e-mailed
        hist_p = np.ones(len(hist))
        rule = lambda Z: H.rfm_score(pd.DataFrame(Z, columns=H.FEATURES))
        L1, P1 = log_round(B1, rule, rng)
        round1 = {"naive": fit_naive(np.r_[hist, L1], seed),
                  "left-alone": fit_left_alone(np.r_[hist, L1], np.r_[hist_p, P1], seed),
                  "ours": fit_ours(np.r_[hist, L1], seed)}
        models = {}
        for name, f in round1.items():                     # each method's score runs round 2 itself
            L2, P2 = log_round(B2, f, rng)
            rows, probs = np.r_[hist, L1, L2], np.r_[hist_p, P1, P2]
            models[name] = {"naive": lambda: fit_naive(rows, seed + 100),
                            "left-alone": lambda: fit_left_alone(rows, probs, seed + 100),
                            "ours": lambda: fit_ours(rows, seed + 100)}[name]()
        models["reference"] = fit_naive(np.r_[hist, B1[T[B1] == 0], B2[T[B2] == 0]], seed + 200)
        live_C, _ = log_round(C, rule, np.random.default_rng(5000 + seed))   # the CRM's own logged data
        for name, f in models.items():
            r = judge(f, C, live_C, np.random.default_rng(1000 + seed))
            r.update(method=name, repeat=seed)
            rows_out.append(r)
        print(f"  repeat {seed + 1}/{REPEATS} done ({time.time() - t0:.0f} s)")
    df = pd.DataFrame(rows_out)
    order = ["naive", "ours", "left-alone", "reference"]
    cols = ["overstatement_pct", "honest_auc", "apparent_auc", "honest_logloss", "live_logloss"]
    mean, sd = df.groupby("method")[cols].mean().reindex(order), df.groupby("method")[cols].std().reindex(order)
    piv = df.pivot(index="repeat", columns="method")
    picks_naive = int((piv["live_logloss"]["naive"] < piv["live_logloss"]["ours"]).sum())
    ours_better = int((piv["honest_logloss"]["ours"] < piv["honest_logloss"]["naive"]).sum())
    less_inflated = int((piv["overstatement_pct"]["ours"] < piv["overstatement_pct"]["naive"]).sum())
    labels = {"naive": "Naive retrain (how CRMs retrain)", "ours": "Ours (told what the CRM did)",
              "left-alone": "Left-alone customers only (weighted)", "reference": "Reference: no loop at all"}
    lines = ["# Learning loop on real randomized data (Hillstrom, 42,613 customers: men's e-mail vs none)", "",
             f"{REPEATS} repeats; the CRM e-mails the top {TARGET_SHARE:.0%} by its score, {EPS:.0%} of choices random; "
             "two retraining rounds; judged on held-out customers the real experiment left alone.", "",
             "| Method | Overstates targeted customers by | Honest AUC | AUC on the CRM's own data | Honest log-loss | Log-loss on the CRM's own data |",
             "|---|---|---|---|---|---|"]
    for m in order:
        r, s = mean.loc[m], sd.loc[m]
        lines.append(f"| {labels[m]} | {r['overstatement_pct']:+.1f}% (sd {s['overstatement_pct']:.1f}) | "
                     f"{r['honest_auc']:.3f} | {r['apparent_auc']:.3f} | {r['honest_logloss']:.4f} | {r['live_logloss']:.4f} |")
    lines += ["", f"- Judged by fit on the CRM's own logged data (the usual check), the naive model is picked over ours in "
                  f"**{picks_naive} of {REPEATS}** repeats.",
              f"- Judged on the randomized left-alone truth, ours is more accurate than naive in **{ours_better} of {REPEATS}**.",
              f"- Ours overstates targeted customers less than naive in **{less_inflated} of {REPEATS}**.",
              f"- The gap between AUC on the CRM's own data and honest AUC is the accuracy illusion: "
              f"{mean.loc['naive', 'apparent_auc'] - mean.loc['naive', 'honest_auc']:+.3f} for naive."]
    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, "learning_loop.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(RESULTS, "learning_loop.json"), "w", encoding="utf-8") as f:
        json.dump({"repeats": REPEATS, "exploration": EPS, "mean": mean.round(5).to_dict(orient="index"),
                   "sd": sd.round(5).to_dict(orient="index"), "naive_picked_by_live_check": picks_naive,
                   "ours_better_on_truth": ours_better, "ours_less_overstated": less_inflated}, f, indent=2)
    print("\n" + "\n".join(lines))
    print(f"\n({time.time() - t0:.0f} s) Saved ml/results/learning_loop.md")


if __name__ == "__main__":
    main()
