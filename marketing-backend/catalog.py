"""
catalog.py — the course catalogue as the backend sees it.

catalog.json is generated from the website's own course list
(user-frontend/src/data/courses.js) by tools/sync-catalog.mjs, which
start-all.bat runs on every launch. The backend uses it so that prices,
titles and course facts come from the server, never from the browser
(previously anyone could add a course to the cart at ₹1 by editing the
request).
"""
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
# user-backend keeps catalog.json next to this file; marketing-backend reads the same one.
_PATH = next((p for p in (os.path.join(_HERE, "catalog.json"),
                          os.path.join(_HERE, "..", "user-backend", "catalog.json"))
              if os.path.exists(p)), os.path.join(_HERE, "catalog.json"))
_cache = {"mtime": None, "courses": [], "by_slug": {}}


def _load():
    try:
        mtime = os.path.getmtime(_PATH)
    except OSError:
        return _cache
    if mtime != _cache["mtime"]:
        with open(_PATH, encoding="utf-8") as f:
            courses = json.load(f)
        _cache.update(mtime=mtime, courses=courses, by_slug={c["slug"]: c for c in courses})
    return _cache


def all_courses():
    return _load()["courses"]


def get_course(slug):
    return _load()["by_slug"].get(slug) if slug else None


def title_of(slug, default=None):
    c = get_course(slug)
    return c["title"] if c else (default if default is not None else (slug or ""))


def price_of(slug):
    c = get_course(slug)
    return float(c["price"]) if c else None


def average_price():
    courses = all_courses()
    return sum(c["price"] for c in courses) / len(courses) if courses else 40000.0


def slug_for_title(title):
    """Best-effort reverse lookup (older lead rows only stored a title)."""
    if not title:
        return None
    t = title.strip().lower()
    for c in all_courses():
        if c["title"].lower() == t or c["slug"] == t:
            return c["slug"]
    return None


def facts(slug):
    """Short, true facts about a course for emails / chat (no invented numbers)."""
    c = get_course(slug)
    if not c:
        return None
    modules = ", ".join(m["title"] for m in c["curriculum"][:4])
    return {
        "title": c["title"], "duration": c["duration"], "level": c["level"],
        "price": c["price"], "emi": c["emi"], "modules": modules,
        "outcomes": c["outcomes"], "instructor": c["instructor"]["name"],
        "instructor_role": c["instructor"]["role"],
    }
