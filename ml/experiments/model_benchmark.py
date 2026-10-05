"""
Does our modelling method hold up on REAL data? A fair comparison on the 9,240 real X Education
leads, with only the 9 columns known before any contact (no leaked columns).

The CRM's own lead model is trained on simulated leads that carry every signal the website records
(video, pricing, cart, checkout ...), choosing between the same two families tested here (logistic
regression vs gradient boosting) by held-out log-loss. The public file has none of those website
signals, so it cannot train or directly test the CRM's model; it CAN show whether the method works on
real leads without leakage. The CRM's base model applied to these real leads as they are is reported
too, for honesty.

Models: logistic regression, gradient boosting, random forest, two neural networks (MLP), a
boosting + neural-network average, and TabPFN (a pretrained transformer for small tables, Nature 2025)
when it is installed (pip install tabpfn; it downloads its weights on first use).
Also shown, for contrast: gradient boosting WITH the post-contact columns most public notebooks use
(Tags, Lead Quality, Last Activity ...) — it looks far better and is useless for a new lead.

5-fold stratified cross-validation, 3 seeds. Run:  python ml/experiments/model_benchmark.py
Writes ml/results/model_benchmark.md and .json
"""
import json
import os
import sys
import time
import warnings

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path[:0] = [os.path.join(ROOT, "user-backend"), os.path.join(ROOT, "ml")]
warnings.filterwarnings("ignore")
import ml_features as F   # noqa: E402
import real_leads as RL   # noqa: E402
import train_model as T   # noqa: E402

SEEDS = (42, 7, 2026)
LEAKY = ["Tags", "Lead Quality", "Last Notable Activity", "Last Activity", "Lead Profile"]


def models():
    out = {
        "Gradient boosting": lambda: T.candidates()["gradient_boosting"],
        "Logistic regression": lambda: LogisticRegression(C=0.5, max_iter=3000),
        "Random forest": lambda: RandomForestClassifier(n_estimators=500, min_samples_leaf=10, n_jobs=-1, random_state=0),
        "Neural network, 2 hidden layers (64-32)": lambda: MLPClassifier(hidden_layer_sizes=(64, 32), alpha=1e-3,
                                                                       early_stopping=True, max_iter=500, random_state=0),
        "Neural network, 3 hidden layers (128-64-32)": lambda: MLPClassifier(hidden_layer_sizes=(128, 64, 32), alpha=1e-2,
                                                                           early_stopping=True, max_iter=500, random_state=0),
        "Neural network, calibrated": lambda: CalibratedClassifierCV(MLPClassifier(hidden_layer_sizes=(64, 32), alpha=1e-3,
                                                                     early_stopping=True, max_iter=500, random_state=0),
                                                                     method="isotonic", cv=3),
    }
    try:
        from tabpfn import TabPFNClassifier   # optional
        out["TabPFN (pretrained transformer)"] = lambda: TabPFNClassifier(device="cpu")
    except Exception:
        pass
    return out


