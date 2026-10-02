# X Education — Machine learning: how it works and how well it works

Three models work together, and all three keep learning from what happens on the site:

| Question | Model | Where |
|---|---|---|
| How likely is this person to buy? | **Lead score**: calibrated classifier | `user-backend/predict.py`, `ml/train_model.py` |
| Which action will *change* whether they buy, and is it worth its cost? | **Next-best-action**: uplift model + profit rule | `user-backend/nba_core.py`, `nba.py`, `ml/train_uplift.py` |
| What realistic steps would move this lead into the next tier? | **How to convert**: counterfactual search | `user-backend/recourse.py` |

Every number below is reproducible with `run-experiments.bat` (results in `ml/results/`).
No number is tuned to look good; where our method does not win, this document says so.

---

## 1. How the pieces fit

```
website (tracker.js) ─► /api/track ─► lead score (+ "why", + tips) ─► score snapshot ───────────┐
                                                                                                  │
trigger: cart / checkout left, wishlist cold, visit ended, enquiry                              │
   └─► next-best-action: P(buy | each action) → expected extra profit → choose (15 % random)     │
          ├─ email (info / 10 % / 20 % coupon) — sent, click-tracked                             │
          ├─ advisor call / WhatsApp — task in "Today's actions"                                 │
          └─ do nothing                                                                          │
                       │ decision logged with its probability (propensity)                       │
purchase ──────────────┴─► labels decisions and snapshots ─► retrain-model.bat ◄────────────────┘
                                  champion vs challengers on held-out logged data; swap only if better
```

| File | Role |
|---|---|
| `user-backend/ml_features.py` | **One feature definition for training and serving**: vocabularies, cleaning, engineered features, tiers, personas. |
| `ml/generate_dataset.py` | Training data that matches what the website tracks (see 2.1). |
| `ml/train_model.py` | Lead model: logistic regression vs gradient boosting, chosen by held-out log-loss; model card. |
| `user-backend/predict.py`, `scoring.py` | Scoring, explanations, snapshots; the only path from user data to a score. |
| `user-backend/nba_core.py`, `nba.py` | Actions, costs, uplift model, decision rule, exploration, decision log. |
| `ml/nba_simulation.py`, `ml/train_uplift.py` | Simulated randomized campaign → cold-start uplift model + policy comparison. |
| `user-backend/recourse.py` | "How to convert" tips for sales and next steps for learners. |
| `ml/retrain_from_live.py`, `ml/retrain_nba_from_live.py` | Closed loop for both models. |
| `ml/seed_demo_data.py` | Optional simulated learners so the closed loop can be demonstrated. |
| `ml/experiments/*` | The four experiments reported below. |

---

## 2. Lead score

### 2.1 Why the product model is trained on generated data
The public X Education dataset (Kaggle, 9,240 leads) does not contain most signals our
website records (video watched, pricing dwell, cart, checkout, wishlist, WhatsApp opt-in …)
and *does* contain columns written by the sales team after contact. So the product model
is trained on `generate_dataset.py`: 60,000 leads whose behaviour is driven by a hidden
"intent" (correlated signals, realistic 34 % conversion, an irreducible "luck" term). The
real dataset is used to evaluate the **modelling approach** (2.4).

### 2.2 Model
* Features: 32 (profile, source, device, visits, time, per-visit time, content engagement,
  commerce intent, profile completeness, consent flags), cleaned by `normalize_raw()` so
  the website can never send a value the model has not seen.
* Candidates: logistic regression and gradient boosting; the one with lower held-out
  log-loss is kept (logistic regression unless boosting is clearly better — it is easier to
  explain).
* Output: a calibrated probability → score 0–100 → tier (Target ≥ 80, Nurture ≥ 60,
  Campaign ≥ 40, Low) and persona. Paying customers are floored at 80.
* "Why this score?": each present signal is removed in turn and the lead re-scored; the
  difference is shown in points (e.g. "Started checkout +17 pts").

### 2.3 Results on generated hold-out data (12,000 leads)
ROC-AUC 0.877, accuracy 81.5 %, and each tier converts at the rate it promises:

| Tier | Predicted | Actual |
|---|---|---|
| Target Immediately | 91.9 % | 92.7 % |
| Nurture via Email/WhatsApp | 69.8 % | 67.3 % |
| Marketing Campaign | 49.9 % | 50.9 % |
| Low Priority | 14.8 % | 14.4 % |

