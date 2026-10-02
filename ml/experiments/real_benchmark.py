"""
=================================================================
 EXPERIMENT 1 — Lead scoring on REAL data (X Education, 9,240 leads)
=================================================================
 Data: ml/data/Leads.csv (Kaggle "Lead Scoring Dataset", X Education).

 Three feature sets:
   A  all columns              — what many published notebooks/papers use
   B  pre-contact only         — what is actually known when a lead arrives:
                                 removes Tags, Lead Quality, Lead Profile,
                                 Asymmetrique indices/scores and Last (Notable)
                                 Activity, which are written by the sales team
                                 or record sales actions (SMS sent, phone call)
   C  B + learner-side activity — Last Activity kept only when it is something
                                 the learner did (opened/clicked an email,
                                 visited a page, chatted, submitted a form)

 Models: majority class, rule-based points scoring (the manual lead-scoring
 rubric typical of marketing-automation tools), logistic regression (the
 standard case-study model), gradient boosting, and OURS (the calibrated
 pipeline used by the product: best of LR / gradient boosting by inner
 log-loss).  5-fold stratified cross-validation, out-of-fold predictions,
 mean ± std per fold, paired-bootstrap CIs for AUC differences.

 Run:  python ml/experiments/real_benchmark.py      (writes ml/results/real_benchmark.*)
=================================================================
"""
import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, average_precision_score, brier_score_loss, f1_score,
                             log_loss, precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data", "Leads.csv")
RESULTS = os.path.join(HERE, "..", "results")
SEED = 42

ID_COLS = ["Prospect ID", "Lead Number"]
TARGET = "Converted"
POST_CONTACT = ["Tags", "Lead Quality", "Lead Profile", "Asymmetrique Activity Index",
                "Asymmetrique Profile Index", "Asymmetrique Activity Score", "Asymmetrique Profile Score",
                "Last Activity", "Last Notable Activity"]
LEARNER_ACTIVITY = {"Email Opened", "Email Link Clicked", "Page Visited on Website",
                    "Olark Chat Conversation", "Form Submitted on Website", "Unsubscribed",
                    "Email Bounced", "Resubscribed to emails", "Visited Booth in Tradeshow",
                    "View in browser link Clicked", "Email Received"}
NUMERIC = ["TotalVisits", "Total Time Spent on Website", "Page Views Per Visit"]


def load():
    df = pd.read_csv(DATA)
    df = df.drop(columns=ID_COLS)
    for c in df.columns:
        if df[c].dtype == object or str(df[c].dtype) in ("string", "str"):
            df[c] = df[c].astype("object").where(df[c].notna(), None)
            df[c] = df[c].map(lambda v: v.strip() if isinstance(v, str) else v)
            # 'Select' = the form's default option was left unchanged
            df[c] = df[c].map(lambda v: "Not selected" if v == "Select" else v)
    df["Lead Source"] = df["Lead Source"].replace({"google": "Google", "Facebook": "Facebook"})
    # learner-side activity only (for feature set C)
    df["Learner Last Activity"] = df["Last Activity"].map(
        lambda v: v if v in LEARNER_ACTIVITY else ("No learner activity recorded" if v is not None else None))
    for c in df.columns:
        if c not in NUMERIC and c != TARGET and df[c].dtype != object:
            df[c] = df[c].astype("object")
    return df


def feature_sets(df):
    all_cols = [c for c in df.columns if c not in (TARGET, "Learner Last Activity")]
    pre = [c for c in all_cols if c not in POST_CONTACT]
    return {
        "A: all columns (as commonly published)": all_cols,
        "B: pre-contact only (leakage-free)": pre,
        "C: pre-contact + learner activity": pre + ["Learner Last Activity"],
    }


def preprocessor(cols):
    num = [c for c in cols if c in NUMERIC or c in ("Asymmetrique Activity Score", "Asymmetrique Profile Score")]
    cat = [c for c in cols if c not in num]
    return ColumnTransformer([
        ("num", Pipeline([("imp", SimpleImputer(strategy="median", add_indicator=True)),
                          ("log", FunctionTransformer(np.log1p, feature_names_out="one-to-one")),
                          ("sc", StandardScaler())]), num),
        ("cat", Pipeline([("imp", SimpleImputer(strategy="constant", fill_value="Missing")),
                          ("oh", OneHotEncoder(handle_unknown="ignore", min_frequency=10, sparse_output=False))]), cat),
    ])


def lr():
    return LogisticRegression(C=1.0, max_iter=5000)


def gbm():
    return HistGradientBoostingClassifier(max_iter=400, learning_rate=0.05, max_leaf_nodes=24,
                                          min_samples_leaf=30, l2_regularization=1.0, early_stopping=True,
                                          validation_fraction=0.15, n_iter_no_change=25, random_state=SEED)


