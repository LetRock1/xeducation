# X Education — New Features: How They Work, How to Test, How to Demo

For the team. Assumes the 4 servers are running (see `new.txt` Part 4):

| Service | Port | Note |
|---|---|---|
| user-backend | 8000 | `DEMO_MODE=true` in `.env` shrinks all wait-times to 1–2 min |
| marketing-backend | 8001 | login: `admin@xeducation.in` / `123` |
| user-frontend | 5173 | the student-facing site |
| marketing-frontend | 5174 | the marketing dashboard |

All background jobs run every 5 minutes on a timer. To skip waiting, hit
`POST http://localhost:8000/api/debug/trigger-jobs` — it force-runs every job
immediately (cart, checkout, session, wishlist abandonment).

---

## 1. Checkout Abandonment

**What it does:** If a student reaches checkout but doesn't pay, they get a
follow-up email with the deepest discount we offer (`LAST_CHANCE_30`, 30%
off).

**How it works:**
1. Student opens `/checkout` → frontend silently calls `POST /api/checkout/start`, which writes a row to `checkout_sessions`.
2. If `POST /api/checkout` (the "Pay Now" button) is never called, that session sits `completed=0`.
3. Every 5 min, `checkout_abandonment_job()` (`user-backend/scheduler.py`) looks for sessions older than `CHECKOUT_ABANDON_MINUTES` (1 min in demo mode) that are still incomplete, scores the lead, generates the email, and sends it.
4. A new lead row appears in the marketing dashboard with `trigger_reason = checkout_abandon`.

**Manual test:**
1. Log into the user site (5173), add a course to cart, go to `/checkout`.
2. **Don't click Pay Now.** Wait ~1 min (demo mode) or call the debug endpoint:
   ```
   POST http://localhost:8000/api/debug/trigger-jobs
   ```
3. Open marketing dashboard (5174) → Leads → filter by trigger `checkout_abandon`.

**Expected outcome:** A new lead with `trigger_reason: checkout_abandon`, tier is at least "Nurture" (business rule floors it at 62+), coupon code `LAST_CHANCE_30`. Check the inbox for the email — it should mention "one click from completing checkout."

**Quick demo:** Add to cart → go to checkout → don't pay → hit `/api/debug/trigger-jobs` → refresh Leads page → point at the new lead and the urgency-toned email with the 30% coupon.

---

## 2. Closed-Loop Email Open/Click Tracking

**What it does:** Every marketing email has an invisible tracking pixel and a
tracked "View Course" button. Opening or clicking the email bumps the lead's
score in real time — this is what "closed-loop" means (send → engage →
re-score).

**How it works:**
1. Whenever an email is sent (cart/checkout/wishlist jobs, enquiry
   confirmation, or a manual send from the dashboard), a unique `token` is
   generated and logged in `email_sends`.
2. The email HTML gets two things: `<img src=".../track/open/{token}.gif">`
   (invisible, loads when the email client renders images) and a CTA button
   linking through `.../track/click/{token}?to=<course url>`.
