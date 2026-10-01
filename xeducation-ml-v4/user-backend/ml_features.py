"""
ml_features.py — THE single source of truth for model features.

Used by:
  * ml/generate_dataset.py   (to produce training data with these exact columns)
  * ml/train_model.py        (to engineer features before training)
  * ml/retrain_from_live.py  (closed-loop retraining on real outcomes)
  * user-backend/predict.py  (to engineer features at prediction time)

Because training and serving import the SAME functions, the model can never
again receive a value it was not trained on (e.g. LeadOrigin="Website
Interaction" or CourseType="Browsing"): normalize_raw() maps anything outside
the training vocabulary to "Unknown"/"Other" before the model sees it.
"""
import numpy as np
import pandas as pd

FEATURE_VERSION = 4

# ── Vocabularies (what the website can actually produce) ────────────────────
LEAD_ORIGINS = ["Landing Page Submission", "Lead Add Form", "API",
                "Quick Add Form", "Lead Import"]
LEAD_SOURCES = ["Google", "Direct Traffic", "Organic Search", "Olark Chat",
                "Reference", "Social Media", "Email Campaign", "Webinar",
                "LinkedIn", "YouTube"]
DEVICE_TYPES = ["Mobile", "Desktop", "Tablet"]
OCCUPATIONS = ["Working Professional", "Student", "Unemployed",
               "Businessman", "Housewife", "Other", "Unknown"]
SPECIALIZATIONS = [
    "Finance Management", "Human Resource Management", "Marketing Management",
    "Operations Management", "IT Projects Management", "Supply Chain Management",
    "Banking, Investment And Insurance", "Travel and Tourism",
    "Media and Advertising", "Business Administration", "E-Commerce",
    "Retail Management", "Healthcare Management", "International Business",
    "Services Excellence", "Unknown",
]
COURSE_TYPES = ["Data Science & Analytics", "Digital Marketing", "MBA Core",
                "Supply Chain Management", "HR Management", "Finance & Banking",
                "Operations Management", "E-Commerce", "Unknown"]
CITIES = ["Mumbai", "Pune", "Delhi", "Bangalore", "Hyderabad", "Chennai",
          "Kolkata", "Ahmedabad", "Jaipur", "Surat", "Lucknow", "Nagpur",
          "Other", "Unknown"]
COUNTRIES = ["India", "UAE", "USA", "UK", "Singapore", "Australia", "Canada", "Other"]
AGE_BRACKETS = ["18-24", "25-30", "31-35", "36-45", "46+", "Unknown"]
HOW_HEARD = ["Online Search", "Word of Mouth", "Social Media Ad",
             "Friend/Colleague Referral", "Email Newsletter", "Webinar/Event",
             "Other Website", "Unknown"]

# Course slug (website) -> CourseType (model vocabulary)
COURSE_TYPE_BY_SLUG = {
    "data-science-analytics": "Data Science & Analytics",
    "business-analytics": "Data Science & Analytics",
    "ai-machine-learning": "Data Science & Analytics",
    "digital-marketing": "Digital Marketing",
    "social-media-marketing": "Digital Marketing",
    "performance-marketing": "Digital Marketing",
    "mba-core": "MBA Core",
    "executive-mba": "MBA Core",
    "mba-entrepreneurship": "MBA Core",
    "supply-chain-management": "Supply Chain Management",
    "logistics-operations": "Supply Chain Management",
    "procurement-sourcing": "Supply Chain Management",
    "hr-management": "HR Management",
    "talent-acquisition": "HR Management",
    "hr-analytics": "HR Management",
    "finance-banking": "Finance & Banking",
    "financial-modelling": "Finance & Banking",
    "investment-wealth": "Finance & Banking",
    "operations-management": "Operations Management",
    "project-management": "Operations Management",
    "lean-six-sigma": "Operations Management",
    "e-commerce": "E-Commerce",
    "d2c-brand-building": "E-Commerce",
    "marketplace-selling": "E-Commerce",
}

