"""Run the public-data analyses in their documented dependency order."""
from pathlib import Path
import argparse
import os
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
STEPS = [
    ('manuscript_20261113/analysis/pollution_markets_rct_20261112/01_analyze.py',),
    ('manuscript_20261113/analysis/pollution_markets_rct_20261112/02_selection_and_validation.py',),
    ('manuscript_20261113/03_measurement_audit.py',),
    ('crosscountry_20261113/causal/04_estimate_national.py',),
    ('crosscountry_20261113/causal/06_final_checks.py',),
    ('crosscountry_20261113/causal/07_overlap_check.py',),
    ('crosscountry_20261113/causal/08_referee_audit.py',),
    ('crosscountry_20261113/causal/09_timing_content_audit.py', '--timing'),
    ('crosscountry_20261113/causal/10_semantic_results.py',),
    ('crosscountry_20261113/causal/05_figures.py',),
    ('make_figures.py',),
    ('verify_results.py',),
]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--figures-only', action='store_true', help='Rebuild figures from the archived numerical results.')
args = parser.parse_args()
env = os.environ.copy()
env['OPENBLAS_NUM_THREADS'] = '1'
env['OMP_NUM_THREADS'] = '1'
logs = ROOT / 'run_logs'
logs.mkdir(exist_ok=True)
steps = STEPS[-3:] if args.figures_only else STEPS
start = time.time()
for index, step in enumerate(steps, 1):
    print(f'[{index}/{len(steps)}] {step[0]}', flush=True)
    with (logs / (Path(step[0]).stem + '.log')).open('w') as log:
        result = subprocess.run([sys.executable, str(ROOT / step[0]), *step[1:]], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        raise SystemExit(f'Failed: {step[0]}. See run_logs/{Path(step[0]).stem}.log')
print(f'Completed successfully in {time.time()-start:.1f} seconds.', flush=True)
