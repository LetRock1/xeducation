# The simulated histories, checked against what is known to be true

6 histories (different random seeds), each 180 days, 2,000 simulated learners, the CRM running by itself: scoring, next-best-action with 15% exploration, campaigns with hold-outs, six A/B tests, auto-adopted winners, and the learning loop at days 30, 60, 90, 120, 150 and the end. The untouched control group is 5% of learners (never contacted). Made by `ml/experiments/history_check.py` from the history databases.

## 1. Is the learning loop fooling itself? (judged on the untouched control group)

Each row is one learning run. The control group's decision points are the moments the CRM would have acted on those people (it logged the decision but did nothing). *Expects* = the average predicted chance to buy within 14 days at those points; *bought* = how often they actually did.

| History | Run | Control group: people / decision points | Bought | Model in use expects | Naive retrain expects | Ours expects | Log-loss naive | Log-loss ours | Usual check picks | Decision |
|---|---|---|---|---|---|---|---|---|---|---|
| seed 2026 | 2026-05-06 | 10 / 22 | 36.4% | 44.5% | 51.5% | 46.0% | 0.6878 | 0.5937 | naive | not_enough_data |
| seed 2026 | 2026-06-05 | 19 / 43 | 30.2% | 44.5% | 47.1% | 40.9% | 0.7458 | 0.6982 | naive | not_enough_data |
| seed 2026 | 2026-07-05 | 33 / 76 | 21.1% | 37.6% | 36.8% | 29.3% | 0.7024 | 0.6310 | naive | kept |
| seed 2026 | 2026-08-04 | 45 / 103 | 20.4% | 35.5% | 34.3% | 27.1% | 0.5488 | 0.4857 | naive | kept |
| seed 2026 | 2026-09-03 | 57 / 141 | 25.5% | 38.0% | 35.5% | 28.8% | 0.4849 | 0.4471 | naive | kept |
| seed 2026 | 2026-10-03 | 78 / 199 | 27.6% | 40.8% | 37.9% | 31.1% | 0.4482 | 0.4114 | naive | swapped |
| seed 11 | 2026-05-06 | 10 / 23 | 52.2% | 56.7% | 67.4% | 63.8% | 0.4845 | 0.4024 | naive | not_enough_data |
| seed 11 | 2026-06-05 | 22 / 57 | 43.9% | 50.5% | 49.9% | 46.2% | 0.4388 | 0.4144 | naive | kept |
| seed 11 | 2026-07-05 | 34 / 95 | 40.0% | 50.2% | 44.9% | 39.9% | 0.4433 | 0.4336 | naive | kept |
| seed 11 | 2026-08-04 | 46 / 128 | 41.4% | 51.0% | 45.0% | 42.5% | 0.4563 | 0.4539 | naive | kept |
| seed 11 | 2026-09-03 | 64 / 159 | 34.0% | 45.8% | 41.5% | 36.7% | 0.4374 | 0.4185 | naive | kept |
| seed 11 | 2026-10-03 | 82 / 210 | 34.8% | 45.0% | 41.0% | 37.7% | 0.3867 | 0.3727 | naive | kept |
| seed 12 | 2026-05-06 | 8 / 10 | 20.0% | 16.1% | 29.3% | 20.0% | 0.4058 | 0.3468 | naive | not_enough_data |
| seed 12 | 2026-06-05 | 19 / 37 | 18.9% | 33.6% | 31.9% | 24.2% | 0.4268 | 0.3791 | naive | not_enough_data |
| seed 12 | 2026-07-05 | 31 / 67 | 29.9% | 34.8% | 32.5% | 27.6% | 0.4125 | 0.4132 | naive | kept |
| seed 12 | 2026-08-04 | 43 / 95 | 25.3% | 34.2% | 31.6% | 27.6% | 0.3892 | 0.3764 | naive | kept |
| seed 12 | 2026-09-03 | 57 / 123 | 27.6% | 36.3% | 33.8% | 29.2% | 0.4288 | 0.4225 | naive | kept |
| seed 12 | 2026-10-03 | 79 / 190 | 28.9% | 41.4% | 38.5% | 32.2% | 0.4976 | 0.4718 | naive | kept |
| seed 13 | 2026-05-06 | 11 / 25 | 52.0% | 46.9% | 50.2% | 43.4% | 0.5457 | 0.6133 | naive | not_enough_data |
| seed 13 | 2026-06-05 | 21 / 54 | 46.3% | 48.4% | 45.4% | 40.6% | 0.4740 | 0.4897 | naive | kept |
| seed 13 | 2026-07-05 | 37 / 82 | 39.0% | 41.1% | 37.1% | 31.9% | 0.4336 | 0.4447 | naive | kept |
| seed 13 | 2026-08-04 | 48 / 108 | 36.1% | 38.0% | 34.9% | 30.9% | 0.4015 | 0.4041 | naive | kept |
| seed 13 | 2026-09-03 | 68 / 151 | 33.8% | 38.7% | 35.0% | 30.9% | 0.4146 | 0.4114 | naive | kept |
| seed 13 | 2026-10-03 | 87 / 203 | 32.0% | 40.8% | 36.6% | 32.8% | 0.4456 | 0.4396 | naive | kept |
| seed 14 | 2026-05-06 | 10 / 22 | 27.3% | 45.2% | 44.8% | 41.2% | 0.6545 | 0.6987 | naive | not_enough_data |
| seed 14 | 2026-06-05 | 22 / 53 | 24.5% | 41.2% | 35.4% | 30.4% | 0.4001 | 0.3841 | naive | swapped |
| seed 14 | 2026-07-05 | 35 / 85 | 18.8% | 26.9% | 32.5% | 26.6% | 0.4084 | 0.3731 | naive | kept |
| seed 14 | 2026-08-04 | 45 / 115 | 20.0% | 29.3% | 33.4% | 28.5% | 0.4428 | 0.4153 | naive | kept |
| seed 14 | 2026-09-03 | 59 / 156 | 21.2% | 31.9% | 35.3% | 29.8% | 0.4787 | 0.4474 | naive | kept |
| seed 14 | 2026-10-03 | 84 / 211 | 19.4% | 29.9% | 33.2% | 28.9% | 0.4479 | 0.4210 | naive | kept |
| seed 15 | 2026-05-06 | 7 / 9 | 44.4% | 31.8% | 33.3% | 34.6% | 0.4120 | 0.3309 | naive | not_enough_data |
| seed 15 | 2026-06-05 | 19 / 37 | 35.1% | 39.2% | 36.0% | 31.8% | 0.3828 | 0.3844 | naive | not_enough_data |
| seed 15 | 2026-07-05 | 30 / 54 | 25.9% | 32.3% | 27.1% | 22.5% | 0.2892 | 0.2925 | naive | kept |
| seed 15 | 2026-08-04 | 43 / 89 | 19.1% | 32.9% | 29.0% | 23.4% | 0.4040 | 0.3768 | naive | kept |
| seed 15 | 2026-09-03 | 58 / 141 | 19.9% | 38.2% | 32.1% | 25.6% | 0.4098 | 0.3734 | naive | swapped |
| seed 15 | 2026-10-03 | 85 / 209 | 23.4% | 27.1% | 33.0% | 27.8% | 0.3766 | 0.3502 | naive | kept |

