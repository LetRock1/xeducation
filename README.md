# X Education — Revenue Intelligence Platform

An end-to-end lead-to-revenue system for an online-education company. It scores every
visitor, decides **which action will actually change whether they buy** (and whether it is
worth its cost), tells sales how to convert each lead, and learns from every outcome.

* **Learner website** (React, port 5173) — course catalogue, accounts, cart, checkout,
  enquiry, chat assistant, brochures, reviews, Q&A, personalised next steps. Every visit
  is tracked silently.
* **User backend** (FastAPI, port 8000) — accounts, tracking, **lead scoring**,
  **next-best-action**, **"how to convert" tips**, automated follow-ups.
* **Marketing backend** (FastAPI, port 8001) — CRM API: leads, sales actions, campaigns,
  A/B tests, coupons, WhatsApp, model health, forecast.
* **Marketing dashboard** (React, port 5174) — the sales & marketing team's workspace.
* **ML** (`ml/`) — data generator, training, uplift model, closed-loop retraining,
  demo data and the research experiments.

## Quick start (Windows)

1. Install **Python 3.11/3.12** (tick *Add to PATH*) and **Node.js 20+**.
2. Copy `user-backend/.env.example` to `user-backend/.env` and
   `marketing-backend/.env.example` to `marketing-backend/.env`, then edit them (Gmail is
   optional — without it, emails are printed in the server window). Use the same
   `INTERNAL_API_KEY` in both.
3. Double-click **`start-all.bat`**. The first run creates the virtual environments,
   installs packages, builds the course catalogue and trains both models (a few minutes).
   Later runs start in seconds.
4. Open <http://localhost:5173> (website) and <http://localhost:5174> (dashboard; log in
   with `MARKETING_EMAIL` / `MARKETING_PASSWORD` from `marketing-backend/.env`).
5. Optional: **`seed-demo-data.bat`** adds 400 clearly-marked simulated learners with six
   weeks of history, so Model health, the next-best-action report and the closed loop have
   data to show. **`remove-demo-data.bat`** removes them.
6. **`stop-all.bat`** stops everything.

| Script | What it does |
|---|---|
| `start-all.bat` | set up (first run) + start all 4 servers |
| `stop-all.bat` | stop all servers / free the ports |
| `train-model.bat` | retrain the lead-scoring and next-best-action models from scratch |
| `retrain-model.bat` | closed loop: retrain both models on logged outcomes, swap only if better (`--dry-run` to only report) |
| `seed-demo-data.bat` / `remove-demo-data.bat` | add / remove simulated demo learners |
| `run-experiments.bat` | re-run the four research experiments (`quick` = the two real-data ones) |

To start from an empty database, stop the servers and delete
`user-backend/xeducation_user.db` and `marketing-backend/xeducation_marketing.db`.

## How the intelligence works

```
visit ─► tracker.js ─► /api/track ─► lead model ─► live score + "why" + how-to-convert tips
                                          │
trigger (cart / checkout / wishlist / visit ended / enquiry)
                                          ▼
                     next-best-action: P(buy) under every action → extra profit
              ┌───────────────┬───────────┴───────┬──────────────┐
          do nothing      email (info /        call task       WhatsApp task
                          10% / 20% coupon)   for sales        for sales
                                          │
     purchase? ◄── every decision logged with its probability ──► retrain-model.bat
                                          (champion vs challengers, swap only if better)
```

* **Lead score** — calibrated probability of buying; one feature module
  (`user-backend/ml_features.py`) is shared by training and serving; "Why this score?"
  shows each signal's contribution in points.
* **Next-best-action** — an uplift model estimates P(buy) under each action and picks the
  one with the highest *incremental profit*, or nothing; consent, call capacity and
  per-trigger rules are enforced; 15 % of decisions are randomised and every decision's
  probability is logged, so policies can be evaluated honestly (inverse-propensity).
* **How to convert** — the cheapest realistic steps predicted to move a lead into the next
  tier; shown to sales, and as personalised next steps on the learner's dashboard.
* **Closed loop** — purchases label score snapshots and decisions; `retrain-model.bat`
  trains challengers (two model families for next-best-action) and replaces a model only
  if it is better on held-out logged data. The dashboard shows calibration on real users,
  next-best-action results with confidence intervals and a pipeline forecast.

## Results at a glance

| What | Result | Where |
|---|---|---|
| Lead scoring on **real** data (X Education, 9,240 leads, leakage-free) | ROC-AUC **0.876** (0.901 with learner activity) vs 0.781 for manual points scoring; 96–97 % of the top-10 % buy | `ml/results/real_benchmark.md` |
| Next-best-action on a **real randomized** experiment (Hillstrom, 64,000 customers) | at a 10 % e-mail budget, **+23.5 %** extra visits vs likelihood-based targeting and **+28.9 %** vs a recency/spend rule (both significant); no significant difference at larger budgets | `ml/results/hillstrom_uplift.md` |
| Next-best-action, simulation with documented assumptions | **3.5×** the profit of lead-score targeting, 90.5 % of the oracle | `ml/results/nba_policy_comparison.md` |
| Robustness: 20 random "wrong-assumption" worlds | beat the best fixed policy in **20/20**; median 84 % of oracle (best fixed 29 %) | `ml/results/nba_robustness.md` |
| How-to-convert tips | reach the next tier as often as a one-size playbook at **⅓ of the effort**; only actionable steps by design (an unconstrained search gave 27 % of leads impossible advice) | `ml/results/recourse_eval.md` |

Honest limitations are listed in [ML_PIPELINE.md](ML_PIPELINE.md#7-limitations-stated-in-the-report-as-well):
the product models are trained on generated data that matches what the site tracks, and
Salesforce Einstein / HubSpot could not be tested directly — we compare against the
approaches they document (likelihood-to-convert scoring, rule-based workflows).

## Documentation
* [ML_PIPELINE.md](ML_PIPELINE.md) — every model, the experiments and their results
* [FEATURE_GUIDE.md](FEATURE_GUIDE.md) — every feature: what it does, how it works, how to test it
* [DEMO.md](DEMO.md) — a 15-minute demo script for the viva
* [CHANGES.md](CHANGES.md) — what changed from the original project, and why

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Address already in use` | run `stop-all.bat` |
| `database is locked` | close DB Browser / any second copy of the backend, then restart |
| No OTP email | check Gmail settings in `user-backend/.env`, the spam folder, or the user-backend window (`[EMAIL MOCK]` shows the code) |
| Marketing pages empty | start user-backend first (it creates the shared database) |
| "Run automations now" says *refused* | `INTERNAL_API_KEY` differs between the two `.env` files |
| Model health / next-best-action report empty | outcomes are only known after a purchase or 14 days — use `seed-demo-data.bat` for a demo |
| `[ML] … not found — using fallback` | run `train-model.bat` |
