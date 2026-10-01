# X Education — Revenue Intelligence Features (Changelog)

This document summarizes the 7 new features added on top of the existing
X Education platform (user-backend, marketing-backend, user-frontend,
marketing-frontend), plus supporting environment setup.

## 0. Environment setup

- Created Python virtual environments and installed dependencies for both
  backends:
  - `user-backend/venv`
  - `marketing-backend/venv`
- Fixed a pre-existing bug where `print()` statements containing `→` crashed
  both backends on startup under Windows' default `cp1252` console encoding
  (`database.py`, `scheduler.py`, `marketing-backend/main.py`). Replaced with
  ASCII `->`.

## 1. Shared schema — `user-backend/database.py`

New tables (created via `init_db()`, safe on existing DBs):

- `checkout_sessions` — tracks when a user starts checkout vs. completes it.
- `email_sends` — logs every marketing email sent, with a unique `token`,
  `variant` (A/B), `ab_test_id`, open/click counters and timestamps.
- `lead_score_history` — audit trail of score/tier changes (decay, email
  opens/clicks, etc).

New columns on `leads` (via additive `ALTER TABLE` migration): `plv`,
`last_active_at`, `decayed`.

New helper functions: `get_abandoned_checkouts`, `start_checkout_session`,
`complete_latest_checkout_session`, `mark_checkout_email_sent`,
`insert_email_send`, `mark_email_opened`, `mark_email_clicked`,
`log_score_change`, `compute_plv`, `update_lead_plv`.

## 2. Checkout abandonment

- **user-backend**
  - `POST /api/checkout/start` — records a checkout session when the user
    reaches the checkout page.
  - `POST /api/checkout` — now marks the session completed on purchase.
  - `scheduler.py`: new `checkout_abandonment_job()`, modeled on the existing
    `cart_abandonment_job()`, fires an email with a `LAST_CHANCE_30` coupon
    for checkouts left unfinished (`CHECKOUT_ABANDON_MINUTES`, cooldown via
    `recent_lead_exists`).
  - `POST /api/debug/trigger-jobs` now also runs the checkout job (and
    wishlist job) for demo purposes.
  - `genai_mock.py` (both copies): added `checkout_abandon` trigger copy in
    `_nurture` and `_target_immediately`, and a coupon override to
    `LAST_CHANCE_30` for this trigger.
- **user-frontend**
  - `tracker.js`: new `checkoutStart()` method.
  - `api.js`: new `checkoutStart()` call.
  - `Checkout.jsx`: fires `checkout/start` + tracker event once per mount.

## 3. Closed-loop email open/click tracking

- `email_service.py` (both copies): `send_marketing_email()` now accepts
  `tracking_pixel_url` and `cta_url`/`cta_label`, injecting a 1×1 tracking
  pixel and a tracked CTA button into the HTML email.
- **user-backend**: `scheduler.py` adds `_send_tracked_email()`, used by
  every job (cart, wishlist, checkout) and by the enquiry handler in
  `main.py`, which generates a token, logs an `email_sends` row, and builds
  the pixel/click URLs pointing at marketing-backend.
- **marketing-backend**: two new **unauthenticated** routes —
  `GET /api/mkt/track/open/{token}.gif` (1×1 GIF, bumps
  `email_opened_count` and `lead_score` +3) and
  `GET /api/mkt/track/click/{token}` (redirects to the destination URL,
  bumps `lead_score` +7). Both log to `lead_score_history`.
  `POST /api/mkt/send-email` also now generates a token and wraps the email.
- New env vars: `PUBLIC_BASE_URL`, `USER_FRONTEND_URL` (marketing-backend);
  `MKT_PUBLIC_BASE_URL`, `USER_FRONTEND_URL` (user-backend).

## 4. Lead decay / re-scoring

- New `marketing-backend/decay.py`: `lead_decay_job()` downgrades a lead one
  tier (`Target Immediately → Nurture → Marketing Campaign → Low Priority`)
  if there's been no behaviour event or email open since the lead was
  created, recomputes PLV for the new tier, and logs to
  `lead_score_history` (reason `decay`).
- `marketing-backend/main.py`: starts an `APScheduler` on startup running
  the decay job every 5 minutes (this dependency existed but was unused
  before).

## 5. Explainability

- New `marketing-backend/explain.py`: pure-function `explain_lead()`
  reconstructs human-readable scoring factors (trigger floors, engagement
  signals, occupation dampening) from the lead's stored columns — no ML
  dependency needed.
- `GET /api/mkt/leads/{lead_id}/explain` — new endpoint.
- `marketing-frontend`: new "Why this score?" tab in `LeadDetail.jsx`.

## 6. Attribution

- `GET /api/mkt/leads/{lead_id}/attribution` — merges behaviour events,
  email opens/clicks, the lead-creation touch, and purchases into one
  chronological timeline with `first_touch`/`last_touch_before_purchase`.
- `GET /api/mkt/campaign-influence` — aggregates opens/clicks/influenced
  conversions (purchase within 7 days of a touch) per trigger reason.
- `marketing-frontend`: new "Attribution" tab in `LeadDetail.jsx`, and a
  "Campaign Influence" bar chart on `Dashboard.jsx`.

## 7. A/B testing

- New `ab_tests` table in `xeducation_marketing.db`.
- `POST /api/mkt/ab-tests` (create), `GET /api/mkt/ab-tests` (list),
  `POST /api/mkt/ab-tests/{id}/send` (50/50 split across matching-tier
  leads, tracked via `email_sends.variant`/`ab_test_id`),
  `GET /api/mkt/ab-tests/{id}/results` (per-variant open/click rate,
  winner once both variants have ≥5 sends).
- `marketing-frontend`: new `ABTests.jsx` page, `Sidebar.jsx` nav entry,
  `App.jsx` route.

## 8. Predictive Lifetime Value (PLV)

- `compute_plv(user_id, tier, conversion_probability)` — total spent +
  `avg_course_price × conversion_probability × tier_multiplier` heuristic.
  Implemented in both `user-backend/database.py` and
  `marketing-backend/main.py`/`decay.py`.
- Persisted to `leads.plv` whenever a lead is created (`_save_lead`,
  enquiry handler) or re-tiered (decay job).
- `GET /api/mkt/leads?sort=plv` and new `GET /api/mkt/priority-queue`
  (leads ranked by `lead_score × plv`).
- `marketing-frontend`: PLV column + "Sort by PLV" toggle in `Leads.jsx`,
  PLV shown in `LeadDetail.jsx`, "Priority Queue" quick-link on
  `Dashboard.jsx`.

## Verification performed

- Both backends import and boot cleanly (`uvicorn main:app`), DB migrations
  run without error against the existing (non-empty) databases.
- Smoke-tested via curl: login, stats, priority-queue, campaign-influence,
  explain, attribution, tracking pixel (200), click redirect (307), full
  A/B test lifecycle (create → send → results with per-variant stats),
  `debug/trigger-jobs` (including the new checkout job).
- Both `user-frontend` and `marketing-frontend` build cleanly with `vite build`.

## Known follow-ups (not done)

- `.env` files in both backends contain real Gmail credentials committed to
  the repo — recommend rotating and adding `.env` to `.gitignore` before
  sharing this project.
- PLV/explain/attribution data for leads created *before* this change won't
  be backfilled (e.g. `plv=0` on old rows) — only new/updated leads get it.
