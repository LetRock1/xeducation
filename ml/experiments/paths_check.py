"""
Do the what-if paths predict what learners really do next? An out-of-time check on the CRM's history.

The what-if paths use, for each lifecycle stage and team step, the mix of reactions in the next
3 days (bought / cart-checkout-enquiry / came back / clicked / nothing) and the chance of buying
within 14 days, learned from earlier decisions (weighted by 1/probability of each decision).

Check: learn that model from the decisions made BEFORE a cut-off date (only outcomes known by then),
and predict the decisions made AFTER it.
  reaction mix   multi-class Brier score (lower is better) against two simpler guesses:
                 the same mix for everyone, and the mix per stage ignoring the step
  buying         predicted vs actual buying rate within 14 days, per step
All test decisions are weighted by 1/probability, so the score is about what each step does, not
about which leads the model happened to pick for it.

Run on a database with history (the simulated starting history, or real data):
    python ml/experiments/paths_check.py [--db user-backend/xeducation_user.db] [--cut 2026-08-15]
Writes ml/results/paths_check.md
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "user-backend"))


def brier(pred, obs, w, reactions):
    total = 0.0
    for r in reactions:
        total = total + (pred[r] - (obs == r).astype(float)) ** 2
    return float((w * total).sum() / w.sum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.join(ROOT, "user-backend", "xeducation_user.db"))
    ap.add_argument("--cut", default=None, help="cut-off date (default: two thirds into the history)")
    a = ap.parse_args()
    import database as db
    db.DB_PATH = a.db
    import journeys as J
    every = J.steps()
    if every.empty:
        raise SystemExit("No decisions in this database.")
    t = pd.to_datetime(every["t"])
    cut = pd.Timestamp(a.cut) if a.cut else t.min() + (t.max() - t.min()) * 2 / 3
    model = J.model_from(J.steps(until=cut.strftime("%Y-%m-%d %H:%M:%S")))
    test = every[(t > cut) & every["matured"]].copy()
    if test.empty:
        raise SystemExit("No matured decisions after the cut-off.")
    R = J.REACTIONS
    test = test[test["stage"].isin(model["stages"])]
    w = test["w"].to_numpy(dtype=float)
    obs = test["reaction"].to_numpy()
    # the model: per stage and step
    cell = {r: np.array([model["stages"][s]["actions"][a]["reactions"][r] for s, a in zip(test["stage"], test["action"])])
            for r in R}
    buy_pred = np.array([model["stages"][s]["actions"][a]["buy14"] for s, a in zip(test["stage"], test["action"])])
    # simpler guesses, learned from the same earlier decisions
    train = J.steps(until=cut.strftime("%Y-%m-%d %H:%M:%S"))
    train = train[train["matured"]]
    tw = train["w"].to_numpy(dtype=float)
    glob = {r: np.full(len(test), float((tw * (train["reaction"] == r)).sum() / tw.sum())) for r in R}
    stage_mix = {}
    for s in model["stages"]:
        m = train[train["stage"] == s]
        mw = m["w"].to_numpy(dtype=float)
        stage_mix[s] = {r: float((mw * (m["reaction"] == r)).sum() / mw.sum()) if len(m) else 0.0 for r in R}
    by_stage = {r: np.array([stage_mix[s][r] for s in test["stage"]]) for r in R}
    scores = {"same mix for everyone": brier(glob, obs, w, R), "mix per stage (ignores the step)": brier(by_stage, obs, w, R),
              "what-if paths (stage and step)": brier(cell, obs, w, R)}
    lines = ["# What-if paths: out-of-time check", "",
             f"Learned from {len(train):,} decisions before {cut:%Y-%m-%d}; tested on {len(test):,} later decisions "
             "(weighted by 1/probability).", "",
             "| Prediction of the reaction in the next 3 days | Brier score (lower is better) |", "|---|---|"]
    lines += [f"| {k} | {v:.4f} |" for k, v in scores.items()]
    lines += ["", "| Team step | Later decisions | Predicted buying within 14 days | Actual |", "|---|---|---|---|"]
    for act in sorted(test["action"].unique()):
        m = (test["action"] == act).to_numpy()
        lines.append(f"| {act} | {int(m.sum()):,} | {np.average(buy_pred[m], weights=w[m]):.1%} | "
                     f"{np.average(test['bought'].to_numpy()[m], weights=w[m]):.1%} |")
    lines.append(f"| all | {len(test):,} | {np.average(buy_pred, weights=w):.1%} | "
                 f"{np.average(test['bought'].to_numpy(), weights=w):.1%} |")
    os.makedirs(os.path.join(ROOT, "ml", "results"), exist_ok=True)
    with open(os.path.join(ROOT, "ml", "results", "paths_check.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
