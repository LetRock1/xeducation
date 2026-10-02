# What changed, and why

From the original project to the current version. Grouped by area; each line says what
changed and the problem it fixed.

## Machine learning
* **One feature module for training and serving** (`ml_features.py`) — the site used to send
  values the model had never seen (`LeadOrigin="Website Interaction"`, course titles as
  `CourseType`, "Business" as specialisation), so those features were silently ignored.
* **New training data generator (v4)** — the old one multiplied the logit by 4.25, making labels
  almost deterministic (three events took a lead from 6 % to 95 %) and drew behaviours
  independently. v4 drives correlated behaviour from a hidden intent with realistic noise, uses
  exactly the website's vocabulary, includes skipped profiles ("Unknown" instead of defaulting to
  "Unemployed" and scoring ~0 %) and the intent signals the site captures (wishlist, cart,
  checkout, enquiry).
* **One calibrated model instead of six `.pkl` files trained elsewhere** — logistic regression vs
  gradient boosting chosen by held-out log-loss, trained with the backend's own scikit-learn
  (version checked at load), hot-reloaded when retrained; model card on the dashboard.
* **Score = probability** — hand-written floors and caps (cart 62, enquiry 42, student × 0.85)
  removed; cart/checkout/wishlist/enquiry are model features. Only rule kept: paying customers
  are floored at 80.
* **Persona from the calibrated score** — the KMeans persona ranked "Warm" above "Hot" and fed
  back into the model as a feature.
* **"Why this score?" computed by the model** (points per signal) instead of a fixed text table
  that described the old rules.
* **Real-data evaluation** on the X Education Kaggle data with a leakage audit, and four
  reproducible experiments (`ml/experiments/`, `run-experiments.bat`).

## Next-best-action, tips and closed loop (new)
* **Next-best-action engine** (`nba_core.py`, `nba.py`, `playbook.py`): an uplift model estimates
  P(buy) under each action (nothing, info email, 10 %/20 % coupon, call, WhatsApp) and chooses
  the highest expected extra profit, or nothing; consent, call capacity and trigger rules are
  enforced; 15 % exploration with logged propensities. Replaces "tier → fixed coupon" templates
  that gave the biggest discounts to people who would buy anyway.
* **Two model families** — interpretable S-learner and flexible gradient-boosting S-learner;
  `retrain-model.bat` keeps whichever earns more on held-out logged decisions (the robustness
  study showed each wins in different worlds).
* **How-to-convert tips** (`recourse.py`) for sales and as personalised next steps for learners.
* **Closed loop for both models** — score snapshots and decisions labelled by purchases;
  champion/challenger retraining (`retrain_from_live.py`, `retrain_nba_from_live.py`); Model
  health and next-best-action reports (with confidence intervals) on the dashboard.
* **Pipeline forecast** — expected revenue and customers with a 90 % range.
* **Demo data** (`seed-demo-data.bat` / `remove-demo-data.bat`) — clearly marked simulated
  learners so the closed loop can be demonstrated; the `.test` email domain is never mailed.

## Learner website
* **Tracking fixed** — the login session id was reused forever (visits stuck at 1), device was
  always "Desktop" and source always "Direct Traffic"; pricing/testimonials/webinar fired on
  scroll. Now: a visit per 30 minutes idle, real device and utm/referrer source, page time sent
  on leave, 4-second dwell, webinar = seat reserved, video counts after half is watched.
* **New pages**: forgot/reset password, Settings (communication preferences, phone, change
  password), printable brochure, course overview (35 s), chat assistant with callback requests.
* **Checkout** — coupon preview, personal 72-hour coupons, UPI/card form with a Luhn check
  (simulated payment), prices always from the catalogue (the browser's price is ignored),
  cannot re-buy an owned course.
* **Learner dashboard** — personalised next steps, recommendations with reasons, optional
  "What our AI sees" transparency panel; the raw score is no longer shown by default.
* **Honest content** — unverifiable placement/salary statistics and testimonials naming real
  employers replaced by catalogue facts and clearly-labelled sample testimonials.

## Automation & email
* All triggers (cart, checkout, wishlist, visit ended, enquiry) go through one playbook and the
  next-best-action engine; cross-trigger cool-downs and job order stop duplicate emails.
* **One follow-up per visit / per wishlist item** — previously an inactive user could be chased
  every 6 hours and a wishlist every 24 hours indefinitely; the sign-up record no longer blocks
  the first follow-up.
* **Email content from true catalogue facts** (duration, modules, instructor, fee/EMI); no
  invented salaries, placement rates or fake deadlines; the offer line matches the coupon issued.
* **Opt-outs respected everywhere** (the scheduler used to ignore "Do not email"); working
  one-click unsubscribe + `List-Unsubscribe`; click tracking redirects only to our own site
  (an open redirect before), and a click now re-scores the lead with the model instead of
  adding fixed points.
* Course links fixed (`/course/<slug>` → `/courses/<slug>`).

## Marketing dashboard & CRM API
* **One row per person** (latest touchpoint) in lists, stats, campaigns and A/B tests — a person
  with three abandoned carts used to be three "leads".
* **Today's actions** (calls/WhatsApp chosen by next-best-action, with outcomes) and
  **Callbacks** pages.
* **Lead detail** rebuilt: recommended action with all options, tips, email coach, WhatsApp
  (wa.me), activity, chat, coupon, why-this-score, attribution, re-score.
* **Campaigns actually send** (1-minute timer, "Send now", personalisation, delivery / click /
  purchase stats, send-once guard).
* **A/B tests with real statistics** — one email per person, random 50/50 split,
  two-proportion z-test, confidence interval, sample size; a winner only when significant.
* **Run automations now** button, pipeline forecast, demo-data banner, CSV export per person,
  Q&A answers emailed to the learner, coupons with validation.
* **Lead decay** keeps score and tier consistent, never demotes customers, and waits 10 minutes
  in demo mode (was 2).

## Security & data integrity
* OTP: attempt limit, resend cooldown, purpose-specific codes; password reset never reveals
  whether an email exists; password hash never returned by `/api/auth/me`.
* Validation of emails, phones, ratings, questions, coupon ranges, campaign dates.
* `/api/track` only accepts known events and the user's own session.
* Internal re-score endpoint protected by `INTERNAL_API_KEY`; "run automations" open only in
  demo mode or with the key.
* SQLite WAL mode and busy timeouts ("database is locked" fixes).
* Next-best-action can no longer crash when every action is blocked (opted out everywhere), and
  never logs "do nothing" for an enquiry that was in fact emailed.

## Developer experience
* `start-all.bat` / `stop-all.bat` (venvs, installs, catalogue sync, first-run training, all four
  servers), `train-model.bat`, `retrain-model.bat`, `seed-demo-data.bat`,
  `remove-demo-data.bat`, `run-experiments.bat`.
* `.env.example` for both backends; `README.md`, `ML_PIPELINE.md`, `FEATURE_GUIDE.md`,
  `DEMO.md` (the old `README.txt` is replaced by `README.md`).
* Course catalogue generated for the backend from the website's `courses.js`
  (`tools/sync-catalog.mjs`), so prices and facts have one source.
