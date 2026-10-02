"""
=================================================================
 EXPERIMENT 3 — Does next-best-action still win when our assumptions are WRONG?
=================================================================
 The policy comparison in train_uplift.py scores every policy against a
 simulator whose response assumptions we wrote ourselves (nba_simulation.py)
 — and our interpretable uplift model has the same functional form as that
 simulator. A fair reviewer will ask whether the advantage is just that.
 This study removes the advantage on purpose:

   documented   the documented assumptions (as in train_uplift.py)
   null         no action changes anything — only costs and discounts are real.
                The right answer is to do nothing; does the model learn that?
   reversed     the opposite world: discounts move the hottest leads, calls work
                on cold leads — the world in which a tier playbook is "right"
   hidden       effects driven by things the interpretable model cannot see,
                non-linearly: hidden intent (undecided people are the
                persuadable ones), age, specialisation and device
   random x20   20 randomly drawn worlds. Each mixes a part that is linear in
                the model's context with a part driven by hidden intent and by
                random categorical attributes; the HIDDEN SHARE lambda is drawn
                uniformly from 0 (fully representable) to 1 (fully hidden).

 In every world the models only see a randomized campaign (each lead got one
 random allowed action; only its outcome is observed) — the same kind of data
 the closed loop collects — and are scored on 30,000 fresh leads against that
 world's truth.

 Compared:
   ours            interpretable logistic S-learner on the fixed context (nba_core)
   flexible        gradient-boosting S-learner on all features (nba_core.FlexibleSLearner)
   champion/challenger  the family chosen by the closed loop's own rule: fit both
                   on 75 % of the logged decisions, estimate each greedy policy's
                   profit on the other 25 % by self-normalised inverse-propensity
                   weighting (no access to the truth), keep the better family
   the six fixed policies of train_uplift.py, and the oracle (knows the truth)

 Run (after train-model.bat):  python ml/experiments/nba_robustness.py   (~15 min)
 Writes ml/results/nba_robustness.{json,md} (+ figure if matplotlib is installed)
=================================================================
"""
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ML = os.path.dirname(HERE)
sys.path.insert(0, ML)
import generate_dataset as G          # noqa: E402
import nba_simulation as S            # noqa: E402
import train_model as T               # noqa: E402
import train_uplift as U              # noqa: E402

F, N = S.F, S.N
RESULTS = os.path.join(ML, "results")
N_TRAIN, N_TEST = 60000, 30000
SELECT_SHARE = 0.75
N_RANDOM = 20
TRAIN_SIZES = [1000, 3000, 10000, 30000, 60000]
OURS = "Next-best-action (ours, interpretable)"
FLEX = "Next-best-action (flexible GBM)"
SEL = "Next-best-action (champion/challenger pick)"
ORACLE = "Oracle (knows true effects)"
CTX = {name: i for i, name in enumerate(N.CONTEXT_NAMES)}
NAMED = ["documented", "null", "reversed", "hidden"]
CAT_DRIVERS = ["AgeBracket", "Specialization", "DeviceType", "City", "LeadSource", "CurrentOccupation"]


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


# ── worlds: true effect of each action on the log-odds of buying ──────────────
def world_info(raw):
    frame = F.to_model_frame(raw)
    return {"frame": frame, "ctx": N.context(frame, np.full(len(frame), 0.5)),
            "intent": raw["_intent"].to_numpy(), "p_none": raw["_p_true"].to_numpy(),
            "blocked": S._blocked_matrix(frame), "price": S.prices_for(frame)}


def eff_documented(info, _=None):
    return {a: info["ctx"] @ np.asarray(S.TRUE_EFFECTS[a], dtype=float) for a in N.TREATMENTS}


def eff_null(info, _=None):
    return {a: np.zeros(len(info["frame"])) for a in N.TREATMENTS}


def eff_reversed(info, _=None):
    #             bias  base price  high  cart  prof  email  wa   low_eng
    W = {"email_info":      [0.05, 0, 0.00, 0.00, 0.00, 0.00, -0.10, 0.0, 0.25],
         "email_coupon_10": [0.00, 0, -0.30, 0.80, 0.30, 0.25, 0.00, 0.0, -0.10],
         "email_coupon_20": [0.05, 0, -0.40, 1.20, 0.40, 0.35, 0.00, 0.0, -0.15],
         "call":            [0.00, 0, 0.30, -0.40, -0.30, -0.40, 0.00, 0.0, 0.90],
         "whatsapp":        [0.05, 0, 0.00, 0.00, 0.00, 0.00, 0.00, 0.10, 0.10]}
    return {a: info["ctx"] @ np.asarray(W[a], dtype=float) for a in N.TREATMENTS}


