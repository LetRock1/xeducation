# What changed, and why

## v6 (October 2026): learning that does not fool itself

**The problem v6 fixes.** v5 retrained its lead score on "who bought". But the CRM's own calls,
e-mails and coupons made many of those people buy, so the retrained model learned its own follow-ups
as lead quality, and the champion/challenger check on the CRM's own data rewarded that mistake. v6
tells the model what the CRM did, checks every new model on leads the CRM never contacts, and
measures everything against control groups.

### Lead score
* **Base model** (`ml/train_model.py`): trained on 60,000 simulated leads with all 32 inputs the
  website records; logistic regression vs gradient boosting chosen on a held-out 20% (logistic
  regression, AUC 0.877). Saved models from v5 are retrained automatically on the next start, and
  the v5 demo history is replaced.
* **Live layer** (`user-backend/lead_model.py`): a recalibration plus corrections for 13 website
  signals, learned by the learning loop from the CRM's own outcomes.
* **Real data, no leakage** (`ml/real_leads.py`, `ml/experiments/model_benchmark.py`): the 9,240
  real X Education leads, only the 9 columns a new lead has, check the method; `tests/test_no_leakage.py`
  fails if a post-contact column (Tags, Lead Quality, Last Activity, …) is ever used.

### Learning loop (`user-backend/learning.py`; replaces `ml/retrain_from_live.py` and `ml/retrain_nba_from_live.py`)
* Runs inside the server whenever 30 new outcomes are known; no script to run.
* Learns from decision points (what the CRM knew, the step it took then, did the lead buy within
  14 days). The step and the time since the last visit are inputs; the score is read with them
  switched off.
* The new model, the current one and a naive retrain are compared on the **untouched control
  group**; a switch needs a better fit in at least 90% of bootstrap resamples (by person).
* Every run, with its numbers and reason, is on the new **Learning loop** page.

### 5% control group (new)
Chosen by a fixed hash (`crm_settings.json` → `global_control`). These leads never get automatic
steps, campaigns or A/B e-mails; the decision is still computed and logged as "holdout". It is the
honest test set for the learning loop and measures the CRM's total impact.

### A/B tests (rebuilt, `marketing-backend/experiments.py`) and adopted winners (new, `adoption.py`)
* v5 split two variants 50/50 and ran a z-test. v6: 2–3 variants plus a 20% no-e-mail group, hash
  assignment stored with its probability, sample size planned before sending, Newcombe 95%
  intervals, Bonferroni correction for the comparisons actually made, revenue and profit per person,
  a 14-day curve, a split (sample-ratio) check, results by segment, "use the winner" as a campaign.
* **Adopted winners:** a clear winner without a discount becomes the standard information e-mail by
  itself; 10% keep the old e-mail and the CRM keeps checking (confirmed / collecting evidence /
  switched back).
* Checked on simulated tests with known truth (`ml/experiments/ab_engine_check.py`).

### New pages and features
* **What-if paths** on the lead page and the **Journeys** page (`paths.py`, `journeys.py`):
  lifecycle stages, a two-step look-ahead per lead, the funnel and the flow graph.
* **Pipeline board**: lifecycle stages from behaviour, drag-and-drop with the CRM's own view kept,
  Customer only by purchase.
* **Ask the CRM** (`marketing-backend/copilot.py`): questions answered from live data with sources;
  drafts e-mails and A/B tests, never sends.
* **Learning loop** page and the CRM's total impact.

### Starting history (replaces the demo-data scripts)
`ml/generate_history.py` creates 2,000 simulated learners over 180 days through the real backend
code — scoring, decisions, campaigns, six A/B tests with known effects, adopted winners and monthly
learning runs — in a simulated business that differs from the training data in three documented
ways. Marked "simulated" everywhere; `--remove` deletes it. `ml/experiments/history_check.py` checks
six such histories against the known truth (`ml/results/history_runs.md`).

### Start and stop: two files
Only `start-all.bat` and `stop-all.bat` remain. `start-all.bat` runs `ml/first_run.py`, which trains
what is missing and creates the starting history once. Deleted: `train-model.bat`,
`retrain-model.bat`, `seed-demo-data.bat`, `remove-demo-data.bat`, `run-experiments.bat`,
`ml/seed_demo_data.py`, `ml/retrain_from_live.py`, `ml/retrain_nba_from_live.py`.

### Other
* **One settings file** (`crm_settings.json`, read by both backends): tiers, costs, timings,
  learning, A/B defaults, control group, starting history.
