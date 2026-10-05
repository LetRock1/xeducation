"""
gemini.py — the one place that talks to Gemini. Optional: without GEMINI_API_KEY nothing calls it,
and every caller falls back to its templates or rules when a call fails.

Three things make it safe for a live demo:
  * Google retires model names every few months (gemini-1.5-flash in 2025, gemini-2.0-flash in
    June 2026), so it tries GEMINI_MODEL from .env first, then gemini-flash-latest, gemini-3.5-flash
    and gemini-2.5-flash, and remembers the first one that answers.
  * Every call has a time limit (GEMINI_TIMEOUT seconds, default 12) and uses the REST transport,
    which fails at once when there is no internet (the default gRPC transport kept retrying for
    minutes in our tests).
  * After a network failure Gemini is skipped for 5 minutes, so an offline demo does not wait on
    every e-mail.
(The same file is in user-backend/ and marketing-backend/.)
"""
import os
import time

CANDIDATES = ["gemini-flash-latest", "gemini-3.5-flash", "gemini-2.5-flash"]
PAUSE_AFTER_NETWORK_ERROR = 300
_state = {"model": None, "down_until": 0.0}


def enabled():
    return bool(os.getenv("GEMINI_API_KEY")) and time.time() >= _state["down_until"]


def _names():
    first = (os.getenv("GEMINI_MODEL") or "").strip()
    names = [first] if first else []
    return names + [m for m in CANDIDATES if m != first]


def _model_missing(e):
    s = str(e).lower()
    return any(k in s for k in ("404", "not found", "not_found", "is not supported", "no longer available",
                                "deprecated"))


def generate(prompt, json_mode=False):
    """Gemini's answer as text. Raises when it cannot answer (the caller then uses its fallback)."""
    if not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY is not set")
    if time.time() < _state["down_until"]:
        raise RuntimeError("Gemini paused after a network error")
    import google.generativeai as genai
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"), transport="rest")
    opts = {"timeout": float(os.getenv("GEMINI_TIMEOUT", "12"))}
    cfg = {"response_mime_type": "application/json"} if json_mode else None
    names = [_state["model"]] if _state["model"] else _names()
    last = None
    for name in names:
        try:
            model = genai.GenerativeModel(name)
            resp = (model.generate_content(prompt, generation_config=cfg, request_options=opts) if cfg
                    else model.generate_content(prompt, request_options=opts))
            text = resp.text
            _state["model"] = name
            return text
        except Exception as e:
            last = e
            if _model_missing(e):
                print(f"[GEMINI] model '{name}' is not available; trying the next one")
                if _state["model"] == name:          # the remembered model was retired: try them all again
                    _state["model"] = None
                    return generate(prompt, json_mode)
                continue
            if any(k in str(e).lower() for k in ("connection", "timed out", "timeout", "proxy", "resolve",
                                                 "unreachable", "network")):
                _state["down_until"] = time.time() + PAUSE_AFTER_NETWORK_ERROR
                print(f"[GEMINI] network problem — using templates for the next {PAUSE_AFTER_NETWORK_ERROR // 60} minutes")
            raise
    raise last or RuntimeError("no Gemini model is available")


def model_name():
    """The model that last answered (None before the first successful call)."""
    return _state["model"]
