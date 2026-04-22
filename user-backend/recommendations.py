"""
recommendations.py — Rule-based course recommendation engine.
Uses occupation + specialization + browsing history.
No separate ML model needed — pure logic.
"""

OCCUPATION_MAP = {
    "Working Professional": ["Data Science & Analytics", "MBA Core", "Finance & Banking", "Digital Marketing"],
    "Student":              ["Data Science & Analytics", "Digital Marketing", "E-Commerce", "HR Management"],
    "Businessman":          ["MBA Core", "Finance & Banking", "E-Commerce", "Supply Chain Management"],
    "Unemployed":           ["Digital Marketing", "Data Science & Analytics", "E-Commerce", "HR Management"],
    "Housewife":            ["Digital Marketing", "E-Commerce", "HR Management"],
    "Other":                ["Digital Marketing", "MBA Core", "Data Science & Analytics"],
}

SPECIALIZATION_MAP = {
    "Finance Management":               ["Finance & Banking", "MBA Core", "Data Science & Analytics"],
    "Human Resource Management":        ["HR Management", "MBA Core", "Digital Marketing"],
    "Marketing Management":             ["Digital Marketing", "MBA Core", "Data Science & Analytics"],
    "Operations Management":            ["Operations Management", "Supply Chain Management", "MBA Core"],
    "IT Projects Management":           ["Data Science & Analytics", "MBA Core", "Operations Management"],
    "Supply Chain Management":          ["Supply Chain Management", "Operations Management", "MBA Core"],
    "Banking, Investment And Insurance":["Finance & Banking", "MBA Core", "Data Science & Analytics"],
    "Travel and Tourism":               ["Digital Marketing", "E-Commerce", "Operations Management"],
    "Media and Advertising":            ["Digital Marketing", "MBA Core", "E-Commerce"],
    "Business Administration":          ["MBA Core", "Finance & Banking", "HR Management"],
    "E-Commerce":                       ["E-Commerce", "Digital Marketing", "Data Science & Analytics"],
    "Retail Management":                ["E-Commerce", "Supply Chain Management", "Digital Marketing"],
    "Healthcare Management":            ["HR Management", "MBA Core", "Operations Management"],
    "International Business":           ["MBA Core", "Supply Chain Management", "Finance & Banking"],
    "Services Excellence":              ["HR Management", "MBA Core", "Digital Marketing"],
}

ALL_COURSES = [
    "Data Science & Analytics", "Digital Marketing", "MBA Core",
    "Supply Chain Management", "HR Management", "Finance & Banking",
    "Operations Management", "E-Commerce",
]

def get_recommendations(
    occupation: str,
    specialization: str,
    viewed_slugs: list[str],
    purchased_slugs: list[str],
    limit: int = 4,
) -> list[str]:
    """
    Returns ordered list of recommended course titles.
    Excludes already-purchased courses and recently viewed (to show variety).
    """
    scores = {c: 0 for c in ALL_COURSES}

    occ_recs  = OCCUPATION_MAP.get(occupation, [])
    spec_recs = SPECIALIZATION_MAP.get(specialization, [])

    for i, c in enumerate(occ_recs):
        if c in scores:
            scores[c] += (len(occ_recs) - i) * 2   # higher weight for occupation

    for i, c in enumerate(spec_recs):
        if c in scores:
            scores[c] += (len(spec_recs) - i) * 3  # highest weight for specialization

    # Penalise purchased courses (they shouldn't be recommended again)
    for slug in purchased_slugs:
        title = _slug_to_title(slug)
        if title in scores:
            scores[title] = -999

    # Slightly boost courses they viewed but didn't purchase (re-engage)
    for slug in viewed_slugs:
        title = _slug_to_title(slug)
        if title in scores and scores[title] > 0:
            scores[title] += 5

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [c for c, s in ranked if s > 0][:limit]


def _slug_to_title(slug: str) -> str:
    return {
        "data-science-analytics":    "Data Science & Analytics",
        "digital-marketing":         "Digital Marketing",
        "mba-core":                  "MBA Core",
        "supply-chain-management":   "Supply Chain Management",
        "hr-management":             "HR Management",
        "finance-banking":           "Finance & Banking",
        "operations-management":     "Operations Management",
        "e-commerce":                "E-Commerce",
    }.get(slug, slug.replace("-", " ").title())
