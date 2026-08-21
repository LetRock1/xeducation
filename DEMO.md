# X Education — Closed-Loop Scoring: Demo &amp; Test Guide

This covers the **purchase-triggered closed loop** added on top of the existing
platform (see `FEATURE_GUIDE.md` for the other 7 features, `new.txt` for full
first-time setup). Read this if you just want to run the app and verify the
new behaviour works.

## What's new, in one paragraph

The `.pkl` models (`user-backend/ml_models/*.pkl`) already scored leads on
signup/browsing, but two things never fed back into that scoring: real email
open/click counts (the model's `EmailOpenedCount` feature was always hardcoded
to `0`), and actual purchases (buying a course never re-ran the model or told
anyone which channel converted the buyer). Both are now wired up — that's the
"closed loop": **send email → user engages → loop feeds back into the pkl
model → user buys → loop closes with an attributed confirmation email.**

---

## 1. Run it

You need the 6 `.pkl` files in `user-backend/ml_models/` (see that folder's
`README.txt`) and both backends' `.env` files filled in (see `new.txt` Part 3
for exact contents — Gmail App Password, JWT secrets). Four terminals:

```powershell
# Terminal 1 — user-backend (port 8000)
cd xeducation\user-backend
venv\Scripts\activate
uvicorn main:app --reload --port 8000

# Terminal 2 — marketing-backend (port 8001)
cd xeducation\marketing-backend
venv\Scripts\activate
uvicorn main:app --reload --port 8001

# Terminal 3 — user-frontend (port 5173)
cd xeducation\user-frontend
npm run dev

# Terminal 4 — marketing-frontend (port 5174)
cd xeducation\marketing-frontend
npm run dev
```

Confirm user-backend printed `[ML] All 6 artefacts loaded.` on startup — if it
says "Running in mock mode" instead, the pkl files are missing and scores will
be random, which still works for testing the *plumbing* below but won't
reflect the real model.

`DEMO_MODE=true` in `user-backend/.env` shrinks scheduler wait-times to
1–2 minutes so you don't have to wait hours between test steps.

---

## 2. Test: real email engagement feeds the pkl model

Before this change, `EmailOpenedCount` sent to `predict_lead()` was always
`0`. Now it's pulled live from `email_sends`.

1. Log in on the user site (5173), browse a course, add it to cart, leave it
   (don't check out).
2. Trigger the abandonment jobs immediately instead of waiting:
   ```
   POST http://localhost:8000/api/debug/trigger-jobs
   ```
   This sends a cart-abandonment email and creates a lead.
3. In the marketing dashboard (5174), open that lead → **Email** tab → note
   the current `lead_score`. Send it an email (or use the one auto-sent).
4. Grab its tracking token from `email_sends` (SQLite: `user-backend/xeducation_user.db`,
   table `email_sends`, latest row's `token` column), then simulate an open:
   ```
   GET http://localhost:8001/api/mkt/track/open/<token>.gif
   ```
5. Back on the user site, trigger any behaviour event (e.g. visit another
   course page) or hit:
   ```
   GET http://localhost:8000/api/live-score
   Authorization: Bearer <user JWT>
   ```
   The score/persona returned now factors in the real `EmailOpenedCount` you
   just bumped — check `user-backend` console/DB to confirm the feature
   value isn't `0` anymore for that user.

## 3. Test: purchase rescoring + PLV update

1. As the same test user, add a course to cart and go through
   `POST /api/checkout` (the real "Pay Now" flow, or call it directly with a
   bearer token).
2. Inspect the response — it now includes two new fields:
   ```json
   {
     "message": "Purchase successful! Great! Welcome to X Education.",
     "courses_purchased": ["..."],
     "discount_applied": "None",
     "attributed_to": "your cart reminder email",
     "updated_lead_score": 87.5
   }
   ```
3. In the marketing dashboard, open that user's lead → the `lead_score`,
   `recommended_action`, and `plv` columns should reflect the post-purchase
   rescore, not the pre-purchase snapshot.
4. Check `lead_score_history` (SQLite or via
   `GET /api/mkt/leads/{lead_id}` → cross-reference in DB Browser) for a new
   row with `reason = purchase_conversion`.

## 4. Test: attributed purchase confirmation email

Same checkout as above — check the inbox (or the `[EMAIL MOCK]` console line
if Gmail isn't configured) for a **second** email distinct from the OTP/
marketing emails: subject `Enrollment Confirmed: <course> — X Education`,
body includes a line crediting the channel, e.g. *"Attribution: this
enrollment is credited to your cart reminder email."*

The credited channel comes from the lead's `trigger_reason` at the time of
purchase (`cart_abandon`, `session_end`, `wishlist`, `checkout_abandon`,
`behaviour_snapshot`, `enquiry_submitted`, `email_open`, `email_click`,
`decay`) — mapped to plain English in
`user-backend/email_service.py::ATTRIBUTION_LABELS`. If the user had no prior
lead record, it falls back to "your visit to X Education".

---

## 5. Endpoints you can hit directly

All on **user-backend, port 8000** unless noted. Interactive docs at
`http://localhost:8000/docs` and `http://localhost:8001/docs`.

| Endpoint | Auth | Purpose |
|---|---|---|
| `POST /api/checkout` | user bearer token | Completes purchase — now rescores the lead via the pkl model and sends the attributed confirmation email. Returns `attributed_to` + `updated_lead_score`. |
| `GET /api/live-score` | user bearer token | Live score/persona, now computed with real `EmailOpenedCount` instead of a hardcoded 0. |
| `POST /api/track` | user bearer token | Logs a behaviour event and rescoring pass (also uses real engagement now). |
| `POST /api/enquiry` | user bearer token | Creates a lead from an enquiry form; rescoring also uses real engagement now. |
| `POST /api/debug/trigger-jobs` | none | Force-runs all scheduler jobs immediately (cart/checkout/session/wishlist abandonment) — skip the wait during testing. |
| `GET /api/mkt/leads/{lead_id}` | marketing bearer token (`POST /api/mkt/login` first) | Full lead record including `plv`, `lead_score`, `recommended_action`. |
| `GET /api/mkt/leads/{lead_id}/attribution` | marketing bearer token | Full timeline (behaviour, opens/clicks, purchase) — the same channel data driving the confirmation email. |
| `GET /api/mkt/track/open/{token}.gif` | none (public, hit by email clients) | Simulate an email open manually during testing. |
| `GET /api/mkt/track/click/{token}?to=<url>` | none (public) | Simulate a click; redirects to `<url>`. |

To get a user bearer token for manual `curl`/Postman testing: `POST /api/auth/signup` →
`POST /api/auth/verify-otp` (OTP prints to console if Gmail isn't configured) →
`POST /api/auth/login` → use the returned token as `Authorization: Bearer <token>`.

To get a marketing bearer token: `POST http://localhost:8001/api/mkt/login`
with the `MARKETING_EMAIL`/`MARKETING_PASSWORD` from `marketing-backend/.env`.

---

## Known caveats

- Both backends' `.env` files contain real Gmail credentials — don't commit
  them, and rotate the App Password if they ever end up in git history.
- Leads created before this change won't retroactively get a rescore; only
  new `/api/track`, `/api/enquiry`, `/api/checkout` calls use the fixed
  feature vector.
- If a user purchases with no prior lead row at all (e.g. bought without ever
  triggering a lead-creating event), the confirmation email still sends but
  attribution falls back to "your visit to X Education" and no
  `lead_score_history` row is written (nothing to update).