def points_score(X):
    """Manual lead-scoring rubric (points), typical of rule-based marketing automation."""
    s = np.zeros(len(X))
    origin = X["Lead Origin"].fillna("")
    source = X["Lead Source"].fillna("")
    occ = X["What is your current occupation"].fillna("")
    s += np.where(origin.isin(["Lead Add Form", "Quick Add Form"]), 25, np.where(origin == "Landing Page Submission", 10, 0))
    s += np.where(source.isin(["Reference", "Referral Sites", "Welingak Website"]), 20,
                  np.where(source.isin(["Google", "Organic Search"]), 5, 0))
    s += np.where(occ == "Working Professional", 15, np.where(occ == "Businessman", 5, np.where(occ == "Student", -5, 0)))
    s += np.clip(X["TotalVisits"].fillna(0), 0, 10)
    s += np.clip(X["Total Time Spent on Website"].fillna(0) / 60, 0, 30)
    s += 2 * np.clip(X["Page Views Per Visit"].fillna(0), 0, 5)
    s -= np.where(X["Do Not Email"] == "Yes", 20, 0)
    return s


def ece(y, p, bins=10):
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
    return float(sum(abs(p[idx == b].mean() - y[idx == b].mean()) * (idx == b).mean()
                     for b in range(bins) if (idx == b).any()))