CATEGORICAL = {
    "LeadOrigin": (LEAD_ORIGINS, "Landing Page Submission"),
    "LeadSource": (LEAD_SOURCES, "Direct Traffic"),
    "DeviceType": (DEVICE_TYPES, "Desktop"),
    "CurrentOccupation": (OCCUPATIONS, "Unknown"),
    "Specialization": (SPECIALIZATIONS, "Unknown"),
    "CourseType": (COURSE_TYPES, "Unknown"),
    "City": (CITIES, "Unknown"),
    "Country": (COUNTRIES, "Other"),
    "AgeBracket": (AGE_BRACKETS, "Unknown"),
    "HowDidYouHear": (HOW_HEARD, "Unknown"),
}
# value used when the field is empty vs. when it is filled but not in the list
_EMPTY_DEFAULT = {"Country": "India", "City": "Unknown"}
_OUT_OF_VOCAB = {"City": "Other"}

# numeric raw features: (min, max) clip range
NUMERIC = {
    "TotalVisits": (1, 30),
    "TotalTimeOnWebsite": (0, 6000),       # seconds, summed over all visits
    "PageViewsPerVisit": (0, 20),
    "EmailOpenedCount": (0, 10),
}
# 0/1 flags
BINARY = [
    "VideoWatched", "BrochureDownloaded", "ChatInitiated",
    "PricingPageVisited", "TestimonialVisited", "WebinarAttended",
    "AddedToWishlist", "AddedToCart", "CheckoutStarted", "EnquirySubmitted",
    "WhatsAppOptIn", "DoNotEmail", "DoNotCall",
]

RAW_FEATURES = list(CATEGORICAL) + list(NUMERIC) + BINARY
TARGET = "Converted"


def course_type_from(value):
    """Accepts a slug, a site domain, a course title or a CourseType."""
    if not value:
        return "Unknown"
    v = str(value).strip()
    if v in COURSE_TYPES:
        return v
    if v in COURSE_TYPE_BY_SLUG:
        return COURSE_TYPE_BY_SLUG[v]
    slug = v.lower().replace("&", "").replace(",", "")
    slug = "-".join(slug.split())
    if slug in COURSE_TYPE_BY_SLUG:
        return COURSE_TYPE_BY_SLUG[slug]
    if v == "MBA":
        return "MBA Core"
    low = v.lower()
    for key, ct in (("data", "Data Science & Analytics"), ("analytic", "Data Science & Analytics"),
                    ("machine learning", "Data Science & Analytics"), ("marketing", "Digital Marketing"),
                    ("mba", "MBA Core"), ("supply", "Supply Chain Management"),
                    ("logistic", "Supply Chain Management"), ("procure", "Supply Chain Management"),
                    ("hr", "HR Management"), ("talent", "HR Management"), ("finance", "Finance & Banking"),
                    ("financial", "Finance & Banking"), ("invest", "Finance & Banking"),
                    ("operation", "Operations Management"), ("project", "Operations Management"),
                    ("six sigma", "Operations Management"), ("commerce", "E-Commerce"),
                    ("d2c", "E-Commerce"), ("marketplace", "E-Commerce")):
        if key in low:
            return ct
    return "Unknown"


def _yes_no_to_int(v):
    if isinstance(v, str):
        return 1 if v.strip().lower() in ("yes", "1", "true") else 0
    try:
        return 1 if int(v) else 0
    except (TypeError, ValueError):
        return 0


def normalize_raw(raw: dict) -> dict:
    """Clean one lead's raw features so they always match the training vocabulary."""
    out = {}
    for col, (vocab, unknown) in CATEGORICAL.items():
        v = raw.get(col)
        if col == "CourseType":
            out[col] = course_type_from(v)
            continue
        if v is None or (isinstance(v, float) and np.isnan(v)) or str(v).strip() == "":
            out[col] = _EMPTY_DEFAULT.get(col, unknown)
        else:
            v = str(v).strip()
            out[col] = v if v in vocab else _OUT_OF_VOCAB.get(col, unknown)
    for col, (lo, hi) in NUMERIC.items():
        try:
            v = float(raw.get(col) or 0)
        except (TypeError, ValueError):
            v = 0.0
        out[col] = float(min(max(v, lo), hi))
    for col in BINARY:
        out[col] = _yes_no_to_int(raw.get(col, 0))
    return out


