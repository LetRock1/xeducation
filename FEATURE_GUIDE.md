# X Education — Feature guide

What every feature does, how it works, and how to test it. For the models and their
evaluation see [ML_PIPELINE.md](ML_PIPELINE.md); for a ready-made demo run see [DEMO.md](DEMO.md).

| Service | Address | What it is |
|---|---|---|
| Learner website | <http://localhost:5173> | where learners browse, sign up and buy |
| Marketing dashboard | <http://localhost:5174> | the sales & marketing workspace (log in with `MARKETING_EMAIL` / `MARKETING_PASSWORD` from `marketing-backend/.env`) |
| User API | <http://localhost:8000/docs> | accounts, tracking, scoring, next-best-action, automations |
| Marketing API | <http://localhost:8001/docs> | CRM: leads, actions, campaigns, A/B tests, model health |

**Demo mode** (`DEMO_MODE=true` in both `.env` files, the default): automations fire 1 minute
after a cart / checkout / wishlist / visit goes quiet (instead of 15–60 min), and leads decay
after 10 minutes of inactivity (instead of 7 days). The automation timer runs every 5 minutes;
to skip the wait press **⚡ Run automations now** on the dashboard.

**Emails**: with `GMAIL_USER` / `GMAIL_APP_PASSWORD` set they are really sent; otherwise every
email (including OTP codes) is printed in the user-backend window as `[EMAIL MOCK] …`.

---

## A. Learner website

### A1. Sign-up with email code, login, password reset
* **What it does** — accounts are verified with a 6-digit code; forgotten passwords are reset
  with a code; logged-in users can change their password in Settings.
* **How it works** — `/api/auth/signup` → code by email (valid 10 min, 5 wrong tries burn it,
  resend after 60 s) → `/api/auth/verify-otp` creates the account **and a CRM lead**
  (so every learner appears in the dashboard immediately). `/api/auth/forgot-password` never
  reveals whether an email is registered.
* **How to test** — 1. Sign up on the website. 2. Enter the code from your inbox (or the
  `[EMAIL MOCK]` line). 3. In the dashboard → **Leads**, the person appears with trigger
  `signup`. 4. Log out → **Forgot password?** → reset with the new code → log in.
* **Expected** — wrong codes are rejected; "resend" is blocked for 60 s; the password change
  works with the new password only.

### A2. Complete profile and Settings
* **What it does** — occupation, specialisation, city, age bracket, phone; communication
  preferences (email, calls, WhatsApp) and password change.
* **How it works** — `/api/profile/complete`, `/api/profile/preferences`. Consent is used
  everywhere: opted-out learners are never emailed or called, WhatsApp needs an opt-in and a
  phone number.
* **How to test** — **Settings** → untick email → save. Trigger any automation for this
  learner (A5/B1): no email is sent; the next-best-action picks a different channel or nothing.

### A3. Silent behaviour tracking
* **What it does** — measures what the model needs: visits (a new visit after 30 minutes idle),
  time on each page, pages per visit, device, traffic source (`utm_source` / referrer), and
  intent signals: overview video watched (counts after half of it has played), pricing and
  testimonials (only after **4 s actually in view**), brochure, chat, webinar seat, wishlist,
  cart, checkout, enquiry.
* **How it works** — `user-frontend/src/utils/tracker.js` → `/api/track`; each event re-scores
  the learner's lead row (`scoring.rescore_latest_lead`) and stores a score snapshot for the
  closed loop.
* **How to test** — log in, open a course, scroll to **Pricing** and wait 4 s, watch the
  **Course overview · 35 sec**. Open the lead in the dashboard → **Activity**: the events and
  the score change; **Why this score?** lists "Spent time on pricing +x pts", etc.

### A4. Course page, overview, brochure, reviews, Q&A
* **What it does** — course details from the catalogue; a 35-second overview (5 slides);
  a printable brochure page (**Download PDF** = the browser's Save-as-PDF); reviews (only
  enrolled learners may review); questions answered by the team (B6/D9).
