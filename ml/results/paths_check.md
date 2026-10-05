# What-if paths: out-of-time check

Learned from 2,655 decisions before 2026-08-04; tested on 2,040 later decisions (weighted by 1/probability).

| Prediction of the reaction in the next 3 days | Brier score (lower is better) |
|---|---|
| same mix for everyone | 0.5558 |
| mix per stage (ignores the step) | 0.5397 |
| what-if paths (stage and step) | 0.5457 |

| Team step | Later decisions | Predicted buying within 14 days | Actual |
|---|---|---|---|
| call | 498 | 38.6% | 38.1% |
| email_coupon_10 | 251 | 40.1% | 47.1% |
| email_coupon_20 | 449 | 40.4% | 43.3% |
| email_info | 311 | 37.9% | 40.6% |
| none | 398 | 37.8% | 27.4% |
| whatsapp | 133 | 34.3% | 34.2% |
| all | 2,040 | 38.7% | 39.2% |
