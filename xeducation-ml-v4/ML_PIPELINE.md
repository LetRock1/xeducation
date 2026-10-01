# X Education — Lead Scoring Pipeline (v4)

## How it fits together

```
 Website (user-frontend)            user-backend                         marketing-backend
 ───────────────────────            ────────────                         ─────────────────
 tracker.js                         /api/track ─┐
  • visit = new session after         /api/enquiry│     scoring.py
    30 min idle                       scheduler  ├──▶  build_raw()  ──▶ predict.py ──▶ leads (+ why, model version)
  • time on every page                jobs       │     (ONE feature     ml_features.py    score_snapshots  ◀── closed loop
  • device + utm/referrer source      checkout ──┘      builder)        lead_model.pkl          │
  • pricing/testimonial: 4 s dwell                                            ▲                  │ labelled by purchases
  • webinar: seat reserved                                                    │                  ▼
                                    /api/internal/rescore  ◀──── email click (track_click)   /api/mkt/model/health
                                                                              │
                                    ml/retrain_from_live.py ──────────────────┘  (champion / challenger)
```

## Files

| File | What it does |
|---|---|
| `user-backend/ml_features.py` | **Single source of truth**: feature list, vocabularies, cleaning (`normalize_raw`), feature engineering, score→tier/persona, explanation signals. Used by training *and* serving. |
| `ml/generate_dataset.py` | Synthetic dataset v4 (60k leads) that matches what the site tracks. |
| `ml/train_model.py` | Trains Logistic Regression vs Gradient Boosting, keeps the better-calibrated one, saves `user-backend/ml_models/lead_model.pkl` + `model_card.json`. |
| `ml/retrain_from_live.py` | Closed loop: trains on synthetic + real labelled snapshots, replaces the live model only if it is better on real held-out users. |
| `user-backend/predict.py` | Loads the model (hot-reloads when retrained), scores, explains ("+17 pts: started checkout"). |
| `user-backend/scoring.py` | `build_raw()` / `score_user()` / `save_lead()` / `rescore_latest_lead()` — every endpoint and job uses these. |
| `train-model.bat` / `retrain-model.bat` | Run the scripts with the backend venv (same scikit-learn as the server). |

## What was wrong before, and the fix

| Problem | Effect | Fix |
|---|---|---|
| Generator multiplied the logit by 4.25 | Near-deterministic labels: 3 events took a lead from 6 % to 95 % | Label driven by hidden intent + realistic effects; AUC ≈ 0.88, graded probabilities |
| Behaviours drawn independently | Unrealistic; model learned "any event = buyer" | Behaviours correlated through intent |
| Site sent values never seen in training (`LeadOrigin="Website Interaction"`, `CourseType="Browsing"`/course title, `Specialization="Business"`) | Those features silently ignored | `normalize_raw()` maps to training vocabulary; course slug → course type |
| Skipped profile defaulted to "Unemployed" | Score ≈ 0 % | "Unknown" category, trained on 15 % skipped profiles |
| Hand rules overrode the model (cart floor 62, enquiry 42, Student cap 72 × 0.85) | Score ≠ probability; PLV used one, dashboard the other | Cart/wishlist/checkout/enquiry are model features; only rule left: customers floor at 80 |
| KMeans persona ordered by engagement | "Warm" converted better than "Hot"; cluster fed back as a feature | Persona from calibrated score |
| Pricing/testimonial/webinar fired on scroll | Everyone looked hot | 4-second dwell; webinar = seat reserved |
| Session id reused until logout; device "Desktop", source "Direct Traffic" hard-coded | Visits stuck at 1 | Session per visit, real device + utm/referrer source |
| Email click added +10 to score without changing tier | Score and tier disagreed | Click → model rescore (EmailOpenedCount is a feature) |
| Decay changed tier but not score | Disagreed again | Score capped to new tier; customers don't decay |
| No outcome feedback | "Closed loop" never learned | `score_snapshots` + purchases → `retrain_from_live.py`, model health on dashboard |
| 6 × `.pkl` files trained in another environment | Version mismatch risk | One bundle trained with the backend venv; version check at load |

## Model results (synthetic hold-out, 12 000 leads)

- ROC-AUC ≈ 0.88, accuracy ≈ 81 %, well calibrated. 0.88 is the ceiling the generator allows: the remaining error is the "luck" built into the data, so a higher number would mean leakage.
- Each tier converts at roughly its stated rate: Target ≈ 92 %, Nurture ≈ 67 %, Campaign ≈ 51 %, Low ≈ 14 %.
- A typical journey for a Working Professional: signed up 2 → viewed course 10 → video + pricing 30 → brochure on a 2nd visit 56 → cart 76 → checkout 91.

## Demo the closed loop

1. `start-all.bat` (trains the model on first run).
2. Use the site: browse, watch video, add to cart, start checkout, then buy. The marketing **Dashboard → Model health** card shows snapshots, and **Lead → Why this score?** shows the model's factors.
3. After a few users have bought (and some have not, for longer than the window), run `retrain-model.bat --window-days 1`. It reports champion vs challenger on real users and swaps the model only if it is better.