* **How to test** — open any course → **Course overview**; brochure → **Download PDF**; ask a
  question in Q&A; try to review a course you have not bought (refused).

### A5. Enquiry
* **What it does** — the learner asks about a course (optional phone + WhatsApp opt-in). They
  always get a confirmation email; the next-best-action engine decides whether it carries a
  10 % or 20 % coupon or whether an advisor should call.
* **How it works** — `/api/enquiry` → `playbook.handle_trigger(..., "enquiry")` (see C2).
* **How to test** — **Enquire Now** on a course → submit. Dashboard → **Leads** → open the
  person → **Recommended action** shows the decision, the options it compared and why.

### A6. Wishlist, cart, checkout and coupons
* **What it does** — save for later, cart priced from the catalogue (prices sent by the browser
  are ignored), coupon preview before paying, simulated payment by UPI or card (card numbers
  are checked with the Luhn algorithm — use `4242 4242 4242 4242`; nothing is charged).
* **How it works** — `/api/cart`, `/api/wishlist`, `/api/checkout/start` (records the checkout
  for abandonment), `/api/coupons/check`, `/api/checkout`. Coupons are personal (issued to one
  learner), expire after 72 h and work once. A purchase labels the learner's earlier score
  snapshots and decisions as **converted** (closed loop) and the confirmation email says which
  touchpoint the purchase is attributed to.
* **How to test** — add a course → **Checkout** → your offers appear as buttons → **Apply** →
  the total drops → pay with the test card → thank-you page; the dashboard shows the purchase,
  revenue and the lead as Customer.

### A7. Chat assistant and callback requests
* **What it does** — an automated assistant (clearly labelled) answers fees, duration,
  syllabus, instructors, refunds and "which course suits me?" from the catalogue; "Talk to an
  advisor" opens a **Request callback** form.
* **How it works** — `/api/chat` (intent rules + course matcher in `assistant.py`; optional
  Gemini with `GEMINI_API_KEY`); `/api/callback` saves the request, records it as an
  enquiry-type signal and creates a lead. Transcripts are visible to sales (D3).
* **How to test** — open the chat bubble, ask "what are the fees for data science?", then
  "talk to an advisor" → submit a phone number → dashboard **Callbacks** shows it.