Even a model that knew every lead's hidden intent would only reach AUC 0.89 on this data
(the generator's "luck" term); a higher number would mean the model had learned the
generator, not customers.

### 2.4 The modelling approach on real data (X Education, 9,240 leads, 5-fold CV)
`ml/experiments/real_benchmark.py`. Using every column gives a very high score, but
`Tags`, `Lead Quality`, `Lead Profile` and the Asymmetrique scores are written **by the
sales team after contacting the lead** (e.g. the tag "Closed by Horizzon" converts 99.4 %),
and some `Last Activity` values record sales actions ("SMS Sent", "Had a Phone
Conversation"). That is target leakage: this information does not exist when a lead arrives.
We report three feature sets (C keeps only the `Last Activity` values that are things the
learner did, such as opening an email or visiting a page):

| Feature set | Model | ROC-AUC | Accuracy | F1 | Precision in top 10 % | ECE |
|---|---|---|---|---|---|---|
| A — all columns (leaky) | Ours | 0.985 ± 0.003 | 94.8 % | 0.932 | 99.5 % | 0.013 |
| **B — pre-contact only (leakage-free)** | Rule-based points (manual scoring) | 0.781 ± 0.010 | 76.5 % | 0.667 | 84.3 % | — |
| | Logistic regression | 0.847 ± 0.007 | 79.0 % | 0.704 | 93.0 % | 0.037 |
| | **Ours** | **0.876 ± 0.009** | **81.2 %** | **0.746** | **95.8 %** | **0.023** |
| **C — B + learner-side activity** | **Ours** | **0.901 ± 0.006** | **82.8 %** | **0.775** | **96.6 %** | 0.026 |

Paired-bootstrap AUC gains (set B): ours − rule-based **+0.099** (95 % CI +0.091 to +0.109),
ours − logistic regression **+0.029** (+0.024 to +0.034); set C: +0.124 and +0.030.
"Ours" chose gradient boosting in every fold. The honest headline is set B/C: a lead
arriving today can be ranked at AUC 0.88–0.90, and 96–97 % of the top-10 % actually buy.

---

## 3. Next-best-action (the novelty)

### 3.1 Why a score is not enough
A score answers "who will buy?". Marketing needs "whose decision will **our action
change**?". The hottest leads mostly buy anyway — a discount there is money given away —
and some cold leads are annoyed by a call. Ranking by likelihood to convert (what predictive
lead scoring does) and tier playbooks ("hot → biggest discount + call") cannot see this.

### 3.2 Method
* **Actions** (cost / discount): do nothing; information email (₹2); email + 10 % coupon;
  email + 20 % coupon; advisor call (₹150); WhatsApp (₹5).
* **Uplift model** (interpretable S-learner):
  `logit P(buy | x, a) = β·c(x) + γ_a·c(x)`, where the context `c(x)` holds the lead
  score's own logit ("score-anchored") and interpretable flags (price-sensitive, high
  intent, cart/enquiry, professional, email-engaged, WhatsApp opt-in, low engagement).
  Each `γ_a` reads as "how much action *a* moves the odds for people like this".
* **Decision**: expected profit of each allowed action =
  `P(buy | a) × price × (1 − discount) − cost`; choose the largest gain over doing nothing,
  or do nothing when nothing pays. Consent (do-not-email/call, WhatsApp opt-in, phone),
  a daily call capacity, "no 20 % coupon for existing customers" and per-trigger action
  lists are enforced. At an enquiry a confirmation email is always sent, so "do nothing"
  is not an option there.
* **Exploration and logging**: 15 % of decisions are random among the allowed actions; every
  decision stores the action, the model's preferred action and the **probability** of the
  action taken. That makes unbiased off-policy evaluation possible (inverse-propensity
  weighting, IPS/SNIPS) — on the dashboard and in retraining.
* **Two model families**: the interpretable S-learner above and a flexible
  gradient-boosting S-learner on all features (`nba_core.FlexibleSLearner`). The closed loop
  keeps whichever earns more on held-out logged decisions (3.6).

### 3.3 Simulation with documented assumptions (`train_uplift.py`)
Semi-synthetic evaluation (the standard approach for uplift — IHDP/ACIC style): realistic
leads + response assumptions written down in `nba_simulation.py`, so every policy can be
scored against the truth. 60,000 randomized decisions for training, 30,000 fresh leads for
evaluation, the same 10 % call capacity for every policy:

| Policy (per 1,000 leads) | Extra purchases | Net extra profit (₹) | Discount given (₹) |
|---|---|---|---|
| Tier playbook (rule-based workflow) | 38.2 | 904,886 | 859,310 |
| Lead-score targeting (score-based CRM) | 40.0 | 1,001,634 | 852,107 |
| Email everyone | 30.1 | 1,400,533 | 0 |
| 20 % coupon to everyone | 94.2 | 546,857 | 3,848,015 |
| **Next-best-action (ours)** | **97.6** | **3,520,489** | 1,080,662 |
| Next-best-action, flexible model | 92.0 | 3,285,963 | 1,057,772 |
| Oracle (knows the true effects) | 104.3 | 3,890,265 | 1,002,946 |

Ours earns **3.5×** lead-score targeting, **3.9×** the tier playbook and **2.5×** the best
fixed policy (email everyone), **90.5 %** of the oracle. Predicted vs true per-person uplift
correlates at r = 0.65–0.89 per action.
*Caveat:* these assumptions are ours, and the interpretable model has the simulator's
functional form — 3.5 tests what happens when that is not true.

### 3.4 Real randomized experiment (Hillstrom, 64,000 customers)
`ml/experiments/hillstrom_uplift.py` — the standard public uplift benchmark: customers were
randomly sent a Mens e-mail, a Womens e-mail or nothing (⅓ each); visits recorded for two
weeks. Because assignment was random, every targeting policy can be evaluated honestly on
held-out customers (5 folds × 3 repeats, IPS with the known probability ⅓, paired bootstrap).

**Who to contact (ranking quality).** Womens e-mail: normalised Qini **0.065** (ours) vs
**0.036** for ranking by predicted response (likelihood to act) and ≈0 for random or a
recency/spend rule. Mens e-mail: every method's Qini is small (0.004–0.023, fold-to-fold
SD ≈ 0.013) and response ranking is highest — this e-mail's effect hardly varies between
customers — although the logistic uplift learners, ours included, give the largest lift in the
top 10 % (+13.4 points for ours vs +10.7 for response ranking).

