"""
Re-runs every experiment behind the paper's numbers and writes ml/results/*.md (fixed seeds).

    user-backend\\venv\\Scripts\\python.exe ml\\run_experiments.py          (about 10 minutes)
    user-backend\\venv\\Scripts\\python.exe ml\\run_experiments.py quick    (skips the slow robustness study)

  E1  model_benchmark.py    our modelling method on REAL data: boosting vs logistic, random forest, neural
                            networks (+ TabPFN when installed) on the 9,240 real leads, no leaked columns
  E2  hillstrom_uplift.py   next-best-action on a real randomized e-mail experiment (64,000 customers)
      nba_robustness.py     next-best-action when our assumptions about the world are wrong (simulation)
  E3  learning_loop.py      does naive retraining fool itself, and does ours avoid it? (real data)
  E4  ab_engine_check.py    are the A/B statistics trustworthy? (simulated tests with known truth)
  E5  paths_check.py        do the what-if paths predict what learners do next? (on the CRM's history)
The next-best-action policy comparison (profit per 1,000 leads) is written by ml/train_uplift.py.
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.join(HERE, "experiments")
QUICK = len(sys.argv) > 1 and sys.argv[1] == "quick"
STEPS = [("E1 lead scoring on real data", "model_benchmark.py"),
         ("E2 next-best-action on real data", "hillstrom_uplift.py"),
         ("E2b next-best-action robustness", "nba_robustness.py"),
         ("E3 learning loop on real data", "learning_loop.py"),
         ("E4 A/B engine", "ab_engine_check.py"),
         ("E5 what-if paths", "paths_check.py")]

os.environ.setdefault("OMP_NUM_THREADS", "1")
for title, script in STEPS:
    if QUICK and script == "nba_robustness.py":
        continue
    print(f"\n==== {title} ({script}) ====", flush=True)
    t0 = time.time()
    code = subprocess.call([sys.executable, os.path.join(EXP, script)], cwd=os.path.dirname(HERE))
    print(f"---- {'done' if code == 0 else f'FAILED (exit {code})'} in {time.time() - t0:.0f} s", flush=True)
print("\nResults: ml/results/*.md")