- Runs with a control-group check: **36**. Ours predicted the control group better (lower log-loss) than the naive retrain in **28 of 36**, and better than the model in use at that time in 21 of 36.
- The usual check (fit on all live outcomes, which the CRM's own follow-ups shaped) would have picked the naive retrain in **36 of 36** runs.
- How much each overstated the control group's buying, mean over all runs: naive **+32%**, ours **+13%**, the model in use before the run +33%. (Some overstatement is expected for every model: the score is the chance to buy if we do nothing *now*, but the control group also gets nothing later.)
- Final runs only (most data): naive +36%, ours +17%.
- Lead model swapped 3 times over 36 runs (only when better on the control group in ≥90% of bootstrap resamples); next-best-action swapped 2 times.

## 2. What the loop learned about this business, vs the truth

The simulated business differs from the base model's training data in three documented ways (log-odds of buying, `WORLD_DRIFT` in ml/generate_history.py). Below: what the final learning run of each history learned (ours), and whether the CRM is using a learned model.

| History | Opted in to WhatsApp (true +0.6) | Browses on mobile (true -0.5) | Joined a webinar (true +0.7) | Largest other corrections | Model in use at the end |
|---|---|---|---|---|---|
| seed 2026 | +0.85 | -0.22 | +0.70 | Clicked our emails -1.38, Started checkout +0.75, Sent an enquiry +0.40 | learned model from 2026-10-03 |
| seed 11 | +0.59 | -0.21 | +0.55 | Clicked our emails -1.69, Started checkout +0.42, Downloaded a brochure +0.16 | the starting model (no new model was confirmed with 90% confidence) |
| seed 12 | +0.59 | -0.16 | +0.55 | Clicked our emails -0.99, Added to cart +0.41, Sent an enquiry +0.33 | the starting model (no new model was confirmed with 90% confidence) |
| seed 13 | +0.74 | -0.48 | +0.56 | Clicked our emails -1.18, Started checkout +0.68, Sent an enquiry +0.57 | the starting model (no new model was confirmed with 90% confidence) |
| seed 14 | +0.79 | -0.12 | +0.61 | Clicked our emails -1.19, Started checkout +0.51, Sent an enquiry +0.46 | learned model from 2026-06-05 |
| seed 15 | +0.68 | -0.32 | +0.87 | Clicked our emails -1.18, Sent an enquiry +0.45, Added to cart +0.39 | learned model from 2026-09-03 |

Learned vs true, range over the histories: Opted in to WhatsApp +0.59 to +0.85 (true +0.6, right sign in 6 of 6); Browses on mobile -0.48 to -0.12 (true -0.5, right sign in 6 of 6); Joined a webinar +0.55 to +0.87 (true +0.7, right sign in 6 of 6).

Weights are log-odds added for a lead with the signal. They are ridge-shrunk toward 0 and fitted together with a recalibration of the base score, so only the sign and rough size should match.
The large negative correction for *Clicked our emails* is not one of the designed differences, and it is right: in the base model's training data e-mail opens depend only on the learner's interest, but in a running CRM they also depend on how many e-mails the CRM has already sent (learners it kept e-mailing without a purchase pile up clicks), so a click says less about interest than the base model assumed.
A learned model is used only once the untouched control group confirms it with 90% confidence. With about 80 untouched people after six months that bar is high: where no model was confirmed, the CRM kept the starting model even though the new one was often better (section 1). A larger control group or a lower bar (crm_settings.json) makes it switch sooner, at the cost of fewer people worked on or more risk of switching on noise.

The naive retrain learns similar signal weights to ours (median difference 0.03, largest 0.50 log-odds). Its main mistake is the overall level: most decision points were followed by an action of the CRM, and the naive retrain folds the average effect of those actions into every lead's baseline — which is what section 1 shows.

## 3. The CRM's total impact (worked-on leads vs the untouched control group)

Share of learners who bought within 30 days of signing up (learners who signed up at least 30 days before the end).

| History | Worked on | Control group | Difference (95% interval) | p |
|---|---|---|---|---|
| seed 2026 | 472/1524 = 31.0% | 16/78 = 20.5% | +10.5 pts (-0.0 to +18.3) | 0.050 |
| seed 11 | 499/1560 = 32.0% | 20/80 = 25.0% | +7.0 pts (-3.7 to +15.5) | 0.190 |
| seed 12 | 481/1535 = 31.3% | 24/80 = 30.0% | +1.3 pts (-9.7 to +10.6) | 0.802 |
| seed 13 | 497/1564 = 31.8% | 20/80 = 25.0% | +6.8 pts (-3.9 to +15.3) | 0.203 |
| seed 14 | 494/1531 = 32.3% | 17/78 = 21.8% | +10.5 pts (-0.1 to +18.5) | 0.053 |
| seed 15 | 444/1533 = 29.0% | 14/78 = 17.9% | +11.0 pts (+0.8 to +18.3) | 0.035 |

Mean difference +7.8 pts, positive in 6 of 6 histories; the 95% interval is above zero in 1 of 6 (the control group is only ~5% of learners, so each single history has a wide interval).
All 6 independent histories together: worked on 2,887/9,247 = 31.2%, control group 111/474 = 23.4%: **+7.8 pts** (95% interval +3.7 to +11.5, p = 0.0003).

## 4. A/B test verdicts vs the true effects

| History | Test | Metric | People per arm | Verdict | Lift of the best variant (95% interval) | True effect | Judged |
|---|---|---|---|---|---|---|---|
| seed 2026 | 10% vs 20% coupon | purchase | control 49, A 93, B 97 | no_difference | B vs control: +8.4 pts (-7.7 to +21.1) | both coupons raise buying (20% more); the audience is far below the planned size | missed (too few people) |
| seed 2026 | Webinar invite vs brochure | purchase | control 70, A 129, B 145 | no_difference | A vs control: -0.3 pts (-10.4 to +7.1) | true null: neither email changes buying | correct (true null) |
| seed 2026 | Subject line: benefit vs urgency | click | A 285, B 301 | winner B | B vs A: +8.1 pts (+1.6 to +14.5) | urgency subject: +0.8 log-odds on clicks, same buying | correct |
| seed 2026 | Short mobile email vs long email | purchase | control 151, A 304, B 307 | winner B (on phones: B) | B vs control: +8.7 pts (+2.3 to +14.1) | short email +1.4 on phones only; long email +0.4 on desktop only | correct |
| seed 2026 | Personalised course pick vs generic newsletter | purchase | control 198, A 369, B 388 | winner B | B vs control: +6.6 pts (+0.7 to +11.5) | personalised +1.2 log-odds on buying; newsletter nothing | correct |
| seed 2026 | EMI message vs refund guarantee | purchase | control 204, A 381, B 435 | running | A vs control: +3.3 pts (-0.8 to +6.7) | sent 5 days before the end: cannot be final yet | running (correct: not final) |
| seed 11 | 10% vs 20% coupon | purchase | control 50, A 96, B 110 | no_difference | A vs control: -1.5 pts (-16.9 to +10.7) | both coupons raise buying (20% more); the audience is far below the planned size | missed (too few people) |
| seed 11 | Webinar invite vs brochure | purchase | control 70, A 134, B 136 | no_difference | A vs control: +3.7 pts (-3.3 to +9.4) | true null: neither email changes buying | correct (true null) |
| seed 11 | Subject line: benefit vs urgency | click | A 293, B 333 | no_difference | B vs A: +4.0 pts (-2.5 to +10.3) | urgency subject: +0.8 log-odds on clicks, same buying | missed (too few people) |
| seed 11 | Short mobile email vs long email | purchase | control 155, A 318, B 301 | no_difference (on phones: B) | A vs control: +3.9 pts (-2.6 to +9.2) | short email +1.4 on phones only; long email +0.4 on desktop only | missed (too few people) |
| seed 11 | Personalised course pick vs generic newsletter | purchase | control 192, A 380, B 391 | no_difference | B vs control: +4.8 pts (-0.9 to +9.5) | personalised +1.2 log-odds on buying; newsletter nothing | missed (too few people) |
| seed 11 | EMI message vs refund guarantee | purchase | control 200, A 403, B 421 | running | B vs control: +3.7 pts (-0.2 to +6.9) | sent 5 days before the end: cannot be final yet | running (correct: not final) |
| seed 12 | 10% vs 20% coupon | purchase | control 45, A 87, B 97 | no_difference | A vs control: +12.8 pts (-1.7 to +24.1) | both coupons raise buying (20% more); the audience is far below the planned size | missed (too few people) |
| seed 12 | Webinar invite vs brochure | purchase | control 61, A 130, B 116 | no_difference | B vs control: +3.6 pts (-6.7 to +11.3) | true null: neither email changes buying | correct (true null) |
| seed 12 | Subject line: benefit vs urgency | click | A 294, B 280 | winner B | B vs A: +12.6 pts (+5.8 to +19.3) | urgency subject: +0.8 log-odds on clicks, same buying | correct |
| seed 12 | Short mobile email vs long email | purchase | control 144, A 287, B 279 | no_difference | B vs control: +4.9 pts (-2.2 to +10.7) | short email +1.4 on phones only; long email +0.4 on desktop only | missed (too few people) |
| seed 12 | Personalised course pick vs generic newsletter | purchase | control 190, A 356, B 378 | winner B | B vs control: +6.6 pts (+0.8 to +11.6) | personalised +1.2 log-odds on buying; newsletter nothing | correct |
| seed 12 | EMI message vs refund guarantee | purchase | control 203, A 399, B 406 | running | A vs control: +2.8 pts (-1.0 to +5.9) | sent 5 days before the end: cannot be final yet | running (correct: not final) |
| seed 13 | 10% vs 20% coupon | purchase | control 44, A 103, B 109 | no_difference | B vs control: +3.8 pts (-12.9 to +16.2) | both coupons raise buying (20% more); the audience is far below the planned size | missed (too few people) |
| seed 13 | Webinar invite vs brochure | purchase | control 49, A 121, B 141 | no_difference | A vs control: +5.0 pts (-4.8 to +11.4) | true null: neither email changes buying | correct (true null) |
| seed 13 | Subject line: benefit vs urgency | click | A 292, B 307 | winner B | B vs A: +11.6 pts (+5.1 to +18.0) | urgency subject: +0.8 log-odds on clicks, same buying | correct |
| seed 13 | Short mobile email vs long email | purchase | control 155, A 337, B 293 | winner A | A vs control: +6.2 pts (+0.2 to +11.1) | short email +1.4 on phones only; long email +0.4 on desktop only | correct |
| seed 13 | Personalised course pick vs generic newsletter | purchase | control 186, A 369, B 388 | no_difference | B vs control: +4.4 pts (-1.6 to +9.3) | personalised +1.2 log-odds on buying; newsletter nothing | missed (too few people) |
| seed 13 | EMI message vs refund guarantee | purchase | control 205, A 397, B 405 | running | B vs control: +1.5 pts (-2.4 to +4.5) | sent 5 days before the end: cannot be final yet | running (correct: not final) |
| seed 14 | 10% vs 20% coupon | purchase | control 46, A 90, B 107 | no_difference | B vs control: +6.0 pts (-9.8 to +17.6) | both coupons raise buying (20% more); the audience is far below the planned size | missed (too few people) |
| seed 14 | Webinar invite vs brochure | purchase | control 70, A 132, B 127 | no_difference | B vs control: +2.5 pts (-5.6 to +8.6) | true null: neither email changes buying | correct (true null) |
| seed 14 | Subject line: benefit vs urgency | click | A 293, B 290 | no_difference | B vs A: +6.4 pts (-0.3 to +13.0) | urgency subject: +0.8 log-odds on clicks, same buying | missed (too few people) |
| seed 14 | Short mobile email vs long email | purchase | control 143, A 298, B 303 | winner B | B vs control: +7.3 pts (+0.2 to +13.0) | short email +1.4 on phones only; long email +0.4 on desktop only | correct |
| seed 14 | Personalised course pick vs generic newsletter | purchase | control 181, A 372, B 380 | no_difference | B vs control: +5.3 pts (-0.5 to +10.1) | personalised +1.2 log-odds on buying; newsletter nothing | missed (too few people) |
| seed 14 | EMI message vs refund guarantee | purchase | control 216, A 379, B 403 | running | A vs control: +1.4 pts (-2.6 to +4.6) | sent 5 days before the end: cannot be final yet | running (correct: not final) |
| seed 15 | 10% vs 20% coupon | purchase | control 45, A 100, B 96 | no_difference | B vs control: +10.3 pts (-2.6 to +19.9) | both coupons raise buying (20% more); the audience is far below the planned size | missed (too few people) |
| seed 15 | Webinar invite vs brochure | purchase | control 74, A 130, B 138 | no_difference | B vs control: +3.1 pts (-5.6 to +9.6) | true null: neither email changes buying | correct (true null) |
| seed 15 | Subject line: benefit vs urgency | click | A 294, B 298 | winner B | B vs A: +8.5 pts (+1.9 to +15.0) | urgency subject: +0.8 log-odds on clicks, same buying | correct |
| seed 15 | Short mobile email vs long email | purchase | control 162, A 337, B 293 | no_difference | A vs control: +3.1 pts (-2.7 to +7.7) | short email +1.4 on phones only; long email +0.4 on desktop only | missed (too few people) |
| seed 15 | Personalised course pick vs generic newsletter | purchase | control 198, A 392, B 390 | winner B | B vs control: +9.8 pts (+4.9 to +14.1) | personalised +1.2 log-odds on buying; newsletter nothing | correct |
| seed 15 | EMI message vs refund guarantee | purchase | control 217, A 416, B 435 | running | A vs control: +0.9 pts (-3.4 to +4.2) | sent 5 days before the end: cannot be final yet | running (correct: not final) |

Tally: correct: 16, missed: 14, running: 6. Wrong verdicts (a winner or loser that is not true): **0**. *Missed* = a real effect the test was too small to confirm; the plan shown before sending warns when the audience is smaller than needed.

### Adopted winners

| History | From test | Adopted email | Audience | Status | Last check |
|---|---|---|---|---|---|
| seed 2026 | Subject line: benefit vs urgency | Urgency subject | All leads | superseded | Collecting evidence: 92 people got the adopted email, 12 the old one (need 30+ each). (Adopted winner: 92 people, 27.2%, Old standard email (check group): 12 people, 33.3%) |
| seed 2026 | Short mobile email vs long email | Short mobile-first email | All leads | superseded | Collecting evidence: 126 people got the adopted email, 13 the old one (need 30+ each). (Adopted winner: 126 people, 34.9%, Old standard email (check group): 13 people, 30.8%) |
| seed 2026 | Personalised course pick vs generic newsletter | Personalised course pick | All leads | active | Collecting evidence: 43 people got the adopted email, 8 the old one (need 30+ each). (Adopted winner: 43 people, 16.3%, Old standard email (check group): 8 people, 0.0%) |
| seed 12 | Subject line: benefit vs urgency | Urgency subject | All leads | superseded | No clear difference yet (-0.7 points; the 95% interval still includes zero). (Adopted winner: 249 people, 37.8%, Old standard email (check group): 39 people, 38.5%) |
| seed 12 | Personalised course pick vs generic newsletter | Personalised course pick | All leads | active | Collecting evidence: 62 people got the adopted email, 3 the old one (need 30+ each). (Adopted winner: 62 people, 6.5%, Old standard email (check group): 3 people, 0.0%) |
| seed 13 | Subject line: benefit vs urgency | Urgency subject | All leads | superseded | Collecting evidence: 121 people got the adopted email, 16 the old one (need 30+ each). (Adopted winner: 121 people, 42.1%, Old standard email (check group): 16 people, 37.5%) |
| seed 13 | Short mobile email vs long email | Long email | All leads | active | Collecting evidence: 230 people got the adopted email, 28 the old one (need 30+ each). (Adopted winner: 230 people, 20.9%, Old standard email (check group): 28 people, 28.6%) |
| seed 14 | Short mobile email vs long email | Short mobile-first email | All leads | active | No clear difference yet (+6.0 points; the 95% interval still includes zero). (Adopted winner: 195 people, 31.8%, Old standard email (check group): 31 people, 25.8%) |
| seed 15 | Subject line: benefit vs urgency | Urgency subject | All leads | superseded | Still winning: +21.7 points vs the old email (95% interval +4.4 to +33.1). (Adopted winner: 241 people, 39.8%, Old standard email (check group): 33 people, 18.2%) |
| seed 15 | Personalised course pick vs generic newsletter | Personalised course pick | All leads | active | Collecting evidence: 55 people got the adopted email, 4 the old one (need 30+ each). (Adopted winner: 55 people, 3.6%, Old standard email (check group): 4 people, 0.0%) |
