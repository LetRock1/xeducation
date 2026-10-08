# How X Education CRM works

## 1. The problem

About 38% of X Education's 9,240 real leads bought a course, but advisors can call only a few of
them each day (the settings assume 20). The team has to decide **who** to contact, **how** (call,
WhatsApp, e-mail, coupon, or nothing) and has to know **whether it worked**.

A CRM that retrains its lead score on its own results adds a fourth problem. Hot leads get chased,
the chasing makes them buy, and the retrained model concludes they were even hotter: it counts its
own follow-ups as lead quality. The usual check — accuracy on recent outcomes — uses the same
contaminated outcomes, so it rewards the mistake. This is what CRMs that "retrain on who converted"
do today, and it is the problem this project improves on.

## 2. The loop

```
learner on the website ──► 1 WATCH   every event (video, pricing, cart, checkout, enquiry …)
                              │
                              ▼
                           2 SCORE   chance they buy within 14 days if we do nothing (milliseconds)
                              │
          trigger (left the site, cart, checkout, wishlist, enquiry)
                              ▼
                           3 DECIDE  next-best-action: the step that adds the most profit, within
                              │      call capacity and consent; 15% random; every decision logged
                              ▼
                           4 ACT     e-mail / coupon / WhatsApp message / call task / nothing
                              │
                              ▼
                           5 MEASURE purchases; A/B no-e-mail groups; campaign hold-outs;
                              │      the 5% control group that is never contacted
                              ▼
                           6 LEARN   retrain, told what the CRM did; switch only if better on
                              │      the untouched control group
                              └──────────────► back to 2
```

## 2b. The learners: one pool, and the simulated ones keep living (v6.3)

The CRM has **one pool of learners** and treats everyone in it the same way: every learner is
scored, gets decisions, e-mails, coupons and calls, and feeds the learning loop.

* **People who sign up themselves** on the website (you, a friend, the examiner).
* **Simulated learners** (`…@demo.xeducation.test`): the 2,000 people of the six-month starting
  history, plus about 13 new ones a day. A CRM is normally switched on inside a business that
  already has leads; this project has no company behind it, so the simulated learners are that
  business. They carry a small "simulated" tag and can be filtered, nothing more.

While the servers run, the simulated learners **keep living** (`ml/live_simulation.py`, started by
the user-backend every 10 seconds):

* they use the website through **its own API over HTTP**, with the requests a browser sends: start a
  visit, each page and its seconds, video, pricing, brochure, chat, webinar, wishlist, cart,
  checkout, enquiry, the button in an e-mail, payment, sign-up with the code from their inbox. The
  CRM has no special code for them;
* they react to what the CRM **really does**: the e-mails it sends them (clicked or not), the coupons
  (used at checkout), the calls and WhatsApp messages (made by a simulated advisor, because their
  phone numbers are fake);
* they behave as the **documented simulator** of the history (table below); the 2,000 are re-created
  exactly from the history's seed, so the live data continues the history at the same pace (tested:
  7.4 purchases a day expected vs 7.2 in the history's last 30 days);
* **real time**: a second is a second. When the servers are off nobody can use the website, so
  nothing happens then, and nothing is caught up afterwards;
* the **hidden** part of each person (intent, luck, how they react to each step) is kept in the
  simulator's own database (`user-backend/simulation_world.db`); the CRM never reads it. The CRM sees
  only what any CRM sees: sign-ups, pages, clicks, purchases;
* nothing reaches a real person: their e-mails end in the reserved `.test` domain (recorded, never
  delivered) and their phone numbers are `+91 00000 …`.

