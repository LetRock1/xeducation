"""
=================================================================
 X EDUCATION CRM — BASE LEAD MODEL (v6)
=================================================================
 Produces the files the backend loads:

     user-backend/ml_models/lead_model.pkl          the live model (base model + live layer)
     user-backend/ml_models/lead_model.starter.pkl  a copy of the fresh base model
     user-backend/ml_models/model_card.json         version, metrics, what it was trained on

 The lead score is   base model (this script)  +  live layer (learned from the CRM's own
 outcomes by the learning loop, user-backend/learning.py). See user-backend/lead_model.py.

 Training data: 60,000 simulated leads from ml/generate_dataset.py, with exactly the
 signals the website records (profile, visits, time, video, pricing, brochure, chat,
 webinar, wishlist, cart, checkout, enquiry, email clicks, WhatsApp, consent). The
 public X Education dataset cannot be used for this: it has none of the website's
 behaviour columns. It is used to test the METHOD on real data instead
 (ml/experiments/model_benchmark.py: same model family, 9 leak-free real columns).

 Two candidates (logistic regression, gradient boosting) are compared on a held-out
 20 %; logistic regression is kept unless boosting is clearly better (lower log-loss).

 Run with the backend's own Python (start-all.bat does this on first start):
     user-backend\\venv\\Scripts\\python.exe ml\\train_model.py
=================================================================
"""
import argparse
import datetime as dt
import json
import os
import shutil
import sys

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "user-backend")
sys.path.insert(0, BACKEND)
import lead_model as LM   # noqa: E402
import ml_features as F   # noqa: E402

MODEL_DIR = os.path.join(BACKEND, "ml_models")
MODEL_PATH = os.path.join(MODEL_DIR, "lead_model.pkl")
STARTER_PATH = os.path.join(MODEL_DIR, "lead_model.starter.pkl")
CARD_PATH = os.path.join(MODEL_DIR, "model_card.json")
DATA_PATH = os.path.join(HERE, "lead_data_v4.csv")
ROWS = 60000

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
            max_iter=400, learning_rate=0.05, max_leaf_nodes=24, min_samples_leaf=40,
            l2_regularization=1.0, early_stopping=True, validation_fraction=0.1,
            n_iter_no_change=25, random_state=42),
    }


def ece(y, p, bins=10):
    """Expected calibration error: mean |predicted - actual| over 10 probability bins."""
    y, p = np.asarray(y), np.asarray(p)
    edges = np.linspace(0, 1, bins + 1)
    total = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (p >= lo) & (p < hi) if hi < 1 else (p >= lo) & (p <= hi)
        if m.any():
            total += m.mean() * abs(p[m].mean() - y[m].mean())
    return float(total)


def metrics(y, p):
    y, p = np.asarray(y), np.asarray(p)
    k = max(1, int(0.1 * len(y)))
    top = np.argsort(-p)[:k]
    return {"roc_auc": round(float(roc_auc_score(y, p)), 4), "log_loss": round(float(log_loss(y, p)), 4),
            "brier": round(float(brier_score_loss(y, p)), 4), "ece": round(ece(y, p), 4),
            "accuracy": round(float(accuracy_score(y, (p >= 0.5).astype(int))), 4),
            "precision_top10": round(float(np.mean(y[top])), 4)}


def tier_table(y, p):
    t = pd.DataFrame({"tier": pd.Series(p * 100).apply(F.tier_for), "y": np.asarray(y), "p": p})
    out = t.groupby("tier").agg(leads=("y", "size"), predicted=("p", "mean"), actual=("y", "mean"))
    order = [name for _, name in F.TIERS]
    return out.reindex([o for o in order if o in out.index])


def atomic_dump(obj, path):
    tmp = path + ".tmp"
    joblib.dump(obj, tmp)
    os.replace(tmp, path)


