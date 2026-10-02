# Next-best-action on a real randomized experiment (Hillstrom, 64,000 customers)

Arms: none 21,306, mens 21,307, womens 21,387. Randomization check: max |standardised mean difference| = 0.014.

| Arm | Visit rate | Conversion rate | Spend / customer |
|---|---|---|---|
| none | 10.62% | 0.57% | $0.653 |
| mens | 18.28% | 1.25% | $1.423 |
| womens | 15.14% | 0.88% | $1.077 |

Cross-fitted: 5 folds × 3 repeats; models trained for **visit**.

## Q1 — Who to contact: ranking quality per e-mail vs no e-mail

Normalised Qini coefficient (0 = random, 1 = perfect) and uplift in visit rate (percentage points) among the top-ranked customers; mean ± sd over 15 held-out folds.

### Mens e-mail vs no e-mail

| Method | Qini coefficient | Uplift top 10% | Uplift top 20% | Uplift top 30% |
|---|---|---|---|---|
| Response model (GBM) | 0.023 ± 0.013 | +10.70 ± 3.11 | +9.52 ± 1.78 | +9.06 ± 1.18 |
| RFM rule (recency + spend) | 0.020 ± 0.012 | +9.50 ± 2.40 | +9.20 ± 1.28 | +8.94 ± 0.83 |
| Class transformation (LR) | 0.014 ± 0.013 | +13.16 ± 2.42 | +9.56 ± 1.45 | +8.75 ± 0.89 |
| Ours: score-anchored S-learner (LR) | 0.010 ± 0.015 | +13.44 ± 2.29 | +9.38 ± 1.61 | +8.38 ± 1.44 |
| Ours without score anchor (ablation) | 0.010 ± 0.014 | +13.60 ± 2.48 | +8.72 ± 1.67 | +8.12 ± 1.28 |
| T-learner (LR) | 0.009 ± 0.014 | +13.54 ± 2.49 | +8.84 ± 1.56 | +8.10 ± 1.42 |
| S-learner (GBM) | 0.006 ± 0.013 | +11.74 ± 2.41 | +8.91 ± 1.89 | +8.13 ± 1.23 |
| X-learner (GBM) | 0.006 ± 0.018 | +10.95 ± 2.67 | +8.85 ± 1.59 | +8.23 ± 1.15 |
| T-learner (GBM) | 0.004 ± 0.011 | +9.87 ± 2.27 | +8.50 ± 1.37 | +8.02 ± 1.01 |
| Random | -0.002 ± 0.016 | +7.96 ± 2.64 | +8.06 ± 1.60 | +7.82 ± 1.10 |

### Womens e-mail vs no e-mail

| Method | Qini coefficient | Uplift top 10% | Uplift top 20% | Uplift top 30% |
|---|---|---|---|---|
| Ours: score-anchored S-learner (LR) | 0.065 ± 0.011 | +6.91 ± 1.34 | +6.99 ± 0.84 | +7.20 ± 0.69 |
| Ours without score anchor (ablation) | 0.065 ± 0.012 | +6.90 ± 1.71 | +6.99 ± 1.12 | +6.93 ± 0.82 |
| T-learner (LR) | 0.065 ± 0.012 | +7.12 ± 1.70 | +6.79 ± 1.09 | +7.04 ± 0.87 |
| Class transformation (LR) | 0.064 ± 0.014 | +8.18 ± 1.65 | +7.60 ± 1.60 | +7.38 ± 1.05 |
| X-learner (GBM) | 0.063 ± 0.013 | +7.15 ± 2.20 | +7.18 ± 1.44 | +7.67 ± 0.95 |
| S-learner (GBM) | 0.061 ± 0.011 | +7.18 ± 1.84 | +7.51 ± 1.12 | +7.23 ± 0.91 |
| T-learner (GBM) | 0.056 ± 0.015 | +7.84 ± 1.87 | +7.74 ± 1.19 | +7.31 ± 0.72 |
| Response model (GBM) | 0.036 ± 0.010 | +7.22 ± 2.00 | +6.94 ± 1.11 | +6.69 ± 0.78 |
| Random | 0.001 ± 0.018 | +4.78 ± 2.31 | +4.55 ± 1.48 | +4.79 ± 0.88 |
| RFM rule (recency + spend) | -0.003 ± 0.011 | +4.42 ± 1.77 | +5.05 ± 1.08 | +4.56 ± 0.80 |

