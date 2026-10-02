"""
=================================================================
 EXPERIMENT 2 — Next-best-action on a REAL randomized experiment
=================================================================
 Data: ml/data/hillstrom.csv — Kevin Hillstrom's MineThatData e-mail
 experiment (2008), the standard public benchmark for uplift modelling.
 64,000 customers were randomly split into three equal groups:
     Mens e-mail  |  Womens e-mail  |  No e-mail
 and visits, conversions and spend were recorded for the next two weeks.
 Because assignment was random, the probability of each action is KNOWN
 (1/3), so the value of ANY targeting policy can be measured honestly from
 the logged data (inverse-propensity weighting) — no simulator involved.

 Q1  Who should be contacted?  Does ranking customers by predicted UPLIFT
     (extra visits caused by the e-mail) find the persuadable customers better
     than ranking by predicted RESPONSE (likelihood to act — what score-based
     targeting does)?  Metrics: normalised Qini coefficient and uplift in the
     top 10/20/30 %, separately for each e-mail versus no e-mail.

 Q2  Which action, for whom?  Choosing per customer between {mens e-mail,
     womens e-mail, nothing} (our next-best-action) versus one-size-fits-all,
     a recency/monetary rule, response-score targeting and random, at the same
     e-mail budget. Metric: incremental visits / conversions / spend per 1,000
     customers, estimated by inverse-propensity weighting on held-out folds,
     with paired-bootstrap 95 % confidence intervals.

 OURS is the same model family that runs in the product (user-backend/nba_core.py):
 a logistic S-learner whose context c(x) contains the response score's logit
 ("score-anchored") and whose action x context interaction weights are the
 per-action effects:   logit P(y | x, a) = b.c(x) + g_a.c(x),  g_none = 0.
 Baselines: random, recency/monetary (RFM) rule, response model (GBM),
 T-learner (LR, GBM), S-learner (GBM), X-learner (GBM), class transformation
 (LR), and OURS without the score anchor (ablation).

 Everything is cross-fitted (5 folds x 3 repeats): every number is measured
 on customers the models never saw. Models are trained for VISITS (the usual
 primary outcome for this data — only 0.9 % of customers convert);
 conversions and spend are reported for the same decisions.

 Run:  python ml/experiments/hillstrom_uplift.py   (about 4-6 minutes)
       writes ml/results/hillstrom_uplift.{json,md} (+ figures if matplotlib
       is installed)
=================================================================
"""
import json
import os
import time

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data", "hillstrom.csv")
RESULTS = os.path.join(HERE, "..", "results")

SEGMENT_TO_ACTION = {"No E-Mail": "none", "Mens E-Mail": "mens", "Womens E-Mail": "womens"}
TREAT = ["mens", "womens"]
ACTIONS = ["none"] + TREAT
PROPENSITY = 1 / 3            # known: the experiment assigned each action with probability 1/3
OUTCOME = "visit"
SECONDARY = ["conversion", "spend"]
FOLDS, REPEATS, BOOT = 5, 3, 1000
BUDGETS = [0.10, 0.20, 0.30, 0.50, 1.00]
TOP_K = [0.10, 0.20, 0.30]
SEED = 2026
GBM = dict(learning_rate=0.05, max_iter=300, max_leaf_nodes=15, min_samples_leaf=100,
           early_stopping=True, validation_fraction=0.15, n_iter_no_change=20)
NUMERIC = ["recency", "log_history"]
FEATURES = ["recency", "log_history", "mens_buyer", "womens_buyer", "newbie",
            "urban", "rural", "web", "multichannel"]


# ── data ──────────────────────────────────────────────────────────────────────
def load(path=DATA):
    h = pd.read_csv(path)
    X = pd.DataFrame({
        "recency": h["recency"].astype(float),
        "log_history": np.log1p(h["history"].astype(float)),
        "mens_buyer": h["mens"].astype(float),
        "womens_buyer": h["womens"].astype(float),
        "newbie": h["newbie"].astype(float),
        "urban": (h["zip_code"] == "Urban").astype(float),
        "rural": (h["zip_code"] == "Rural").astype(float),
        "web": (h["channel"] == "Web").astype(float),
        "multichannel": (h["channel"] == "Multichannel").astype(float),
    })[FEATURES]
    a = h["segment"].map(SEGMENT_TO_ACTION).to_numpy()
    if pd.isna(a).any():
        raise SystemExit("Unexpected segment values in hillstrom.csv")
    return h, X, a


