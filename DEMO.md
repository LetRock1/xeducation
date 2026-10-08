# Viva guide (v6.3): what to show, what to say, and the questions to expect

## 1. Your project in one minute (say this first)

> "Every CRM scores leads, decides what to send, and retrains its score on *who bought*. The
> problem: the leads it chased were helped by its own e-mails, coupons and calls. So a normal
> retrain mistakes the CRM's own follow-ups for 'good leads', and its scores inflate over time —
> and the usual accuracy check even prefers that inflated model.
> Our CRM is told what it did to each lead, takes that out of the score, and only switches to a new
> model when a small group of leads it never contacts (5%) confirms the new one is better.
> On a real randomized experiment with 64,000 customers, a normal retrain overestimated the chased
> customers by about 40%, ours by about 10%, and the usual check picked the wrong model 20 times out
> of 20."

## 2. What is real and what is simulated (say it before she asks)

| What | Data | Real? | What it shows |
|---|---|---|---|
| Lead-scoring method | X Education Kaggle file, 9,240 leads, only the 9 columns a new lead has | Real | AUC 0.874 with no leakage (0.98 is only possible with columns sales writes after contacting the lead) — `ml/results/model_benchmark.md` |
| Choosing who gets which e-mail | Hillstrom, 64,000 customers e-mailed at random | Real | At a 10% budget, 13.7 extra visits per 1,000 vs 11.1 for targeting by likelihood (+2.6, 95% CI +0.5 to +4.7); no clear difference at larger budgets — `hillstrom_uplift.md` |
| Learning without fooling itself (the novelty) | Hillstrom outcomes, 20 repeats | Real | Normal retrain off by +39.6%, ours +10.2%; the usual check picks the wrong one 20/20 — `learning_loop.md` |
| The CRM's learners: 2,000 with a six-month history, about 13 new a day, using the website live | Documented simulator, through the website's own API | Simulated, tagged "simulated" | That the whole system runs end to end, in real time, and that its decisions and learning loop do the right thing when the truth is known |
| You (or a friend, or the examiner) on the website | Live | Real | That it works on a real person, right now, through exactly the same code |

How to say it, in your own words:

> "The CRM is real software, running live. It has one pool of learners. A CRM is normally switched
> on inside a company that already has leads; a student project has no company, so 2,000 simulated
> learners stand in for that business. They are not clicks I make: a simulator in `ml/` uses the
> website through the same API a browser uses, in real time, and reacts to the e-mails, coupons and
> calls the CRM really sends, following documented rules. Their hidden intent is kept in a separate
> database the CRM never reads — the CRM only sees what any CRM sees: pages, clicks, purchases.
> Everything it does for them it does for a real person in exactly the same way, and I will show you
> that live. What I claim about real markets comes from the two real datasets."

Do **not** say they are real customers, and do not hide them: they carry a "simulated" tag, and their
numbers describe the simulator, not a market.

## 3. The demo: 6 steps, about 12 minutes