## Q2 — Which action for whom: value of the targeting policy

Incremental outcomes per 1,000 customers versus e-mailing nobody, estimated by inverse-propensity weighting on held-out customers (95% bootstrap CI). *Ours − policy* is the paired difference.

### E-mail budget: 10% of customers

| Policy | E-mailed | Extra visits /1000 | Extra conversions /1000 | Extra spend /1000 ($) | Ours − policy (visits) |
|---|---|---|---|---|---|
| NBA · Ours without score anchor (ablation) | 10% | 13.9 [11.0, 16.7] | 1.56 [0.77, 2.31] | 194 [51, 324] | -0.2 [-0.5, +0.1] |
| NBA · T-learner (LR) | 10% | 13.9 [11.1, 16.7] | 1.58 [0.78, 2.33] | 195 [51, 326] | -0.2 [-0.5, +0.1] |
| **NBA · Ours: score-anchored S-learner (LR)** | 10% | 13.7 [10.9, 16.6] | 1.55 [0.75, 2.31] | 193 [50, 323] | — |
| NBA · Class transformation (LR) | 10% | 13.6 [10.8, 16.4] | 1.59 [0.80, 2.36] | 196 [60, 335] | +0.1 [-0.4, +0.6] |
| NBA · S-learner (GBM) | 10% | 11.7 [9.2, 14.2] | 1.41 [0.78, 2.03] | 169 [59, 282] | +2.0 [+0.7, +3.4] |
| Response-score targeting (GBM) | 10% | 11.1 [8.5, 13.7] | 1.30 [0.61, 2.00] | 137 [29, 242] | +2.6 [+0.5, +4.7] |
| NBA · X-learner (GBM) | 10% | 10.8 [8.4, 13.1] | 1.28 [0.69, 1.88] | 180 [80, 282] | +2.9 [+1.2, +4.6] |
| RFM rule + e-mail matching past purchases | 10% | 10.7 [8.1, 13.2] | 0.94 [0.19, 1.69] | 110 [9, 218] | +3.1 [+0.2, +6.0] |
| NBA · T-learner (GBM) | 10% | 10.2 [8.1, 12.4] | 1.03 [0.52, 1.59] | 131 [29, 237] | +3.5 [+1.5, +5.7] |
| Best single e-mail (mens) to random customers | 10% | 7.8 [6.4, 9.3] | 0.58 [0.23, 0.94] | 70 [10, 132] | +5.9 [+2.9, +8.7] |
| Random customers, random e-mail | 10% | 5.5 [4.0, 6.8] | 0.33 [0.00, 0.64] | 43 [-3, 92] | +8.3 [+5.3, +11.3] |

### E-mail budget: 20% of customers

| Policy | E-mailed | Extra visits /1000 | Extra conversions /1000 | Extra spend /1000 ($) | Ours − policy (visits) |
|---|---|---|---|---|---|
| NBA · Class transformation (LR) | 20% | 20.2 [17.0, 23.4] | 1.81 [0.86, 2.72] | 203 [32, 366] | -0.5 [-2.5, +1.5] |
| **NBA · Ours: score-anchored S-learner (LR)** | 20% | 19.7 [16.4, 22.9] | 1.95 [1.02, 2.81] | 234 [79, 388] | — |
| RFM rule + e-mail matching past purchases | 20% | 19.3 [15.3, 22.9] | 1.56 [0.53, 2.56] | 164 [23, 320] | +0.3 [-3.5, +4.1] |
| Response-score targeting (GBM) | 20% | 19.1 [15.7, 22.8] | 1.78 [0.86, 2.72] | 207 [49, 359] | +0.5 [-2.4, +3.5] |
| NBA · Ours without score anchor (ablation) | 20% | 18.5 [14.8, 21.9] | 1.83 [0.87, 2.67] | 204 [47, 357] | +1.2 [+0.1, +2.4] |
| NBA · T-learner (LR) | 20% | 18.3 [14.8, 21.7] | 1.78 [0.84, 2.63] | 201 [42, 356] | +1.3 [+0.4, +2.4] |
| NBA · S-learner (GBM) | 20% | 18.2 [15.0, 21.2] | 1.97 [1.16, 2.80] | 226 [73, 377] | +1.4 [-0.8, +3.7] |
| NBA · X-learner (GBM) | 20% | 17.7 [14.5, 20.9] | 1.89 [1.03, 2.75] | 252 [102, 405] | +2.0 [-0.5, +4.4] |
| NBA · T-learner (GBM) | 20% | 17.1 [14.2, 19.9] | 1.61 [0.83, 2.38] | 229 [94, 366] | +2.6 [-0.0, +5.1] |
| Best single e-mail (mens) to random customers | 20% | 15.9 [13.7, 18.1] | 1.45 [0.89, 2.00] | 165 [59, 267] | +3.8 [+0.4, +6.9] |
| Random customers, random e-mail | 20% | 12.4 [10.4, 14.4] | 0.88 [0.41, 1.33] | 128 [56, 202] | +7.3 [+3.8, +10.4] |

