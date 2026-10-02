"""
=================================================================
 CLOSED LOOP for next-best-action: learn from real decisions
=================================================================
 Every decision the website makes is logged in nba_decisions with the
 features, the action taken and the PROBABILITY that action had under the
 policy (15% of decisions are randomised). A purchase within the window
 after a decision is its outcome.

 This script:
   1. builds the real training set from those logs (inverse-propensity
      weights correct for the model having chosen most actions itself)
   2. trains TWO challengers on simulated prior + real data: the
      interpretable S-learner (nba_core.design) and the flexible
      gradient-boosting S-learner (nba_core.FlexibleSLearner)
   3. compares the champion and both challengers on held-out REAL decisions
      with the self-normalised inverse-propensity estimate (SNIPS) of the
      profit their greedy policies would earn — off-policy evaluation
   4. replaces the model only if the best challenger beats the champion

 Usage: user-backend\\venv\\Scripts\\python.exe ml\\retrain_nba_from_live.py [--window-days 14] [--dry-run] [--force]
=================================================================
"""
import argparse
import json
import os
import shutil
import sqlite3
import sys

import joblib
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import generate_dataset as G     # noqa: E402
import nba_simulation as S       # noqa: E402
import train_model as T          # noqa: E402
import train_uplift as U         # noqa: E402

F, N = S.F, S.N
DB_PATH = os.path.join(T.BACKEND, "xeducation_user.db")
MIN_REAL = 100


def load_real(db_path, window_days):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    w = int(window_days)
    rows = con.execute(f"""
        SELECT d.*,
          EXISTS(SELECT 1 FROM purchases p WHERE p.user_id=d.user_id AND p.purchased_at >= d.created_at
                 AND p.purchased_at <= datetime(d.created_at, '+{w} days')) AS converted,
          (d.created_at <= datetime('now','localtime','-{w} days')) AS matured,
          EXISTS(SELECT 1 FROM purchases p WHERE p.user_id=d.user_id AND p.purchased_at < d.created_at) AS customer
        FROM nba_decisions d""").fetchall()
    con.close()
    recs = []
    for r in rows:
        if r["customer"] or not (r["converted"] or r["matured"]) or not r["propensity"]:
            continue
        f = json.loads(r["features_json"])
        recs.append({**f, "_action": r["action"], "_prop": r["propensity"], "_y": int(r["converted"]),
                     "_base": r["base_probability"], "_price": r["price"], "_user": r["user_id"]})
    return pd.DataFrame(recs)


def snips_value(model, frame, base_p, actions, props, y, price):
    """Off-policy estimate of the profit per lead of the model's greedy policy (either model family)."""
    pred = U.predict_all(model, frame, base_p)
    blocked = U.blocked_matrix(frame)
    greedy = U.greedy_policy(pred, price, blocked, capacity=1.0)
    w = (greedy == actions) / np.clip(props, 1e-3, None)
    disc = np.array([N.ACTIONS[a]["discount"] for a in actions])
    cost = np.array([N.ACTIONS[a]["cost_inr"] for a in actions])
    profit = y * price * (1 - disc) - cost
    return float((w * profit).sum() / w.sum()) if w.sum() else float("-inf")


def demo_note(db_path):
    """Say so when the 'real' data includes simulated demo learners (seed-demo-data.bat)."""
    try:
        con = sqlite3.connect(db_path)
        n = con.execute("SELECT COUNT(*) FROM users WHERE email LIKE '%@demo.xeducation.test'").fetchone()[0]
        con.close()
    except sqlite3.Error:
        return
    if n:
        print(f"Note: includes {n} simulated demo learners (seed-demo-data.bat) whose purchases come from "
              f"the simulator — this demonstrates the mechanism, not real-world performance.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB_PATH)
    ap.add_argument("--window-days", type=int, default=14)
    ap.add_argument("--real-weight", type=float, default=5.0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    demo_note(args.db)
    real = load_real(args.db, args.window_days)
    print(f"Real decisions with known outcome: {len(real)}"
          + (f" ({int(real['_y'].sum())} purchases)" if len(real) else ""))
    if len(real) < MIN_REAL and not args.force:
        print(f"Need at least {MIN_REAL} — keep collecting (or use --force).")
        return

    prior_raw = G.generate(60000, seed=2024, return_truth=True)
    pf, pa, _, py, _ = S.simulate_randomized_campaign(prior_raw, None, seed=11)
    pb = U.base_probability(pf)

    rf = F.to_model_frame(real)
    rb = real["_base"].to_numpy(dtype=float)
    ra = real["_action"].to_numpy()
    ry = real["_y"].to_numpy()
    rp = real["_prop"].to_numpy(dtype=float)
    rprice = real["_price"].to_numpy(dtype=float)

    users = real["_user"].unique()
    rng = np.random.default_rng(3)
    test_users = set(rng.choice(users, size=max(1, len(users) // 3), replace=False))
    is_test = real["_user"].isin(test_users).to_numpy()

    X_frame = pd.concat([pf, rf[~is_test]], ignore_index=True)
    X_base = np.concatenate([pb, rb[~is_test]])
    X_act = np.concatenate([pa, ra[~is_test]])
    y = np.concatenate([py, ry[~is_test]])
    w = np.concatenate([np.ones(len(py)),
                        args.real_weight * np.clip(1 / rp[~is_test], 1, 20)])
    challengers = {
        "interpretable S-learner": U.fit_uplift(X_frame, X_base, X_act, y, weights=w),
        "flexible S-learner (GBM)": U.fit_flexible(X_frame, X_act, y, weights=w),
    }
    bundle_old = joblib.load(U.NBA_PATH) if os.path.exists(U.NBA_PATH) else {}
    champion = bundle_old.get("model")
    t = is_test
    held_out = (rf[t].reset_index(drop=True), rb[t], ra[t], rp[t], ry[t], rprice[t])
    cp = snips_value(champion, *held_out) if champion is not None else float("-inf")
    scores = {name: snips_value(m, *held_out) for name, m in challengers.items()}
    print(f"Off-policy profit per lead on {int(t.sum())} held-out real decisions:")
    print(f"  champion ({N.model_kind(champion) if champion is not None else 'none'}): ₹{cp:,.0f}")
    for name, v in scores.items():
        print(f"  challenger — {name}: ₹{v:,.0f}")
    best = max(scores, key=scores.get)
    challenger, ch = challengers[best], scores[best]

    if args.dry_run:
        print("Dry run — not saved.")
        return
    if not (ch > cp) and not args.force:
        print("No challenger beats the champion — keeping the current model.")
        return
    if os.path.exists(U.NBA_PATH):
        shutil.copy2(U.NBA_PATH, U.NBA_PATH.replace(".pkl", ".previous.pkl"))
    import datetime as dt
    bundle = {**{k: v for k, v in bundle_old.items() if k != "model"}, "model": challenger,
              "kind": N.model_kind(challenger),
              "version": dt.datetime.now().strftime("nba-%Y%m%d-%H%M%S"),
              "trained_on": {"simulated_rows": int(len(py)), "real_rows": int((~is_test).sum())},
              "offpolicy_profit_per_lead": {"champion": cp, **scores}}
    joblib.dump(bundle, U.NBA_PATH)
    print(f"Saved new uplift model {bundle['version']} ({best}) — the backend reloads it automatically.")


if __name__ == "__main__":
    main()
