# Datasets used by the experiments

| File | What it is | Used by |
|---|---|---|
| `Leads.csv` | **X Education Lead Scoring dataset** (Kaggle): 9,240 real leads of an online-education company, 37 columns, `Converted` = became a customer (38.5 %). | `ml/experiments/real_benchmark.py` |
| `Leads_Data_Dictionary.xlsx` | Column descriptions for `Leads.csv`. | reference |
| `hillstrom.csv` | **Kevin Hillstrom – MineThatData E-Mail Analytics and Data Mining Challenge (2008)**: 64,000 customers randomly assigned to a Mens e-mail, a Womens e-mail or no e-mail (one third each); outcomes `visit`, `conversion`, `spend` in the next two weeks. The standard public benchmark for uplift modelling. | `ml/experiments/hillstrom_uplift.py` |

Both are public datasets, kept here so every result in `ml/results/` can be reproduced
with `run-experiments.bat`. If this repository is made public, check the licence terms
on the original download pages first.

The product's own models are **not** trained on these files: the website tracks
different signals, so `ml/generate_dataset.py` generates training data that matches
what the site records (see `ML_PIPELINE.md`).