### E-mail budget: 30% of customers

| Policy | E-mailed | Extra visits /1000 | Extra conversions /1000 | Extra spend /1000 ($) | Ours − policy (visits) |
|---|---|---|---|---|---|
| NBA · Class transformation (LR) | 30% | 27.9 [24.2, 32.0] | 2.36 [1.23, 3.41] | 271 [77, 451] | -2.0 [-4.6, +0.9] |
| Response-score targeting (GBM) | 30% | 27.4 [23.5, 31.7] | 2.22 [1.12, 3.38] | 248 [66, 428] | -1.4 [-5.0, +2.1] |
| RFM rule + e-mail matching past purchases | 30% | 26.0 [21.5, 30.2] | 1.75 [0.59, 2.95] | 248 [69, 439] | -0.0 [-4.0, +3.9] |
| **NBA · Ours: score-anchored S-learner (LR)** | 30% | 25.9 [22.0, 29.9] | 2.59 [1.52, 3.64] | 318 [137, 494] | — |
| NBA · T-learner (LR) | 30% | 25.2 [21.3, 29.2] | 2.59 [1.52, 3.59] | 327 [141, 516] | +0.7 [-0.4, +1.9] |
| NBA · Ours without score anchor (ablation) | 30% | 25.1 [20.9, 29.0] | 2.53 [1.42, 3.55] | 313 [126, 502] | +0.8 [-0.5, +2.2] |
| NBA · S-learner (GBM) | 30% | 24.9 [21.2, 28.4] | 2.55 [1.58, 3.47] | 316 [151, 496] | +1.0 [-2.0, +3.8] |
| NBA · X-learner (GBM) | 30% | 24.8 [21.1, 28.4] | 2.58 [1.62, 3.53] | 341 [167, 514] | +1.2 [-1.8, +4.5] |
| NBA · T-learner (GBM) | 30% | 23.7 [20.1, 27.0] | 1.98 [1.09, 2.84] | 256 [98, 398] | +2.2 [-0.7, +5.5] |
| Best single e-mail (mens) to random customers | 30% | 22.2 [19.2, 25.0] | 2.00 [1.28, 2.69] | 270 [161, 384] | +3.8 [-0.0, +7.5] |
| Random customers, random e-mail | 30% | 20.7 [18.1, 23.4] | 1.77 [1.14, 2.38] | 223 [121, 329] | +5.2 [+1.6, +8.8] |

### E-mail budget: 50% of customers

| Policy | E-mailed | Extra visits /1000 | Extra conversions /1000 | Extra spend /1000 ($) | Ours − policy (visits) |
|---|---|---|---|---|---|
| NBA · Class transformation (LR) | 50% | 42.0 [37.3, 46.9] | 3.48 [2.16, 4.77] | 410 [200, 610] | -2.3 [-5.3, +0.8] |
| Response-score targeting (GBM) | 50% | 41.5 [36.4, 47.2] | 3.30 [2.00, 4.72] | 416 [196, 637] | -1.9 [-5.9, +2.4] |
| RFM rule + e-mail matching past purchases | 50% | 41.5 [36.0, 47.5] | 3.61 [2.25, 5.13] | 405 [175, 632] | -1.9 [-6.2, +2.3] |
| NBA · Ours without score anchor (ablation) | 50% | 39.8 [35.0, 44.4] | 3.61 [2.30, 4.81] | 451 [235, 675] | -0.2 [-1.8, +1.5] |
| NBA · S-learner (GBM) | 50% | 39.8 [35.1, 44.3] | 3.41 [2.23, 4.56] | 414 [216, 611] | -0.1 [-3.2, +3.3] |
| **NBA · Ours: score-anchored S-learner (LR)** | 50% | 39.6 [35.0, 44.5] | 3.58 [2.33, 4.78] | 447 [238, 673] | — |
| NBA · T-learner (GBM) | 50% | 38.9 [34.6, 43.2] | 3.22 [2.11, 4.33] | 407 [217, 592] | +0.7 [-2.9, +4.3] |
| Best single e-mail (mens) to random customers | 50% | 38.9 [34.9, 43.0] | 2.97 [1.91, 3.95] | 327 [162, 489] | +0.7 [-3.3, +4.5] |
| NBA · X-learner (GBM) | 50% | 38.9 [34.1, 43.2] | 3.53 [2.31, 4.72] | 429 [222, 625] | +0.8 [-2.7, +4.1] |
| NBA · T-learner (LR) | 50% | 38.8 [34.0, 43.7] | 3.53 [2.25, 4.72] | 439 [229, 670] | +0.8 [-0.6, +2.4] |
| Random customers, random e-mail | 50% | 30.2 [26.6, 33.9] | 2.48 [1.56, 3.38] | 334 [196, 472] | +9.4 [+5.0, +13.7] |

