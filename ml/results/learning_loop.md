# Learning loop on real randomized data (Hillstrom, 42,613 customers: men's e-mail vs none)

20 repeats; the CRM e-mails the top 30% by its score, 15% of choices random; two retraining rounds; judged on held-out customers the real experiment left alone.

| Method | Overstates targeted customers by | Honest AUC | AUC on the CRM's own data | Honest log-loss | Log-loss on the CRM's own data |
|---|---|---|---|---|---|
| Naive retrain (how CRMs retrain) | +39.6% (sd 7.1) | 0.637 | 0.686 | 0.3285 | 0.3736 |
| Ours (told what the CRM did) | +10.2% (sd 6.6) | 0.637 | 0.683 | 0.3248 | 0.3809 |
| Left-alone customers only (weighted) | +13.1% (sd 10.5) | 0.616 | 0.666 | 0.3307 | 0.3901 |
| Reference: no loop at all | +7.5% (sd 6.6) | 0.638 | 0.684 | 0.3242 | 0.3811 |

- Judged by fit on the CRM's own logged data (the usual check), the naive model is picked over ours in **20 of 20** repeats.
- Judged on the randomized left-alone truth, ours is more accurate than naive in **19 of 20**.
- Ours overstates targeted customers less than naive in **20 of 20**.
- The gap between AUC on the CRM's own data and honest AUC is the accuracy illusion: +0.049 for naive.