### A8. Learner dashboard
* **What it does** — courses, cart, saved courses, active offers, **Your next steps**
  (personalised, ranked by the model — e.g. "Join Saturday's free live session", "Get the MBA
  Core brochure"), recommended courses with the reason, and an optional **What our AI sees**
  panel (*Transparency / demo view*: the learner's own score, factors and the step that would
  move it most). The score is hidden unless that panel is switched on.
* **How it works** — `/api/dashboard` (`recourse.learner_steps`), `/api/recommendations`
  (profile + viewed + co-purchases, never recommends what you own or have in the cart),
  `/api/me/insights`.

---

## B. Automations (run every 5 minutes, or **⚡ Run automations now**)

Each trigger scores the learner, asks the **next-best-action** engine what to do (C2), and
then sends the chosen email, or creates a call / WhatsApp task in **Today's actions**, or does
nothing. Every decision is logged with its probability so it can be evaluated (C4).

| Trigger | Fires when (demo / normal) | Once per | Actions allowed |
|---|---|---|---|
| Checkout left | checkout started, not paid for 1 / 30 min | checkout | all |
| Cart left | course in cart for 1 / 60 min | cart item | all |
| Wishlist cold | saved for 1 / 30 min, not bought | wishlist item | nothing, info email, 10 % coupon, WhatsApp |
| Visit ended | no activity for 1 / 15 min, visit in the last 48 h, a course was viewed | visit | all |
| Enquiry | form submitted | enquiry | info / coupon email, call (an email is always sent) |

Cool-downs stop pile-ups: no cart follow-up within 12 h of another cart/checkout touch, no
wishlist one within 24 h, no visit follow-up within 6 h of any touchpoint. Customers who are
only browsing their own course are not chased.

### B1. Testing an automation
1. On the website: log in, open a course for a minute, add it to the cart, open **Checkout**
   and leave without paying.
2. Wait one minute, then press **⚡ Run automations now** on the dashboard. The panel lists
   each decision ("Priya · checkout abandon → call").
3. Open the lead → **Recommended action** (the decision and every option's expected profit),
   **Email** (the email text) or **Today's actions** (the call task).

### B2. Tracked emails and one-click unsubscribe
* Every marketing email has a tracked **View Course** button (click → `/api/mkt/track/click`
  → the course page, only ever on our own site) and an unsubscribe link (+ `List-Unsubscribe`
  header). A click re-scores the learner with the model (clicked emails are a model signal).
  There is no hidden tracking pixel.
* **Test** — open an email's button link: the lead's **Emails** list shows the click and its
  score history logs `email_click`. Open the unsubscribe link: a confirmation page appears and
  no further marketing emails go to that learner.

### B3. Lead decay
* A lead with no activity for 10 min (demo) / 7 days drops one tier; its score is capped at the
  new tier's ceiling so score and tier always agree; customers never decay. New activity
  re-scores the lead with the model.

---

## C. Intelligence

### C1. Lead score, tier, persona, "Why this score?"
Calibrated probability of buying (0–100), tier (Target ≥ 80, Nurture ≥ 60, Campaign ≥ 40, Low),
persona (Hot/Warm/Cold/Customer). **Why this score?** shows, for each signal the learner has,
how many points the score would lose without it — computed by the model, not hand-written
rules. Leads scored by an older version show a note and can be refreshed with **↻ Re-score now**.

### C2. Next-best-action
For each allowed action — do nothing, information email, 10 % / 20 % coupon email, advisor call,
WhatsApp — the uplift model estimates P(buy). Expected profit = P(buy) × price × (1 − discount)
− cost; the engine picks the largest gain over doing nothing (or nothing). Consent, phone
number, a daily call capacity (`NBA_DAILY_CALLS`), "no 20 % coupon for existing customers" and
the trigger's allowed actions are enforced. 15 % of decisions (`NBA_EXPLORE_RATE`) are random —
marked "random — learning sample" — so the system keeps learning what works.
**Test** — lead → **Recommended action**: the chosen action, the reason in plain words and a
table of every option (P(buy), uplift, expected profit, or why it was blocked).

### C3. How to convert (tips)
The cheapest set of up to 3 realistic steps (watch the overview, brochure, pricing walk-through,
webinar, enquiry …) predicted to lift the lead into the next tier, with the predicted score.
Shown to sales (lead → **Recommended action**, and in **Today's actions**) and, as
"Your next steps", to the learner. Labelled as guidance: the model shows these signals go with
buying; it does not prove a step causes it (see ML_PIPELINE §4).

### C4. Closed loop
* **Model health** (dashboard): predicted vs actual conversion per tier for real learners whose
  outcome is known (bought, or 14 days passed).
* **Next-best-action** card (dashboard): decisions per action, the random slice, and the
  estimated profit per lead of "follow the model", "do nothing" and "information email to all"
  (inverse-propensity estimates with 95 % intervals and the number of matching decisions).
* **`retrain-model.bat`**: retrains the lead model (champion vs challenger on held-out real
  learners) and the next-best-action model (champion vs an interpretable and a flexible
  challenger, compared by off-policy profit on held-out real decisions). A model is replaced
  only if the new one is better; the backend reloads it automatically.
* **Test** — run `seed-demo-data.bat` (D1), refresh the dashboard (both cards fill), then run
  `retrain-model.bat` and read the champion/challenger comparison.

### C5. Pipeline forecast
Dashboard card: expected revenue and new customers from everyone who has not bought yet
(Σ P(buy) × course price), with a 90 % range and a per-tier breakdown. It is only as reliable
as the calibration shown in Model health.

### C6. Course recommendations
Profile, viewed courses and "learners who bought X also bought Y"; each comes with its reason;
never what the learner owns or has in the cart.

---

## D. Marketing dashboard

### D1. Dashboard
KPIs (people, average score, emails sent · clicked, active carts, open callbacks, purchases ·
revenue, Target / Nurture counts), **Model health**, **Next-best-action**, **Pipeline forecast**,
score distribution, leads by tier, campaign influence (clicks and purchases within 14 days of a
click, per trigger/campaign), quick links, **⬇️ Export CSV** (one row per person) and
**⚡ Run automations now**.
*Demo data*: `seed-demo-data.bat` adds 400 simulated learners (emails ending in
`@demo.xeducation.test`, which is never mailed) with six weeks of history, scored and decided
by the live models; a banner and a "simulated" tag mark them; `remove-demo-data.bat` removes
them and everything linked to them.

### D2. Leads
One row per person (their latest touchpoint), filter by tier, search, sort by **Newest**,
**Score** or **Value** (P(buy) × course price). Status shows Customer, open callback,
unsubscribed or emailed.

### D3. Lead detail
Profile card and **↻ Re-score now**, plus tabs:
* **Recommended action** — the next-best-action decision and options, and *How to move this
  lead up* (tips).
* **Email** — the drafted email; **Improve email** (rule-based coach that removes spam
  triggers and unverifiable claims such as salary or placement promises, and adds the real
  course facts; Gemini if configured) and **Send email** (tracked).
* **WhatsApp** — opens WhatsApp (wa.me) with the message; only for opted-in learners with a
  phone number; logged.
* **Activity** — recent events, score history, emails, purchases.
* **Chat & callbacks** — chat transcript and callback requests.
* **Coupon** — **Generate & assign** a personal code (5–50 %, 1–720 h).
* **Why this score?** and **Attribution** (first touch, last touch before purchase, full
  timeline).

### D4. Today's actions
Calls and WhatsApp messages chosen by next-best-action, highest expected extra profit first,
with the call script / message and the tips. Record the result (**Spoke to them**, **No
answer**, **Not interested**, or **Open WhatsApp** → **Mark sent**); outcomes are logged for
learning. One open task per person and channel.

### D5. Callbacks
Requests from the website chat with phone and preferred time; **Open lead**, **Mark called**.

### D6. Campaigns
Schedule an email to a tier or **All leads** at a date and time (sent by a 1-minute timer), or
**Send now**. `{first_name}`, `{name}`, `{course}` are personalised; opted-out learners are
skipped. Each campaign shows delivered, clicks and purchases within 14 days; a campaign can
only ever be sent once.

### D7. A/B tests
Two subject/body variants to a tier; recipients are split randomly 50/50 and each person gets
one email. Results show click and purchase rates, a two-proportion z-test (p-value, 95 % CI)
and how many sends are needed to detect a 5-point difference — a winner is declared only when
the difference is significant.

### D8. Coupons
All issued coupons (automatic and manual) with status, expiry and delete.

### D9. Q&A
Unanswered course questions; publishing an answer shows it on the course page and emails the
learner.

---

## Troubleshooting
| Symptom | Cause / fix |
|---|---|
| `[ML] … not found — using fallback scoring` | no trained model: run `train-model.bat` |
| `[NBA] nba_model.pkl not found — using the built-in prior` | same: run `train-model.bat` |
| **Run automations now** says the backend refused | `INTERNAL_API_KEY` differs between the two `.env` files |
| No emails arrive | Gmail not configured → look for `[EMAIL MOCK]` lines in the user-backend window |
| Model health / NBA card say "no outcomes yet" | outcomes need a purchase or 14 days → use `seed-demo-data.bat` |
| A lead dropped a tier during the demo | lead decay after 10 min idle in demo mode; any activity re-scores it |
