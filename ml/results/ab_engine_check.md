# A/B engine check (simulated tests with known truth)

4,000 simulated tests per row, seed 2026.

| Check | Result | Should be |
|---|---|---|
| A/A tests (no real difference, 2 variants + control): engine declares a difference | 3.7% | at most 5% |
| 95% interval contains the true lift (+3 pts on 10%) | 95.2% | about 95% |
| Real +5 pt lift found with the planned 686 people per arm | 79.8% | about 80% |
| Split check false alarms (hash split, 3,000 people) | 0.0% | about 0.1% |
| Split check catches 10% of the control group lost (60 of 600 people) | 7.6% | low at this size: the check is strict (p < 0.001) |
| Split check catches 30% of the control group lost | 100.0% | high |

## End to end (analyse() on 4,000 simulated people, true lift of B = +6 pts)

- Day 5: **running** — Collecting outcomes — day 5 of 14
- Day 15: **winner** — Variant B wins: +6.2 pts purchases vs sending nothing. 95% interval +3.2 pts to +8.9 pts, adjusted p = 0.0000.

| Arm | People | Bought | Rate |
|---|---|---|---|
| control | 767 | 57 | 7.4% |
| A | 1624 | 137 | 8.4% |
| B | 1609 | 219 | 13.6% |

## Adopted winners: the 10% check group (adoption.evaluate(), 200 simulated adoptions per row)

The old e-mail sells to 10% of people; the adopted one truly sells 4 points more, the same, or 4 points less. The check confirms (95% interval above zero), switches back (interval below zero) or keeps checking.

| People who got the e-mail since adoption | Truth | Confirmed | Still checking | Switched back |
|---|---|---|---|---|
| 400 | adopted e-mail better | 6% | 94% | 0% |
| 400 | adopted e-mail no difference | 3% | 92% | 5% |
| 400 | adopted e-mail worse | 0% | 78% | 22% |
| 1,500 | adopted e-mail better | 26% | 74% | 0% |
| 1,500 | adopted e-mail no difference | 2% | 91% | 7% |
| 1,500 | adopted e-mail worse | 0% | 64% | 36% |
| 5,000 | adopted e-mail better | 72% | 28% | 0% |
| 5,000 | adopted e-mail no difference | 2% | 94% | 3% |
| 5,000 | adopted e-mail worse | 0% | 8% | 92% |

With no real difference it should confirm or switch back about 2.5% of the time each (200 runs per row is noisy; the same statistics from counts, 20,000 runs each: wrongly confirmed 1.2%, 1.8%, 2.0%; wrongly switched back 3.5%, 3.1%, 2.5% for 400, 1,500, 5,000 people). A real 4-point difference needs a few thousand people before the 10% check group can show it; until then the dashboard says "collecting evidence".
