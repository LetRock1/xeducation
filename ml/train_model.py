"""
=================================================================
 X EDUCATION — LEAD SCORING MODEL TRAINER (v4)
=================================================================
 Replaces the old notebook export. Produces ONE file the backend loads:

     user-backend/ml_models/lead_model.pkl   (preprocessing + model, one Pipeline)
     user-backend/ml_models/model_card.json  (version, metrics, what it was trained on)

 IMPORTANT — run it with the backend's own Python so the scikit-learn
 version that trains the model is the same one that loads it:

     user-backend\\venv\\Scripts\\python.exe ml\\train_model.py
 (or just double-click train-model.bat in the project root)

 What it does:
   1. Loads ml/lead_data_v4.csv (generates it if missing)
   2. Engineers features with user-backend/ml_features.py (same code as live)
   3. Trains two candidates — Logistic Regression and Gradient Boosting —
      and keeps the one with the best log-loss on held-out data
      (log-loss rewards honest probabilities, not just ranking)
   4. Prints accuracy, ROC-AUC, calibration, and the real conversion rate
      inside each action tier, then a sanity check on typical website journeys
   5. Saves the bundle; the running backend picks it up automatically.

 Why no KMeans/PCA persona any more: the old clusters were ordered by
 "engagement", but "Warm Lead" converted better than "Hot Lead", and the
 cluster was also fed back into the model as a feature. Persona is now
 derived from the calibrated score, so it always agrees with it.
=================================================================
"""
import argparse
import datetime as dt
import json
import os
import shutil
import sys

import numpy as np
import pandas as pd
import joblib
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, brier_score_loss, f1_score,
                             log_loss, roc_auc_score)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "user-backend")
sys.path.insert(0, BACKEND)
import ml_features as F  # noqa: E402

MODEL_DIR = os.path.join(BACKEND, "ml_models")
MODEL_PATH = os.path.join(MODEL_DIR, "lead_model.pkl")
CARD_PATH = os.path.join(MODEL_DIR, "model_card.json")
DATA_PATH = os.path.join(HERE, "lead_data_v4.csv")

SKEWED = ["TotalVisits", "TotalTimeOnWebsite", "TimePerVisit", "EmailOpenedCount"]


def build_preprocessor():
    other_numeric = [c for c in F.MODEL_NUMERIC if c not in SKEWED]
    return ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), F.MODEL_CATEGORICAL),
        ("skew", Pipeline([("log", FunctionTransformer(np.log1p, feature_names_out="one-to-one")),
                           ("scale", StandardScaler())]), SKEWED),
        ("num", StandardScaler(), other_numeric),
    ])


def candidates():
    return {
        "logistic_regression": LogisticRegression(C=0.5, max_iter=3000),
        "gradient_boosting": HistGradientBoostingClassifier(
            max_iter=400, learning_rate=0.05, max_leaf_nodes=24,
            min_samples_leaf=40, l2_regularization=1.0,
            early_stopping=True, validation_fraction=0.1,
            n_iter_no_change=25, random_state=42),
    }


def evaluate(y, p):
    pred = (p >= 0.5).astype(int)
    return {
        "roc_auc": round(float(roc_auc_score(y, p)), 4),
        "log_loss": round(float(log_loss(y, p)), 4),
        "brier": round(float(brier_score_loss(y, p)), 4),
        "accuracy": round(float(accuracy_score(y, pred)), 4),
        "f1": round(float(f1_score(y, pred)), 4),
    }


def tier_table(y, p):
    s = pd.Series(p * 100)
    tiers = s.apply(F.tier_for)
    t = pd.DataFrame({"tier": tiers, "y": np.asarray(y), "p": p})
    out = t.groupby("tier").agg(leads=("y", "size"), predicted=("p", "mean"), actual=("y", "mean"))
    order = [name for _, name in F.TIERS]
    return out.reindex([o for o in order if o in out.index])


def fit_best(X_tr, y_tr, X_va, y_va, w_tr=None, verbose=True):
    """Train every candidate, return (name, fitted pipeline, metrics) of the best."""
    results = []
    for name, clf in candidates().items():
        pipe = Pipeline([("prep", build_preprocessor()), ("clf", clf)])
        pipe.fit(X_tr, y_tr, clf__sample_weight=w_tr)
        p = pipe.predict_proba(X_va)[:, 1]
        m = evaluate(y_va, p)
        results.append((m["log_loss"], name, pipe, m))
        if verbose:
            print(f"  {name:20s} AUC={m['roc_auc']:.4f}  log-loss={m['log_loss']:.4f}  "
                  f"Brier={m['brier']:.4f}  accuracy={m['accuracy']*100:.1f}%")
    results.sort(key=lambda r: r[0])
    _, name, pipe, m = results[0]
    # Prefer logistic regression unless boosting is clearly better: it is
    # monotonic (doing more never lowers a score), fully explainable, and
    # far less likely to break when scikit-learn is upgraded.
    lr = next(r for r in results if r[1] == "logistic_regression")
    if name != "logistic_regression" and lr[0] - results[0][0] < 0.005:
        _, name, pipe, m = lr
    return name, pipe, m


