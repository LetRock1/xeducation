"""
recommendations.py — Rule-based course recommendation engine.
Covers all 24 courses across 8 domains.
No ML model needed — pure scoring logic.
"""

OCCUPATION_MAP = {
    "Working Professional": [
        "Data Science & Analytics", "AI & Machine Learning", "MBA Core",
        "Finance & Banking", "Financial Modelling & Valuation", "Digital Marketing",
        "Project Management Professional", "Operations Management",
    ],
    "Student": [
        "Data Science & Analytics", "Digital Marketing", "Social Media Marketing",
        "E-Commerce", "HR Management", "Business Analytics",
    ],
    "Businessman": [
        "MBA Core", "Executive MBA Essentials", "MBA in Entrepreneurship",
        "Finance & Banking", "E-Commerce", "D2C & Brand Building",
        "Supply Chain Management", "Operations Management",
    ],
    "Unemployed": [
        "Digital Marketing", "Social Media Marketing", "Data Science & Analytics",
        "E-Commerce", "Marketplace Selling & Management", "HR Management",
    ],
    "Housewife": [
        "Digital Marketing", "Social Media Marketing", "E-Commerce",
        "D2C & Brand Building", "HR Management",
    ],
    "Other": [
        "Digital Marketing", "MBA Core", "Data Science & Analytics",
        "Business Analytics",
    ],
}

SPECIALIZATION_MAP = {
    "Finance Management": [
        "Finance & Banking", "Financial Modelling & Valuation",
        "Investment & Wealth Management", "MBA Core", "Data Science & Analytics",
    ],
    "Human Resource Management": [
        "HR Management", "HR Analytics & People Data", "Talent Acquisition & Recruitment",
        "MBA Core", "Digital Marketing",
    ],
    "Marketing Management": [
        "Digital Marketing", "Performance Marketing", "Social Media Marketing",
        "MBA Core", "Data Science & Analytics",
    ],
    "Operations Management": [
        "Operations Management", "Project Management Professional",
        "Lean Six Sigma Green Belt", "Supply Chain Management", "MBA Core",
    ],
    "IT Projects Management": [
        "Data Science & Analytics", "AI & Machine Learning", "Project Management Professional",
        "MBA Core", "Business Analytics",
    ],
    "Supply Chain Management": [
        "Supply Chain Management", "Logistics & Operations",
        "Procurement & Strategic Sourcing", "Operations Management", "MBA Core",
    ],
    "Banking, Investment And Insurance": [
        "Finance & Banking", "Investment & Wealth Management",
        "Financial Modelling & Valuation", "MBA Core", "Data Science & Analytics",
    ],
    "Travel and Tourism": [
        "Digital Marketing", "E-Commerce", "Operations Management",
        "MBA Core",
    ],
    "Media and Advertising": [
        "Digital Marketing", "Performance Marketing", "Social Media Marketing",
        "MBA Core", "D2C & Brand Building",
    ],
    "Business Administration": [
        "MBA Core", "Executive MBA Essentials", "Finance & Banking",
        "HR Management", "Operations Management",
    ],
    "E-Commerce": [
        "E-Commerce", "D2C & Brand Building", "Marketplace Selling & Management",
        "Digital Marketing", "Performance Marketing",
    ],
    "Retail Management": [
        "E-Commerce", "Marketplace Selling & Management", "Supply Chain Management",
        "Digital Marketing",
    ],
    "Healthcare Management": [
        "HR Management", "MBA Core", "Operations Management",
        "Project Management Professional",
    ],
    "International Business": [
        "MBA Core", "Supply Chain Management", "Finance & Banking",
        "Investment & Wealth Management",
    ],
    "Services Excellence": [
        "HR Management", "MBA Core", "Digital Marketing",
        "Operations Management",
    ],
}

# All 24 course titles — used as the scoring dict keys
ALL_COURSES = [
    # Data Science
    "Data Science & Analytics", "Business Analytics", "AI & Machine Learning",
    # Digital Marketing
    "Digital Marketing", "Social Media Marketing", "Performance Marketing",
    # MBA
    "MBA Core", "Executive MBA Essentials", "MBA in Entrepreneurship",
    # Supply Chain
    "Supply Chain Management", "Logistics & Operations", "Procurement & Strategic Sourcing",
    # HR
    "HR Management", "Talent Acquisition & Recruitment", "HR Analytics & People Data",
    # Finance
    "Finance & Banking", "Financial Modelling & Valuation", "Investment & Wealth Management",
    # Operations
    "Operations Management", "Project Management Professional", "Lean Six Sigma Green Belt",
    # E-Commerce
    "E-Commerce", "D2C & Brand Building", "Marketplace Selling & Management",
]

# Maps slug → title for all 24 courses
SLUG_TO_TITLE = {
    "data-science-analytics":    "Data Science & Analytics",
    "business-analytics":        "Business Analytics",
    "ai-machine-learning":       "AI & Machine Learning",
    "digital-marketing":         "Digital Marketing",
    "social-media-marketing":    "Social Media Marketing",
    "performance-marketing":     "Performance Marketing",
    "mba-core":                  "MBA Core",
    "executive-mba":             "Executive MBA Essentials",
    "mba-entrepreneurship":      "MBA in Entrepreneurship",
    "supply-chain-management":   "Supply Chain Management",
    "logistics-operations":      "Logistics & Operations",
    "procurement-sourcing":      "Procurement & Strategic Sourcing",
    "hr-management":             "HR Management",
    "talent-acquisition":        "Talent Acquisition & Recruitment",
    "hr-analytics":              "HR Analytics & People Data",
    "finance-banking":           "Finance & Banking",
    "financial-modelling":       "Financial Modelling & Valuation",
    "investment-wealth":         "Investment & Wealth Management",
    "operations-management":     "Operations Management",
    "project-management":        "Project Management Professional",
    "lean-six-sigma":            "Lean Six Sigma Green Belt",
    "e-commerce":                "E-Commerce",
    "d2c-brand-building":        "D2C & Brand Building",
    "marketplace-selling":       "Marketplace Selling & Management",
}


def get_recommendations(
    occupation: str,
    specialization: str,
    viewed_slugs: list,
    purchased_slugs: list,
    limit: int = 4,
) -> list:
    scores = {c: 0 for c in ALL_COURSES}

    occ_recs  = OCCUPATION_MAP.get(occupation, [])
    spec_recs = SPECIALIZATION_MAP.get(specialization, [])

    for i, c in enumerate(occ_recs):
        if c in scores:
            scores[c] += (len(occ_recs) - i) * 2

    for i, c in enumerate(spec_recs):
        if c in scores:
            scores[c] += (len(spec_recs) - i) * 3

    for slug in purchased_slugs:
        title = _slug_to_title(slug)
        if title in scores:
            scores[title] = -999

    for slug in viewed_slugs:
        title = _slug_to_title(slug)
        if title in scores and scores[title] > 0:
            scores[title] += 5

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [c for c, s in ranked if s > 0][:limit]


def _slug_to_title(slug: str) -> str:
    return SLUG_TO_TITLE.get(slug, slug.replace("-", " ").title())