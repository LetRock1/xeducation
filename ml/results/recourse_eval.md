# “How to convert” tips — counterfactual quality

3,000 fresh simulated leads below the top tier. Plans use at most 3 steps. *Predicted gain* = lead-model score change; *true gain* = change in the simulator's true purchase probability for the same person (hidden intent held fixed), averaged over plans that reach the next tier.

Structural check: behaviour coefficients recovered from the generated data within 0.017 (residual sd 0.45).

One-size plan (same for everyone): WebinarAttended + EnquirySubmitted + AddedToCart.

| Leads | Method | Coverage (reaches next tier) | Steps | Effort (reached) | Effort (all) | Predicted gain (pts) | True gain (pts) | True / predicted | True gain per effort |
|---|---|---|---|---|---|---|---|---|---|
| all (3,000) | Ours (cheapest personalised plan) | 89.2% | 2.05 | 2.82 | 2.83 | 26.3 | 13.3 | 0.51 | 4.72 |
| all (3,000) | One-size plan | 87.5% | 2.69 | 8.07 | 8.15 | 46.4 | 32.9 | 0.71 | 4.08 |
| Low Priority (2,298) | Ours (cheapest personalised plan) | 85.9% | 2.32 | 3.35 | 3.29 | 29.7 | 14.5 | 0.49 | 4.33 |
| Low Priority (2,298) | One-size plan | 84.0% | 2.84 | 8.51 | 8.55 | 51.2 | 34.8 | 0.68 | 4.09 |
| Marketing Campaign (417) | Ours (cheapest personalised plan) | 100.0% | 1.20 | 1.22 | 1.22 | 18.1 | 10.3 | 0.57 | 8.51 |
| Marketing Campaign (417) | One-size plan | 100.0% | 2.40 | 7.19 | 7.19 | 39.3 | 32.0 | 0.82 | 4.46 |
| Nurture via Email/WhatsApp (285) | Ours (cheapest personalised plan) | 100.0% | 1.38 | 1.44 | 1.44 | 14.4 | 9.2 | 0.64 | 6.39 |
| Nurture via Email/WhatsApp (285) | One-size plan | 97.9% | 2.11 | 6.34 | 6.25 | 23.5 | 20.8 | 0.88 | 3.27 |

## Why actionability constraints matter

On 600 of the leads, an unconstrained search (any attribute may change, cost 1 each) reaches the next tier for 91.5% (ours: 89.7% on the same leads) — but **27.0%** of its plans require changing something no one can act on (most often: CurrentOccupation ×148).

## Average predicted gain of each single step (pts)

| Step | Gain |
|---|---|
| EnquirySubmitted | +14.02 |
| WebinarAttended | +10.71 |
| AddedToCart | +10.08 |
| BrochureDownloaded | +7.78 |
| ChatInitiated | +6.53 |
| AddedToWishlist | +6.17 |
| TotalVisits | +4.82 |
| PricingPageVisited | +4.68 |
| VideoWatched | +4.48 |
| TestimonialVisited | +3.32 |
| EmailOpenedCount | +2.96 |