def eff_hidden(info, _=None):
    f, z = info["frame"], info["intent"]
    undecided = np.exp(-z ** 2)                                       # bell-shaped in hidden intent
    young = f["AgeBracket"].isin(["18-24", "25-30"]).to_numpy(dtype=float)
    tech = f["Specialization"].isin(["IT Projects Management", "E-Commerce", "Finance Management",
                                     "Banking, Investment And Insurance"]).to_numpy(dtype=float)
    mobile = (f["DeviceType"] == "Mobile").to_numpy(dtype=float)
    return {"email_info": 0.45 * undecided - 0.25 * mobile,
            "email_coupon_10": 1.0 * undecided * young - 0.3 * (z > 1),
            "email_coupon_20": 1.5 * undecided * young - 0.5 * (z > 1),
            "call": 1.1 * tech * (z > 0) - 0.7 * (z < -0.5),
            "whatsapp": 0.35 * mobile * undecided}


def random_world(seed):
    """Draw a random world once (so train and test leads share it). Returns (effects_fn, hidden share)."""
    rng = np.random.default_rng(10_000 + seed)
    lam = float(rng.uniform(0, 1))
    spec = {}
    for a in N.TREATMENTS:
        w = rng.normal(0, 0.5, len(N.CONTEXT_NAMES))
        w[CTX["bias"]] = 0.0
        w[CTX["base_logit"]] = 0.0
        cats = []
        for _ in range(2):
            col = CAT_DRIVERS[int(rng.integers(len(CAT_DRIVERS)))]
            vocab = [v for v in F.CATEGORICAL[col][0]]
            cats.append((col, set(rng.choice(vocab, size=max(1, len(vocab) // 3), replace=False)),
                         float(rng.normal(0, 0.8))))
        spec[a] = {"bias": float(rng.normal(0.1, 0.2)), "w": w, "intent": float(rng.normal(0, 0.5)),
                   "bell": float(rng.normal(0, 0.9)), "cats": cats, "cat_x_intent": float(rng.normal(0, 0.5))}

    def effects(info, _=None):
        f, z = info["frame"], info["intent"]
        out = {}
        for a, sp in spec.items():
            linear = info["ctx"] @ sp["w"]
            hidden = sp["intent"] * z + sp["bell"] * np.exp(-z ** 2)
            for i, (col, levels, coef) in enumerate(sp["cats"]):
                hit = f[col].isin(levels).to_numpy(dtype=float)
                hidden = hidden + coef * hit + (sp["cat_x_intent"] * hit * z if i == 0 else 0)
            out[a] = sp["bias"] + (1 - lam) * linear + lam * hidden
        return out
    return effects, lam


def truth_for(info, effects, seed, noise_sd=S.EFFECT_NOISE_SD):
    """True P(buy | x, a): no-contact probability shifted by the world's effect, plus each person's own
    unobservable response (noise_sd on the log-odds; 0 in the null world so that nothing truly works)."""
    rng = np.random.default_rng(seed)
    base = N._logit(info["p_none"])
    out = {"none": info["p_none"]}
    for a in N.TREATMENTS:
        e = effects[a] + rng.normal(0, noise_sd, len(base))
        out[a] = sigmoid(base + np.where(info["blocked"][a], 0.0, e))
    return out


def randomized_campaign(info, truth, seed):
    """Every lead gets one uniformly random ALLOWED action; only its outcome is observed."""
    rng = np.random.default_rng(seed)
    allowed = np.column_stack([~info["blocked"][a] for a in N.ACTION_LIST])
    idx = np.where(allowed, rng.random(allowed.shape), -1.0).argmax(1)
    P = np.column_stack([truth[a] for a in N.ACTION_LIST])
    p = P[np.arange(len(idx)), idx]
    return np.array(N.ACTION_LIST)[idx], (rng.random(len(idx)) < p).astype(int), 1.0 / allowed.sum(1)


def snips_profit(model, frame, base, blocked, price, actions, props, y):
    """The closed loop's off-policy estimate (same rule as retrain_nba_from_live.snips_value)."""
    greedy = U.greedy_policy(U.predict_all(model, frame, base), price, blocked, capacity=1.0)
    w = (greedy == actions) / props
    disc = np.array([N.ACTIONS[a]["discount"] for a in actions])
    cost = np.array([N.ACTIONS[a]["cost_inr"] for a in actions])
    return float((w * (y * price * (1 - disc) - cost)).sum() / w.sum())


def subset(info, idx):
    return {"frame": info["frame"].iloc[idx].reset_index(drop=True), "base": info["base"][idx],
            "blocked": {a: b[idx] for a, b in info["blocked"].items()}, "price": info["price"][idx]}


def run_world(name, effects_fn, tr, te, fixed, seed, sizes=None, noise_sd=S.EFFECT_NOISE_SD, extra=None):
    sizes = sizes or (N_TRAIN,)
    truth_tr = truth_for(tr, effects_fn(tr), seed + 1, noise_sd)
    truth_te = truth_for(te, effects_fn(te), seed + 2, noise_sd)
    actions, y, props = randomized_campaign(tr, truth_tr, seed + 3)
    price, blocked = te["price"], te["blocked"]
    evaluate = lambda model: U.evaluate_policy(
        U.greedy_policy(U.predict_all(model, te["frame"], te["base"]), price, blocked), truth_te, price)
    res = {"policies": {}, "learning_curve": {}, **(extra or {})}
    for pol, choice in fixed.items():
        res["policies"][pol] = U.evaluate_policy(choice, truth_te, price)
    res["policies"][ORACLE] = U.evaluate_policy(U.greedy_policy(truth_te, price, blocked), truth_te, price)

    models = {}
    for m in sizes:
        ours = U.fit_uplift(tr["frame"].iloc[:m], tr["base"][:m], actions[:m], y[:m])
        flex = U.fit_flexible(tr["frame"].iloc[:m], actions[:m], y[:m])
        res["learning_curve"][m] = {"ours": evaluate(ours)["net_incremental_profit_per_1000_inr"],
                                    "flexible": evaluate(flex)["net_incremental_profit_per_1000_inr"]}
        if m == N_TRAIN:
            models = {OURS: ours, FLEX: flex}
    res["policies"][OURS] = evaluate(models[OURS])
    res["policies"][FLEX] = evaluate(models[FLEX])

    # champion/challenger: pick the family by off-policy value on held-out LOGGED decisions only
    k = int(SELECT_SHARE * N_TRAIN)
    fit_idx, val_idx = np.arange(k), np.arange(k, N_TRAIN)
    v = subset(tr, val_idx)
    cand = {OURS: U.fit_uplift(tr["frame"].iloc[fit_idx], tr["base"][fit_idx], actions[fit_idx], y[fit_idx]),
            FLEX: U.fit_flexible(tr["frame"].iloc[fit_idx], actions[fit_idx], y[fit_idx])}
    ope = {n_: snips_profit(mdl, v["frame"], v["base"], v["blocked"], v["price"], actions[val_idx], props[val_idx],
                            y[val_idx]) for n_, mdl in cand.items()}
    picked = max(ope, key=ope.get)
    res["policies"][SEL] = res["policies"][picked]
    res["selection"] = {"picked": picked, "snips_profit_per_lead": ope}

    prof = {k_: v_["net_incremental_profit_per_1000_inr"] for k_, v_ in res["policies"].items()}
    best_fixed = max(fixed, key=lambda k_: prof[k_])
    oracle = prof[ORACLE]
    pct = lambda x: (100 * x / oracle) if oracle > 1 else None
    res["summary"] = {
        "best_fixed_policy": best_fixed, "best_fixed_profit": prof[best_fixed], "oracle_profit": oracle,
        "ours_profit": prof[OURS], "flexible_profit": prof[FLEX], "selected_profit": prof[SEL], "picked": picked,
        "ours_pct_of_oracle": pct(prof[OURS]), "flexible_pct_of_oracle": pct(prof[FLEX]),
        "selected_pct_of_oracle": pct(prof[SEL]), "best_fixed_pct_of_oracle": pct(prof[best_fixed]),
        "ours_contacted_per_1000": res["policies"][OURS]["contacted_per_1000"],
        "ours_coupons_per_1000": res["policies"][OURS]["coupons_per_1000"],
        "ours_calls_per_1000": res["policies"][OURS]["calls_per_1000"],
    }
    s = res["summary"]
    p = lambda x: "  n/a" if x is None else f"{x:5.1f}%"
    print(f"  {name:10s} ours {p(s['ours_pct_of_oracle'])} · flexible {p(s['flexible_pct_of_oracle'])} · "
          f"picked {'interp' if picked == OURS else 'flex  '} {p(s['selected_pct_of_oracle'])} · best fixed "
          f"{p(s['best_fixed_pct_of_oracle'])}  (₹/1000: ours {s['ours_profit']:,.0f}, oracle {oracle:,.0f})"
          + (f"  hidden share {res['hidden_share']:.2f}" if "hidden_share" in res else ""))
    return res


def main():
    t0 = time.time()
    if not os.path.exists(T.MODEL_PATH):
        raise SystemExit("Train the lead model first (train-model.bat or python ml/train_model.py).")
    os.makedirs(RESULTS, exist_ok=True)
    print("Generating leads and scoring them with the live lead model ...")
    tr = world_info(G.generate(N_TRAIN, seed=2024, return_truth=True))
    te = world_info(G.generate(N_TEST, seed=7777, return_truth=True))
    tr["base"], te["base"] = U.base_probability(tr["frame"]), U.base_probability(te["frame"])
    fixed = U.baseline_policies(te["frame"], te["base"], te["blocked"], np.random.default_rng(5))

    worlds = {}
    print(f"Named worlds ({N_TRAIN:,} randomized decisions for training):")
    worlds["documented"] = run_world("documented", eff_documented, tr, te, fixed, 100, sizes=TRAIN_SIZES)
    worlds["null"] = run_world("null", eff_null, tr, te, fixed, 200, noise_sd=0.0)
    worlds["reversed"] = run_world("reversed", eff_reversed, tr, te, fixed, 300)
    worlds["hidden"] = run_world("hidden", eff_hidden, tr, te, fixed, 400, sizes=TRAIN_SIZES)
    print(f"{N_RANDOM} random worlds:")
    for s in range(N_RANDOM):
        fn, lam = random_world(s)
        worlds[f"random_{s + 1:02d}"] = run_world(f"random {s + 1:02d}", fn, tr, te, fixed, 1000 + 17 * s,
                                                  extra={"hidden_share": lam})

    rand = [w for k, w in worlds.items() if k.startswith("random")]
    S_ = [w["summary"] for w in rand]
    med = lambda key: float(np.median([r[key] for r in S_ if r[key] is not None]))
    lam = np.array([w["hidden_share"] for w in rand])
    gap = np.array([r["ours_profit"] - r["flexible_profit"] for r in S_])
    agg = {
        "worlds": len(S_),
        "ours_beats_best_fixed": int(sum(r["ours_profit"] > r["best_fixed_profit"] for r in S_)),
        "flexible_beats_best_fixed": int(sum(r["flexible_profit"] > r["best_fixed_profit"] for r in S_)),
        "selected_beats_best_fixed": int(sum(r["selected_profit"] > r["best_fixed_profit"] for r in S_)),
        "ours_beats_flexible": int(sum(gap > 0)),
        "selection_picked_better_family": int(sum(
            (r["picked"] == OURS) == (r["ours_profit"] >= r["flexible_profit"]) for r in S_)),
        "median_pct_of_oracle": {"ours": med("ours_pct_of_oracle"), "flexible": med("flexible_pct_of_oracle"),
                                 "champion_challenger": med("selected_pct_of_oracle"),
                                 "best_fixed_in_hindsight": med("best_fixed_pct_of_oracle")},
        "min_pct_of_oracle": {"ours": float(min(r["ours_pct_of_oracle"] for r in S_)),
                              "flexible": float(min(r["flexible_pct_of_oracle"] for r in S_)),
                              "champion_challenger": float(min(r["selected_pct_of_oracle"] for r in S_))},
        "corr_hidden_share_vs_ours_minus_flexible": float(np.corrcoef(lam, gap)[0, 1]),
        "ours_beats_flexible_when_hidden_share_below_0.5": f"{int(sum(gap[lam < 0.5] > 0))}/{int(sum(lam < 0.5))}",
        "ours_beats_flexible_when_hidden_share_above_0.5": f"{int(sum(gap[lam >= 0.5] > 0))}/{int(sum(lam >= 0.5))}",
    }
    out = {"design": {"train_decisions": N_TRAIN, "test_leads": N_TEST, "random_worlds": N_RANDOM,
                      "selection_split": SELECT_SHARE, "train_sizes": TRAIN_SIZES, "call_capacity": U.CALL_CAPACITY},
           "random_world_summary": agg, "worlds": worlds, "runtime_s": round(time.time() - t0, 1)}
    with open(os.path.join(RESULTS, "nba_robustness.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, default=float)
    write_markdown(out)
    plot(out)
    m = agg["median_pct_of_oracle"]
    print(f"\nRandom worlds: beat the best fixed policy (chosen in hindsight) — ours {agg['ours_beats_best_fixed']}/{agg['worlds']}, "
          f"flexible {agg['flexible_beats_best_fixed']}/{agg['worlds']}, champion/challenger {agg['selected_beats_best_fixed']}/{agg['worlds']}. "
          f"Median % of oracle: ours {m['ours']:.1f}, flexible {m['flexible']:.1f}, champion/challenger "
          f"{m['champion_challenger']:.1f}, best fixed {m['best_fixed_in_hindsight']:.1f}. "
          f"Selection picked the better family in {agg['selection_picked_better_family']}/{agg['worlds']}.")
    print(f"Saved {os.path.relpath(RESULTS)}/nba_robustness.json and .md  ({time.time() - t0:,.0f}s)")


def write_markdown(R):
    pct = lambda v: "n/a" if v is None else f"{v:.1f}%"
    L = ["# Next-best-action robustness: worlds where our assumptions are wrong", "",
         f"Share of the oracle's net incremental profit captured on {R['design']['test_leads']:,} fresh leads (each world's "
         f"true response). Models trained on {R['design']['train_decisions']:,} randomized decisions. *Best fixed* = the "
         "best of the six fixed policies in that "
         "world, chosen in hindsight. *Pick* = the family the closed loop's champion/challenger rule selected using "
         "only logged decisions (off-policy estimate on a 25% hold-out).", "",
         "| World | Hidden share | Ours (interpretable) | Flexible (GBM) | Champion/challenger pick | Best fixed policy | Best fixed | Oracle ₹/1000 |",
         "|---|---|---|---|---|---|---|---|"]
    for k, w in R["worlds"].items():
        s = w["summary"]
        lam = f"{w['hidden_share']:.2f}" if "hidden_share" in w else "—"
        if s["oracle_profit"] <= 1:   # null world: report money, not shares
            L.append(f"| {k} | {lam} | ₹{s['ours_profit']:,.0f} | ₹{s['flexible_profit']:,.0f} | ₹{s['selected_profit']:,.0f} "
                     f"| {s['best_fixed_policy']} | ₹{s['best_fixed_profit']:,.0f} | {s['oracle_profit']:,.0f} |")
            continue
        pick = "interpretable" if s["picked"] == OURS else "flexible"
        L.append(f"| {k} | {lam} | {pct(s['ours_pct_of_oracle'])} | {pct(s['flexible_pct_of_oracle'])} | "
                 f"{pct(s['selected_pct_of_oracle'])} ({pick}) | {s['best_fixed_policy']} | "
                 f"{pct(s['best_fixed_pct_of_oracle'])} | {s['oracle_profit']:,.0f} |")
    a = R["random_world_summary"]
    m, mn = a["median_pct_of_oracle"], a["min_pct_of_oracle"]
    L += ["", f"**{a['worlds']} random worlds.** Beat the best fixed policy (chosen in hindsight): ours "
              f"{a['ours_beats_best_fixed']}/{a['worlds']}, flexible {a['flexible_beats_best_fixed']}/{a['worlds']}, "
              f"champion/challenger {a['selected_beats_best_fixed']}/{a['worlds']}. Median share of oracle profit: ours "
              f"{m['ours']:.1f}% (worst {mn['ours']:.1f}%), flexible {m['flexible']:.1f}% (worst {mn['flexible']:.1f}%), "
              f"champion/challenger {m['champion_challenger']:.1f}% (worst {mn['champion_challenger']:.1f}%), best fixed "
              f"{m['best_fixed_in_hindsight']:.1f}%. The interpretable model beat the flexible one in "
              f"{a['ours_beats_flexible_when_hidden_share_below_0.5']} worlds with hidden share < 0.5 and "
              f"{a['ours_beats_flexible_when_hidden_share_above_0.5']} with hidden share ≥ 0.5 (correlation of hidden "
              f"share with the interpretable model's advantage: {a['corr_hidden_share_vs_ours_minus_flexible']:+.2f}). "
              f"The champion/challenger rule picked the better family in {a['selection_picked_better_family']}/{a['worlds']}.",
          "", "## Named worlds — every policy (net incremental profit per 1,000 leads, ₹)", "",
          "| Policy | " + " | ".join(NAMED) + " |", "|---|" + "---|" * len(NAMED)]
    for pol in R["worlds"]["documented"]["policies"]:
        L.append(f"| {pol} | " + " | ".join(
            f"{R['worlds'][w]['policies'][pol]['net_incremental_profit_per_1000_inr']:,.0f}" for w in NAMED) + " |")
    nw = R["worlds"]["null"]["summary"]
    L += ["", f"Null world: ours contacted {nw['ours_contacted_per_1000']:.0f} of every 1,000 leads "
              f"({nw['ours_coupons_per_1000']:.0f} coupons, {nw['ours_calls_per_1000']:.0f} calls).", "",
          "## Learning curve (net profit per 1,000 leads vs number of randomized decisions)", "",
          "| World | Decisions | Ours (interpretable) | Flexible (GBM) | Best fixed | Oracle |", "|---|---|---|---|---|---|"]
    for k in ("documented", "hidden"):
        w = R["worlds"][k]
        for n_, v in w["learning_curve"].items():
            L.append(f"| {k} | {int(n_):,} | {v['ours']:,.0f} | {v['flexible']:,.0f} | "
                     f"{w['summary']['best_fixed_profit']:,.0f} | {w['summary']['oracle_profit']:,.0f} |")
    with open(os.path.join(RESULTS, "nba_robustness.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


def plot(R):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  (matplotlib not installed — skipping figure)")
        return
    os.makedirs(os.path.join(RESULTS, "figures"), exist_ok=True)
    rand = [w for k, w in R["worlds"].items() if k.startswith("random")]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    ax = axes[0]
    lam = [w["hidden_share"] for w in rand]
    for key, label, mk in (("ours_pct_of_oracle", "ours (interpretable)", "o"),
                           ("flexible_pct_of_oracle", "flexible (GBM)", "s"),
                           ("best_fixed_pct_of_oracle", "best fixed policy (hindsight)", "x")):
        ax.scatter(lam, [w["summary"][key] for w in rand], marker=mk, label=label)
    ax.set_xlabel("hidden share of the true effect (0 = representable, 1 = hidden)")
    ax.set_ylabel("% of oracle profit")
    ax.set_title("20 random response worlds")
    ax.grid(alpha=.3)
    ax.legend(fontsize=7)
    ax = axes[1]
    for k, style in (("documented", "-"), ("hidden", "--")):
        lc = R["worlds"][k]["learning_curve"]
        ms = [int(m) for m in lc]
        ax.plot(ms, [lc[m]["ours"] / 1e6 for m in lc], "o" + style, label=f"ours · {k}")
        ax.plot(ms, [lc[m]["flexible"] / 1e6 for m in lc], "s" + style, label=f"flexible · {k}")
        ax.axhline(R["worlds"][k]["summary"]["best_fixed_profit"] / 1e6, ls=style, c="grey", lw=0.8)
    ax.set_xscale("log")
    ax.set_xlabel("randomized decisions used for training")
    ax.set_ylabel("net profit per 1,000 leads (₹ million)")
    ax.set_title("Learning curve (grey = best fixed policy)")
    ax.legend(fontsize=7)
    ax.grid(alpha=.3)
    fig.tight_layout()
    fig.savefig(os.path.join(RESULTS, "figures", "nba_robustness.png"), dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
