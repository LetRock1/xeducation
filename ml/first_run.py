"""
first_run.py — what start-all.bat runs before it starts the servers. Only does what is missing:

  1. the base lead model        (trained on 60,000 simulated leads with every signal the website
                                 records) — also re-trained when the saved one is from an older version
  2. the next-best-action model (trained on a simulated randomized campaign)
  3. the starting history       (6 simulated months of learners, marked "simulated"), when the
                                 database has none yet and crm_settings.json says so
                                 (starting_history.create_on_first_start)

Everything later (re-scoring, decisions, learning) runs by itself inside the servers.
To delete the simulated history:  python ml/generate_history.py --remove
"""
import os
import sqlite3
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BACKEND = os.path.join(ROOT, "user-backend")
sys.path.insert(0, BACKEND)

import settings  # noqa: E402

MODELS = os.path.join(BACKEND, "ml_models")
LEAD = os.path.join(MODELS, "lead_model.pkl")
NBA = os.path.join(MODELS, "nba_model.pkl")
DB = os.path.join(BACKEND, "xeducation_user.db")


def step(title):
    print(f"\n==== {title} ====", flush=True)


def run(script, *args):
    t0 = time.time()
    code = subprocess.call([sys.executable, os.path.join(HERE, script), *args], cwd=ROOT)
    print(f"  ({time.time() - t0:.0f} s)", flush=True)
    return code


def lead_model_ok():
    if not os.path.exists(LEAD):
        return False, "not found"
    try:
        import joblib
        import ml_features as F
        b = joblib.load(LEAD)
    except Exception as e:                        # unreadable / other scikit-learn version
        return False, f"cannot be loaded ({e.__class__.__name__})"
    if "starter" not in b:
        return False, "is from an older version"
    if b.get("feature_version") != F.FEATURE_VERSION:
        return False, "was built for other features"
    return True, b.get("version")


def simulated_learners():
    """(simulated learners, simulated learning runs) in the database."""
    if not os.path.exists(DB):
        return 0, 0
    con = sqlite3.connect(DB)
    try:
        learners = con.execute("SELECT COUNT(*) FROM users WHERE email LIKE '%@demo.xeducation.test'").fetchone()[0]
        try:
            runs = con.execute("SELECT COUNT(*) FROM learning_runs WHERE simulated=1").fetchone()[0]
        except sqlite3.Error:                     # database from before v6
            runs = 0
        return learners, runs
    except sqlite3.Error:
        return 0, 0
    finally:
        con.close()


def main():
    os.makedirs(MODELS, exist_ok=True)
    retrained = False
    ok, why = lead_model_ok()
    if not ok:
        step(f"Training the lead-scoring model (model {why}; about 1 minute)")
        if run("train_model.py") != 0:
            print("[WARN] Lead model training failed - the backend will use fallback scoring.")
        retrained = True
    if retrained or not os.path.exists(NBA):
        step("Training the next-best-action model (about 20 s)")
        if run("train_uplift.py") != 0:
            print("[WARN] Next-best-action training failed - the backend will use its built-in prior.")
    conf = settings.S.get("starting_history") or {}
    learners, runs = simulated_learners()
    if learners and (not runs or retrained):      # demo history from an older version, or made with the old model
        step("Removing the old simulated history (it was made with an older version; real data is kept)")
        run("generate_history.py", "--remove")
        learners = 0
    if conf.get("create_on_first_start", True) and learners == 0:
        n, days = int(conf.get("learners", 2000)), int(conf.get("days", 180))
        step(f"Creating the starting history: {n:,} simulated learners over {days} days "
             f"(first start only, about 10 minutes)")
        if run("generate_history.py", "--n", str(n), "--days", str(days)) != 0:
            print("[WARN] The starting history could not be created - the dashboards will be empty until "
                  "real activity arrives.")
    print("\nModels and data are ready.", flush=True)


if __name__ == "__main__":
    main()