### E-mail budget: 100% of customers

| Policy | E-mailed | Extra visits /1000 | Extra conversions /1000 | Extra spend /1000 ($) | Ours − policy (visits) |
|---|---|---|---|---|---|
| RFM rule + e-mail matching past purchases | 100% | 78.7 [71.5, 85.9] | 6.56 [4.92, 8.39] | 780 [514, 1065] | -0.8 [-3.7, +2.3] |
| NBA · Ours without score anchor (ablation) | 100% | 78.3 [71.3, 85.2] | 6.86 [5.23, 8.59] | 815 [538, 1085] | -0.4 [-1.4, +0.8] |
| NBA · Class transformation (LR) | 100% | 78.0 [70.9, 85.1] | 7.14 [5.39, 8.75] | 842 [566, 1118] | -0.1 [-2.2, +2.2] |
| **NBA · Ours: score-anchored S-learner (LR)** | 100% | 77.9 [70.8, 84.8] | 6.94 [5.31, 8.67] | 825 [547, 1107] | — |
| NBA · T-learner (LR) | 100% | 77.7 [70.8, 84.6] | 6.81 [5.17, 8.52] | 812 [535, 1084] | +0.2 [-0.9, +1.3] |
| NBA · X-learner (GBM) | 100% | 77.0 [70.0, 84.2] | 6.80 [5.16, 8.47] | 809 [536, 1081] | +0.9 [-1.8, +3.6] |
| NBA · S-learner (GBM) | 100% | 77.0 [70.1, 84.3] | 6.77 [5.16, 8.48] | 820 [550, 1106] | +0.9 [-1.3, +3.4] |
| Best single e-mail (mens) to random customers | 100% | 76.5 [69.4, 83.8] | 6.80 [5.01, 8.58] | 769 [494, 1051] | +1.4 [-2.4, +5.2] |
| Response-score targeting (GBM) | 100% | 75.8 [69.1, 82.7] | 6.25 [4.66, 7.91] | 735 [476, 999] | +2.1 [-0.6, +4.9] |
| NBA · T-learner (GBM) | 99% | 74.5 [67.8, 81.5] | 6.27 [4.67, 7.91] | 741 [479, 1004] | +3.4 [+0.7, +6.2] |
| Random customers, random e-mail | 100% | 62.5 [56.2, 68.7] | 5.66 [4.06, 7.22] | 682 [424, 931] | +15.4 [+11.3, +19.4] |

## Interpretable effects learned by our model (log-odds, all customers)

Rows: context term. *effect of X e-mail* = how much that e-mail changes the log-odds of a visit for customers with that attribute (numeric features standardised).

| Term | baseline | effect of mens e-mail | effect of womens e-mail |
|---|---|---|---|
| intercept | -1.453 | -0.509 | -0.140 |
| score_logit | +0.542 | -0.411 | -0.172 |
| recency | -0.156 | -0.004 | +0.067 |
| log_history | +0.094 | -0.002 | -0.046 |
| mens_buyer | +0.310 | +0.352 | -0.080 |
| womens_buyer | +0.190 | +0.434 | +0.494 |
| newbie | -0.464 | +0.057 | +0.202 |
| urban | -0.030 | +0.045 | +0.001 |
| rural | +0.326 | -0.032 | -0.181 |
| web | +0.214 | -0.026 | -0.036 |
| multichannel | +0.114 | -0.065 | -0.021 |
