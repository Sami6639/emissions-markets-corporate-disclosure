"""Check the main reported effects and sample definitions against frozen values."""
from pathlib import Path
import json
import math
import pandas as pd

ROOT = Path(__file__).resolve().parent
I = ROOT / 'manuscript_20261113/analysis/pollution_markets_rct_20261112/results'
A = ROOT / 'manuscript_20261113/audit_results'
C = ROOT / 'crosscountry_20261113/causal/results'

def close(actual, expected, label):
    assert math.isclose(float(actual), expected, rel_tol=1e-6, abs_tol=1e-8), (label, actual, expected)

india = pd.read_csv(I / 'evidence_outcome_estimates.csv')
row = india.query("scope == 'all_active_13' and assignment == 'Z' and adjusted == True and outcome == 'observed'").iloc[0]
close(row.coefficient, 0.2251631502365513, 'India monthly availability')
assert row.n == 318
monitor = pd.read_csv(A / 'measurement_sensitivity.csv')
row2 = monitor.query("scope == 'all_13' and model == 'additive' and outcome == 'valid_hours_share'").iloc[0]
close(row2.coefficient, 0.24432265766826688, 'India calibrated monitoring hours')
china = pd.read_csv(C / 'national_ets_estimates.csv')
row3 = china.query("model == 'Primary' and term == 'did'").iloc[0]
close(row3.beta, 0.607995277288626, 'China main coefficient')
close(row3.lo, 0.26269720236491617, 'China lower confidence bound')
close(row3.hi, 0.9532933522123359, 'China upper confidence bound')
assert (row3.n, row3.firms, row3.clusters) == (480, 80, 13)
panel = pd.read_csv(C / 'primary_estimation_panel.csv', dtype={'code': str})
assert not panel.duplicated(['code', 'year']).any()
assert panel.loc[panel.treated.eq(1), 'code'].nunique() == 22
assert panel.loc[panel.treated.eq(0), 'code'].nunique() == 58
assert set(panel.year) == {2017, 2018, 2019, 2021, 2022, 2023}
audit = json.loads((C / 'semantic_audit_summary.json').read_text())
assert audit['n_reports'] == 46 and audit['unresolved'] == 0
assert audit['category_counts'] == {'0': 24, 'Q': 10, 'F': 7, 'G': 5}
sensitivity = json.loads((C / 'classification_error_summary.json').read_text())
assert sensitivity['smallest_budget_allowing_nonpositive_coefficient'] == 25
assert sensitivity['lower_at_previous_budget'] > 0 > sensitivity['lower_at_threshold']
close(sensitivity['baseline_beta'], row3.beta, 'Classification sensitivity baseline')
bounds = pd.read_csv(C / 'classification_error_bounds.csv')
five = bounds.query('max_recoded_reports == 5').iloc[0]
close(five.lower_pp, 47.50076890386898, 'Five-recoding lower endpoint')
close(five.upper_pp, 73.3165628658379, 'Five-recoding upper endpoint')
assert all(v < 1e-9 for v in sensitivity['validation'].values())
print('Verified: Indian effects, Chinese coefficient and interval, 80-firm panel, semantic audit and classification sensitivity.')
