# What changed, and why

## v6.3 (6 October 2026): one pool of learners, and the simulated learners keep living

**Why.** v6.2 hid the simulated learners behind a "real people" switch and called them a test
bench. But they are the CRM's starting business: a CRM is normally switched on inside a company that
already has leads, and in this project those leads are simulated. Hidden, the dashboard looked empty
and the system looked like a demo that only reacts when someone clicks. Now there is one pool of
learners, the simulated ones keep using the website in real time, and the CRM works on all of them
in the same way, all the time.

### The simulated learners keep living (`ml/live_simulation.py`)
* While the servers run, the 2,000 simulated learners keep coming back, reading pages, watching
  videos, adding to the cart and sending enquiries; they react to the e-mails, coupons, calls and
  WhatsApp messages the CRM really sends them, and they buy. About 13 new ones sign up every day
  (sign-up → code from their inbox → profile → first visit).
* They use the website's own API over HTTP with the requests a browser sends; the CRM has no special
  code for them. Their behaviour is the documented simulator of the history (the 2,000 are
  re-created exactly from its seed), so the live data continues the history at the same pace
  (7.4 purchases a day expected vs 7.2 in the history's last 30 days).
* Real time, no catching up: when the servers are off, nothing happens.
* A simulated advisor makes the calls and WhatsApp messages the CRM asks for them (their numbers are
  fake), 1–24 hours later, unless you record the outcome first. It has its own daily call capacity,
  so simulated learners never take a real advisor's calls, and it is refused for real people's tasks.
  Today's actions says who did each task.
* Their hidden traits and the simulator's to-do list are in its own database
  (`user-backend/simulation_world.db`), never in the CRM's.
* Dashboard → **Simulated learners, live**: the last 24 hours, their latest steps, **Send a learner
  to the website now**, **New sign-up now**, **Pause**. `crm_settings.json` → `live_simulation`
  (on/off, sign-ups per day, the advisor's hours).

### One pool
* Leads, Today's actions, Pipeline, the Learning loop's live activity and the Dashboard show
  everyone by default, with a small "simulated" tag and filters (Everyone · Signed up themselves ·
  Simulated). The Leads list shows 300 rows at a time; search, a tier or a sort finds the others.
* The adopted A/B winner is the standard information e-mail for everyone again (v6.2 had kept
  people who signed up themselves on the old one).
* `generate_history.py --remove` also clears the live simulation; with no simulated learners it
  invents nobody.
* The old "drop a tier after 10 minutes" sentence in HOW_IT_WORKS.md (the rule removed in v6.2) is
  replaced by what really happens: the score includes the learned effect of time away.

### "Visit ended" means the learner left
* The website now says "still here" every 30 seconds while the learner is really using the page
  (tab visible, some input in the last minute: `POST /api/session/ping`, no event recorded). Before,
  in demo mode a learner reading one page for more than a minute already counted as gone, and the
  CRM could send its follow-up while they were still on the page. The simulated learners send the
  same ping.

### Tests
* `tests/test_live_simulation.py` (11 checks): starts a private copy of the website on a copy of
  the database (your data is never touched) and checks that the simulated learners are the history's
  people, that a visit sends the requests a browser sends and the CRM reacts, that they buy with their
  best valid coupon, click e-mails through the website, that the simulated advisor handles only
  simulated learners, that the call capacities are separate, that sign-ups go through the e-mailed
  code, and that nothing is replayed after the servers were off.
* `tests/e2e_test.py`: 45 checks (was 41): one pool, the live simulation running, "send a learner
  now", only the team can close a real person's call task, the "still here" ping.

## v6.2 (5 October 2026): what a real test on the laptop showed

Found by using the CRM as a learner and as the marketing team, on the laptop.

### Scores
* **Many leads had exactly the same score (59.9).** The old "lead decay" job (marketing-backend
  `decay.py`) moved every lead without activity for 10 minutes one tier down and capped its score at
  the top of that tier (59.9, 79.9, 39.9) — so the whole simulated history piled up at three
  numbers. Removed. The score now drops with time away by what the learning loop learned for it
  (last seen 1–7 / 7–14 / 14–30 / 30+ days), so every lead keeps its own number
  (`lead_model.recency_effect`).
* **Scores from an old model stayed until someone pressed "Re-score now".** Every lead is now
  re-scored by itself at start-up, every few minutes and right after a model switch
  (`scoring.refresh_scores`, one batch, under a second for 2,000 people). The button is gone; the
  lead page and Leads list refresh themselves.
* **A customer was shown as "80/100 Target Immediately, 54% chance to buy, coupons".** The customer
  floor is removed and customers are shown as customers: what they bought, when, what they paid.
  They get no recommendation, coupons or what-if paths for a course they own, and they sit in their
  own "Customers" tab instead of a tier.
* **Clicking our e-mail could lower a score.** The learned correction for e-mail clicks comes out
  negative (people who keep getting follow-ups without buying pile up clicks). A click now counts at
  least zero.
* The lead page always shows the person's current record (older touchpoints only list their score
  at the time).

### Decisions
* **Recommended action and What-if paths disagreed** (e.g. call vs e-mail). Both now use one
  calculation (`nba.evaluate`) on the learner as they are now; the what-if paths start from the same
  pick with the same numbers. The stored decision of an earlier trigger is shown separately, with
  "random pick (the model's own pick: …)" when it was one of the 15% random choices.
* **"Do it now"** on the recommendation, on every step of the receipt and on the what-if paths: sends
  the e-mail or creates the call / WhatsApp task through the same code as an automatic decision,
  logged as policy `manual` (kept out of the uplift training and the journey statistics). Not
  possible for the 5% control group.
* **What the CRM has done so far**: every decision with its receipt and what happened next (e-mail
  clicked, call outcome, next visit, bought within 14 days), plus campaigns and A/B tests.
* What-if paths no longer show a made-up reaction mix when there is too little history ("not enough
  history yet"), never move a customer back to "SQL", and apply the same rules as the decisions.
* Plain explanation when a step lowers the chance or costs money ("costs about ₹788 compared with
  doing nothing" instead of "worth ₹-788 more").

### E-mail
* **"View Course" opens the course the person looked at, on the website itself**
  (`/courses/<slug>?ref=<token>`); the page reports the click (`POST /api/email/click`), so it no
  longer depends on reaching the marketing backend's port (which failed from a phone). Unsubscribe
  goes to `/unsubscribe` on the website. `PUBLIC_SITE_URL` (optional, in both `.env` files) makes the
  links work on a phone on the same Wi-Fi; the website now also listens on the network (Vite
  `host: true`).
* Winners of SIMULATED A/B tests no longer change the e-mails real learners get. *(Undone in v6.3:
  one pool.)*
* Gmail is called with a 10-second limit; after a network error e-mail pauses for 5 minutes instead
  of making every request wait. In DEMO_MODE a sign-up goes on when the code cannot be e-mailed (the
  code is printed in the user-backend window). The purchase confirmation is sent after the checkout
  reply. (`tests/test_email_fallback.py`)

### Real people and simulated history
* Leads, Today's actions, Pipeline and Live activity show **real people by default**, with a switch
  for the simulated history; the Dashboard shows real people, customers and revenue apart.
  *(v6.3: everyone by default, simulated learners tagged and filterable.)*
* Learning loop page: clear labels ("decision points with a known outcome", control-group people vs
  decision points), "next run by itself after N more outcomes", one chart point per day, and
  pressing "Retrain now" with nothing new no longer adds a duplicate run.
* Lifecycle stages in plain words: New lead, Engaged, Interested (MQL), Ready to buy (SQL), Customer.

### Speed and safety (was v6.1)
* Server-to-server calls and both Vite proxies use 127.0.0.1 (on Windows "localhost" first tries
  IPv6, which cost about 2 seconds per new connection).
* `scraping.py` never copies `.env` files, models or old update folders into `new.txt`.
* The harmless passlib/bcrypt start-up traceback is silenced; sign-up codes use `secrets`.

### Tests
* `tests/e2e_test.py`: 41 checks (was 36): recommendation and what-if agree, Do it now, e-mail
  click via the course page, customer view, real vs simulated lists, no identical scores.
* `tests/test_v62_fixes.py` (9 checks, on a copy of the database) and `tests/test_email_fallback.py`
  (8 checks, never sends).

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
