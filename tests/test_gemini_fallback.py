"""
Checks the optional Gemini helper (user-backend/gemini.py) without internet or a real key, using a
stand-in for the google.generativeai package:
  * a retired model name (404) -> the next candidate is tried, and the one that works is remembered
  * a network error -> templates at once, and Gemini is skipped for the next 5 minutes
  * the content generator falls back to its templates whenever Gemini fails
Run:  user-backend\\venv\\Scripts\\python.exe tests\\test_gemini_fallback.py
"""
import importlib
import json
import os
import sys
import time
import types

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "user-backend"))

calls = []


class FakeModel:
    behaviour = {}

    def __init__(self, name):
        self.name = name

    def generate_content(self, prompt, generation_config=None, request_options=None):
        calls.append((self.name, request_options))
        what = FakeModel.behaviour.get(self.name, "ok")
        if what == "404":
            raise Exception(f"404 models/{self.name} is not found for API version v1beta")
        if what == "network":
            raise Exception("HTTPSConnectionPool: Max retries exceeded (Caused by ProxyError / connection refused)")
        text = json.dumps({"email_subject": "Hi from Gemini", "email_body": "Body", "whatsapp_message": "WA",
                           "call_script": "Script"}) if generation_config else "plain answer"
        return types.SimpleNamespace(text=text)


fake = types.ModuleType("google.generativeai")
fake.configured = {}
fake.configure = lambda **kw: fake.configured.update(kw)
fake.GenerativeModel = FakeModel
google = types.ModuleType("google")
google.generativeai = fake
sys.modules["google"] = google
sys.modules["google.generativeai"] = fake

passed = failed = 0


def check(name, ok, detail=""):
    global passed, failed
    passed += bool(ok)
    failed += not ok
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail and not ok else ""))


def fresh():
    import gemini
    importlib.reload(gemini)
    calls.clear()
    return gemini


os.environ.pop("GEMINI_API_KEY", None)
g = fresh()
check("no key: Gemini is off", not g.enabled())

os.environ["GEMINI_API_KEY"] = "test-key-not-real"
os.environ["GEMINI_MODEL"] = "gemini-1.5-flash"            # retired name some old .env files still have
FakeModel.behaviour = {"gemini-1.5-flash": "404", "gemini-flash-latest": "404"}
g = fresh()
out = g.generate("hello")
check("retired names are skipped", [c[0] for c in calls] == ["gemini-1.5-flash", "gemini-flash-latest", "gemini-3.5-flash"],
      str(calls))
check("the working model is remembered", g.model_name() == "gemini-3.5-flash")
calls.clear()
g.generate("again")
check("next call goes straight to it", [c[0] for c in calls] == ["gemini-3.5-flash"], str(calls))
check("every call has a time limit", all((c[1] or {}).get("timeout") for c in calls))
check("REST transport (fails fast offline)", fake.configured.get("transport") == "rest")

FakeModel.behaviour = {"gemini-1.5-flash": "network", "gemini-flash-latest": "network", "gemini-3.5-flash": "network"}
g = fresh()
t = time.time()
try:
    g.generate("hello")
    check("network error raises", False)
except Exception:
    check("network error raises at once", time.time() - t < 1.0)
check("after a network error Gemini pauses", not g.enabled())

# the content generator falls back to its templates
import genai_mock  # noqa: E402
importlib.reload(genai_mock)
FakeModel.behaviour = {}
g = fresh()
importlib.reload(genai_mock)
c = genai_mock.generate_content("Asha Rao", "Working Professional", "Finance", "Data Science & Analytics",
                                "Nurture via Email/WhatsApp", course_slug="data-science-analytics", offer_pct=0)
check("with Gemini working, Gemini writes the e-mail", c["email_subject"] == "Hi from Gemini", c.get("email_subject"))
FakeModel.behaviour = {"gemini-1.5-flash": "network", "gemini-flash-latest": "network", "gemini-3.5-flash": "network",
                       "gemini-2.5-flash": "network"}
g = fresh()
importlib.reload(genai_mock)
t = time.time()
c = genai_mock.generate_content("Asha Rao", "Working Professional", "Finance", "Data Science & Analytics",
                                "Nurture via Email/WhatsApp", course_slug="data-science-analytics", offer_pct=0)
check("offline: template e-mail at once", c["email_subject"] != "Hi from Gemini" and time.time() - t < 1.0,
      c.get("email_subject"))

print(f"\n{passed} of {passed + failed} checks passed")
sys.exit(1 if failed else 0)