def save_bundle(pipe, name, metrics, base_rate, trained_on, extra=None):
    os.makedirs(MODEL_DIR, exist_ok=True)
    version = dt.datetime.now().strftime("v4-%Y%m%d-%H%M%S")
    if os.path.exists(MODEL_PATH):
        shutil.copy2(MODEL_PATH, MODEL_PATH.replace(".pkl", ".previous.pkl"))
    bundle = {
        "pipeline": pipe, "model_type": name, "version": version,
        "feature_version": F.FEATURE_VERSION, "sklearn_version": sklearn.__version__,
        "trained_at": dt.datetime.now().isoformat(timespec="seconds"),
        "metrics": metrics, "base_rate": base_rate, "trained_on": trained_on,
    }
    joblib.dump(bundle, MODEL_PATH)
    card = {k: v for k, v in bundle.items() if k != "pipeline"}
    card.update(extra or {})
    with open(CARD_PATH, "w", encoding="utf-8") as f:
        json.dump(card, f, indent=2)
    return version


JOURNEYS = [
    ("Just signed up, nothing else", {}),
    ("Viewed 1 course for 3 min", dict(TotalTimeOnWebsite=180, PageViewsPerVisit=3, CourseType="data-science-analytics")),
    ("+ watched video, read pricing", dict(TotalTimeOnWebsite=420, PageViewsPerVisit=4, VideoWatched=1, PricingPageVisited=1, CourseType="data-science-analytics")),
    ("+ brochure, 2nd visit", dict(TotalVisits=2, TotalTimeOnWebsite=900, PageViewsPerVisit=4, VideoWatched=1, PricingPageVisited=1, BrochureDownloaded=1, CourseType="data-science-analytics")),
    ("+ added to cart", dict(TotalVisits=2, TotalTimeOnWebsite=1000, PageViewsPerVisit=4, VideoWatched=1, PricingPageVisited=1, BrochureDownloaded=1, AddedToCart=1, CourseType="data-science-analytics")),
    ("+ started checkout (abandoned)", dict(TotalVisits=2, TotalTimeOnWebsite=1100, PageViewsPerVisit=5, VideoWatched=1, PricingPageVisited=1, BrochureDownloaded=1, AddedToCart=1, CheckoutStarted=1, CourseType="data-science-analytics")),
    ("Skipped profile, browsed 5 min", dict(CurrentOccupation=None, Specialization=None, City=None, AgeBracket=None, HowDidYouHear=None, TotalTimeOnWebsite=300, PageViewsPerVisit=3)),
    ("Student, very engaged + enquiry", dict(CurrentOccupation="Student", TotalVisits=3, TotalTimeOnWebsite=1500, PageViewsPerVisit=5, VideoWatched=1, PricingPageVisited=1, BrochureDownloaded=1, ChatInitiated=1, EnquirySubmitted=1)),
    ("Unemployed, opted out of email", dict(CurrentOccupation="Unemployed", DoNotEmail="Yes", TotalTimeOnWebsite=200)),
]
JOURNEY_BASE = dict(LeadOrigin="Landing Page Submission", LeadSource="Direct Traffic", DeviceType="Desktop",
                    CurrentOccupation="Working Professional", Specialization="Finance Management",
                    City="Pune", Country="India", AgeBracket="25-30", HowDidYouHear="Online Search",
                    TotalVisits=1, TotalTimeOnWebsite=0, PageViewsPerVisit=1)


def journey_check(pipe):
    rows = [dict(JOURNEY_BASE, **j) for _, j in JOURNEYS]
    p = pipe.predict_proba(F.to_model_frame(rows))[:, 1]
    print("\nSanity check — typical website journeys (Working Professional unless stated):")
    for (label, _), prob in zip(JOURNEYS, p):
        s = prob * 100
        print(f"  {label:38s} {s:5.1f}  {F.persona_for(s):9s}  {F.tier_for(s)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=DATA_PATH)
    args = ap.parse_args()

    if not os.path.exists(args.data):
        print("Dataset not found — generating it first...")
        import generate_dataset
        generate_dataset.generate(60000).to_csv(args.data, index=False)

    df = pd.read_csv(args.data)
    X = F.to_model_frame(df)
    y = df[F.TARGET].astype(int).to_numpy()
    print(f"Rows: {len(df):,}   conversion rate: {y.mean()*100:.1f}%   features: {X.shape[1]}")

    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)
    print("\nCandidates (held-out 20%):")
    name, pipe, metrics = fit_best(X_tr, y_tr, X_te, y_te)
    print(f"\nSelected: {name}")

    p_te = pipe.predict_proba(X_te)[:, 1]
    print("\nAction tiers on held-out leads (does the tier mean what it says?):")
    print(tier_table(y_te, p_te).round(3).to_string())

    # Refit the chosen model on all data before saving
    final = Pipeline([("prep", build_preprocessor()), ("clf", candidates()[name])])
    final.fit(X, y)
    journey_check(final)

    version = save_bundle(final, name, metrics, float(y.mean()),
                          {"synthetic_rows": int(len(df)), "real_rows": 0})
    print(f"\nSaved {MODEL_PATH}\n  version {version}  (scikit-learn {sklearn.__version__})")
    print("The running backend reloads it automatically on the next score.")


if __name__ == "__main__":
    main()