3. Opening the pixel hits `GET /api/mkt/track/open/{token}.gif` on
   marketing-backend (no login needed — it's a public endpoint, since email
   clients can't send auth headers). This increments `open_count` and adds
   **+3** to the lead's score.
4. Clicking the CTA hits `GET /api/mkt/track/click/{token}`, adds **+7** to
   the score, and redirects the browser to the real destination.

**Manual test (no need to wait for a real email client):**
1. Send any lead an email from the dashboard (LeadDetail → Email tab → Send).
2. Open the marketing-backend logs or query `email_sends` for the token, OR just note the lead's current score.
3. Simulate an "open" by visiting in a browser:
   ```
   http://localhost:8001/api/mkt/track/open/<token>.gif
   ```
4. Refresh the lead in the dashboard — score should be +3.
5. Visit the click URL from the email body (or `.../track/click/<token>?to=http://localhost:5173`) — score should be +7 more, and your browser should redirect to the course page.

**Expected outcome:** `email_sends.open_count`/`click_count` increment, `leads.lead_score` rises, a row appears in `lead_score_history` with reason `email_open`/`email_click`.

**Quick demo:** Send an email from LeadDetail → open the tracking pixel URL in a new tab → refresh LeadDetail → show the score ticked up live. This is the single best "wow" moment for the demo — it's the thing HubSpot/Salesforce don't expose to the end customer.

---

## 3. Lead Decay / Re-scoring

**What it does:** If a hot lead goes quiet (no site activity, no email
opens) for a while, they automatically get downgraded a tier instead of
sitting in the "call immediately" queue forever.

**How it works:**
1. Every 5 min, `lead_decay_job()` (`marketing-backend/decay.py`) checks every lead that isn't already "Low Priority".
2. It compares "now" against the lead's most recent activity: `created_at`, latest `behaviour_events`, or latest email open.
3. If that's older than `DECAY_INACTIVITY_MINUTES` (2 min in demo mode, 7 days in production), the tier drops one step: `Target Immediately → Nurture → Marketing Campaign → Low Priority`.
4. Logged to `lead_score_history` with reason `decay`; `leads.decayed=1` so it only decays once per lead.

**Manual test:**
1. Create a "Target Immediately" lead (e.g. submit an enquiry with high engagement, or use an existing one).
2. Do nothing with that user for ~2 minutes (demo mode).
3. Wait for the scheduler tick (up to 5 min) — there's no debug-trigger for this one, since it's on marketing-backend's own scheduler, not user-backend's. Just wait, or watch the marketing-backend console for `[DECAY JOB] Downgraded N lead(s)`.
4. Refresh the lead in the dashboard.

**Expected outcome:** `recommended_action` moved down one tier, `decayed=1`, new row in `lead_score_history` with reason `decay`.

**Quick demo:** Show a lead's tier before, explain the console log line printing every 5 min, then show the tier after the wait — frames it as "the system doesn't let stale leads clog the priority queue."

---

## 4. Explainability ("Why this score?")

**What it does:** A plain-English breakdown of what drove a lead's score,
instead of a black-box number.

**How it works:** `marketing-backend/explain.py` reads the lead's stored
signals (video watched, brochure downloaded, chat opened, trigger reason,
occupation, etc.) and reconstructs the same business rules `predict.py`
applies, as a list of factors with a plain description and impact.

**Manual test:**
1. Open any lead in the dashboard → LeadDetail → click the **"Why this score?"** tab.
   — or —
   ```
   GET http://localhost:8001/api/mkt/leads/{id}/explain
   Authorization: Bearer <token from /api/mkt/login>
   ```

**Expected outcome:** A list of factors, e.g. "Downloaded brochure — +25 engagement, +3 intent", "Cart abandonment — floor 62", "Occupation dampening — cap 72, ×0.85". At minimum one factor always appears (falls back to "Baseline browsing" if nothing else fired).

**Quick demo:** Open a high-score lead, click the tab, read out 2-3 factors — this is your answer to "how do we know the AI isn't just guessing."

---

## 5. Attribution

**What it does:** Shows the full path a user took before becoming a lead or
converting — first touch, last touch before purchase, and everything in
between (page views, emails, clicks, purchase).

**How it works:** `GET /api/mkt/leads/{id}/attribution` merges four sources
by timestamp: `behaviour_events`, `email_sends` (opens/clicks), the lead's
own creation event, and `purchases`. Also `GET /api/mkt/campaign-influence`
aggregates, per trigger reason, how many opens/clicks led to a purchase
within 7 days — feeds the Dashboard's "Campaign Influence" chart.

**Manual test:**
1. LeadDetail → **Attribution** tab for any lead with some behaviour history.
2. Dashboard → scroll to the "Campaign Influence" chart (only shows once there's at least one email send in the system).

**Expected outcome:** A chronological timeline (page views → email opens/clicks → lead created → purchase if any), with First Touch / Last Touch Before Purchase summary boxes at the top.

**Quick demo:** Pick a lead who has browsed, gotten an email, and clicked it — walk through their timeline top to bottom as "this is the exact path that led to the sale."

---

## 6. A/B Testing

**What it does:** Lets marketing test two subject/body variants against a
tier of leads and see which one performs better (by open rate).

**How it works:**
1. Dashboard → **A/B Tests** page → fill in Variant A and Variant B subject/body + target tier → Create.
2. Click **Send to Matching Leads** — every lead currently in that tier is randomly assigned variant A or B (50/50), each gets its own tracked `email_sends` row (`variant`, `ab_test_id`).
3. Open/click tracking (feature #2) does the rest — opens and clicks get attributed back to the right variant.
4. Click **View Results** — shows sent/opened/clicked and open-rate per variant. A winner is only declared once both variants have ≥5 sends (avoids calling it on tiny samples).

**Manual test:**
1. Create a test targeting a tier that has a few leads in it (check the dashboard tier counts first).
2. Send it.
3. Manually "open" a few of the resulting `email_sends` tokens via the tracking pixel URL (see feature #2) to simulate opens.
4. View Results — confirm the numbers reflect what you just did.

**Expected outcome:** `variant_a`/`variant_b` sent/opened/clicked counts, `open_rate`/`click_rate`, and (once ≥5 sends each) a `winner`.

**Quick demo:** Create a test with an obviously punchier Variant B subject, send it, open a couple of B's pixels manually, show B pulling ahead in Results.

---

## 7. Predictive Lifetime Value (PLV)

**What it does:** Ranks leads not just by how likely they are to convert,
but by how much money they're worth — total already spent, plus a
projected future value based on tier and conversion probability.

**How it works:** `compute_plv(user_id, tier, conversion_probability)` =
money already spent (`SUM(purchases.price_paid)`) + `avg_course_price ×
conversion_probability × tier_multiplier` (multiplier: Target Immediately
1.5, Nurture 1.0, Campaign 0.6, Low Priority 0.2). Recomputed and saved to
`leads.plv` whenever a lead is created or re-tiered by the decay job.

**Manual test:**
1. Leads page → click **Sort by PLV** — list re-orders by `plv` descending.
2. Dashboard → **Priority Queue (High PLV)** quick-link card → shows leads ranked by `lead_score × plv`.
3. Or directly: `GET /api/mkt/priority-queue`.

**Expected outcome:** Leads with purchase history or high-tier + high
conversion probability sort to the top; a fresh, low-engagement lead shows
a low PLV (often near 0 if they haven't purchased anything and are Low
Priority tier).

**Quick demo:** Sort Leads by PLV, point out the top lead's number, open
LeadDetail and show the PLV figure in the profile card — frame it as "not
just who's hot, but who's worth chasing."

---

## Fastest end-to-end demo script (~5 min)

1. Sign up on user site → browse a course (watch video, download brochure, view pricing) → add to cart → go to checkout, don't pay.
2. `POST /api/debug/trigger-jobs` on 8000.
3. Marketing dashboard → Leads → open the new `checkout_abandon` lead.
4. Show **Why this score?** tab (explainability).
5. Send the email → open its tracking pixel URL in a new tab → refresh → show score bump (closed-loop tracking).
6. Show **Attribution** tab → the full path from first page view to this email.
7. Dashboard → Priority Queue card → PLV in action.
8. A/B Tests page → create + send a quick test, open one variant's pixel, show results.
9. Mention lead decay running quietly in the background (point at the marketing-backend console log).
