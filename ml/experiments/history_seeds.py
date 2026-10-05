"""
history_seeds.py — re-creates ml/results/history_runs.md from scratch: six 180-day simulated
histories with different random seeds, each in its own temporary copy of the project (your own
database is never touched), then history_check.py over all six.

Run (servers may be running):  user-backend\\venv\\Scripts\\python.exe ml\\experiments\\history_seeds.py
About 5-10 minutes per history. Optional: --seeds 2026 11 12   --keep (keep the copies)
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
SKIP = shutil.ignore_patterns("venv", ".venv", "node_modules", "dist", ".git", "__pycache__", "*.db", "*.db-wal",
                              "*.db-shm", "*.db-journal", "*.previous.pkl")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[2026, 11, 12, 13, 14, 15])
    ap.add_argument("--keep", action="store_true", help="keep the temporary project copies")
    args = ap.parse_args()
    for name in ("lead_model.starter.pkl", "nba_model.starter.pkl"):
        if not os.path.exists(os.path.join(ROOT, "user-backend", "ml_models", name)):
            raise SystemExit(f"user-backend/ml_models/{name} not found — run start-all.bat (or ml/first_run.py) once first.")
    work = tempfile.mkdtemp(prefix="xedu_histories_")
    folders = []
    env = dict(os.environ, PYTHONUTF8="1", OMP_NUM_THREADS="1")
    try:
        for s in args.seeds:
            d = os.path.join(work, f"seed{s}")
            shutil.copytree(ROOT, d, ignore=SKIP)
            t0 = time.time()
            print(f"history with seed {s} ...", flush=True)
            subprocess.run([sys.executable, os.path.join(d, "ml", "generate_history.py"), "--n", "2000", "--seed", str(s)],
                           cwd=d, env=env, check=True, stdout=subprocess.DEVNULL)
            print(f"  done ({(time.time() - t0) / 60:.1f} min)", flush=True)
            folders.append(d)
        subprocess.run([sys.executable, os.path.join(HERE, "history_check.py"), *folders], cwd=ROOT, env=env, check=True)
    finally:
        if args.keep:
            print(f"Copies kept in {work}")
        else:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
