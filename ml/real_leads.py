"""
real_leads.py — the public X Education lead data (ml/data/Leads.csv, 9,240 real leads), used ONLY
to test our modelling method on real data. The CRM's own lead model is trained on simulated
leads that carry every signal the website records (ml/train_model.py); the real file has no
video, pricing, cart or checkout columns, so a model trained only on it could not react to them.

Leakage: the real file also has columns the sales team fills in AFTER contacting a lead (Tags,
Lead Quality, Lead Profile, Last Activity, Asymmetrique scores ...). With them a model scores
AUC ~0.98, but a new lead never has them. They are never read here; tests/test_no_leakage.py
fails if one is ever used.
"""
import os

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

HERE = os.path.dirname(os.path.abspath(__file__))
REAL_DATA = os.path.join(HERE, "data", "Leads.csv")

# The only inputs: all are known when a lead signs up, and the website records them too.
REAL_COLUMNS = ["LeadOrigin", "LeadSource", "DoNotEmail", "DoNotCall", "TotalVisits",
                "TotalTimeOnWebsite", "PageViewsPerVisit", "CurrentOccupation", "Specialization"]
REAL_CATEGORICAL = ["LeadOrigin", "LeadSource", "CurrentOccupation", "Specialization"]

# Written by sales after contact (or IDs): never used as inputs.
LEAKY_COLUMNS = ["Tags", "Lead Quality", "Lead Profile", "Last Activity", "Last Notable Activity",
                 "Asymmetrique Activity Index", "Asymmetrique Profile Index", "Asymmetrique Activity Score",
                 "Asymmetrique Profile Score", "Prospect ID", "Lead Number"]

# Kaggle "Lead Source" values -> the website's vocabulary (ml_features.LEAD_SOURCES)
SOURCE_MAP = {
    "Google": "Google", "google": "Google", "Pay per Click Ads": "Google",
    "Direct Traffic": "Direct Traffic", "Click2call": "Direct Traffic",
    "Olark Chat": "Olark Chat", "Live Chat": "Olark Chat",
    "Organic Search": "Organic Search", "bing": "Organic Search",
    "Reference": "Reference", "Referral Sites": "Reference", "Welingak Website": "Reference",
    "Facebook": "Social Media", "Social Media": "Social Media",
    "youtubechannel": "YouTube", "NC_EDM": "Email Campaign",
}
SPEC_MAP = {"Select": None, "E-COMMERCE": "E-Commerce", "E-Business": "E-Commerce"}


def load_real_leads(path=REAL_DATA):
    """The real X Education leads as the website's raw features. Returns (rows, y)."""
    if not os.path.exists(path):
        raise SystemExit(f"Real lead data not found: {path} (see ml/data/README.md)")
    d = pd.read_csv(path)
    visits = d["TotalVisits"].fillna(d["TotalVisits"].median())
    pages = d["Page Views Per Visit"].fillna(d["Page Views Per Visit"].median())
    occ = d["What is your current occupation"].where(d["What is your current occupation"].notna(), None)
    spec = d["Specialization"].map(lambda v: SPEC_MAP.get(v, v) if isinstance(v, str) else None)
    raw = pd.DataFrame({
        "LeadOrigin": d["Lead Origin"],
        "LeadSource": d["Lead Source"].map(lambda v: SOURCE_MAP.get(v, "Direct Traffic") if isinstance(v, str) else "Direct Traffic"),
        "DoNotEmail": (d["Do Not Email"] == "Yes").astype(int),
        "DoNotCall": (d["Do Not Call"] == "Yes").astype(int),
        "TotalVisits": visits.clip(lower=1),
        "TotalTimeOnWebsite": d["Total Time Spent on Website"].fillna(0),
        "PageViewsPerVisit": pages,
        "CurrentOccupation": occ,
        "Specialization": spec,
    })
    return raw.to_dict("records"), d["Converted"].astype(int).to_numpy()


def build_real_preprocessor():
    """One-hot categories, log-scaled counts, consent flags — for the 9 real columns."""
    return ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), REAL_CATEGORICAL),
        ("skew", Pipeline([("log", FunctionTransformer(np.log1p, feature_names_out="one-to-one")),
                           ("scale", StandardScaler())]), ["TotalVisits", "TotalTimeOnWebsite", "PageViewsPerVisit"]),
        ("flags", "passthrough", ["DoNotEmail", "DoNotCall"]),
    ])
