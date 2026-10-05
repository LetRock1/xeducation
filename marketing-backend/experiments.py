"""
experiments.py — the A/B experiment engine (statistics + assignment), with no web code,
so the dashboard API (main.py) and the history generator (ml/generate_history.py) share it.

How a test works (standard practice, e.g. Kohavi, Tang & Xu, "Trustworthy Online
Controlled Experiments", 2020):
  * 2-3 email variants + a CONTROL group that gets no email (default 20 %). Every
    variant is compared with the control, so the result is the extra purchases (or
    clicks) the email CAUSED — not just "A beat B".
  * Assignment is deterministic: a hash of (test, person) decides the arm, so the same
    person always lands in the same arm and the split can be re-checked at any time.
    Every assignment is stored with its probability and is a decision point for the
    learning loop, so it knows which e-mail (or none) each person got.
  * Fixed horizon: the result is final when the outcome window (14 days) has passed
    after the send. Numbers shown earlier are marked "not final" (no peeking problem).
  * 95 % confidence intervals (Newcombe score interval for a difference of proportions),
    p-values from the two-proportion z-test, Bonferroni-adjusted when there are 2+
    variants; a sample-ratio-mismatch check (chi-square) warns if the split is broken.
  * Revenue, coupon cost and profit per recipient, cumulative conversion by day, and
    results by segment (tier, occupation, device, source) — labelled exploratory.
"""
import hashlib
import math
from datetime import datetime, timedelta

ARM_LABELS = {"control": "Control (no email)", "A": "Variant A", "B": "Variant B", "C": "Variant C"}


# ── assignment ────────────────────────────────────────────────────────────────
def unit(kind, experiment_id, user_id):
    """A number in [0, 1) that depends only on (experiment, person)."""
    h = hashlib.sha256(f"{kind}:{experiment_id}:{user_id}".encode()).hexdigest()
    return int(h[:15], 16) / float(16 ** 15)


def arm_for(kind, experiment_id, user_id, arms):
    """arms = [(key, share), ...] with shares summing to 1. Returns (key, share)."""
    u = unit(kind, experiment_id, user_id)
    acc = 0.0
    for key, share in arms:
        acc += share
        if u < acc:
            return key, share
    return arms[-1]


def arms_for_test(control_share, variant_keys):
    rest = (1.0 - control_share) / max(len(variant_keys), 1)
    arms = [("control", control_share)] if control_share > 0 else []
    return arms + [(k, rest) for k in variant_keys]


def campaign_arms(holdout_share):
    return [("holdout", holdout_share), ("send", 1.0 - holdout_share)] if holdout_share > 0 else [("send", 1.0)]


# ── statistics (no scipy needed) ──────────────────────────────────────────────
def norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def norm_ppf(p):
    """Inverse standard normal CDF (Acklam's approximation, |error| < 1.2e-9 after one refinement)."""
    if p <= 0:
        return -1e9
    if p >= 1:
        return 1e9
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02,
         -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01,
         -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00,
         4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00]
    lo, hi = 0.02425, 1 - 0.02425
    if p < lo:
        q = math.sqrt(-2 * math.log(p))
        x = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    elif p <= hi:
        q = p - 0.5
        r = q * q
        x = (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    else:
        q = math.sqrt(-2 * math.log(1 - p))
        x = -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    e = norm_cdf(x) - p                                 # one Halley refinement step
    u = e * math.sqrt(2 * math.pi) * math.exp(x * x / 2)
    return x - u / (1 + x * u / 2)


def wilson(x, n, z=1.959964):
    if n == 0:
        return (0.0, 1.0)
    p = x / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, centre - half), min(1.0, centre + half))


def diff_ci(x1, n1, x0, n0, z=1.959964):
    """Newcombe (1998) hybrid score interval for p1 - p0."""
    if not n1 or not n0:
        return (None, None)
    p1, p0 = x1 / n1, x0 / n0
    l1, u1 = wilson(x1, n1, z)
    l0, u0 = wilson(x0, n0, z)
    d = p1 - p0
    return (d - math.sqrt((p1 - l1) ** 2 + (u0 - p0) ** 2), d + math.sqrt((u1 - p1) ** 2 + (p0 - l0) ** 2))


def two_prop_p(x1, n1, x0, n0):
    if not n1 or not n0:
        return None
    pooled = (x1 + x0) / (n1 + n0)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n0))
    if se == 0:
        return 1.0
    z = (x1 / n1 - x0 / n0) / se
    return 2 * (1 - norm_cdf(abs(z)))