| What the simulator decides | How (documented) |
|---|---|
| Who they are | profile, hidden intent and luck from `ml/generate_dataset.py`; how much each CRM step changes their chance to buy: `TRUE_EFFECTS` in `ml/nba_simulation.py` plus a personal deviation |
| Coming back | chance per day sig(−2.6 + 0.7·intent − 0.05·days away + boost), within 21 days of the last visit; a call that reached them adds 0.5 for two days, a WhatsApp 0.3; a click in an e-mail brings them back a minute later |
| On the website | 1 + Poisson pages, log-normal seconds per page; each first-time step (video, pricing, testimonials, brochure, chat, webinar, wishlist, cart, checkout, enquiry) with its own chance (`EVENTS` in `ml/generate_history.py`) |
| E-mails | clicked with chance sig(−1.7 + 0.6·intent, +0.4 with a coupon), 12 minutes to 30 hours after sending |
| Buying | the generator's buying formula on everything they have done, plus the strongest effect of a CRM step in the last 14 days; spread over the day (daily chance 1 − (1 − p14)^(1/14)); only within 14 days of a visit; they pay with their best valid coupon |
| Calls and WhatsApp | a simulated advisor does their tasks 1–24 hours after the CRM creates them (reached 60%, no answer 30%, not interested 10%) unless you record an outcome first. It has its own daily call capacity (real people never lose a call slot to a simulated learner) and is refused for real people's tasks |
| New sign-ups | about 13 a day: sign-up → code from their inbox → profile → first visit |

**Dashboard → Simulated learners, live** shows what they did in the last 24 hours and their latest
steps, has **Send a learner to the website now** (one learner who is still deciding comes back
immediately; what they do there is drawn as usual) and **New sign-up now**, and can pause them.
`crm_settings.json` → `live_simulation` switches them off or changes the sign-ups per day and the
advisor's hours. `tests/test_live_simulation.py` checks all of it on a private copy of the website
and database.

**What this shows, and what it does not.** It shows the CRM working end to end, in real time, on a
stream of learners whose true behaviour is known — so we can check that its decisions and its
learning loop do the right thing. Numbers measured on simulated learners (purchases, impact, A/B
verdicts) describe the simulator, not a real market; the claims about real markets come from the two
real datasets (section 11). People who sign up themselves go through exactly the same code.

## 3. The lead score

* **Base model** (`ml/train_model.py`): trained once on 60,000 **simulated** leads
  (`ml/generate_dataset.py`) with all 32 inputs the website records — profile, visits, time on
  site, video, pricing, brochure, testimonials, webinar, chat, wishlist, cart, checkout, enquiry,
  e-mail clicks, WhatsApp opt-in, device. Logistic regression and gradient boosting are compared on
  a held-out 20%; the simpler one is kept unless the other is clearly better. Result: logistic
  regression, AUC 0.877, log-loss 0.4055, calibration error 0.011. The tiers mean what they say on
  held-out leads:

  | Tier (score) | Leads | Predicted to buy | Actually bought |
  |---|---|---|---|
  | Target Immediately (80+) | 1,633 | 91.9% | 92.7% |
  | Nurture via Email/WhatsApp (60–79) | 1,124 | 69.8% | 67.3% |
  | Marketing Campaign (40–59) | 1,318 | 49.9% | 50.9% |
  | Low Priority (below 40) | 7,925 | 14.8% | 14.4% |

* **Why simulated data:** the score must react to video, pricing, cart and checkout, and no public
  lead dataset records those. The real X Education file (9,240 leads) has only 9 columns a new lead
  has (origin, source, do-not-email/call, visits, time on site, pages per visit, occupation,
  specialisation) plus columns sales fills in **after** contacting the lead (Tags, Lead Quality,
  Last Activity, …). It is used to check the **method** without leakage (section 11).
* **Live layer** (`user-backend/lead_model.py`): on top of the base model, the learning loop learns
  how this business differs — a recalibration and a correction for 13 website signals — from the
  CRM's own outcomes (section 5). The score is the chance to buy within 14 days **if nobody contacts
  the lead now**.
* **Time since the last visit** (v6.2): the learning loop also learns how much being away 1–7,
  7–14, 14–30 or 30+ days lowers the chance to buy (in the sandbox history: about 0, −0.5, −1.4 and
  −1.7 on the log-odds scale). The score applies it, so a lead that goes quiet drops by itself. This
  replaced the old hand-written "lead decay" rule, which moved every quiet lead one tier down and
  capped its score at the top of that tier (59.9, 79.9, 39.9): that is why so many leads used to show
  exactly the same score.
