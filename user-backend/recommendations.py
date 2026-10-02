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


def recommend(occupation, specialization, viewed_slugs, purchased_slugs,
              co_purchase=None, cart_slugs=(), limit=4):
    """
    Hybrid recommender. Each course gets points from:
      * profile fit      — occupation / specialization knowledge maps above
      * content affinity — same domain as courses the user looked at
      * collaborative    — "learners who bought X also bought Y" (co_purchase counts)
    Purchased and in-cart courses are excluded. Returns [{title, slug, reason}].
    """
    import catalog
    scores, reasons = {}, {}

    def add(title, pts, why):
        if title not in SLUG_TO_TITLE.values():
            return
        scores[title] = scores.get(title, 0) + pts
        if pts > 0 and (title not in reasons or pts >= reasons[title][0]):
            reasons[title] = (pts, why)

    occ = OCCUPATION_MAP.get(occupation or "", [])
    for i, t in enumerate(occ):
        add(t, (len(occ) - i) * 2, f"Popular with {occupation}s")
    spec = SPECIALIZATION_MAP.get(specialization or "", [])
    for i, t in enumerate(spec):
        add(t, (len(spec) - i) * 3, f"Fits a {specialization} background")

    viewed_domains = {}
    for slug in viewed_slugs or []:
        c = catalog.get_course(slug)
        if c:
            viewed_domains[c["domain"]] = c["title"]
    for c in catalog.all_courses():
        if c["domain"] in viewed_domains:
            add(c["title"], 6, f"Related to {viewed_domains[c['domain']]}, which you viewed")

    for slug, count in (co_purchase or {}).items():
        t = _slug_to_title(slug)
        add(t, 4 * count, "Learners who took your course also took this")

    # don't recommend what they bought, already have in the cart, or are looking at right now
    excluded = {_slug_to_title(s) for s in list(purchased_slugs or []) + list(cart_slugs or [])
                + list(viewed_slugs or [])}
    ranked = sorted(((t, sc) for t, sc in scores.items() if t not in excluded and sc > 0),
                    key=lambda x: -x[1])
    if not ranked:   # cold start: most popular courses
        pop = sorted(catalog.all_courses(), key=lambda c: -c["enrolled"])
        ranked = [(c["title"], 1) for c in pop if c["title"] not in excluded]
        reasons = {t: (1, "Popular with all learners") for t, _ in ranked}
    out = []
    for t, _ in ranked[:limit]:
        slug = next((s for s, title in SLUG_TO_TITLE.items() if title == t), None)
        out.append({"title": t, "slug": slug, "reason": reasons.get(t, (0, ""))[1]})
    return out


def get_recommendations(occupation, specialization, viewed_slugs, purchased_slugs, limit=4):
    """Titles only (kept for older callers)."""
    return [r["title"] for r in recommend(occupation, specialization, viewed_slugs, purchased_slugs, limit=limit)]


def _slug_to_title(slug: str) -> str:
    return SLUG_TO_TITLE.get(slug, (slug or "").replace("-", " ").title())
