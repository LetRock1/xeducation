"""
No leakage. Two checks:

1. The real-data benchmark (ml/experiments/model_benchmark.py, 9,240 real X Education leads) never
   reads a column that is only known AFTER sales has contacted the lead (Tags, Lead Quality, Last
   Activity, Asymmetrique scores ...). Those columns make a score look far better than it can be
   for a new lead (AUC ~0.98).
2. The CRM's own lead model only uses inputs the website records before any contact.

Run:  python tests/test_no_leakage.py
"""
import inspect
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "user-backend"), os.path.join(ROOT, "ml")]

import ml_features as F          # noqa: E402
import real_leads as RL          # noqa: E402

# The only source columns the benchmark may read (all known when the lead signs up).
ALLOWED = ["Lead Origin", "Lead Source", "Do Not Email", "Do Not Call", "TotalVisits",
           "Total Time Spent on Website", "Page Views Per Visit", "What is your current occupation",
           "Specialization", "Converted"]


def test_real_data_columns():
    src = inspect.getsource(RL.load_real_leads)
    for col in RL.LEAKY_COLUMNS:
        assert f'"{col}"' not in src and f"'{col}'" not in src, f"leaky column read: {col}"
    read = set(re.findall(r'd\["([^"]+)"\]', src))
    assert read <= set(ALLOWED), f"unexpected columns read: {sorted(read - set(ALLOWED))}"
    rows, y = RL.load_real_leads()
    assert len(rows) == 9240 and set(rows[0]) == set(RL.REAL_COLUMNS)
    return sorted(read), len(rows)


def test_product_model_inputs():
    # every input is something the website records itself (no sales-entered field)
    sales_fields = {"Tags", "LeadQuality", "LeadProfile", "LastActivity", "LastNotableActivity"}
    assert not (set(F.MODEL_COLUMNS) & sales_fields)
    path = os.path.join(ROOT, "user-backend", "ml_models", "lead_model.pkl")
    if os.path.exists(path):
        import joblib
        b = joblib.load(path)
        got = list(getattr(b["starter"], "feature_names_in_", []))
        assert got == list(F.MODEL_COLUMNS), f"trained model uses {got}"
    return len(F.MODEL_COLUMNS)


if __name__ == "__main__":
    cols, n = test_real_data_columns()
    k = test_product_model_inputs()
    print(f"OK  no leakage: the real-data benchmark reads only {len(cols) - 1} source columns "
          f"({', '.join(c for c in cols if c != 'Converted')}) from {n:,} real leads; "
          f"the CRM's lead model uses {k} inputs, all recorded by the website itself.")