* **Always current** (v6.2): every lead is re-scored by the current model at start-up, every few
  minutes (`score_refresh_minutes`) and right after the learning loop switches models
  (`scoring.refresh_scores`, one batch for everyone, under a second for 2,000 people). There is no
  "Re-score" button any more.
* **Customers** (v6.2): no score floor any more. A buyer is shown as a customer (what they bought,
  when, what they paid), not as a chance to buy; the CRM does not offer them the course they own.
* **E-mail clicks never lower a score** (v6.2): the base model counts clicks as interest, but the
  loop learns a negative correction for them, because people who keep getting follow-ups without
  buying stay in its data longer and pile up clicks. That is an artefact of how often the CRM writes
  to someone, so the score treats a click as worth at least nothing.
* **Why this score?** shows each reason in points, worked out by the current model when the tab is
  opened (including time since the last visit).

## 4. Next-best-action (`user-backend/nba_core.py`, `nba.py`, `playbook.py`)

At each trigger an uplift model estimates the chance to buy under every step — nothing, information
e-mail, 10% or 20% coupon, advisor call, WhatsApp — and picks the one with the highest **extra
profit** (price × extra chance − discount − cost), or nothing. Consent, the daily call capacity (20
calls a day for the team; the simulated advisor has 20 of its own) and per-trigger rules are
enforced, and blocked options are shown with the reason. The model is
anchored so that "nothing" equals the lead's score. 15% of decisions are random and every decision is
stored with its probability, the lead's data at that moment and the model version, so policies can
be compared honestly later (inverse-propensity weighting).

| Check | Result | File |
|---|---|---|
| Simulator with known effects, per 1,000 leads | net extra profit ₹35.2 lakh vs ₹10.0 lakh for targeting by score (3.5×); 90.5% of the best possible | `nba_policy_comparison.md` |
| 20 random simulated worlds where our assumptions are wrong | beat the best fixed policy in 20 of 20; median 83.8% of the best possible (worst 56.7%) | `nba_robustness.md` |
| A world where no step does anything | small loss (₹16,331 per 1,000 leads): it still contacts people it should not | `nba_robustness.md` |
| Real randomized e-mail data (Hillstrom), e-mail budget 10% | 13.7 extra visits per 1,000 customers vs 11.1 when targeting by response score (difference +2.6, 95% interval +0.5 to +4.7); at budgets of 30% or more no clear difference | `hillstrom_uplift.md` |

Choosing steps by uplift is established practice; here it is the engine the learning loop serves.

## 5. The learning loop (`user-backend/learning.py`)

Every time 30 new outcomes are known (checked every 5 minutes in demo mode, hourly live):

1. **Data:** every decision point with a known outcome — what the CRM knew about the lead, what it
   did at that moment, and whether the lead bought within 14 days.
2. **Told what we did:** the step the CRM took at that moment (information e-mail, coupons, call,
   WhatsApp, campaign) and how long since the lead was last on the site are inputs; the score is
   read with them switched off — the chance to buy if we do nothing. (Only the step at that moment:
   counting every follow-up in the next 14 days would make our own follow-ups look harmful, because
   follow-ups keep coming while a lead has *not* bought.)
3. **Check:** the new model, the current one and a **naive retrain** (the same model, not told what
   the CRM did — how CRMs retrain today) are compared on the **untouched control group**: 5% of
   leads, chosen by a fixed hash, who never get automatic follow-ups (standard practice, e.g.
   Braze's global control group). Each model is judged only on people it was not fitted on (5-fold
   cross-fitting by person).
4. **Switch** only if the new model is better on the control group in at least 90% of 300
   bootstrap resamples (resampling people); otherwise keep the current model. The previous model
   file is kept.
5. **Next-best-action** is retrained on the logged decisions (weighted by 1/probability) and
   switched only if the lower end of the 95% interval of its profit gain on held-out decisions is
   above zero.
