"""
=================================================================
 X EDUCATION — CLOSED-LOOP RETRAINING
=================================================================
 The loop:
   1. Every time the backend scores a user it stores a snapshot in
      score_snapshots: the exact features the model saw + its prediction.
   2. A purchase is the real outcome. A snapshot is labelled
         Converted = 1  if the user bought within WINDOW days after it
         Converted = 0  if WINDOW days have passed with no purchase
      (younger snapshots without a purchase are skipped: outcome unknown).
   3. This script trains a CHALLENGER on synthetic data + real labelled
      snapshots (real rows weighted higher), and compares it with the live
      CHAMPION on real held-out users. The challenger replaces the champion
      only if it is better on real data (lower log-loss). The old model is
      kept as lead_model.previous.pkl.
   4. The backend reloads the new model automatically.

 Usage (from the project root, with the backend venv):
     user-backend\\venv\\Scripts\\python.exe ml\\retrain_from_live.py
     ...  --window-days 1      (for a demo: label outcomes after 1 day)
     ...  --dry-run            (report only, don't replace the model)
     ...  --force              (replace even with little real data)
=================================================================
"""
import argparse
import json
import os
import sqlite3
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import log_loss, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import train_model as T  # noqa: E402
F = T.F

DB_PATH = os.path.join(T.BACKEND, "xeducation_user.db")
MIN_REAL_ROWS = 50
MIN_REAL_POSITIVES = 5


def load_real(db_path, window_days):
    if not os.path.exists(db_path):
        raise SystemExit(f"Database not found: {db_path}")
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    window = f"+{int(window_days)} days"
    rows = con.execute(f"""
        SELECT s.id, s.user_id, s.features_json, s.created_at,
               EXISTS(SELECT 1 FROM purchases p WHERE p.user_id = s.user_id
                      AND p.purchased_at >= s.created_at
                      AND p.purchased_at <= datetime(s.created_at, '{window}')) AS converted,
               (s.created_at <= datetime('now','localtime','-{int(window_days)} days')) AS matured,
               EXISTS(SELECT 1 FROM purchases p WHERE p.user_id = s.user_id
                      AND p.purchased_at <= s.created_at) AS already_customer
        FROM score_snapshots s
        WHERE s.source != 'purchase_conversion'      -- taken after the purchase: would leak the answer
        ORDER BY s.user_id, s.created_at
    """).fetchall()
    con.close()

    records = []
    for r in rows:
        if r["already_customer"]:
            continue            # the model predicts first purchase, not repeat purchase
        if not (r["converted"] or r["matured"]):
            continue            # outcome not known yet
        feats = json.loads(r["features_json"])
        feats["Converted"] = int(r["converted"])
        feats["_user"] = r["user_id"]
        feats["_day"] = r["created_at"][:10]
        records.append(feats)
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    # one row per user per day (many near-identical snapshots would over-weight active users)
    return df.drop_duplicates(subset=["_user", "_day"], keep="last").reset_index(drop=True)


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
    n_real = len(real)
    n_pos = int(real["Converted"].sum()) if n_real else 0
    print(f"Real labelled snapshots: {n_real} ({n_pos} converted, "
          f"{real['_user'].nunique() if n_real else 0} users, window {args.window_days} days)")

    if (n_real < MIN_REAL_ROWS or n_pos < MIN_REAL_POSITIVES or n_pos == n_real) and not args.force:
        print(f"Not enough real outcomes yet (need {MIN_REAL_ROWS}+ rows incl. {MIN_REAL_POSITIVES}+ "
              "conversions and some non-conversions). Keep collecting, or use --force.")
        return

    synth = pd.read_csv(T.DATA_PATH) if os.path.exists(T.DATA_PATH) else None
    if synth is None:
        import generate_dataset
        synth = generate_dataset.generate(60000)

    # Hold out real USERS (not rows) so the comparison is honest
    if n_real >= 10 and real["Converted"].nunique() == 2:
        gss = GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=7)
        tr_idx, te_idx = next(gss.split(real, groups=real["_user"]))
        real_tr, real_te = real.iloc[tr_idx], real.iloc[te_idx]
        if real_te["Converted"].nunique() < 2:
            real_tr, real_te = real, real          # too small to split cleanly
    else:
        real_tr, real_te = real, real

    X_syn, y_syn = F.to_model_frame(synth), synth["Converted"].astype(int).to_numpy()
    X_rtr, y_rtr = F.to_model_frame(real_tr), real_tr["Converted"].astype(int).to_numpy()
    X_rte, y_rte = F.to_model_frame(real_te), real_te["Converted"].astype(int).to_numpy()

    X_train = pd.concat([X_syn, X_rtr], ignore_index=True)
    y_train = np.concatenate([y_syn, y_rtr])
    w_train = np.concatenate([np.ones(len(y_syn)), np.full(len(y_rtr), args.real_weight)])

    print("\nChallenger candidates (scored on synthetic hold-out):")
    from sklearn.model_selection import train_test_split
    Xa, Xb, ya, yb, wa, _ = train_test_split(X_train, y_train, w_train, test_size=0.2,
                                             stratify=y_train, random_state=42)
    name, _, syn_metrics = T.fit_best(Xa, ya, Xb, yb, w_tr=wa)

    from sklearn.pipeline import Pipeline
    challenger = Pipeline([("prep", T.build_preprocessor()), ("clf", T.candidates()[name])])
    challenger.fit(X_train, y_train, clf__sample_weight=w_train)

    def real_score(pipe):
        p = np.clip(pipe.predict_proba(X_rte)[:, 1], 1e-4, 1 - 1e-4)
        auc = roc_auc_score(y_rte, p) if len(set(y_rte)) == 2 else float("nan")
        return log_loss(y_rte, p, labels=[0, 1]), auc

    ch_ll, ch_auc = real_score(challenger)
    champion = None
    if os.path.exists(T.MODEL_PATH):
        try:
            champion = joblib.load(T.MODEL_PATH)
        except Exception as e:
            print(f"(could not load current model: {e})")
    if champion and champion.get("feature_version") == F.FEATURE_VERSION:
        cp_ll, cp_auc = real_score(champion["pipeline"])
    else:
        cp_ll, cp_auc = float("inf"), float("nan")

    print(f"\nOn REAL held-out users ({len(y_rte)} snapshots):")
    print(f"  champion   ({champion['version'] if champion else 'none':>22s})  log-loss={cp_ll:.4f}  AUC={cp_auc:.3f}")
    print(f"  challenger ({name:>22s})  log-loss={ch_ll:.4f}  AUC={ch_auc:.3f}")

    better = ch_ll < cp_ll
    if args.dry_run:
        print("\nDry run — model not replaced.")
        return
    if not better and not args.force:
        print("\nChallenger is not better on real data — keeping the current model.")
        return

    metrics = dict(syn_metrics, real_log_loss=round(float(ch_ll), 4),
                   real_auc=None if np.isnan(ch_auc) else round(float(ch_auc), 4))
    version = T.save_bundle(challenger, name, metrics, float(y_train.mean()),
                            {"synthetic_rows": int(len(y_syn)), "real_rows": int(len(y_rtr) + 0)},
                            extra={"retrained_from_live": True, "window_days": args.window_days,
                                   "real_holdout_rows": int(len(y_rte))})
    print(f"\nNew model {version} saved to {T.MODEL_PATH} (previous kept as lead_model.previous.pkl).")
    print("The backend picks it up on the next score — no restart needed.")


if __name__ == "__main__":
    main()