* **Gemini made safe for a live demo** (`gemini.py` in both backends): tries `GEMINI_MODEL`, then
  `gemini-flash-latest`, `gemini-3.5-flash`, `gemini-2.5-flash` (old names such as `gemini-1.5-flash`
  are retired); a 12-second limit per call; templates for 5 minutes after a network error (the
  previous setup could hang for minutes offline). `tests/test_gemini_fallback.py`.
* **Speed**: one compute thread per request; event → new score 45 ms (median). The Leads page sends
  only the columns it shows, and the database has indexes on the person id.
* **Privacy**: a plain-words privacy notice (`/privacy`); **Delete my account** on the Settings page
  removes the learner and everything linked to them.
* **Tests**: `tests/e2e_test.py` (36 checks over HTTP, from sign-up to purchase and account deletion),
  `tests/test_no_leakage.py`, `tests/test_gemini_fallback.py`.
* **Experiments**: `ml/run_experiments.py` re-runs E1–E5 into `ml/results/`;
  `ml/experiments/history_seeds.py` re-creates the six-history check. Removed the v5 experiments that
  no longer match the product (`real_benchmark`, `recourse_eval`).
* **Docs**: `README.md`, `HOW_IT_WORKS.md` (replaces `FEATURE_GUIDE.md` and `ML_PIPELINE.md`),
  `DEMO.md` (viva script and hard questions).

## v4-v5: still in place

### Scoring and next-best-action
* One feature module for training and serving (`ml_features.py`); the website used to send values
  the model had never seen, which were silently ignored.
* Score = calibrated probability; the hand-written floors and caps were removed (paying customers
  are still floored at 80). Persona comes from the score.
* "Why this score?" is computed by the model (points per signal), not a fixed text table.
* **Next-best-action** (`nba_core.py`, `nba.py`, `playbook.py`): an uplift model estimates the
  chance to buy under each step (nothing, info e-mail, 10%/20% coupon, call, WhatsApp) and picks
  the highest extra profit, or nothing; consent, call capacity and trigger rules enforced; 15%
  random decisions logged with their probability. Replaced "tier → fixed coupon" templates that
  gave the biggest discounts to people who would buy anyway.
* "How to convert" tips (`recourse.py`) for sales and as "Your next steps" for learners; labelled
  as guidance, not proof of cause.
* Pipeline forecast: expected revenue and customers with a 90% range.

### Learner website
* Tracking fixed: a new visit after 30 minutes idle (the session id used to be reused forever),
  real device and traffic source, page time sent on leave, 4-second dwell for pricing and
  testimonials, video counted after half is watched.
* Forgot/reset password, Settings (communication preferences, phone, password), printable
  brochure, course overview, chat assistant with callback requests.
* Checkout: coupon preview, personal 72-hour coupons, UPI/card form with a Luhn check (simulated
  payment), prices always from the catalogue, no re-buying an owned course.
* Learner dashboard with personalised next steps and recommendations with reasons; the raw
  score is hidden unless the transparency panel is switched on.
* Unverifiable placement/salary claims and testimonials naming real employers replaced by
  catalogue facts and clearly labelled sample testimonials.

### Automation and e-mail
* All triggers (cart, checkout, wishlist, visit ended, enquiry) go through one playbook; one
  follow-up per visit or wishlist item; cool-downs stop pile-ups.
* E-mail content from true catalogue facts; the offer line matches the coupon issued.
* Opt-outs respected everywhere; one-click unsubscribe and `List-Unsubscribe`; click tracking
  redirects only to our own site, and a click re-scores the lead.

### Marketing dashboard
* One row per person in lists, stats, campaigns and A/B tests.
* Today's actions (calls and WhatsApp tasks with outcomes), Callbacks, lead detail (recommended
  action with every option, tips, e-mail coach, WhatsApp, activity, chat, coupon, why this score,
  attribution), campaigns that really send, CSV export, coupons, Q&A.
* Lead decay keeps score and tier consistent and never demotes customers.

### Security and data
* OTP attempt limits and resend cooldown; password reset never reveals whether an e-mail exists;
  the password hash is never returned.
* Validation of e-mails, phones, ratings, questions, coupons and campaign dates; `/api/track`
  accepts only known events for the user's own session.
* The internal re-score endpoint needs `INTERNAL_API_KEY`; SQLite WAL mode and busy timeouts.
* Course catalogue generated from the website's `courses.js` (`tools/sync-catalog.mjs`), so prices
  and facts have one source.
