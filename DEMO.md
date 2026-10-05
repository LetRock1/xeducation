# Viva demo (about 15 minutes) and the hard questions

## The day before
1. Run `start-all.bat` once (the first start takes 5–10 minutes). On the day it starts in seconds;
   both browser tabs open by themselves: website (5173) and dashboard (5174).
2. With the servers running: `user-backend\venv\Scripts\python.exe tests\e2e_test.py` must end
   with **"36 of 36 checks passed"**. If anything fails, you know before the examiners do.
3. Have ready: a second e-mail address for the live sign-up (or read the 6-digit code from the
   `[EMAIL MOCK]` line in the user-backend window) and the test card `4242 4242 4242 4242`.
4. Keep `DEMO_MODE=true` in both `.env` files (the default): follow-ups then fire 1 minute after a
   learner leaves instead of 15–60 minutes, and the learning loop checks every 5 minutes.

## 1. The problem in one minute
> "Every CRM retrains its lead score on who bought. But the CRM's own calls, e-mails and coupons
> made many of those people buy, so the retrained model counts its own follow-ups as lead
> quality — and the usual accuracy check rewards that mistake. On a real experiment with 64,000
> customers, a normal retrain overstated targeted customers by 40%, and the usual check still
> picked it in 20 of 20 runs. Our CRM is told what it did, removes that from the score, and only
> accepts a new model if the 5% of leads it never contacts confirm it."

## 2. The loop, live (6 minutes)
1. **Website**: sign up, enter the code, complete the profile, open a course, play the overview
   video, keep the pricing section in view for a few seconds, add to cart, open checkout, leave.
2. **Dashboard → Leads**: the learner is already there with a live score. Open them:
   * **Why this score?** — each reason in points, computed by the model.
   * **What-if paths** — e.g. "send an information e-mail; if there is no response, send the 10%
     coupon"; click another first step to compare. It shows the chance to buy and the extra profit
     of each plan, and the flow graph of the learner's likely reactions.
3. **Run automations now** (top right of the Dashboard, after about a minute): the checkout trigger
   fires and the lead page shows the **recommended action**: every option compared by chance to buy
   and extra profit, and why blocked options were blocked (consent, call capacity).
