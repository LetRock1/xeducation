"""
Can the A/B engine's verdicts be trusted? Simulated tests where the true answer is known.

  1. A/A tests     2 variants + a 20% control, all with the SAME true buying rate: how often does
                   the engine still declare a difference? (should be at most 5%)
  2. Coverage      one variant with a known true lift: how often does the 95% interval contain it?
                   (should be about 95%)
  3. Power         the planned sample size for +5 points on a 10% rate: how often is a real +5
                   point lift found? (should be about 80%)
  4. Split check   people split by the engine's own hash; how often does the sample-ratio check
                   raise a false alarm, and how often does it catch a broken split (10% of the
                   control group silently lost)?
  5. End to end    analyse() on a full simulated test (people, purchases, dates) gives the
                   right verdict before and after the 14-day window.
  6. Adopted winners  "ship the winner with a holdback": 10% of the audience keeps the old e-mail
                   (marketing-backend/adoption.py). With the true effect known, how often does the
                   check confirm a real winner, switch back from a real loser, or wrongly do either
                   when there is no difference — and how many people does that take?

Run:  python ml/experiments/ab_engine_check.py      (about a minute; fixed seed)
Writes ml/results/ab_engine_check.md and .json
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "marketing-backend"))
import adoption as AD    # noqa: E402
import experiments as X  # noqa: E402

RESULTS = os.path.normpath(os.path.join(HERE, "..", "results"))
RUNS = 4000
rng = np.random.default_rng(2026)


def significant(x1, n1, x0, n0, k, alpha=0.05):
    z = X.norm_ppf(1 - alpha / (2 * k))
    lo, hi = X.diff_ci(x1, n1, x0, n0, z)
    p = X.two_prop_p(x1, n1, x0, n0)
    return (p is not None and min(1.0, p * k) < alpha and (lo > 0 or hi < 0)), (lo, hi)


def aa_tests(p=0.10, people=3000):
    n0, n1 = int(people * 0.2), int(people * 0.4)
    alarms = 0
    for _ in range(RUNS):
        x0 = rng.binomial(n0, p)
        xa, xb = rng.binomial(n1, p), rng.binomial(n1, p)
        a, _ = significant(xa, n1, x0, n0, 2)
        b, _ = significant(xb, n1, x0, n0, 2)
        alarms += a or b
    return alarms / RUNS


def coverage(p0=0.10, lift=0.03, n=1500):
    hit = 0
    for _ in range(RUNS):
        x0, x1 = rng.binomial(n, p0), rng.binomial(n, p0 + lift)
        _, (lo, hi) = significant(x1, n, x0, n, 1)
        hit += lo <= lift <= hi
    return hit / RUNS


def power(p0=0.10, lift=0.05):
    n = X.sample_size(p0, lift, 0.05, 0.80, 1)
    found = 0
    for _ in range(RUNS):
        x0, x1 = rng.binomial(n, p0), rng.binomial(n, p0 + lift)
        sig, _ = significant(x1, n, x0, n, 1)
        found += sig
    return n, found / RUNS


def split_check(people=3000, tests=1000):
    arms = X.arms_for_test(0.2, ["A", "B"])
    shares = [s for _, s in arms]
    false_alarm = caught10 = caught30 = 0
    for t in range(tests):
        counts = {k: 0 for k, _ in arms}
        for u in range(people):
            counts[X.arm_for("ab", 100000 + t, u, arms)[0]] += 1
        obs = [counts[k] for k, _ in arms]
        false_alarm += X.srm_p(obs, shares) < 0.001
        caught10 += X.srm_p([int(obs[0] * 0.9)] + obs[1:], shares) < 0.001     # 10% of the control lost
        caught30 += X.srm_p([int(obs[0] * 0.7)] + obs[1:], shares) < 0.001     # 30% of the control lost
    return false_alarm / tests, caught10 / tests, caught30 / tests


def end_to_end(p_control=0.08, lift_b=0.06, people=4000):
    """A full test through analyse(): people assigned by hash, purchases on real dates."""
    start = datetime(2026, 9, 1, 11, 0, 0)
    arms = X.arms_for_test(0.2, ["A", "B"])
    rate = {"control": p_control, "A": p_control + 0.005, "B": p_control + lift_b}
    assignments, purchases = [], {}
    for u in range(people):
        arm, prob = X.arm_for("ab", 777, u, arms)
        assignments.append({"user_id": u, "arm": arm, "probability": prob, "assigned_at": start.strftime("%Y-%m-%d %H:%M:%S"),
                            "tier": "All", "occupation": "x", "device": "Mobile" if u % 2 else "Desktop", "source": "Google"})
        if rng.random() < rate[arm]:
            day = float(rng.uniform(0.1, 13.5))
            purchases[u] = [((start + timedelta(days=day)).strftime("%Y-%m-%d %H:%M:%S"), 20000.0, 0.0)]
    test = {"id": 777, "metric": "purchase", "variants": [{"key": "A"}, {"key": "B"}]}
    early = X.analyse(test, assignments, purchases, {}, now=start + timedelta(days=5))
    final = X.analyse(test, assignments, purchases, {}, now=start + timedelta(days=15))
    return early["verdict"], final["verdict"], final


def adoption_check(sizes=(400, 1500, 5000), reps=200, base=0.10, lift=0.04, share=0.10):
    """adoption.evaluate() on simulated adoptions with a known true effect of the adopted e-mail."""
    start = datetime(2026, 9, 1, 11, 0, 0)
    now = start + timedelta(days=15)
    ts = start.strftime("%Y-%m-%d %H:%M:%S")
    out = []
    for n in sizes:
        for name, d in (("better", lift), ("no difference", 0.0), ("worse", -lift)):
            states = {"confirmed": 0, "checking": 0, "reverted": 0}
            for r in range(reps):
                aid = 10_000 * n + r + (0 if d > 0 else 1_000 if d == 0 else 2_000)
                assignments, purchases = [], {}
                for u in range(n):
                    arm, prob = AD.arm_for(aid, u, share)
                    assignments.append({"user_id": u, "arm": arm, "probability": prob, "assigned_at": ts,
                                        "tier": "All", "occupation": "x", "device": "Mobile", "source": "Google"})
                    if rng.random() < base + (d if arm == AD.ADOPTED else 0.0):
                        purchases[u] = [((start + timedelta(days=float(rng.uniform(0.1, 13.5)))).strftime(
                            "%Y-%m-%d %H:%M:%S"), 20000.0, 0.0)]
                state, _ = AD.evaluate({"id": aid, "metric": "purchase"}, assignments, purchases, {}, now)
                states[state] += 1
            out.append({"people": n, "truth": name, **{k: v / reps for k, v in states.items()}})
    return out


def adoption_false_alarms(sizes=(400, 1500, 5000), reps=20000, base=0.10, share=0.10):
    """The same check from counts only (no dates), many more repetitions: with NO real difference, how
    often is the adopted e-mail wrongly confirmed or wrongly switched back?"""
    z = X.norm_ppf(1 - 0.05 / 2)
    out = []
    for n in sizes:
        conf = rev = 0
        for _ in range(reps):
            n0 = rng.binomial(n, share)
            n1 = n - n0
            if n0 < AD.MIN_PER_ARM or n1 < AD.MIN_PER_ARM:
                continue
            lo, hi = X.diff_ci(rng.binomial(n1, base), n1, rng.binomial(n0, base), n0, z)
            conf += lo > 0
            rev += hi < 0
        out.append({"people": n, "false_confirm": conf / reps, "false_switch_back": rev / reps})
    return out


def main():
    t0 = time.time()
    out = {}
    out["aa_false_alarm_rate"] = aa_tests()
    out["ci_coverage"] = coverage()
    n, pw = power()
    out["planned_per_arm"], out["power"] = n, pw
    fa, c10, c30 = split_check()
    out["srm_false_alarm_rate"], out["srm_detection_10pct"], out["srm_detection_30pct"] = fa, c10, c30
    early, final, details = end_to_end()
    out["adoption"] = adoption_check()
    out["adoption_false_alarms"] = adoption_false_alarms()
    out["end_to_end"] = {"day5": early, "day15": final,
                         "arms": [{k: a[k] for k in ("arm", "n", "purchases", "rate")} for a in details["arms"]]}
    lines = ["# A/B engine check (simulated tests with known truth)", "",
             f"{RUNS:,} simulated tests per row, seed 2026.", "",
             "| Check | Result | Should be |", "|---|---|---|",
             f"| A/A tests (no real difference, 2 variants + control): engine declares a difference | {out['aa_false_alarm_rate']:.1%} | at most 5% |",
             f"| 95% interval contains the true lift (+3 pts on 10%) | {out['ci_coverage']:.1%} | about 95% |",
             f"| Real +5 pt lift found with the planned {n} people per arm | {out['power']:.1%} | about 80% |",
             f"| Split check false alarms (hash split, 3,000 people) | {out['srm_false_alarm_rate']:.1%} | about 0.1% |",
             f"| Split check catches 10% of the control group lost (60 of 600 people) | {out['srm_detection_10pct']:.1%} | low at this size: the check is strict (p < 0.001) |",
             f"| Split check catches 30% of the control group lost | {out['srm_detection_30pct']:.1%} | high |", "",
             "## End to end (analyse() on 4,000 simulated people, true lift of B = +6 pts)", "",
             f"- Day 5: **{early['status']}** — {early['headline']}",
             f"- Day 15: **{final['status']}** — {final['headline']}. {final['detail']}", "",
             "| Arm | People | Bought | Rate |", "|---|---|---|---|"]
    lines += [f"| {a['arm']} | {a['n']} | {a['purchases']} | {a['rate']:.1%} |" for a in out["end_to_end"]["arms"]]
    lines += ["", "## Adopted winners: the 10% check group (adoption.evaluate(), 200 simulated adoptions per row)", "",
              "The old e-mail sells to 10% of people; the adopted one truly sells 4 points more, the same, or 4 points less. "
              "The check confirms (95% interval above zero), switches back (interval below zero) or keeps checking.", "",
              "| People who got the e-mail since adoption | Truth | Confirmed | Still checking | Switched back |",
              "|---|---|---|---|---|"]
    lines += [f"| {a['people']:,} | adopted e-mail {a['truth']} | {a['confirmed']:.0%} | {a['checking']:.0%} | {a['reverted']:.0%} |"
              for a in out["adoption"]]
    fa = out["adoption_false_alarms"]
    sizes = ", ".join(f"{a['people']:,}" for a in fa)
    lines += ["", "With no real difference it should confirm or switch back about 2.5% of the time each (200 runs per "
              "row is noisy; the same statistics from counts, 20,000 runs each: wrongly confirmed "
              + ", ".join(f"{a['false_confirm']:.1%}" for a in fa) + "; wrongly switched back "
              + ", ".join(f"{a['false_switch_back']:.1%}" for a in fa) + f" for {sizes} people). "
              "A real 4-point difference needs a few thousand people before the 10% check group can show it; "
              "until then the dashboard says \"collecting evidence\"."]
    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, "ab_engine_check.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(RESULTS, "ab_engine_check.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    print("\n".join(lines))
    print(f"\n({time.time() - t0:.0f} s) Saved ml/results/ab_engine_check.md")


if __name__ == "__main__":
    main()