def engineer(df: pd.DataFrame) -> pd.DataFrame:
    """Add engineered features. Identical for training and serving."""
    d = df.copy()
    d["TimePerVisit"] = d["TotalTimeOnWebsite"] / d["TotalVisits"].clip(lower=1)
    d["IsReturningVisitor"] = (d["TotalVisits"] > 1).astype(int)
    d["ContentEngagement"] = (d["VideoWatched"] + d["BrochureDownloaded"] +
                              d["TestimonialVisited"] + d["WebinarAttended"])
    d["CommerceIntent"] = (d["AddedToWishlist"] + 2 * d["AddedToCart"] +
                           3 * d["CheckoutStarted"] + 2 * d["EnquirySubmitted"] +
                           d["PricingPageVisited"])
    d["ProfileCompleteness"] = (
        (d["CurrentOccupation"] != "Unknown").astype(int) +
        (d["Specialization"] != "Unknown").astype(int) +
        (d["City"] != "Unknown").astype(int) +
        (d["AgeBracket"] != "Unknown").astype(int) +
        (d["HowDidYouHear"] != "Unknown").astype(int)
    )
    return d


ENGINEERED_NUMERIC = ["TimePerVisit", "IsReturningVisitor", "ContentEngagement",
                      "CommerceIntent", "ProfileCompleteness"]
MODEL_CATEGORICAL = list(CATEGORICAL)
MODEL_NUMERIC = list(NUMERIC) + BINARY + ENGINEERED_NUMERIC
MODEL_COLUMNS = MODEL_CATEGORICAL + MODEL_NUMERIC


def to_model_frame(rows) -> pd.DataFrame:
    """list[dict] or DataFrame of raw leads -> engineered frame in model column order."""
    if isinstance(rows, pd.DataFrame):
        records = rows.to_dict("records")
    else:
        records = list(rows)
    df = pd.DataFrame([normalize_raw(r) for r in records], columns=RAW_FEATURES)
    return engineer(df)[MODEL_COLUMNS]


# ── Score → tier / persona (one definition used everywhere) ─────────────────
TIERS = [(80, "Target Immediately"), (60, "Nurture via Email/WhatsApp"),
         (40, "Marketing Campaign"), (0, "Low Priority")]


def tier_for(score: float) -> str:
    for cutoff, name in TIERS:
        if score >= cutoff:
            return name
    return "Low Priority"


def persona_for(score: float, is_customer: bool = False) -> str:
    if is_customer:
        return "Customer"
    if score >= 60:
        return "Hot Lead"
    if score >= 35:
        return "Warm Lead"
    return "Cold Lead"


# ── Human-readable explanation of what moved the score ─────────────────────
# (feature, label, value that means "signal absent")
EXPLAIN_SIGNALS = [
    ("CheckoutStarted", "Started checkout", 0),
    ("AddedToCart", "Added a course to cart", 0),
    ("EnquirySubmitted", "Submitted an enquiry", 0),
    ("AddedToWishlist", "Wishlisted a course", 0),
    ("WebinarAttended", "Attended a webinar", 0),
    ("BrochureDownloaded", "Downloaded a brochure", 0),
    ("ChatInitiated", "Opened chat", 0),
    ("VideoWatched", "Watched a course video", 0),
    ("PricingPageVisited", "Spent time on pricing", 0),
    ("TestimonialVisited", "Read testimonials", 0),
    ("EmailOpenedCount", "Engaged with our emails", 0),
    ("WhatsAppOptIn", "Opted in to WhatsApp", 0),
    ("TotalVisits", "Returning visitor", 1),
    ("TotalTimeOnWebsite", "Time on site", 120),     # vs. a typical 2-minute visit
    ("CurrentOccupation", "Occupation", "Unknown"),
    ("LeadSource", "Traffic source", "Direct Traffic"),
    ("DoNotEmail", "Opted out of email", 0),
    ("DoNotCall", "Opted out of calls", 0),
]