4. **Today's actions**: the call and WhatsApp tasks the engine created, best first, with a script.
   (A call is only possible if the learner gave a phone number and allows calls — enter one in the
   learner's Settings before the demo if you want to show a call.) **Pipeline**: the learner sits in
   *SQL* (they reached checkout); drag the card to *MQL* — the board remembers the team's choice and
   still shows what the CRM thinks ("auto: SQL").
5. Back on the website, pay with the test card: the Pipeline moves them to *Customer* by itself.

## 3. Learning that does not fool itself (4 minutes) — Learning loop page
Read the numbers off the page (they come from the history on your machine); the pattern is the
same in every history we ran (`ml/results/history_runs.md`).
* **Three boxes:** what a normal (naive) retrain expects of the untouched control group, what ours
  expects, what they actually bought. The naive one is further from the truth.
* Under them: "picking the model that fits live data best would have chosen the naive one" — the
  usual check is fooled, ours is not.
* **Runs table:** a new model replaces the old one only when it is better on the control group in
  at least 90% of resamples; otherwise "kept", so the CRM does not change its mind on noise.
* **The CRM's total impact:** leads it worked on vs the control group.
* Press **Dry run** to show a learning run live (it changes nothing).

## 4. Experiments (2 minutes) — A/B tests page
* Open **Subject line: benefit vs urgency**: verdict with a 95% interval, the 14-day curve, the
  split check and segments.
* **Adopted winners**: the CRM made the winning e-mail its standard e-mail by itself; 10% still get
  the old one, so it keeps checking and switches back if the winner stops winning ("collecting
  evidence" until enough people have received it).
* **Webinar invite vs brochure**: two e-mails with no real difference — the engine finds no winner.
* Start a new test: the page says how many people you need **before** you send.

## 5. Ask the CRM (1 minute)
Ask "Who should we call today?", "Is the learning loop fooling itself?", "Tell me about <the
learner's name>", "Draft an A/B test for a better subject line". Every answer shows which live data
it read ("How I got this"); drafts open in the right page for a person to review — it never sends.

## 6. Evidence (1 minute)
`ml/results/`: `learning_loop.md` (real data, 20 repeats) · `history_runs.md` (six simulated
histories checked against the known truth) · `model_benchmark.md` (no leakage) ·
`nba_policy_comparison.md`, `nba_robustness.md`, `hillstrom_uplift.md` (next-best-action) ·
`ab_engine_check.md` (A/B statistics) · `paths_check.md` (what-if paths).

## If something goes wrong
* A page is empty: the backend window shows the error; `stop-all.bat`, then `start-all.bat`.
* No decision after "Run automations now": wait a minute and press it again; or the learner is in
  the 5% control group (the lead page says so) — sign up another learner.
* No internet: e-mail text falls back to templates; everything else works offline.

## The hard questions

**Is your data real?** The software, website, tracking, decisions and learning are real and run
live. The main evidence for the learning loop is a real randomized experiment (Hillstrom, 64,000
customers). The base lead model is trained on simulated leads, and the six-month demo history is
simulated and marked as such, because X Education's own CRM history is not public.

**Why train the score on simulated data instead of the real 9,240 leads?** The score has to react to
video, pricing, cart and checkout, and the real file records none of them — it has only 9 columns a
new lead has, plus columns sales fills in after contact. So the real file is used to check the
modelling method without leakage (AUC 0.874), and the learning loop corrects the base model from the
CRM's own outcomes. Applied to the real file as it is, our base model gets only 0.612 — we say so in
`model_benchmark.md`.

**A Kaggle notebook gets AUC 0.88 / 80% accuracy with plain logistic regression. Why not you?** It
keeps "Last Activity" (SMS Sent, Unreachable, Had a Phone Conversation …), which is recorded while
sales works the lead. A new lead never has it. Without such columns the best we reach is 0.874; with
all post-contact columns the same data reaches 0.98, which is the leakage, not skill.
`tests/test_no_leakage.py` fails if we ever use them.

**Why not deep learning?** We tested it: neural networks 0.867–0.868 against 0.874 for gradient
boosting, with less reliable probabilities. On small tables boosting is still the standard. We use
AI where the data is language: e-mails, WhatsApp messages, call scripts and Ask the CRM's wording.

**What is new compared with Salesforce or HubSpot? Is it the first?** Not the first: control groups,
champion/challenger switching and uplift models exist (Braze, Pega), and research calls the problem
"performative prediction". CRMs that keep lead scores fresh retrain on "who converted"; we improve
that practice: the retrain is told what the CRM did, and a new model goes live only if leads the CRM
never touched confirm it. We measured the difference on real randomized data: a normal retrain
overstated buyers by 40% and its own check still preferred it 20 times out of 20.

**How do you know a new model is better?** It must predict the untouched control group better in at
least 90% of bootstrap resamples; otherwise the old one stays, and the old file is kept.

**Then why did the loop keep the starting model in three of your six histories?** Because after six
months only about 80 people were in the control group, and the evidence did not reach 90%. That is
the safe side of a setting; a bigger control group or a lower bar switches sooner, at a cost.

**Is your model perfect?** No. On the control group ours is still about 13% too optimistic, because
the score means "if we do nothing now" while most leads get more follow-ups later in the 14 days and
the control group never does. Marking website actions that happen *after* a CRM action (cart after a
coupon) as caused by the CRM is the next step.

**Are next-best-action and the what-if paths new?** Not as research: choosing steps by their extra
effect (uplift) is known, and the what-if paths are a planning aid (calibrated overall, 38.7%
predicted vs 39.2% actual, but they predict the next reaction only a little better than a per-stage
average). The research contribution is the learning loop.

**Your A/B engine missed 14 real effects. Is it weak?** Those tests had fewer people than the plan
said were needed — the page warns before sending. It never declared a false winner or loser in 36
verdicts, and A/A tests raise a false alarm 3.7% of the time (should be at most 5%).

**Does choosing 15% at random lose money?** A little, on purpose: it is how the CRM measures what each
step really does. The share is a setting; large platforms do the same (exploration).

**Does Ask the CRM make things up?** It answers only from live data and shows what it read. With
Gemini switched on, any wording whose numbers differ from the data is rejected. Its drafts are never
sent by it.

**What if there is no internet in the viva room?** Everything runs locally. Without Gemini, e-mails
and answers come from templates (it also stops trying for 5 minutes after a network error).