**Which action for whom, at the same e-mail budget** (extra visits per 1,000 customers):

| Budget | Ours (NBA) | Response-score targeting | Recency/spend rule + matching e-mail | Best single e-mail, random people |
|---|---|---|---|---|
| 10 % | **13.7** | 11.1 (ours +2.6, CI +0.5 to +4.7) | 10.7 (ours +3.1, CI +0.2 to +6.0) | 7.8 |
| 20 % | **19.7** | 19.1 (n.s.) | 19.3 (n.s.) | 15.9 |
| 50 % | 39.6 | 41.5 (n.s.) | 41.5 (n.s.) | 38.9 |
| 100 % | 77.9 | 75.8 (n.s.) | 78.7 (n.s.) | 76.5 |

On real data the uplift approach wins **when the budget is tight** — e-mailing the best
10 % gives 23.5 % more extra visits than likelihood-based targeting and 28.9 % more than the
rule (both significant for visits, the outcome the models were trained for; conversions and
spend move the same way but are not significant). At larger budgets there is no significant
difference (response-score targeting is slightly ahead at 30–50 %); n.s. = not significant. Against five other uplift learners (T-learner with logistic
regression or gradient boosting, S- and X-learner with gradient boosting, class
transformation) the interpretable model was never significantly worse at any budget, and at
the 10 % budget it was significantly better than the three gradient-boosting ones. The score anchor made little difference on this data (significant
only at the 20 % budget, +1.2 visits per 1,000).

### 3.5 Robustness: worlds where our assumptions are wrong
`ml/experiments/nba_robustness.py` deliberately breaks the assumptions:

| World | Ours | Flexible | Champion/challenger pick | Best fixed policy (hindsight) |
|---|---|---|---|---|
| Documented assumptions | 92.1 % of oracle | 85.5 % | 92.1 % | 35.7 % |
| Reversed (discounts work on the hottest leads) | 70.2 % | 54.7 % | 70.2 % | 12.9 % |
| Hidden drivers (effects through things the context cannot see) | 37.3 % | 59.5 % | 59.5 % | 29.4 % |
| Nothing works (null) | loses ₹16 per lead | loses ₹6 | — | no contact ₹0 (the right answer); email everyone −₹1.8, tier playbook −₹785, 20 % coupon to all −₹2,971 per lead |
| **20 random worlds (median)** | **83.8 %** | 81.5 % | **86.8 %** | 29.2 % |

* Every learned policy beat the best fixed policy in **20/20** random worlds. (This study
  re-draws the individual response noise and the training campaign, so the documented world
  gives 92.1 % here vs 90.5 % in 3.3.)
* The interpretable model wins when effects run through its context (9 of 10 worlds with
  hidden share < 0.5); the flexible model wins half of the worlds where hidden drivers
  dominate (5 of 10 with share ≥ 0.5, including all four above 0.68) and the "hidden" world.