def main():
    t0 = time.time()
    rows, y = RL.load_real_leads()
    frame = F.to_model_frame(rows)
    res = {}
    for seed in SEEDS:
        oof = {}
        for tr, te in StratifiedKFold(5, shuffle=True, random_state=seed).split(frame, y):
            for name, make in models().items():
                pipe = Pipeline([("prep", RL.build_real_preprocessor()), ("clf", make())])
                pipe.fit(frame.iloc[tr][RL.REAL_COLUMNS], y[tr])
                oof.setdefault(name, np.zeros(len(y)))[te] = pipe.predict_proba(frame.iloc[te][RL.REAL_COLUMNS])[:, 1]
        oof["Boosting + neural network, averaged"] = (oof["Gradient boosting"] + oof["Neural network, calibrated"]) / 2
        for k, p in oof.items():
            res.setdefault(k, []).append(T.metrics(y, p))
        print(f"  seed {seed} done ({time.time() - t0:.0f} s)", flush=True)
    d = pd.read_csv(RL.REAL_DATA)
    leaky = frame.copy()
    for c in LEAKY:
        leaky[c] = d[c].fillna("Missing").astype(str)
    prep = ColumnTransformer([("base", RL.build_real_preprocessor(), RL.REAL_COLUMNS),
                              ("leak", OneHotEncoder(handle_unknown="ignore", sparse_output=False), LEAKY)])
    p = np.zeros(len(y))
    for tr, te in StratifiedKFold(5, shuffle=True, random_state=42).split(leaky, y):
        pipe = Pipeline([("prep", prep), ("clf", T.candidates()["gradient_boosting"])])
        pipe.fit(leaky.iloc[tr], y[tr])
        p[te] = pipe.predict_proba(leaky.iloc[te])[:, 1]
    leak = T.metrics(y, p)
    leak["accuracy"] = float(((p >= 0.5) == y).mean())
    # the CRM's own base model (trained on simulated leads), applied to the real leads as they are
    transfer = None
    starter = os.path.join(ROOT, "user-backend", "ml_models", "lead_model.starter.pkl")
    if os.path.exists(starter):
        import joblib
        import lead_model as LM
        pt = LM.predict_proba(joblib.load(starter), frame)
        transfer = T.metrics(y, pt)
        transfer["mean_predicted"] = float(pt.mean())
    summary = {}
    for k, ms in res.items():
        summary[k] = {m: (float(np.mean([x[m] for x in ms])), float(np.std([x[m] for x in ms])))
                      for m in ("roc_auc", "log_loss", "brier", "ece", "precision_top10")}
    order = sorted(summary, key=lambda k: summary[k]["log_loss"][0])
    lines = ["# Our lead-scoring method on real data (9,240 real X Education leads, 9 leak-free columns)", "",
             "5-fold cross-validation x 3 seeds (mean ± sd). Lower log-loss / Brier / calibration error is better.", "",
             "| Model | AUC | Log-loss | Brier | Calibration error | Bought among the top 10% |", "|---|---|---|---|---|---|"]
    for k in order:
        s = summary[k]
        lines.append(f"| {k} | {s['roc_auc'][0]:.3f} ± {s['roc_auc'][1]:.3f} | {s['log_loss'][0]:.4f} ± {s['log_loss'][1]:.4f} | "
                     f"{s['brier'][0]:.4f} | {s['ece'][0]:.3f} | {s['precision_top10'][0]:.1%} |")
    if not any("TabPFN" in k for k in summary):
        lines += ["", "TabPFN was not installed here, so it is not in the table (pip install tabpfn to add it)."]
    lines += ["", f"For contrast — gradient boosting WITH the post-contact columns ({', '.join(LEAKY)}): "
                  f"AUC {leak['roc_auc']:.3f}, accuracy {leak['accuracy']:.1%}. Those columns are written by sales after "
                  "contacting the lead, so a new lead never has them: that number cannot be reached in real use."]
    if transfer:
        lines += ["", f"The CRM's own base model (trained only on simulated leads) applied to these real leads as they are: "
                      f"AUC {transfer['roc_auc']:.3f}, average predicted chance {transfer['mean_predicted']:.1%} vs "
                      f"{y.mean():.1%} who actually bought. The real file has none of the website signals (video, pricing, "
                      "cart, checkout ...) the model mostly relies on, so it cannot be judged on this file. In the running "
                      "CRM every lead has those signals, and the learning loop corrects the base model from the CRM's own "
                      "outcomes, checked on the untouched control group."]
    os.makedirs(os.path.join(ROOT, "ml", "results"), exist_ok=True)
    with open(os.path.join(ROOT, "ml", "results", "model_benchmark.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(ROOT, "ml", "results", "model_benchmark.json"), "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "with_leaky_columns": leak, "crm_base_model_as_is": transfer}, f, indent=2)
    print("\n".join(lines))
    print(f"\n({time.time() - t0:.0f} s) Saved ml/results/model_benchmark.md")


if __name__ == "__main__":
    main()