6. **Record:** every run is on the Learning loop page with its numbers and its reason.

Results:

* **Real data** (`ml/results/learning_loop.md`; Hillstrom, 42,613 customers, 20 repeats; a CRM
  e-mails the top 30% by its score, 15% of choices random, two retraining rounds; judged on
  customers the real experiment left alone): the naive retrain overstated targeted customers by
  **+39.6%**, ours by **+10.2%**. Judged by fit on its own logged data — the check a normal CRM uses —
  the naive model was preferred in **20 of 20** repeats; on the randomized truth ours was more
  accurate in **19 of 20**. Both rank customers equally well (honest AUC 0.637 for both): the naive
  model's mistake is believing people are much more likely to buy than they are, which is exactly
  what decides who is worth a call or a coupon. Honest limit: a model that is **not retrained at all**
  did as well as ours here (+7.5%), because nothing in that data needed learning; our gain there is
  avoiding the naive retrain's damage.
* **Simulated CRM** (`ml/results/history_runs.md`): six six-month histories, 36 checked runs. The naive
  retrain expected on average **+32%** more of the untouched control group to buy than did; ours
  **+13%**; the model in use before each run +33%. Ours predicted the control group better than the
  naive retrain in **28 of 36** runs (and better than the model in use in 21 of 36); the usual check
  would have picked the naive model in **36 of 36**. The loop found all three built-in differences
  of this business with the right sign in all six histories (WhatsApp opt-in +0.59 to +0.85, true
  +0.6; mobile −0.12 to −0.48, true −0.5; webinar +0.55 to +0.87, true +0.7). It switched the lead
  model 3 times in 36 runs, in 3 of the 6 histories: with about 80 untouched people after six months
  the 90% bar is high, so in the other three it kept the starting model although the new one was
  often better. That is the safe-but-slow side of a setting (`crm_settings.json`: a larger control
  group or a lower bar switches sooner, with fewer people worked on or more risk of switching on noise).
* Why ours is still somewhat above the truth: its score means "if we do nothing now", but most
  leads get another e-mail, call or campaign later within the 14 days, and the control group never
  does.
* Limit: the control group is small (about 80 people after six months), so single runs are noisy;
  the strong evidence is the real-data experiment and the totals over six histories.

**Is this new?** The parts are known: control groups, champion/challenger switching, uplift
models, and the research problem itself ("performative prediction"). What this project adds is
the combination for a CRM with several actions — retraining that is told what the CRM did, a switch
decided only on leads the CRM never touched — and the measurement, on real randomized data, that
the usual check is fooled every time. It improves the standard retraining practice; it is not
claimed as the first of its kind.

## 6. A/B tests and adopted winners (`marketing-backend/experiments.py`, `adoption.py`)

2–3 e-mail variants (each can carry a coupon) plus a 20% no-e-mail group. People are split by a
hash of the test and the person, each assignment is stored with its probability, the needed sample
size is planned before sending, and the result is final once the 14-day window has passed. Lift vs
the no-e-mail group with Newcombe 95% intervals, Bonferroni correction for the comparisons actually
made, revenue and profit per person, a day-by-day curve, a sample-ratio check, results by tier /
occupation / device / source (exploratory), and one click to turn the winner into a campaign.
Click tests compare the variants with each other.

**Adopted winners:** when a test is final and an e-mail without a discount clearly won, it becomes
the standard information e-mail for that audience by itself. 10% of the audience keep the old
e-mail, so the CRM keeps comparing them: *confirmed* (still winning), *collecting evidence*, or
*switched back* (now worse). A newer winner for the same audience replaces it. Whether to give a
discount is left to next-best-action.

