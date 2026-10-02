# Demo script (about 15 minutes) and viva preparation

## Before the viva (10 minutes, once)
1. `start-all.bat` — wait until both browser tabs open (website 5173, dashboard 5174).
2. `seed-demo-data.bat` — 400 simulated learners with six weeks of history, so Model health,
   the next-best-action report and the forecast have data. They are tagged "simulated" and a
   banner says so — mention it, it is a strength (honest demo data).
3. Keep ready: a second email address for a live sign-up (or read the code from the
   `[EMAIL MOCK]` line in the user-backend window), the test card `4242 4242 4242 4242`.
4. Open `ml/results/` in VS Code (the four `.md` result files) for the evidence part.

---

## 1. The idea (1 minute)
> "CRMs like Salesforce Einstein and HubSpot score leads by **how likely they are to buy**.
> But the hottest leads mostly buy anyway — discounting them gives money away — and some
> cold leads are put off by a call. We built a system that decides **which action will change
> the outcome, and whether it is worth its cost**, explains every decision, tells sales how to
> move each lead forward, and keeps learning from what happens — with honest, reproducible
> evaluation on real data."

## 2. A learner's journey (4 minutes) — website
1. **Sign up** → enter the 6-digit code → complete the profile (e.g. Working Professional).
2. Open a course → watch the **Course overview · 35 sec** → scroll to **Pricing** and pause 4 s
   ("counted only when actually looked at, not scrolled past").
3. **Dashboard** → switch on **What our AI sees**: score, the factors in points and the step
   that would move it most. ("Learners normally don't see their score — this is a transparency
   view.")
4. **Add to Cart** → **Checkout** → leave without paying.

## 3. The sales side (4 minutes) — dashboard
1. **Leads**: the learner is already there (every verified sign-up becomes a lead). Open them →
   **Why this score?** — each signal's contribution, computed by the model.
2. Wait a minute, then **Dashboard → ⚡ Run automations now**. The panel shows the decision,
   e.g. "checkout abandon → call".
3. Lead → **Recommended action**: the options the engine compared — P(buy) under each
   action, uplift, expected extra profit, and blocked options with the reason (consent, no
   phone, call capacity). Point out: *a discount was not chosen because this person would
   probably buy anyway* (or whatever the table shows).
4. **How to move this lead up**: the cheapest realistic steps to reach the next tier.
5. **Today's actions**: the call task with its script; click **Spoke to them** — outcomes feed
   learning.
6. **Email** tab → **Improve email**: the coach removes spam triggers and claims we can't back
   up (placement, salary) and adds the real course facts.

## 4. The closed loop (3 minutes)
1. **Model health**: predicted vs actual conversion per tier on learners whose outcome is known.
   (With demo data, actual is a bit higher in the low tiers — the follow-ups worked.)
2. **Next-best-action** card: decisions per action, the 15 % random learning sample, and the
   off-policy estimate of "follow the model" vs "do nothing" vs "email everyone", **with 95 %
   intervals** — "we never claim more than the data supports".
3. **Pipeline forecast**: expected revenue with a 90 % range from calibrated probabilities.
4. Run `retrain-model.bat`: champion vs challengers (interpretable and flexible) on held-out
   logged decisions; the model is replaced only if a challenger earns more.

## 5. The evidence (3 minutes) — `ml/results/`
1. **Real lead data** (`real_benchmark.md`): "With every column of this dataset we also reach
   0.985 AUC — but some columns are filled in by the sales team after contacting the lead
   (Tags, Lead Quality), so that number is leakage. Without them we get **0.876** (0.901 with
   learner activity), vs 0.781 for manual points scoring, and 96–97 % of our top-10 % buy."
2. **Real randomized experiment** (`hillstrom_uplift.md`, 64,000 customers): "With a tight
   budget — e-mail the best 10 % — our uplift policy gets **23.5 % more** extra visits than
   targeting by likelihood, **28.9 % more** than a recency/spend rule (significant for visits);
   with larger budgets there is no significant difference. We report both."
3. **Robustness** (`nba_robustness.md`): "We broke our own assumptions — reversed effects,
   hidden drivers, nothing works, 20 random worlds. Learned policies beat the best fixed
   playbook in **20/20** worlds; when hidden drivers dominate, a flexible model often wins, so
   the closed loop now trains both and keeps the better one — it picked correctly in 16/20."
4. **Tips** (`recourse_eval.md`): "Same success as a one-size playbook at a **third of the
   effort**, only actionable steps by design (an unconstrained search gave 27 % impossible
   advice) — and we measured that only about half of the predicted gain is causal, which is
   why money decisions come from the randomized uplift model."

---

## Likely questions and short answers
* **Why not 90 %+ accuracy?** On real data, 0.98 is only reachable with leaked columns; the
  honest leakage-free result is 0.88–0.90 AUC. On the generated data even a model that knew
  each lead's hidden intent would reach only 0.89 AUC (ours: 0.877). A higher number would
  mean the model learned the answer key.
* **Why generated training data?** The website records signals the public dataset doesn't
  have (video, pricing dwell, cart, checkout, WhatsApp). The generator matches the site; the
  real datasets evaluate the method. Stated as a limitation.
* **How do you know the uplift is causal?** It is learned from randomized decisions (15 %
  exploration) with logged probabilities, and validated on a real randomized experiment
  (Hillstrom) with held-out customers.
* **What if your simulation assumptions are wrong?** That is exactly experiment 3: learned
  policies still beat every fixed playbook in all 20 random worlds, and the champion/challenger
  loop switches model family when needed.
* **Is it better than Einstein/HubSpot?** We could not run those closed products. We implement
  the approach they document — ranking by likelihood to convert, plus rule-based workflows —
  and beat it on the same data: real (Hillstrom, tight budgets) and simulated (3.5× profit).
* **Privacy / consent?** Opt-outs are enforced in every channel, one-click unsubscribe,
  WhatsApp only with opt-in, no hidden tracking pixel, simulated learners can never be emailed.
* **Limitations?** Generated training data for the product model; simulation assumptions for
  costs/discounts; off-policy estimates need a few hundred decisions; greedy rule can waste the
  call budget when nothing works (₹16 per lead in our null-world test).

## If something goes wrong during the demo
| Problem | Fix |
|---|---|
| No OTP email | read it from the `[EMAIL MOCK]` line in the user-backend window |
| Run automations finds nothing | the trigger needs 1 minute of inactivity — wait, press again |
| A lead dropped a tier | demo-mode decay after 10 min idle; any activity re-scores it |
| Dashboard empty / 401 | log in again (sessions last 12 h) |
| Anything else | `stop-all.bat`, then `start-all.bat` |