def sample_size(base_rate, mde, alpha=0.05, power=0.8, comparisons=1):
    """People per arm to detect an absolute lift `mde` over `base_rate` (two-sided, Bonferroni)."""
    p1 = min(max(base_rate, 0.005), 0.99)
    p2 = min(max(p1 + mde, 0.005), 0.995)
    za = norm_ppf(1 - alpha / (2 * max(comparisons, 1)))
    zb = norm_ppf(power)
    pbar = (p1 + p2) / 2
    num = (za * math.sqrt(2 * pbar * (1 - pbar)) + zb * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2
    return int(math.ceil(num / (p2 - p1) ** 2))


def n_comparisons(n_variants, has_control):
    """How many comparisons a test makes (Bonferroni correction): every variant against the no-email
    control group, or — without one (click tests, adoption checks) — every other variant against the first."""
    n = int(n_variants or 0)
    return max(n if has_control else n - 1, 1)


def detectable_effect(base_rate, n, alpha=0.05, power=0.8, comparisons=1):
    """Smallest absolute lift this many people per arm can reliably detect."""
    if n <= 0:
        return None
    p = min(max(base_rate, 0.005), 0.99)
    za = norm_ppf(1 - alpha / (2 * max(comparisons, 1)))
    zb = norm_ppf(power)
    return (za + zb) * math.sqrt(2 * p * (1 - p) / n)


def _gammaincc(s, x):
    """Regularised upper incomplete gamma Q(s, x) (series / continued fraction, Numerical Recipes)."""
    if x <= 0:
        return 1.0
    if x < s + 1:
        term = total = 1.0 / s
        a = s
        for _ in range(500):
            a += 1
            term *= x / a
            total += term
            if abs(term) < abs(total) * 1e-12:
                break
        return 1.0 - total * math.exp(-x + s * math.log(x) - math.lgamma(s))
    b, c, d = x + 1 - s, 1e300, 1 / (x + 1 - s)
    h = d
    for i in range(1, 500):
        an = -i * (i - s)
        b += 2
        d = an * d + b
        d = 1e-300 if abs(d) < 1e-300 else d
        c = b + an / c
        c = 1e-300 if abs(c) < 1e-300 else c
        d = 1 / d
        h *= d * c
        if abs(d * c - 1) < 1e-12:
            break
    return math.exp(-x + s * math.log(x) - math.lgamma(s)) * h


def srm_p(observed, expected_shares):
    """Sample-ratio-mismatch check: chi-square goodness-of-fit p-value of the arm counts."""
    n = sum(observed)
    if n == 0 or len(observed) < 2:
        return None
    chi = sum((o - n * s) ** 2 / (n * s) for o, s in zip(observed, expected_shares) if s > 0)
    return _gammaincc((len(observed) - 1) / 2.0, chi / 2.0)


# ── results ───────────────────────────────────────────────────────────────────
def _mean_var(values):
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    m = sum(values) / n
    v = sum((x - m) ** 2 for x in values) / (n - 1) if n > 1 else 0.0
    return m, v


def _ts(s):
    return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")


def analyse(test, assignments, purchases, clicks, now=None, window_days=14, alpha=0.05, power=0.8,
            mde=0.05, email_cost=2.0, min_segment=30):
    """
    test         : dict with id, metric ('purchase'|'click'), control_share, variants [{key, label, ...}]
    assignments  : [{user_id, arm, probability, assigned_at, tier, occupation, device, source}]
    purchases    : {user_id: [(purchased_at, price_paid, discount_amount), ...]}
    clicks       : {user_id: first_clicked_at}  (for the email of this test)
    """
    now = now or datetime.now()
    window = timedelta(days=window_days)
    variants = [v["key"] for v in test["variants"]]
    arms = (["control"] if any(a["arm"] == "control" for a in assignments) else []) + variants

    def outcome(a):
        t0 = _ts(a["assigned_at"])
        bought = [p for p in purchases.get(a["user_id"], []) if t0 < _ts(p[0]) <= t0 + window and _ts(p[0]) <= now]
        click = clicks.get(a["user_id"])
        clicked = bool(click) and t0 <= _ts(click) <= t0 + window
        first_buy = min((_ts(p[0]) for p in bought), default=None)
        return {"bought": int(bool(bought)), "clicked": int(clicked),
                "revenue": float(sum(p[1] for p in bought)), "discount": float(sum(p[2] for p in bought)),
                "first_buy": first_buy, "t0": t0}

    rows = [dict(a, **outcome(a)) for a in assignments]
    metric = "bought" if test.get("metric", "purchase") == "purchase" else "clicked"
    by_arm = {arm: [r for r in rows if r["arm"] == arm] for arm in arms}

    def arm_stats(rs, arm):
        n = len(rs)
        conv = sum(r["bought"] for r in rs)
        clk = sum(r["clicked"] for r in rs)
        rev = [r["revenue"] for r in rs]
        cost = 0.0 if arm == "control" else email_cost * n
        disc = sum(r["discount"] for r in rs)
        lo, hi = wilson(sum(r[metric] for r in rs), n) if n else (None, None)
        return {"arm": arm, "label": ARM_LABELS.get(arm, arm), "n": n, "purchases": conv, "clicks": clk,
                "conversion_rate": conv / n if n else None, "click_rate": clk / n if n else None,
                "rate": (sum(r[metric] for r in rs) / n) if n else None, "rate_ci": [lo, hi],
                "revenue": sum(rev), "revenue_per_person": (sum(rev) / n) if n else None,
                "coupon_cost": disc, "send_cost": cost,
                "profit_per_person": ((sum(rev) - cost) / n) if n else None}

    stats = {arm: arm_stats(by_arm[arm], arm) for arm in arms}
    # people who got no email cannot click: click tests compare the variants with each other
    has_control = "control" in stats and stats["control"]["n"] > 0 and metric == "bought"
    ref = "control" if has_control else (variants[0] if variants else None)
    k = n_comparisons(len(variants), has_control)     # Bonferroni: one per comparison actually made
    z = norm_ppf(1 - alpha / (2 * k))
    comparisons = []
    for v in variants:
        if v == ref or not stats[v]["n"] or not stats[ref]["n"]:
            continue
        x1 = sum(r[metric] for r in by_arm[v])
        x0 = sum(r[metric] for r in by_arm[ref])
        n1, n0 = stats[v]["n"], stats[ref]["n"]
        lo, hi = diff_ci(x1, n1, x0, n0, z)
        p = two_prop_p(x1, n1, x0, n0)
        p_adj = min(1.0, p * k) if p is not None else None
        r1, r0 = [r["revenue"] for r in by_arm[v]], [r["revenue"] for r in by_arm[ref]]
        m1, v1 = _mean_var(r1)
        m0, v0 = _mean_var(r0)
        se = math.sqrt(v1 / max(n1, 1) + v0 / max(n0, 1))
        comparisons.append({
            "variant": v, "vs": ref, "lift": x1 / n1 - x0 / n0, "lift_ci": [lo, hi],
            "relative_lift": ((x1 / n1) / (x0 / n0) - 1) if x0 else None,
            "p_value": p, "p_adjusted": p_adj, "significant": bool(p_adj is not None and p_adj < alpha and lo > 0 or
                                                                   p_adj is not None and p_adj < alpha and hi < 0),
            "revenue_lift_per_person": m1 - m0, "revenue_lift_ci": [m1 - m0 - z * se, m1 - m0 + z * se],
            "profit_lift_per_person": (stats[v]["profit_per_person"] or 0) - (stats[ref]["profit_per_person"] or 0)})

    # sample-ratio-mismatch
    shares = []
    for arm in arms:
        ps = [r["probability"] for r in by_arm[arm]]
        shares.append(sum(ps) / len(ps) if ps else 0.0)
    total_share = sum(shares) or 1.0
    srm = srm_p([stats[a]["n"] for a in arms], [s / total_share for s in shares])

    # power: planned vs actual
    base = stats[ref]["rate"] if ref and stats[ref]["rate"] else 0.05
    n_min = min((stats[a]["n"] for a in arms), default=0)
    planned = sample_size(base, mde, alpha, power, k)
    detectable = detectable_effect(base, n_min, alpha, power, k)

    # status: final when the outcome window has passed for everyone
    last_assigned = max((_ts(a["assigned_at"]) for a in assignments), default=None)
    first_assigned = min((_ts(a["assigned_at"]) for a in assignments), default=None)
    final = bool(last_assigned and now >= last_assigned + window)
    days_in = (now - first_assigned).days if first_assigned else 0

    # cumulative curve: share of each arm that has converted by day d after assignment
    horizon = min(window_days, max(days_in, 0))
    curve = []
    for d in range(0, horizon + 1):
        point = {"day": d}
        for arm in arms:
            rs = by_arm[arm]
            if rs:
                if metric == "bought":
                    hits = sum(1 for r in rs if r["first_buy"] and r["first_buy"] <= r["t0"] + timedelta(days=d))
                else:
                    hits = sum(1 for r in rs if r["clicked"] and clicks.get(r["user_id"])
                               and _ts(clicks[r["user_id"]]) <= r["t0"] + timedelta(days=d))
                point[arm] = round(100.0 * hits / len(rs), 2)
        curve.append(point)

    # segments (exploratory)
    segments = {}
    for dim in ("tier", "occupation", "device", "source"):
        values = sorted({(r.get(dim) or "Unknown") for r in rows})
        out = []
        for val in values:
            seg = {arm: [r for r in by_arm[arm] if (r.get(dim) or "Unknown") == val] for arm in arms}
            item = {"value": val, "arms": {}, "best": None, "enough": True}
            refs = seg.get(ref, [])
            for arm in arms:
                rs = seg[arm]
                item["arms"][arm] = {"n": len(rs), "rate": (sum(r[metric] for r in rs) / len(rs)) if rs else None}
                if len(rs) < min_segment:
                    item["enough"] = False
            best_lift = None
            for v in variants:
                if v == ref:
                    continue
                rs = seg[v]
                if len(rs) >= min_segment and len(refs) >= min_segment:
                    x1, n1 = sum(r[metric] for r in rs), len(rs)
                    x0, n0 = sum(r[metric] for r in refs), len(refs)
                    lo, hi = diff_ci(x1, n1, x0, n0, z)
                    lift = x1 / n1 - x0 / n0
                    item["arms"][v].update(lift=lift, lift_ci=[lo, hi])
                    if lo > 0 and (best_lift is None or lift > best_lift):
                        best_lift, item["best"] = lift, v
            out.append(item)
        segments[dim] = out

    verdict = _verdict(test, stats, comparisons, srm, final, days_in, window_days, planned, n_min, detectable,
                       metric, ref, alpha)
    return {"metric": metric, "arms": [stats[a] for a in arms], "comparisons": comparisons, "reference": ref,
            "srm_p": srm, "srm_problem": bool(srm is not None and srm < 0.001), "final": final,
            "days_since_start": days_in, "window_days": window_days, "planned_per_arm": planned,
            "smallest_arm": n_min, "detectable_lift": detectable, "curve": curve, "segments": segments,
            "verdict": verdict, "alpha": alpha, "bonferroni_comparisons": k}


def _pts(x):
    return f"{x * 100:+.1f} pts"


def _verdict(test, stats, comps, srm, final, days_in, window_days, planned, n_min, detectable, metric, ref, alpha):
    what = "purchases" if metric == "bought" else "clicks"
    if srm is not None and srm < 0.001:
        return {"status": "broken", "headline": "The split looks broken (sample-ratio mismatch)",
                "detail": "Arm sizes differ from the planned shares far more than chance allows (p < 0.001). "
                          "Don't trust these results; check who was excluded."}
    if not comps:
        return {"status": "waiting", "headline": "Not sent yet", "detail": "Send the test to start collecting data."}
    sig = [c for c in comps if c["significant"] and c["lift"] > 0]
    worse = [c for c in comps if c["significant"] and c["lift"] < 0]
    ref_label = "sending nothing" if ref == "control" else f"variant {ref}"
    if not final:
        lead = max(comps, key=lambda c: c["lift"])
        return {"status": "running",
                "headline": f"Collecting outcomes — day {min(days_in, window_days)} of {window_days}",
                "detail": f"Not final yet: {what} are counted for {window_days} days after the send. So far variant "
                          f"{lead['variant']} is {_pts(lead['lift'])} vs {ref_label} (not a conclusion)."}
    if sig:
        best = max(sig, key=lambda c: c["lift"])
        lo, hi = best["lift_ci"]
        extra = ""
        others = [c for c in sig if c is not best]
        if others:
            extra = " Other variants also beat it; the difference between them is smaller than the uncertainty."
        if best.get("profit_lift_per_person") is not None and best["profit_lift_per_person"] < 0 and metric == "bought":
            extra += " Note: it earns less per person than sending nothing once the discount is counted."
        return {"status": "winner", "winner": best["variant"],
                "headline": f"Variant {best['variant']} wins: {_pts(best['lift'])} {what} vs {ref_label}",
                "detail": f"95% interval {_pts(lo)} to {_pts(hi)}, adjusted p = {best['p_adjusted']:.4f}.{extra}"}
    if worse:
        c = min(worse, key=lambda c: c["lift"])
        return {"status": "loser", "headline": f"Variant {c['variant']} did worse than {ref_label}",
                "detail": f"{_pts(c['lift'])} (95% interval {_pts(c['lift_ci'][0])} to {_pts(c['lift_ci'][1])})."}
    note = ""
    if detectable is not None and n_min < planned:
        note = (f" With {n_min} people per arm this test could only detect lifts of about "
                f"{detectable * 100:.1f} pts or more; {planned} per arm were needed for the planned effect.")
    return {"status": "no_difference", "headline": f"No variant clearly beats {ref_label}",
            "detail": f"All differences are within the uncertainty.{note}"}