Checks with known truth (`ml/results/ab_engine_check.md`): 3.7% false alarms on A/A tests (should
be ≤ 5%), 95.2% interval coverage, 79.8% power at the planned size, no false split alarms. Adopted
winners: with 5,000 people since adoption, a real +4-point winner is confirmed 72% of the time and a
real −4-point loser is switched back 92% of the time; with no real difference it wrongly confirms
1–2% of the time and wrongly switches back 2.5–3.5% (20,000 simulated adoptions per size). A 10% check group needs thousands of people, so in
the six-month history it says "collecting evidence" — which is the honest answer at that size.

In the simulated histories (`ml/results/history_runs.md`): 36 verdicts — 16 correct, 14 real effects missed because the
audience was smaller than the plan needed (the plan says so before sending), 6 still running at the
end, and **0 wrong** (no false winner or loser). Of 10 adopted winners, one was confirmed by its
check group (+21.7 points of clicks, 95% interval +4.4 to +33.1); the others were still collecting
evidence or showed no clear difference yet; none was switched back.

## 7. The control group and the CRM's total impact

5% of leads (`crm_settings.json` → `global_control.share`) never get next-best-action steps,
campaigns or A/B e-mails; the lead page marks them. Comparing them with everyone else measures the
CRM's total impact: over the six simulated histories the worked-on leads
bought within 30 days of signing up **7.8 points** more often (31.2% vs 23.4%; 95% interval +3.7 to
+11.5). It was positive in all six histories but clear in only one of them alone, because about 80
control-group people per history is few.

## 8. What-if paths and Journeys (`user-backend/paths.py`, `journeys.py`)

For one lead: every step the team can take now → how learners in the same lifecycle stage reacted
to that step in the next 3 days (from history, weighted by 1/probability) → the best next step after
each reaction, re-scored with the lead's own models. Since v6.2 the first step uses **the same
calculation as the Recommended action tab and every automatic decision** (`nba.evaluate`): the same
chance for each step, the same rules (consent, call capacity, no 20% coupon for customers) and the
same pick (highest extra profit now), so the two tabs can no longer disagree. When there are fewer
than 30 past decisions for a stage and step, the page says so instead of showing a guessed reaction
mix; customers get no paths. Each step has a **Do it now** button (see section 4b). The **Journeys**
page shows the lifecycle funnel, the flow graph stage → step → reaction → outcome, the top
converting paths and what each step adds at each stage.

## 4b. On the lead page: the recommendation now, Do it now, and what happened (v6.2)

* **Recommended action** works the decision out for the learner as they are *now* (behaviour, time
  away, current models) and shows the full receipt: for every step the chance to buy within 14 days,
  the change against doing nothing, the extra profit, and why a step is not allowed.
