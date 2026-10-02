"""
stats_utils.py — the statistics behind A/B tests and campaign reports.

The old A/B page declared whichever variant had the higher open rate the
"winner", even with 1 email per variant. Here a winner is declared only
when the difference is statistically significant (two-proportion z-test,
p < 0.05), and the page also says how many sends are needed.
"""
import math


def _norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def two_proportion_test(x_a, n_a, x_b, n_b):
    """Returns diff (B-A), z, two-sided p-value and a 95% CI for the difference."""
    if not n_a or not n_b:
        return {"diff": None, "z": None, "p_value": None, "ci_low": None, "ci_high": None}
    pa, pb = x_a / n_a, x_b / n_b
    pooled = (x_a + x_b) / (n_a + n_b)
    se_pooled = math.sqrt(pooled * (1 - pooled) * (1 / n_a + 1 / n_b))
    z = (pb - pa) / se_pooled if se_pooled > 0 else 0.0
    p = 2 * (1 - _norm_cdf(abs(z)))
    se = math.sqrt(pa * (1 - pa) / n_a + pb * (1 - pb) / n_b)
    return {"diff": round(pb - pa, 4), "z": round(z, 3), "p_value": round(p, 4),
            "ci_low": round(pb - pa - 1.96 * se, 4), "ci_high": round(pb - pa + 1.96 * se, 4)}


def sample_size_per_variant(base_rate, min_detectable_lift, alpha=0.05, power=0.8):
    """Sends needed per variant to detect an absolute lift with the given power."""
    p1 = max(min(base_rate, 0.99), 0.01)
    p2 = max(min(p1 + min_detectable_lift, 0.99), 0.01)
    z_a, z_b = 1.959964, 0.841621          # alpha=0.05 two-sided, power=0.8
    pbar = (p1 + p2) / 2
    num = (z_a * math.sqrt(2 * pbar * (1 - pbar)) + z_b * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2
    return int(math.ceil(num / (p2 - p1) ** 2))