Two browser windows: an **incognito window** for the learner (website, http://localhost:5173) and a
normal window for the **dashboard** (http://localhost:5174). Use a real e-mail address you can open
on this laptop.

**Step 0 — The system is alive (1 min).** Dashboard → **Simulated learners, live**: what they did in
the last 24 hours (visits, e-mail clicks, purchases, new sign-ups, calls by the simulated advisor) and
their latest steps. Press **▶ Send a learner to the website now** and open their lead page.
* Within a minute the visit appears on their lead page (pages, video, cart …) and the score moves
  with every event; about a minute after their last click, the CRM decides by itself (demo timing).
* Say: *"I did not click anything for this person. The simulator only decided that they come back
  now; what they do is drawn from the documented model, and it reaches the CRM through the public
  API. The CRM cannot tell them apart from a real visitor, except by their address."*

**Step 1 — A real learner arrives (2 min).** Sign up, enter the code, complete the profile (add a
phone number and tick WhatsApp if you want to show calls). Open a course, play the overview video,
keep the pricing section on screen for a few seconds, add the course to the cart, then close the tab.
* Dashboard → **Leads**: the learner is at the top within seconds, next to the simulated learners
  (one pool; filter "Signed up themselves" to show only real people).
* Open the learner → **Why this score?**: each reason in points, worked out by the model just now.
* Say: *"The score is the chance this person buys within 14 days if we do nothing. It updates on
  every click, and every lead is re-scored by itself every few minutes and whenever the model changes."*

**Step 2 — The CRM decides by itself (2 min).** About a minute after the learner leaves, the CRM
decides (or press ⚡ **Run automations now** on the Dashboard). On the lead page,
**Recommended action**:
* *What the CRM has done so far*: "Cart left → Advisor phone call · chosen by the model" (or an
  e-mail, or "random pick (15% learning sample); the model's own pick: …"). Click **receipt**.
* Say: *"For every possible step the model gives the chance to buy and the extra profit after
  discounts and costs. The highest extra profit wins; if nothing pays for itself, it does nothing.
  15% of decisions are random on purpose, so it can keep measuring what really works."*
* If it chose a call: **Today's actions** shows the call task with a script; click "Spoke to them".
  The CRM decides who to call and why; a person makes the call and records the result. (Calls for
  simulated learners are made by the simulated advisor, because their numbers are fake; each done
  task says who did it.)

**Step 3 — The e-mail and the click (2 min).** On the lead page press **▶ Do it now** on an e-mail
step (or show the e-mail the CRM sent). Open Gmail **on this laptop**, open the e-mail, click
**View Course**: it opens exactly that course. Back on the lead page (it refreshes by itself):
"✉️ e-mail sent · 🖱️ clicked 5:08 pm · 👀 back on the site".
* Say: *"The button links to the course page with the e-mail's token. The page reports the click, so
  it is tied to that exact e-mail. Even without a click, the learner is logged in, so everything they
  do is recorded, and every step is judged by 'bought within 14 days', compared with people who
  randomly got nothing."* The simulated learners click through the very same endpoint.

**Step 4 — The learner buys (1 min).** In the incognito window: cart → checkout → test card
`4242 4242 4242 4242`. The lead page shows **✓ Customer since …** with what they paid. Every
decision before the purchase now says "bought within 14 days". No more chance-to-buy, coupons or
what-if paths: the CRM does not sell a course the person already owns. **Pipeline**: the card moved
to *Customer* by itself.

**Step 5 — The novelty: learning that does not fool itself (3 min).** **Learning loop** page:
* Three boxes: what a normal retrain expects of the untouched control group, what ours expects,
  what they actually bought. *"The normal retrain is further off, because it counts our own
  follow-ups as lead quality."*
* *"Picking the model that fits live data best would have chosen the naive one"* — the usual check
  is fooled; ours is judged only on the people the CRM never contacted.
* Runs table: a new model replaces the old one only when it is better on the control group in at
  least 90% of resamples. After a switch, every lead is re-scored by itself. New outcomes keep
  arriving from the live learners, so the loop runs by itself again ("next run by itself after N
  more outcomes").
* **What our own actions add**: the e-mail / coupon / call effects the loop learned and then
  switched off in the score.

Optional extras: **A/B tests** (verdict with a 95% interval, sample size planned before sending),
**What-if paths** (same pick as the recommendation, plus how similar learners reacted next),
**Ask the CRM** ("Who should we call today?"), **New sign-up now** on the Dashboard.

## 4. How to prove the decisions are made by the ML models

1. **The receipt.** Every decision stores the chance to buy for each step, the extra profit, which
   step won, the model version and the probability of the choice. A rule ("Nurture tier → 10%
   coupon") has no such numbers. Show it on the lead page (Recommended action → receipt).
2. **Same situation, different people, different steps.** Dashboard → Next-best-action: all six
   steps are used. A tier rule would give everyone in a tier the same step. Open two learners in
   the same tier: different recommendations, each with its own numbers.
3. **Change one input, the decision changes.** Remove the learner's phone number in the website's
   Settings: "call" becomes "not possible: no phone number". Opt out of e-mail: every e-mail step is
   blocked. Add a course to the cart: all the chances change.
4. **Random picks are labelled.** "random pick (15% learning sample); the model's own pick: …". That
   is how the CRM measures cause and effect instead of guessing.
5. **It changes itself.** The Learning loop page lists every run, with the model version before and
   after and the reason it switched or kept the model.
6. **Simulated and real learners get the same treatment.** A real person and a simulated one in the
   same situation get the same numbers on the receipt; there is no "if simulated" anywhere in the
   decision code (`user-backend/nba.py`, `playbook.py`). The only difference is the separate call
   capacity of the simulated advisor.

## 5. Questions she may ask

**Are your learners real customers?** No, and I do not claim it. People who sign up on the website
are real; the 2,000 learners with history and the new ones each day are simulated stand-ins for a
company's existing leads, tagged "simulated" everywhere. They are what makes it possible to run the
system end to end, live, and to check its learning against a truth I know. Claims about real markets
come from the two real datasets.

**Then isn't it fake?** The software is not: it runs live, the simulated learners reach it only
through the website's public API, and it treats them exactly like a real person — which I can show
live in the same session. Like a flight simulator: the aircraft software is real, the weather is
simulated, and that is how you test that the software reacts correctly.

**Does the CRM cheat — does it know the hidden intent?** No. The simulator keeps each person's
hidden intent, luck and reactions in its own database (`user-backend/simulation_world.db`). The CRM's
database only has what the website records: sign-ups, pages, clicks, purchases. The scores come from
that alone.

**Who decides what a simulated learner does?** `ml/live_simulation.py`, with documented rules: the
chance to come back each day, what they do on a visit, whether they click an e-mail, whether they buy
(the same rules as the six-month history, so the live data continues it: 7.4 purchases a day expected
vs 7.2 in the history's last month). Every rule is in `HOW_IT_WORKS.md`, section 2b.

**What happens when the laptop is off?** Nothing, like a real website that is down: nobody can visit.
The learners are simulated in real time; nothing is caught up afterwards.

**Who calls the simulated learners?** A simulated advisor, 1–24 hours after the CRM creates the task
(their phone numbers are not real). It has its own daily capacity and it cannot close a real
person's task — only the team can (tested).

**What are MQL and SQL?** Standard CRM stage names (HubSpot, Salesforce). MQL = marketing-qualified
lead: showed interest (pricing, wishlist, chat), marketing keeps nurturing. SQL = sales-qualified
lead: ready to buy (enquiry, cart, checkout, asked for a call), sales should contact now. Nothing
to do with the SQL database language. The dashboard shows "Interested (MQL)" and "Ready to buy (SQL)".

**Why is the live model's starting point simulated?** No public lead dataset records video,
pricing, cart or checkout, and the score must react to them. The real X Education file is used to
check the method without leakage; the learning loop then corrects the model from the CRM's own
outcomes.

**Gmail does not allow tracking, does it?** Gmail allows links; e-mail tools (HubSpot, Mailchimp)
count clicks exactly this way. What Gmail hides is whether an e-mail was *opened*, so we do not use
opens. The links point to the laptop; with `PUBLIC_SITE_URL` set to the laptop's Wi-Fi address they
work from a phone too. E-mails to simulated learners are recorded but never delivered (reserved
`.test` domain).

**Why is "do nothing" sometimes the best step, even when a coupon has a higher chance?** Best means
most extra money, not highest chance. A 20% coupon given to someone who would buy anyway loses 20% of
the price; if it only adds 2 points of chance, it loses money.

**Why does the CRM pick 15% of steps at random?** To measure what each step really changes. Without
random choices the CRM only ever sees the effect of its own habits.

**Can the CRM phone people itself?** No CRM does without a paid phone service. Like Salesforce or
HubSpot, it decides who should be called and why, creates the task with a script, and the advisor
records the result, which the loop learns from.

**What if a new model is worse?** It does not go live: it must beat the current model on the
untouched control group in at least 90% of resamples, and the previous model file is kept.

**Why did the score not go up when I clicked the e-mail?** The loop learned that clicks are a weak
sign here (people who keep getting e-mails without buying collect clicks). We never let a click
*lower* a score; what the person does after coming back (pricing, cart) moves it.

**What is new compared with Salesforce Einstein or HubSpot?** Not the first to use control groups,
uplift models or champion/challenger. What we improve is the usual "retrain on who converted": our
retrain is told what the CRM did, and a new model goes live only if leads nobody contacted confirm
it. We measured the difference on real randomized data.

**Limitations?** The learners' reactions come from a documented simulator (a real pilot would plug
the same CRM into a real company's leads); the control group is small (5%), so the loop switches
models slowly; ours is still about 10–13% optimistic on the control group, because leads get more
follow-ups later in the 14 days. Next step: a real pilot and a larger control group.

## 6. The day before

1. `start-all.bat` (both tabs open by themselves). Keep `DEMO_MODE=true` in both `.env` files:
   follow-ups then come 1 minute after a learner leaves.
2. Let the servers run for a few hours (or overnight, with the laptop set to never sleep while
   plugged in): the Dashboard then shows a real day of live activity, and the learning loop gets new
   outcomes.
3. With the servers running:
   `user-backend\venv\Scripts\python.exe tests\e2e_test.py` → **45 of 45 checks passed**;
   `user-backend\venv\Scripts\python.exe tests\test_live_simulation.py` → **11 of 11** (uses a private copy);
   `user-backend\venv\Scripts\python.exe tests\test_v62_fixes.py` → **9 of 9**;
   `user-backend\venv\Scripts\python.exe tests\test_email_fallback.py` → **8 of 8**.
4. Do the steps once with a fresh e-mail address.
5. If Gmail fails on the day: sign-up still works in demo mode — the code appears in the
   user-backend window.

## If something goes wrong

* A page is empty: the backend window shows the error; `stop-all.bat`, then `start-all.bat`.
* No decision after a minute: press ⚡ Run automations now on the Dashboard. If the lead page says
  "control group", that learner is in the 5% the CRM never contacts — sign up another one.
* Simulated learners show "paused": press **Resume** on the Dashboard. "The website's API is not
  reachable yet": the user-backend is still starting; it retries every 10 seconds.
* No internet: e-mail text comes from templates; everything else runs on the laptop.