* Choosing the family by off-policy value on logged decisions only — the closed loop's own
  rule — picked the better one in 16/20 worlds and gave the best median. This is why
  `retrain-model.bat` now trains both families.
* Learning curve (documented world): 1,000 randomized decisions already double the best fixed
  policy's profit; the flexible model needs ~10× more data.
* Limitation found: when nothing works, the greedy rule still spends the call budget on noise
  (₹16 per lead); a confidence-bound rule would avoid this.

---

## 4. "How to convert" tips
For each lead, `recourse.py` searches all combinations of up to 3 not-yet-done, *actionable*
steps (watch overview, brochure, pricing, testimonials, wishlist, chat, return visit, webinar,
enquiry, cart …) and returns the cheapest (by effort) that the lead model predicts lifts the
lead into the next tier. Never suggested: changing occupation, city, age, source or consent.

`ml/experiments/recourse_eval.py` on 3,000 fresh leads below the top tier:

| | Reaches next tier | Steps | Effort | Predicted gain | **True** gain | True gain per effort |
|---|---|---|---|---|---|---|
| **Ours (cheapest personalised plan)** | 89.2 % | 2.05 | 2.8 | +26.3 pts | +13.3 pts | **4.7** |
| One-size plan (webinar + enquiry + cart for all) | 87.5 % | 2.69 | 8.1 | +46.4 pts | +32.9 pts | 4.1 |

* Personalised plans reach the next tier as often as the playbook at **⅓ of the effort**.
* Our search only uses actionable steps, so by design it never suggests changing
  occupation, age, city, source or consent; an unconstrained counterfactual search (allowed to
  "change" anything) gave **27 %** of leads such impossible advice — mostly "change your
  occupation".
* **Causal gap (honest):** only about half of the predicted gain is real (true/predicted
  0.51), because behaviour also *signals* intent. Tips are therefore labelled as guidance;
  decisions about spending money (discounts, calls) come from the randomized next-best-action
  model, which measures causal effects.

---

## 5. Closed loop
* **Score snapshots**: what the model saw and predicted (at each trigger, and for page
  activity at most every 30 minutes per user).
  A purchase within 14 days labels earlier snapshots as converted; after 14 days without one
  they count as not converted. Snapshots taken after a purchase are excluded.
* **Model health** (dashboard): predicted vs actual conversion per tier on these real labels.
* **Next-best-action report** (dashboard): decisions per action, the randomized slice, and
  IPS/SNIPS profit-per-lead estimates with 95 % bootstrap intervals for "follow the model",
  "do nothing" and "information email to all".
* **`retrain-model.bat`**:
  * lead model — trains on generated + real snapshots (one per user per day, real ones
    weighted ×5); swaps only if log-loss on held-out *real users* improves;
  * next-best-action — trains the interpretable and the flexible challenger on the simulated
    prior + real decisions (inverse-propensity weighted); compares champion and both
    challengers by SNIPS profit on held-out real decisions; swaps only if a challenger wins.
  The backend reloads new models automatically; the previous model is kept as `.previous.pkl`.
* **Demo data** (`seed-demo-data.bat`): 400 simulated learners with six weeks of history,
  scored and decided by the live models, outcomes from the simulator — so the loop can be
  shown end to end. They are marked "simulated", never e-mailed (reserved `.test` domain) and
  removed with `remove-demo-data.bat`.

## 6. Pipeline forecast
Expected revenue from people who have not bought = Σ P(buy) × course price, with a 90 % range
from simulating who converts. It is only as good as the calibration, which Model health shows.

## 7. Limitations (stated in the report as well)
* The product's models are trained on generated data; real-data evidence comes from the two
  public datasets, which have different signals from our website.
* Next-best-action effects in the simulation are our assumptions; Hillstrom validates the
  approach on real randomized data but has two e-mails and no discounts or calls.
* We could not test Salesforce Einstein or HubSpot themselves (closed products). We compare
  against the approaches they document — ranking leads by likelihood to convert, and
  rule-based workflows — implemented on the same data.
* Off-policy estimates need a few hundred logged decisions before their intervals are narrow.

## 8. Reproduce
```
train-model.bat            lead model + next-best-action cold start (+ policy table)
run-experiments.bat        the four experiments (about 30 min; "quick" = real-data ones)
seed-demo-data.bat         simulated learners for a demo; remove-demo-data.bat to undo
retrain-model.bat          closed loop for both models (--dry-run to only report)
```