* **Do it now** carries a step out through the same code as an automatic decision (the e-mail with
  or without coupon is sent; a call or WhatsApp becomes a task in Today's actions). It is logged as a
  decision with policy `manual`, so the learning loop is told about it, but it is kept out of the
  uplift model's training and the journey statistics (it was not drawn by the logging policy).
  People in the 5% control group cannot be contacted this way.
* **What the CRM has done so far** lists every decision with its receipt (random pick or the model's
  pick), the e-mail and whether it was clicked, the call outcome, the next visit, and whether they
  bought within 14 days. Campaigns and A/B tests the person was part of are listed too.
* **E-mail links** (v6.2): the "View Course" button opens the course the person looked at, on the
  website itself (`/courses/<slug>?ref=<token>`). The page reports the click (`POST /api/email/click`),
  logged in or not, so it is tied to that exact e-mail. With `PUBLIC_SITE_URL=http://<laptop-ip>:5173`
  in both `.env` files, the links also open on a phone on the same Wi-Fi. Unsubscribe links go to
  `/unsubscribe` on the website. Links in older e-mails (to the marketing backend) still work.

Check (`ml/results/paths_check.md`, learned before a cut-off date, tested after it): the predicted chance to buy is calibrated
overall (38.7% predicted vs 39.2% actual) but less so per step — after "do nothing" it predicted
37.8% vs 27.4% actual, so the paths understate what acting adds. The predicted reaction mix is better
than one average mix (Brier 0.546 vs 0.556) but not better than a mix per stage that ignores the
step (0.540): the step taken changes the learner's next reaction only a little.
The paths are a planning aid for the sales team, not a research claim.

## 9. Pipeline board

Every lead in its lifecycle stage — New lead, Engaged, Interested (MQL), Ready to buy (SQL),
Customer — worked out from behaviour (SQL = sales-qualified: enquiry, cart or checkout; MQL =
marketing-qualified: pricing, wishlist or chat; Engaged: content or a second visit; Customer: a
purchase). MQL and SQL are the standard CRM lifecycle names (HubSpot, Salesforce); the dashboard
shows the plain words first. Each column shows its expected value; everyone is on the board
(untick "include simulated learners" to see only people who signed up themselves). The team can drag a card to
another stage; the board remembers it and still shows what the CRM would say ("auto: SQL"). Only a
purchase makes a Customer.

## 10. Ask the CRM (`marketing-backend/copilot.py`)

Plain-English questions — who to call today, hot leads, the pipeline, the learning loop, A/B tests,
total impact, revenue, campaigns, one lead by name or e-mail — answered only from live data. Every
answer shows which data it read and when ("How I got this"). It can draft an e-mail for a lead or an
A/B test; drafts open in the lead page or the A/B tests page for a person to review — it never sends
anything. Without a Gemini key it understands the question types it lists; with one, Gemini helps
with freer wording, and any answer whose numbers differ from the data is rejected.

## 11. Data and leakage

| Data | Used for | Real? |
|---|---|---|
| Simulated leads, 60,000 (documented generator) | base lead model | simulated |
| X Education leads (Kaggle), 9,240 | checking the modelling method without leakage | real |
| Hillstrom e-mail experiment, 64,000 customers | next-best-action and learning loop on real randomized data | real |
| Simulated randomized campaign, 60,000 leads | next-best-action starting knowledge | simulated |
| Six-month starting history, 2,000 learners | dashboards, learning loop, A/B tests, what-if paths | simulated (tagged) |
| The same learners and about 13 new a day, live (section 2b) | the CRM's work in real time: visits, decisions, e-mails, calls, purchases, learning | simulated (tagged) |
| Your own sign-ups | everything, live | real |

The real file, 5-fold cross-validation × 3 seeds, only the 9 columns a new lead has
(`ml/results/model_benchmark.md`): gradient boosting AUC 0.874,
calibration error 0.009, 94.5% of the top 10% bought; random forest 0.875; neural networks
0.867–0.868 with less reliable probabilities; logistic regression 0.838. With the post-contact
columns the same boosting model reaches 0.980 — a number no system can reach for a new lead. The
CRM's own base model applied to these leads as they are (its website signals missing) reaches only
0.612, so it cannot be judged on this file; in the running CRM every lead has those signals and the
learning loop corrects the base model.
`tests/test_no_leakage.py` fails if a post-contact column is ever used. Public notebooks that report
0.88–0.98 on this file use those columns (Last Activity, Tags, Lead Quality); a new lead never has
them.

## 12. Gemini (optional)

E-mail copy, chat answers, the e-mail coach and Ask the CRM's wording can use Google Gemini
(`GEMINI_API_KEY`). Without it, everything works from templates and rules. With it
(`user-backend/gemini.py`): it tries `GEMINI_MODEL` first, then `gemini-flash-latest`,
`gemini-3.5-flash` and `gemini-2.5-flash`, keeping the first that answers (model names are retired
often); each call has a 12-second limit; after a network error it uses templates for 5 minutes.
`tests/test_gemini_fallback.py` checks this without internet. The statistics never come from
Gemini.

## 13. Real time

Measured over HTTP in the test run (`tests/e2e_test.py`): event → new score 45 ms (median), trigger → decision → action 106 ms,
what-if paths 0.5 s, pipeline board 73 ms, Ask the CRM 6–231 ms per question. The Learning loop page shows the
live numbers. The servers use one compute thread per request: thread pools made a single prediction
up to 40 times slower on a busy machine.

## 14. Features, page by page

**Website** (<http://localhost:5173>)

| Feature | What it does |
|---|---|
| Sign-up, login, password reset | 6-digit e-mail code (valid 10 minutes, 5 tries, resend after 60 s); every new learner is a CRM lead at once |
| Profile and Settings | occupation, specialisation, phone; e-mail, call and WhatsApp consent (respected everywhere); password; **Delete my account** |
| Tracking | visits (a new one after 30 minutes idle), page time, device, traffic source, overview video (after half is watched), pricing and testimonials (after 4 s in view), brochure, chat, webinar seat, wishlist, cart, checkout, enquiry; every event re-scores the lead; a "still here" ping every 30 s while the page is really in use, so "visit ended" means the learner left |
| Course page | details from the catalogue, 35-second overview, printable brochure, reviews (buyers only), questions answered by the team |
| Wishlist, cart, checkout | catalogue prices only, personal 72-hour coupons, simulated UPI or card payment (test card `4242 4242 4242 4242`, nothing is charged) |
| Chat assistant | fees, duration, syllabus, refunds, "which course suits me?"; callback requests |
| Learner dashboard | courses, offers, personalised next steps, recommended courses with the reason, an optional "What our AI sees" panel |
| Privacy notice | what the site records and why, in plain words |

**Automations** (checked every minute in demo mode, every 5 minutes live; **Run automations now**
on the dashboard skips the wait). One follow-up per visit, cart, checkout or wishlist item, with
cool-downs (6 to 24 hours) so nobody is chased twice.

| Trigger | Fires after (demo / live) | Steps allowed |
|---|---|---|
| Checkout left | 1 / 30 minutes | all |
| Cart left | 1 / 60 minutes | all |
| Wishlist item not bought | 1 / 30 minutes | nothing, information e-mail, 10% coupon, WhatsApp |
| Visit ended (a course was viewed) | 1 / 15 minutes idle | all |
| Enquiry | at once | information or coupon e-mail, call (an e-mail is always sent) |

A lead that goes quiet drops by itself: the score includes the time since the last visit (learned
by the loop, section 3), and every lead is re-scored every 5 minutes (demo) or every hour (live).

**Marketing dashboard** (<http://localhost:5174>)

| Page | What it shows |
|---|---|
| Dashboard | learners (one pool), purchases and revenue; **Simulated learners, live** (last 24 hours, latest steps, **Send a learner to the website now**, **New sign-up now**, **Pause**); model health (predicted vs actual per tier), next-best-action report, pipeline forecast, campaign influence, CSV export, **Run automations now** |
| Ask the CRM | questions answered from live data, with sources; drafts e-mails and A/B tests (never sends) |
| Learning loop | "Is the model fooling itself?" (naive vs ours vs actual on the control group), what the loop learned, what our own actions add, the CRM's total impact, "who is fooled?" over time, every run and its reason, live response times, **Retrain now** / **Dry run** |
| Today's actions | call and WhatsApp tasks ranked by extra profit, with the script; record the outcome (tasks of simulated learners are done by the simulated advisor unless you record them first; each done task says who did it) |
| Leads / lead page | one row per person, everyone (filters: everyone, signed up themselves, simulated); the lead page has the recommended action (every option compared, blocked ones explained), **What-if paths**, **Why this score?**, e-mail with a coach, WhatsApp, activity, chat and callbacks, personal coupon, attribution; a badge if the lead is in the control group |
| Pipeline | lifecycle board with drag-and-drop; Customer only by purchase |
| Journeys | lifecycle funnel, flow graph, top converting paths, what each step adds by stage |
| Callbacks | requests from the website chat |
| Campaigns | schedule or send now to a tier, personalised; 10% of the audience held out to measure what the campaign adds |
| A/B tests | plan (people needed), 2–3 variants plus a no-e-mail group, verdict with a 95% interval, 14-day curve, split check, segments, **Use variant**, **Adopted winners** |
| Coupons, Q&A | every coupon issued; answers to course questions (shown on the course page and e-mailed to the learner) |