def balance_check(X, a):
    """Randomization check: standardised mean difference of every feature, each e-mail arm vs control."""
    out = {}
    c = X[a == "none"]
    for t in TREAT:
        g = X[a == t]
        smd = (g.mean() - c.mean()) / np.sqrt((g.var() + c.var()) / 2)
        out[t] = {k: round(float(v), 4) for k, v in smd.items()}
    return out


# ── helpers ───────────────────────────────────────────────────────────────────
def logit(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


class Scaler:
    def fit(self, X):
        self.mu = X[NUMERIC].mean()
        self.sd = X[NUMERIC].std().replace(0, 1)
        return self

    def __call__(self, X):
        Z = X.copy()
        Z[NUMERIC] = (Z[NUMERIC] - self.mu) / self.sd
        return Z.to_numpy(dtype=float)


def gbm_clf(seed):
    return HistGradientBoostingClassifier(random_state=seed, **GBM)


def gbm_reg(seed):
    return HistGradientBoostingRegressor(random_state=seed, **GBM)


def s_design(ctx, actions):
    """[c | 1{a=mens}.c | 1{a=womens}.c] — the same S-learner design as nba_core.design."""
    actions = np.asarray(actions)
    return np.hstack([ctx] + [ctx * (actions == t)[:, None] for t in TREAT])


class ScoreAnchoredSLearner:
    """OURS — the product's next-best-action model family (user-backend/nba_core.py):
    context c(x) = [1, logit(response score), features];  logit P(y|x,a) = b.c(x) + g_a.c(x).
    The response score is a gradient-boosting P(y|x) pooled over actions (the lead-score analogue),
    cross-fitted on the training rows so the S-learner never sees in-sample scores."""

    def __init__(self, seed, anchored=True, scaler=None):
        self.seed, self.anchored, self.sc = seed, anchored, scaler

    def _ctx(self, X, base):
        Z = self.sc(X)
        cols = [np.ones((len(Z), 1))] + ([logit(base)[:, None]] if self.anchored else []) + [Z]
        return np.hstack(cols)

    def fit(self, X, a, y):
        self.sc = self.sc or Scaler().fit(X)
        Xn = X.to_numpy(dtype=float)
        base = np.zeros(len(X))
        if self.anchored:
            inner = StratifiedKFold(3, shuffle=True, random_state=self.seed)
            strata = pd.Series(a).astype(str) + "_" + pd.Series(y).astype(int).astype(str)
            for itr, ite in inner.split(Xn, strata):
                base[ite] = gbm_clf(self.seed).fit(Xn[itr], y[itr]).predict_proba(Xn[ite])[:, 1]
            self.base_model = gbm_clf(self.seed).fit(Xn, y)
        self.clf = LogisticRegression(C=1.0, max_iter=5000, fit_intercept=False)
        self.clf.fit(s_design(self._ctx(X, base), a), y)
        return self

    def predict(self, X):
        base = self.base_model.predict_proba(X.to_numpy(dtype=float))[:, 1] if self.anchored else np.zeros(len(X))
        ctx = self._ctx(X, base)
        return {act: self.clf.predict_proba(s_design(ctx, np.full(len(X), act)))[:, 1] for act in ACTIONS}


def fit_ours(X, a, y, seed, anchored=True, scaler=None):
    return ScoreAnchoredSLearner(seed, anchored, scaler).fit(X, a, y)


# ── uplift learners (each returns p_hat[action] and/or tau_hat[treatment] for the test rows) ──
def fit_predict_all(Xtr, atr, ytr, Xte, seed):
    """Fit every method on the training fold, predict for the test fold."""
    out = {}
    sc = Scaler().fit(Xtr)
    Ztr, Zte = sc(Xtr), sc(Xte)
    Xtr_np, Xte_np = Xtr.to_numpy(dtype=float), Xte.to_numpy(dtype=float)

    # OURS (+ ablation without the score anchor)
    for name, anchored in (("Ours: score-anchored S-learner (LR)", True), ("Ours without score anchor (ablation)", False)):
        model = fit_ours(Xtr, atr, ytr, seed, anchored=anchored, scaler=sc)
        out[name] = {"p": model.predict(Xte), "model": model}

    # T-learners: one model per action
    t_lr, t_gbm = {}, {}
    for a in ACTIONS:
        m = atr == a
        t_lr[a] = LogisticRegression(C=1.0, max_iter=5000).fit(Ztr[m], ytr[m]).predict_proba(Zte)[:, 1]
        g = gbm_clf(seed).fit(Xtr_np[m], ytr[m])
        t_gbm[a] = {"model": g, "te": g.predict_proba(Xte_np)[:, 1]}
    out["T-learner (LR)"] = {"p": t_lr}
    out["T-learner (GBM)"] = {"p": {a: t_gbm[a]["te"] for a in ACTIONS}}
    # response-score targeting: the same per-action GBMs, ranked by P(visit | e-mail) — no control comparison
    out["Response model (GBM)"] = {"response": {t: t_gbm[t]["te"] for t in TREAT}}

    # S-learner (GBM): action as an input feature
    A_tr = np.column_stack([(atr == t).astype(float) for t in TREAT])
    s_g = gbm_clf(seed).fit(np.hstack([Xtr_np, A_tr]), ytr)
    out["S-learner (GBM)"] = {"p": {a: s_g.predict_proba(np.hstack([Xte_np, np.column_stack(
        [np.full(len(Xte_np), float(a == t)) for t in TREAT])]))[:, 1] for a in ACTIONS}}

    # X-learner (GBM), each e-mail vs control (within-pair propensity 1/2)
    tau_x = {}
    m0 = t_gbm["none"]["model"]
    for t in TREAT:
        mt = t_gbm[t]["model"]
        it, ic = atr == t, atr == "none"
        d1 = ytr[it] - m0.predict_proba(Xtr_np[it])[:, 1]
        d0 = mt.predict_proba(Xtr_np[ic])[:, 1] - ytr[ic]
        r1 = gbm_reg(seed).fit(Xtr_np[it], d1)
        r0 = gbm_reg(seed).fit(Xtr_np[ic], d0)
        tau_x[t] = 0.5 * r0.predict(Xte_np) + 0.5 * r1.predict(Xte_np)
    out["X-learner (GBM)"] = {"tau": tau_x}

    # class transformation (Jaskowski & Jaroszewicz 2012), each e-mail vs control
    tau_ct = {}
    for t in TREAT:
        m = np.isin(atr, ["none", t])
        z = np.where(atr[m] == t, ytr[m], 1 - ytr[m])
        c = LogisticRegression(C=1.0, max_iter=5000).fit(Ztr[m], z)
        tau_ct[t] = 2 * c.predict_proba(Zte)[:, 1] - 1
    out["Class transformation (LR)"] = {"tau": tau_ct}

    for name, d in out.items():
        if "p" in d and "tau" not in d:
            d["tau"] = {t: d["p"][t] - d["p"]["none"] for t in TREAT}
    return out


def rfm_score(X):
    """Classic recency / monetary targeting: recent, high-spending customers first."""
    z = lambda s: (s - s.mean()) / s.std()
    return (z(-X["recency"]) + z(X["log_history"])).to_numpy()


# ── Q1 metrics ────────────────────────────────────────────────────────────────
def qini_curve(y, t, score):
    """Qini curve (Radcliffe 2007): treated responders minus control responders scaled to the
    treated count, after targeting the top-n customers. Ties in the score are grouped."""
    order = np.argsort(-score, kind="mergesort")
    y, t, s = y[order], t[order], score[order]
    n_t, n_c = np.cumsum(t), np.cumsum(1 - t)
    y_t, y_c = np.cumsum(y * t), np.cumsum(y * (1 - t))
    curve = y_t - y_c * np.divide(n_t, n_c, out=np.zeros(len(n_t)), where=n_c > 0)
    idx = np.r_[np.where(np.diff(s))[0], len(s) - 1]
    return np.r_[0, idx + 1].astype(float), np.r_[0, curve[idx]]


def qini_coefficient(y, t, score):
    """Normalised Qini: (area model − area random) / (area perfect − area random)."""
    x, q = qini_curve(y, t, score)
    xp, qp = qini_curve(y, t, (y * t - y * (1 - t)).astype(float))
    rand = x[-1] * q[-1] / 2
    return float((np.trapezoid(q, x) - rand) / (np.trapezoid(qp, xp) - rand))


def uplift_at(y, t, score, frac):
    n = int(round(frac * len(y)))
    top = np.argsort(-score, kind="mergesort")[:n]
    yt, tt = y[top], t[top]
    return float(yt[tt == 1].mean() - yt[tt == 0].mean())


# ── Q2 policies ───────────────────────────────────────────────────────────────
def budget_policy(gain, action, budget):
    """E-mail the top `budget` share by gain, with their chosen e-mail — only if the gain is positive."""
    n = len(gain)
    k = int(round(budget * n))
    order = np.argsort(-gain, kind="mergesort")[:k]
    d = np.full(n, "none", dtype=object)
    sel = order[gain[order] > 0]
    d[sel] = action[sel]
    return d


def policies_for_fold(preds, Xte, best_arm, budget, rng):
    pol = {}
    n = len(Xte)
    for name, d in preds.items():
        if "tau" in d:
            T = np.column_stack([d["tau"][t] for t in TREAT])
            pol[f"NBA · {name}"] = budget_policy(T.max(1), np.array(TREAT)[T.argmax(1)], budget)
        if "response" in d:
            R = np.column_stack([d["response"][t] for t in TREAT])
            pol[f"Response-score targeting ({name.split('(')[1].rstrip(')')})"] = \
                budget_policy(R.max(1), np.array(TREAT)[R.argmax(1)], budget)
    mens_only = (Xte["mens_buyer"] == 1) & (Xte["womens_buyer"] == 0)
    womens_only = (Xte["mens_buyer"] == 0) & (Xte["womens_buyer"] == 1)
    rule_action = np.where(mens_only, "mens", np.where(womens_only, "womens", best_arm))
    pol["RFM rule + e-mail matching past purchases"] = budget_policy(rfm_score(Xte) + 1e3, rule_action, budget)
    pol[f"Best single e-mail ({best_arm}) to random customers"] = budget_policy(
        rng.random(n) + 1, np.full(n, best_arm, dtype=object), budget)
    pol["Random customers, random e-mail"] = budget_policy(
        rng.random(n) + 1, np.where(rng.random(n) < 0.5, "mens", "womens"), budget)
    return pol


def ips_contrib(decisions, a, y):
    """Per-customer inverse-propensity contribution: y * 1{logged action == policy action} / P(logged action)."""
    return y * (a == decisions) / PROPENSITY


def bootstrap_means(M, B=BOOT, chunk=100, seed=SEED):
    """Bootstrap means of every row of M (series x customers) with the SAME customer resamples for every
    series (paired). Returns (series x B)."""
    n = M.shape[1]
    out = []
    for c in range(0, B, chunk):
        m = min(chunk, B - c)
        idx = np.random.default_rng(seed + c).integers(0, n, (m, n))
        counts = np.bincount((idx + np.arange(m)[:, None] * n).ravel(), minlength=m * n).reshape(m, n)
        out.append(M @ counts.T.astype(float) / n)
    return np.hstack(out)


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    t0 = time.time()
    os.makedirs(RESULTS, exist_ok=True)
    h, X, a = load()
    y = h[OUTCOME].to_numpy(dtype=float)
    ys = {o: h[o].to_numpy(dtype=float) for o in [OUTCOME] + SECONDARY}
    n = len(X)
    print(f"Hillstrom: {n:,} customers · arms " + ", ".join(f"{k}={int((a == k).sum()):,}" for k in ACTIONS))
    arm_rates = {k: {o: float(ys[o][a == k].mean()) for o in ys} for k in ACTIONS}
    for k in ACTIONS:
        print(f"  {k:7s} visit {arm_rates[k]['visit']:.4f}  conversion {arm_rates[k]['conversion']:.4f}  "
              f"spend ${arm_rates[k]['spend']:.3f}")
    balance = balance_check(X, a)
    max_smd = max(abs(v) for d in balance.values() for v in d.values())
    print(f"  randomization check: max |standardised mean difference| = {max_smd:.4f}")

    q1 = {}                      # method -> treatment -> metric -> list over folds
    contrib = {}                 # (budget, policy) -> outcome -> sum over repeats of per-customer contributions
    curves = {}                  # Qini curves of repeat 0 / fold 0 for the figure
    coef_rows = None

    for r in range(REPEATS):
        skf = StratifiedKFold(FOLDS, shuffle=True, random_state=SEED + r)
        strata = pd.Series(a).astype(str) + "_" + pd.Series(y.astype(int)).astype(str)
        decisions = {}
        for f, (tr, te) in enumerate(skf.split(X, strata)):
            seed = SEED + 100 * r + f
            rng = np.random.default_rng(seed)
            Xtr, Xte = X.iloc[tr], X.iloc[te]
            preds = fit_predict_all(Xtr, a[tr], y[tr], Xte, seed)
            best_arm = max(TREAT, key=lambda t: y[tr][a[tr] == t].mean())

            # Q1: per e-mail vs control, on the held-out customers of those two arms
            for t in TREAT:
                m = np.isin(a[te], ["none", t])
                yy, tt = y[te][m], (a[te][m] == t).astype(float)
                scores = {"Random": rng.random(m.sum()), "RFM rule (recency + spend)": rfm_score(Xte[m])}
                for name, d in preds.items():
                    scores[name] = (d["tau"][t] if "tau" in d else d["response"][t])[m]
                for name, s in scores.items():
                    rec = q1.setdefault(name, {}).setdefault(t, {})
                    rec.setdefault("qini", []).append(qini_coefficient(yy, tt, s))
                    for k in TOP_K:
                        rec.setdefault(f"uplift_top{int(k * 100)}", []).append(uplift_at(yy, tt, s, k))
                    if r == 0 and f == 0:
                        curves.setdefault(t, {})[name] = qini_curve(yy, tt, s)
            # Q2: per-customer action choice under each e-mail budget
            for b in BUDGETS:
                for name, d in policies_for_fold(preds, Xte, best_arm, b, rng).items():
                    decisions.setdefault((b, name), np.full(n, "none", dtype=object))[te] = d
            print(f"  repeat {r + 1}/{REPEATS} fold {f + 1}/{FOLDS} done ({time.time() - t0:,.0f}s)")
        for key, d in decisions.items():
            for o in ys:
                c = ips_contrib(d, a, ys[o])
                acc = contrib.setdefault(key, {})
                acc[o] = acc.get(o, 0) + c / REPEATS
            contrib[key]["_emailed"] = contrib[key].get("_emailed", 0) + (d != "none") / REPEATS
            contrib[key]["_mens"] = contrib[key].get("_mens", 0) + (d == "mens") / REPEATS

    # interpretable effects of OURS fitted on all customers (for the report)
    clf = fit_ours(X, a, y, SEED).clf
    names = ["intercept", "score_logit"] + FEATURES
    w = clf.coef_[0].reshape(1 + len(TREAT), len(names))
    coef_rows = {"baseline": dict(zip(names, np.round(w[0], 3).tolist()))}
    coef_rows.update({f"effect of {t} e-mail": dict(zip(names, np.round(w[i + 1], 3).tolist()))
                      for i, t in enumerate(TREAT)})

    # ── summarise Q1 ──
    q1_summary = {}
    for name, per_t in q1.items():
        q1_summary[name] = {t: {m: {"mean": float(np.mean(v)), "sd": float(np.std(v))} for m, v in mets.items()}
                            for t, mets in per_t.items()}

    # ── summarise Q2 (IPS on all 64,000 held-out decisions, averaged over repeats; paired bootstrap) ──
    none_value = {o: ips_contrib(np.full(n, "none", dtype=object), a, ys[o]) for o in ys}
    q2 = {}
    ours_key = "NBA · Ours: score-anchored S-learner (LR)"
    for b in BUDGETS:
        names_b = [k[1] for k in contrib if k[0] == b]
        series, keys = [], []
        for name in names_b:
            for o in ys:
                series.append(contrib[(b, name)][o] - none_value[o]); keys.append((name, o, "inc"))
                if name != ours_key:
                    series.append(contrib[(b, ours_key)][o] - contrib[(b, name)][o]); keys.append((name, o, "diff"))
        M = np.vstack(series)
        boots = bootstrap_means(M) * 1000
        means = M.mean(1) * 1000
        q2[b] = {}
        for name in names_b:
            c = contrib[(b, name)]
            q2[b][name] = {"emailed_share": float(np.mean(c["_emailed"])),
                           "mens_share_of_emails": float(np.mean(c["_mens"]) / max(np.mean(c["_emailed"]), 1e-9))}
        for j, (name, o, kind) in enumerate(keys):
            lo, hi = np.percentile(boots[j], [2.5, 97.5])
            if kind == "inc":
                q2[b][name][o] = {"incremental_per_1000": float(means[j]), "ci95": [float(lo), float(hi)]}
        for j, (name, o, kind) in enumerate(keys):
            if kind == "diff":
                lo, hi = np.percentile(boots[j], [2.5, 97.5])
                q2[b][name][o]["ours_minus_this"] = {"mean": float(means[j]), "ci95": [float(lo), float(hi)],
                                                     "share_of_resamples_ours_not_better": float(np.mean(boots[j] <= 0))}

    result = {"data": {"customers": n, "arms": {k: int((a == k).sum()) for k in ACTIONS},
                       "arm_rates": arm_rates, "balance_smd": balance, "max_abs_smd": max_smd},
              "design": {"folds": FOLDS, "repeats": REPEATS, "bootstrap": BOOT, "outcome_trained": OUTCOME,
                         "propensity": PROPENSITY, "gbm_params": GBM, "budgets": BUDGETS},
              "q1_targeting": q1_summary, "q2_policy_value": {str(b): v for b, v in q2.items()},
              "ours_coefficients_logodds": coef_rows, "runtime_s": round(time.time() - t0, 1)}
    with open(os.path.join(RESULTS, "hillstrom_uplift.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
    write_markdown(result)
    plot(curves, q2)
    print(f"\nSaved {os.path.relpath(RESULTS)}/hillstrom_uplift.json and .md  ({time.time() - t0:,.0f}s)")


def write_markdown(R):
    L = ["# Next-best-action on a real randomized experiment (Hillstrom, 64,000 customers)", ""]
    d = R["data"]
    L.append(f"Arms: " + ", ".join(f"{k} {v:,}" for k, v in d["arms"].items())
             + f". Randomization check: max |standardised mean difference| = {d['max_abs_smd']:.3f}.")
    L.append("")
    L.append("| Arm | Visit rate | Conversion rate | Spend / customer |")
    L.append("|---|---|---|---|")
    for k, v in d["arm_rates"].items():
        L.append(f"| {k} | {v['visit'] * 100:.2f}% | {v['conversion'] * 100:.2f}% | ${v['spend']:.3f} |")
    L += ["", f"Cross-fitted: {R['design']['folds']} folds × {R['design']['repeats']} repeats; "
              f"models trained for **{R['design']['outcome_trained']}**.", ""]

    L += ["## Q1 — Who to contact: ranking quality per e-mail vs no e-mail", "",
          "Normalised Qini coefficient (0 = random, 1 = perfect) and uplift in visit rate (percentage points) "
          f"among the top-ranked customers; mean ± sd over {R['design']['folds'] * R['design']['repeats']} held-out folds.", ""]
    for t in TREAT:
        L.append(f"### {t.capitalize()} e-mail vs no e-mail")
        L.append("")
        L.append("| Method | Qini coefficient | Uplift top 10% | Uplift top 20% | Uplift top 30% |")
        L.append("|---|---|---|---|---|")
        rows = sorted(R["q1_targeting"].items(), key=lambda kv: -kv[1][t]["qini"]["mean"])
        for name, per_t in rows:
            m = per_t[t]
            L.append(f"| {name} | {m['qini']['mean']:.3f} ± {m['qini']['sd']:.3f} | "
                     + " | ".join(f"{m[f'uplift_top{k}']['mean'] * 100:+.2f} ± {m[f'uplift_top{k}']['sd'] * 100:.2f}"
                                  for k in (10, 20, 30)) + " |")
        L.append("")

    L += ["## Q2 — Which action for whom: value of the targeting policy", "",
          "Incremental outcomes per 1,000 customers versus e-mailing nobody, estimated by inverse-propensity "
          "weighting on held-out customers (95% bootstrap CI). *Ours − policy* is the paired difference.", ""]
    ours = "NBA · Ours: score-anchored S-learner (LR)"
    for b, rows in R["q2_policy_value"].items():
        L.append(f"### E-mail budget: {float(b) * 100:.0f}% of customers")
        L.append("")
        L.append("| Policy | E-mailed | Extra visits /1000 | Extra conversions /1000 | Extra spend /1000 ($) | Ours − policy (visits) |")
        L.append("|---|---|---|---|---|---|")
        for name, v in sorted(rows.items(), key=lambda kv: -kv[1]["visit"]["incremental_per_1000"]):
            fmt = lambda o, p=1: (f"{v[o]['incremental_per_1000']:.{p}f} "
                                  f"[{v[o]['ci95'][0]:.{p}f}, {v[o]['ci95'][1]:.{p}f}]")
            diff = v["visit"].get("ours_minus_this")
            dtxt = "—" if name == ours else f"{diff['mean']:+.1f} [{diff['ci95'][0]:+.1f}, {diff['ci95'][1]:+.1f}]"
            L.append(f"| {'**' + name + '**' if name == ours else name} | {v['emailed_share'] * 100:.0f}% | "
                     f"{fmt('visit')} | {fmt('conversion', 2)} | {fmt('spend', 0)} | {dtxt} |")
        L.append("")

    L += ["## Interpretable effects learned by our model (log-odds, all customers)", "",
          "Rows: context term. *effect of X e-mail* = how much that e-mail changes the log-odds of a visit for "
          "customers with that attribute (numeric features standardised).", "",
          "| Term | " + " | ".join(R["ours_coefficients_logodds"].keys()) + " |",
          "|---|" + "---|" * len(R["ours_coefficients_logodds"])]
    terms = list(next(iter(R["ours_coefficients_logodds"].values())).keys())
    for term in terms:
        L.append(f"| {term} | " + " | ".join(f"{v[term]:+.3f}" for v in R["ours_coefficients_logodds"].values()) + " |")
    with open(os.path.join(RESULTS, "hillstrom_uplift.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


def plot(curves, q2):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  (matplotlib not installed — skipping figures)")
        return
    fig_dir = os.path.join(RESULTS, "figures")
    os.makedirs(fig_dir, exist_ok=True)
    keep = ["Ours: score-anchored S-learner (LR)", "T-learner (GBM)", "X-learner (GBM)",
            "Response model (GBM)", "RFM rule (recency + spend)", "Random"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for ax, t in zip(axes, TREAT):
        for name in keep:
            if name in curves.get(t, {}):
                x, q = curves[t][name]
                ax.plot(x / x[-1] * 100, q, label=name, lw=2.2 if name.startswith("Ours") else 1.2)
        ax.set_title(f"Qini curve — {t} e-mail vs none (held-out fold)")
        ax.set_xlabel("customers targeted (%)")
        ax.set_ylabel("extra visits")
        ax.grid(alpha=.3)
    axes[0].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(os.path.join(fig_dir, "hillstrom_qini.png"), dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    names = sorted({k for b in q2 for k in q2[b]})
    for name in names:
        if not (name.startswith("NBA · Ours: score") or "T-learner (GBM)" in name or "Response" in name
                or "RFM" in name or "Best single" in name or "Random" in name):
            continue
        xs = [b * 100 for b in BUDGETS]
        ys_ = [q2[b][name]["visit"]["incremental_per_1000"] for b in BUDGETS]
        ax.plot(xs, ys_, marker="o", label=name, lw=2.2 if "Ours" in name else 1.2)
    ax.set_xlabel("e-mail budget (% of customers)")
    ax.set_ylabel("extra visits per 1,000 customers (IPS)")
    ax.set_title("Policy value on held-out customers")
    ax.grid(alpha=.3)
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(os.path.join(fig_dir, "hillstrom_policy_value.png"), dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