def write_card(bundle, extra=None):
    card = {k: v for k, v in bundle.items() if k not in ("starter",)}
    card.update(extra or {})
    tmp = CARD_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(card, f, indent=2, default=str)
    os.replace(tmp, CARD_PATH)


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=DATA_PATH)
    args = ap.parse_args()

    if not os.path.exists(args.data):
        print(f"Generating {ROWS:,} simulated leads (ml/generate_dataset.py) ...", flush=True)
        import generate_dataset
        generate_dataset.generate(ROWS).to_csv(args.data, index=False)
    df = pd.read_csv(args.data)
    X = F.to_model_frame(df)
    y = df[F.TARGET].astype(int).to_numpy()
    print(f"Simulated leads: {len(df):,}   bought: {y.mean()*100:.1f}%   inputs: {X.shape[1]} "
          f"(every signal the website records)")

    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)
    print("\nCandidates (held-out 20%):")
    results, fitted = {}, {}
    for name, clf in candidates().items():
        pipe = Pipeline([("prep", build_preprocessor()), ("clf", clf)])
        pipe.fit(X_tr, y_tr)
        results[name] = metrics(y_te, pipe.predict_proba(X_te)[:, 1])
        fitted[name] = pipe
        m = results[name]
        print(f"  {name:20s} AUC={m['roc_auc']:.3f}  log-loss={m['log_loss']:.4f}  Brier={m['brier']:.4f}  "
              f"ECE={m['ece']:.3f}  accuracy={m['accuracy']*100:.1f}%")
    best = min(results, key=lambda n: results[n]["log_loss"])
    if best != "logistic_regression" and results["logistic_regression"]["log_loss"] - results[best]["log_loss"] < 0.005:
        best = "logistic_regression"
    print(f"\nSelected: {best}")
    print("\nTiers on held-out leads (does a tier mean what it says?):")
    print(tier_table(y_te, fitted[best].predict_proba(X_te)[:, 1]).round(3).to_string())

    final = Pipeline([("prep", build_preprocessor()), ("clf", candidates()[best])])
    final.fit(X, y)

    version = dt.datetime.now().strftime("v6-base-%Y%m%d-%H%M%S")
    bundle = {
        "kind": "starter+live", "starter": final, "starter_columns": list(F.MODEL_COLUMNS),
        "live": LM.empty_live(), "model_type": best, "version": version,
        "feature_version": F.FEATURE_VERSION, "sklearn_version": sklearn.__version__,
        "trained_at": dt.datetime.now().isoformat(timespec="seconds"),
        "metrics": results[best], "metrics_all_candidates": results, "base_rate": float(y.mean()),
        "trained_on": {"simulated_leads": int(len(df)), "history_outcomes": 0},
        "starter_version": version,
    }
    print("\nSanity check — typical website journeys (Working Professional unless stated):")
    jp = LM.predict_proba(bundle, F.to_model_frame([dict(JOURNEY_BASE, **j) for _, j in JOURNEYS]))
    for (label, _), p in zip(JOURNEYS, jp):
        print(f"  {label:38s} {p*100:5.1f}  {F.tier_for(p*100)}")

    os.makedirs(MODEL_DIR, exist_ok=True)
    if os.path.exists(MODEL_PATH):
        shutil.copy2(MODEL_PATH, MODEL_PATH.replace(".pkl", ".previous.pkl"))
    atomic_dump(bundle, MODEL_PATH)
    atomic_dump(bundle, STARTER_PATH)
    write_card(bundle, {"note": "Base model trained on simulated leads that carry every signal the website "
                                "records. The live layer starts at zero and is learned by the learning loop "
                                "from this CRM's own outcomes. The same method on the 9,240 real X Education "
                                "leads (leak-free columns only): ml/results/model_benchmark.md."})
    print(f"\nSaved {MODEL_PATH}\n  version {version}  (scikit-learn {sklearn.__version__})")
    print("The running backend reloads it automatically.")


if __name__ == "__main__":
    main()
