# The two real datasets

| File | What it is | Used by |
|---|---|---|
| `Leads.csv` | **X Education Lead Scoring dataset** (Kaggle): 9,240 real leads of an online-education company, 37 columns, `Converted` = became a customer (38.5%). | checking the lead-scoring method on real data without leakage — E1 (`ml/experiments/model_benchmark.py`, only the 9 columns known before any contact) and `tests/test_no_leakage.py`. It does not train the CRM's own model: it has none of the website signals (video, pricing, cart, checkout …) the CRM scores on. |
| `Leads_Data_Dictionary.xlsx` | Column descriptions for `Leads.csv`. | reference |
| `hillstrom.csv` | **Kevin Hillstrom, MineThatData E-Mail Analytics and Data Mining Challenge (2008)**: 64,000 customers randomly assigned to a men's e-mail, a women's e-mail or no e-mail (one third each); outcomes `visit`, `conversion`, `spend` in the next two weeks. The standard public benchmark for uplift modelling. | E2 (`ml/experiments/hillstrom_uplift.py`), E3 (`ml/experiments/learning_loop.py`) |

Columns of `Leads.csv` that sales fills in after contacting a lead (Tags, Lead Quality, Lead
Profile, Last Activity, Last Notable Activity, the Asymmetrique scores, ...) leak the outcome and
are never used; `tests/test_no_leakage.py` fails if one is.

Both are public datasets, kept here so every result in `ml/results/` can be reproduced with
`python ml/run_experiments.py`. If this repository is made public, check the licence terms on the
original download pages first.

Simulated data is generated, never stored here: `ml/generate_dataset.py` (60,000 simulated leads
for the base lead model, written to `ml/lead_data_v4.csv` on the first start, and the simulated
randomized campaign that gives next-best-action its starting knowledge) and
`ml/generate_history.py` (the six-month starting history, marked "simulated").
