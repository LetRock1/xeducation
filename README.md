# X Education CRM

A CRM for online-course companies that **learns from its own actions without fooling itself**.
It watches what each learner does on the course website, scores how likely they are to buy if
nobody contacts them, picks the most profitable next step for each lead (advisor call, WhatsApp,
e-mail, coupon, or nothing), carries it out, measures what really happened against control groups,
and retrains itself — switching to a new model only when the people it never contacted confirm
the new model is better. Demo client: X Education.

## Start and stop (Windows)

1. Install **Python 3.12** (tick *Add python.exe to PATH*) and **Node.js 20 or newer**.
2. Copy `user-backend/.env.example` to `user-backend/.env` and `marketing-backend/.env.example`
   to `marketing-backend/.env`. Put the **same** `INTERNAL_API_KEY` in both. Gmail and Gemini are
   optional: without Gmail, e-mails and sign-up codes are printed in the server window; without
   Gemini, e-mails are written from templates.
3. Double-click **`start-all.bat`**. The first start installs everything, trains the two models
   (about 1 minute) and creates six simulated months of history (5–10 minutes, once). Later starts
   take seconds. Both browser tabs open by themselves.
4. Website: <http://localhost:5173> · Marketing dashboard: <http://localhost:5174> (log in with
   `MARKETING_EMAIL` / `MARKETING_PASSWORD` from `marketing-backend/.env`).
5. **`stop-all.bat`** stops everything.

Everything else runs by itself while the servers are up. By hand, if you want:

| To | Do |
|---|---|
| Retrain now | Learning loop page → **Retrain now** (or **Dry run**) |
| Check that everything works (servers running) | `user-backend\venv\Scripts\python.exe tests\e2e_test.py` |
| Re-run the experiments behind the numbers below | `user-backend\venv\Scripts\python.exe ml\run_experiments.py` |
| Delete the simulated history | `user-backend\venv\Scripts\python.exe ml\generate_history.py --remove` |
| Change business rules (tiers, costs, timings, control group) | edit `crm_settings.json`, restart |

If something goes wrong:

| You see | Cause and fix |
|---|---|
| `[ML] ... not found` or `[NBA] ... built-in prior` | the first start did not finish: run `start-all.bat` again (it only does what is missing) |
| "The user backend refused — check INTERNAL_API_KEY" | the two `.env` files have different `INTERNAL_API_KEY` values |
| No e-mails arrive | Gmail is not set: codes and e-mails are printed as `[EMAIL MOCK]` in the user-backend window |
| A lead never gets an automatic step | it is in the 5% control group (the lead page says so) |
| `[GEMINI] network problem` | no internet: templates are used for 5 minutes, then Gemini is tried again |

## One loop

| Step | What happens |
|---|---|
| 1 Watch | The website records every event (video, pricing, cart, checkout, enquiry …) |
| 2 Score | Each event re-scores the lead in milliseconds: their chance to buy within 14 days **if we do nothing** |
| 3 Decide | Next-best-action compares every step by the **extra** profit it adds and picks the best (or nothing); 15% of choices are random so the CRM keeps learning; every decision is logged with its probability |
| 4 Act | E-mail, coupon, WhatsApp message or a call task for an advisor |
| 5 Measure | Purchases within 14 days; A/B tests keep a no-e-mail group; campaigns keep a hold-out; 5% of leads are never contacted automatically (the control group) |
| 6 Learn | The model is retrained on the CRM's own results, **told what the CRM did to each lead**, and replaces the old one only if it predicts the untouched control group better |

## What it does differently

1. **Learning that does not fool itself.** A CRM that retrains on "who bought" learns its own
   follow-ups as lead quality — and the usual accuracy check rewards that mistake. Ours is told
   what it did, removes that from the score, and judges every new model on the 5% of leads it
   never contacts.
2. **Decisions by extra effect, not by score.** It contacts the people a step will change, not the
   ones who would buy anyway.
3. **Experiments built in.** A/B tests with a no-e-mail group, planned sample sizes and 95%
   intervals; a clear winner becomes the standard e-mail by itself, while 10% keep the old one so
   the CRM keeps checking — and switches back if the winner stops winning.
4. **For the team:** a pipeline board, what-if paths for each lead, and **Ask the CRM**, which
   answers questions from live data and drafts (never sends) e-mails and A/B tests.

## Results (each number is produced by a script; files in `ml/results/`)

| Question | Result | Data |
|---|---|---|
| Does a normal retrain fool itself? | It overstated targeted customers by 39.6%; ours by 10.2% (not retraining at all: 7.5%) | real randomized e-mail experiment (Hillstrom), 20 repeats |
| Would a normal CRM notice? | No: its usual check preferred the naive model in 20 of 20 repeats; ours was closer to the truth in 19 of 20 | same |
| The same inside our CRM | The naive retrain overstated the untouched control group by 32% on average, ours by 13%; ours predicted it better in 28 of 36 checks; the usual check picked the naive one in 36 of 36 | six simulated six-month histories |
| Does the loop find what is different about this business? | All three built-in differences found with the right sign in 6 of 6 histories; a learned model is used only after the control group confirms it (in 3 of 6 histories within six months) | same |
| Next-best-action | 3.5× the profit of targeting by score (90.5% of the best possible); beats the best fixed rule in 20 of 20 random worlds; on real data +2.6 extra visits per 1,000 customers vs targeting by response score at a 10% budget (95% interval +0.5 to +4.7) | simulator; Hillstrom |
| A/B statistics | 3.7% false alarms on A/A tests, 95.2% interval coverage, 79.8% power at the planned size; **0 wrong verdicts** in 36 simulated tests (14 real effects missed where the audience was smaller than the plan said was needed) | 4,000 simulated tests per check; six histories |
| The CRM's total impact | Worked-on leads bought within 30 days **7.8 points** more often than the untouched control group (31.2% vs 23.4%; 95% interval +3.7 to +11.5) | six simulated histories together |
| Lead scoring method on real data, no leakage | AUC 0.874 with the 9 columns a new lead has; 0.98 only with columns sales fills in after contact | 9,240 real X Education leads |
| Speed | Event → new score 45 ms; trigger → decision → action 106 ms (median, over HTTP) | test run |

Details and the limits of each result: [HOW_IT_WORKS.md](HOW_IT_WORKS.md) · viva script and hard
questions: [DEMO.md](DEMO.md) · what changed: [CHANGES.md](CHANGES.md).

## What is real and what is simulated

* **Real and live:** the website, tracking, scoring, decisions, e-mails, A/B tests, the learning
  loop, the dashboards and every sign-up you make.
* **The base lead model** is trained on 60,000 **simulated** leads, because it needs every signal
  the website records (video, pricing, cart, checkout …) and no public dataset has them. The real
  X Education data (9,240 leads) is used to check the modelling method without leakage. In the
  running CRM the learning loop corrects the base model from the CRM's own outcomes.
* **The main evidence for the learning loop** comes from a **real** randomized e-mail experiment
  (Hillstrom, 64,000 customers).
* **The six-month starting history** (2,000 learners, e-mails ending in `@demo.xeducation.test`,
  never sent) is **simulated** and marked "simulated" everywhere, because X Education's own CRM
  history is not public. Real activity is added on top.

## Folders

`user-backend/` learner API, scoring, decisions, learning loop · `marketing-backend/` dashboard
API, campaigns, A/B engine, adopted winners, Ask the CRM · `user-frontend/` the course website ·
`marketing-frontend/` the dashboard · `ml/` training, history generator, experiments
(`ml/results/`) · `tests/` automated tests · `crm_settings.json` business rules.