def metrics(y, p, thr=0.5, probabilistic=True):
    pred = (p >= thr).astype(int)
    order = np.argsort(-p)
    top10, top20 = order[: len(y) // 10], order[: len(y) // 5]
    out = {
        "roc_auc": roc_auc_score(y, p), "pr_auc": average_precision_score(y, p),
        "accuracy": accuracy_score(y, pred), "precision": precision_score(y, pred, zero_division=0),
        "recall": recall_score(y, pred), "f1": f1_score(y, pred),
        "precision_top10pct": y[top10].mean(), "precision_top20pct": y[top20].mean(),
        "conversions_captured_top20pct": y[top20].sum() / y.sum(),
    }
    if probabilistic:
        pc = np.clip(p, 1e-4, 1 - 1e-4)
        out.update({"log_loss": log_loss(y, pc), "brier": brier_score_loss(y, p), "ece": ece(y, p)})
        hot = p >= 0.8
        out["precision_score_ge_80"] = y[hot].mean() if hot.any() else float("nan")
        out["share_score_ge_80"] = hot.mean()
    return out


def best_threshold(y, s):
    cands = np.quantile(s, np.linspace(0.05, 0.95, 91))
    return max(cands, key=lambda t: accuracy_score(y, (s >= t).astype(int)))


def run_cv(df, cols):
    X, y = df[cols], df[TARGET].to_numpy()
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
    oof = {k: np.zeros(len(y)) for k in ("Majority class", "Rule-based points", "Logistic regression",
                                          "Gradient boosting", "Ours (calibrated, model-selected)")}
    folds = {k: [] for k in oof}
    chosen = []
    for tr, te in skf.split(X, y):
        Xtr, Xte, ytr, yte = X.iloc[tr], X.iloc[te], y[tr], y[te]
        oof["Majority class"][te] = ytr.mean()
        folds["Majority class"].append(metrics(yte, np.full(len(te), ytr.mean())))
        # rule-based: points → threshold chosen on the training fold
        s_tr, s_te = points_score(Xtr), points_score(Xte)
        t = best_threshold(ytr, s_tr)
        lo, hi = s_tr.min(), s_tr.max()
        norm = np.clip((s_te - lo) / (hi - lo), 0, 1)
        oof["Rule-based points"][te] = norm
        folds["Rule-based points"].append(metrics(yte, norm, thr=(t - lo) / (hi - lo), probabilistic=False))
        fitted = {}
        for name, est in (("Logistic regression", lr()), ("Gradient boosting", gbm())):
            pipe = Pipeline([("prep", preprocessor(cols)), ("clf", est)]).fit(Xtr, ytr)
            p = pipe.predict_proba(Xte)[:, 1]
            oof[name][te] = p
            folds[name].append(metrics(yte, p))
            fitted[name] = pipe
        # OURS: pick LR vs GBM by inner validation log-loss (no peeking at the test fold),
        # preferring LR unless boosting is clearly better (same rule as the product)
        inner = StratifiedKFold(n_splits=3, shuffle=True, random_state=SEED + 1)
        ll = {"Logistic regression": [], "Gradient boosting": []}
        for itr, iva in inner.split(Xtr, ytr):
            for name, est in (("Logistic regression", lr()), ("Gradient boosting", gbm())):
                pp = Pipeline([("prep", preprocessor(cols)), ("clf", est)]).fit(Xtr.iloc[itr], ytr[itr])
                ll[name].append(log_loss(ytr[iva], np.clip(pp.predict_proba(Xtr.iloc[iva])[:, 1], 1e-4, 1 - 1e-4)))
        m_lr, m_gb = np.mean(ll["Logistic regression"]), np.mean(ll["Gradient boosting"])
        pick = "Gradient boosting" if m_lr - m_gb >= 0.005 else "Logistic regression"
        chosen.append(pick)
        p = oof[pick][te]
        oof["Ours (calibrated, model-selected)"][te] = p
        folds["Ours (calibrated, model-selected)"].append(metrics(yte, p))
    summary = {}
    for k, fl in folds.items():
        keys = fl[0].keys()
        summary[k] = {m: {"mean": float(np.nanmean([f[m] for f in fl])), "std": float(np.nanstd([f[m] for f in fl]))}
                      for m in keys}
    return summary, oof, y, chosen


def bootstrap_auc_diff(y, p1, p2, n=1000, seed=SEED):
    rng = np.random.default_rng(seed)
    d = []
    for _ in range(n):
        i = rng.integers(0, len(y), len(y))
        if y[i].min() == y[i].max():
            continue
        d.append(roc_auc_score(y[i], p1[i]) - roc_auc_score(y[i], p2[i]))
    d = np.array(d)
    return {"mean": float(d.mean()), "ci_low": float(np.percentile(d, 2.5)), "ci_high": float(np.percentile(d, 97.5))}


def main():
    os.makedirs(RESULTS, exist_ok=True)
    df = load()
    print(f"Leads: {len(df):,}   conversion rate: {df[TARGET].mean()*100:.1f}%")
    out = {"n": int(len(df)), "conversion_rate": float(df[TARGET].mean()), "feature_sets": {}}
    lines = []
    for fs_name, cols in feature_sets(df).items():
        print(f"\n=== {fs_name} ({len(cols)} columns) ===")
        summary, oof, y, chosen = run_cv(df, cols)
        diffs = {
            "ours_vs_rule_based": bootstrap_auc_diff(y, oof["Ours (calibrated, model-selected)"], oof["Rule-based points"]),
            "ours_vs_logistic": bootstrap_auc_diff(y, oof["Ours (calibrated, model-selected)"], oof["Logistic regression"]),
        }
        out["feature_sets"][fs_name] = {"columns": cols, "summary": summary, "auc_differences": diffs,
                                        "model_chosen_per_fold": chosen}
        hdr = f"  {'Model':36s} {'AUC':>13s} {'Accuracy':>13s} {'F1':>13s} {'Prec@top10%':>12s} {'ECE':>7s}"
        print(hdr)
        for name, m in summary.items():
            e = m.get("ece", {}).get("mean")
            print(f"  {name:36s} {m['roc_auc']['mean']:.3f}±{m['roc_auc']['std']:.3f} "
                  f"{m['accuracy']['mean']*100:6.1f}±{m['accuracy']['std']*100:.1f}% "
                  f"{m['f1']['mean']:.3f}±{m['f1']['std']:.3f} {m['precision_top10pct']['mean']*100:11.1f}% "
                  f"{'' if e is None else f'{e:.3f}':>7s}")
        print(f"  models chosen per fold: {chosen}")
        for k, v in diffs.items():
            print(f"  AUC difference {k}: {v['mean']:+.3f} (95% CI {v['ci_low']:+.3f} to {v['ci_high']:+.3f})")
        lines.append((fs_name, summary))

    with open(os.path.join(RESULTS, "real_benchmark.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=float)
    with open(os.path.join(RESULTS, "real_benchmark.md"), "w", encoding="utf-8") as f:
        f.write("# Lead scoring on real X Education data (9,240 leads, 5-fold CV)\n\n")
        for fs_name, summary in lines:
            f.write(f"## {fs_name}\n\n| Model | ROC-AUC | PR-AUC | Accuracy | Precision | Recall | F1 | Precision top 10% | Conversions in top 20% | ECE |\n|---|---|---|---|---|---|---|---|---|---|\n")
            for name, m in summary.items():
                fmt = lambda k, pct=False: (f"{m[k]['mean']*100:.1f}% ± {m[k]['std']*100:.1f}" if pct
                                            else f"{m[k]['mean']:.3f} ± {m[k]['std']:.3f}") if k in m else "—"
                f.write(f"| {name} | {fmt('roc_auc')} | {fmt('pr_auc')} | {fmt('accuracy', True)} | {fmt('precision')} | "
                        f"{fmt('recall')} | {fmt('f1')} | {fmt('precision_top10pct', True)} | "
                        f"{fmt('conversions_captured_top20pct', True)} | {fmt('ece')} |\n")
            f.write("\n")
    print("\nSaved ml/results/real_benchmark.json and .md")


if __name__ == "__main__":
    main()
