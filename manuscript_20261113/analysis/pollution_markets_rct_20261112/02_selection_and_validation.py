"""Post-primary validation: arbitrary outcomes for all 24 excluded plants.
This sensitivity was added after primary estimates were inspected, prompted by
the published 342-to-318 sample flow. It is not a preregistered primary result.
Table A3 uses official arm counts. Original-vs-official reconciliation for the
excluded plants is unavailable, so evaluate ALL allocations of 24 plants.
"""
from pathlib import Path
import json
import pandas as pd
import numpy as np
from scipy import stats as st

p=Path(__file__).resolve().parent/'results'
d=pd.read_csv(p/'all_active_13_plant_outcomes.csv')
rows=[]
for y in ['observed','documented_below_1000']:
    t=d[d.Z.eq(1)][y];c=d[d.Z.eq(0)][y]
    # Bonferroni simultaneous nominal 95% coverage for 4 observed group means.
    qt=st.t.ppf(1-.05/8,len(t)-1);qc=st.t.ppf(1-.05/8,len(c)-1)
    tl=max(0,t.mean()-qt*t.std(ddof=1)/np.sqrt(len(t)))
    tu=min(1,t.mean()+qt*t.std(ddof=1)/np.sqrt(len(t)))
    cl=max(0,c.mean()-qc*c.std(ddof=1)/np.sqrt(len(c)))
    cu=min(1,c.mean()+qc*c.std(ddof=1)/np.sqrt(len(c)))
    for kt in range(25):
        kc=24-kt;nt=len(t)+kt;nc=len(c)+kc
        rows.append(dict(outcome=y,excluded_assigned_treatment=kt,excluded_assigned_control=kc,
                         lower=t.sum()/nt-(c.sum()+kc)/nc,
                         upper=(t.sum()+kt)/nt-c.sum()/nc,
                         outer95_lower=tl*len(t)/nt-(cu*len(c)+kc)/nc,
                         outer95_upper=(tu*len(t)+kt)/nt-cl*len(c)/nc))
r=pd.DataFrame(rows)
r.to_csv(p/'full342_binary_selection_sensitivity.csv',index=False)
s=r.groupby('outcome').agg(lower=('lower','min'),upper=('upper','max'),outer95_lower=('outer95_lower','min'),outer95_upper=('outer95_upper','max'))
s.to_csv(p/'full342_binary_selection_envelope.csv')

# Independent Frisch-Waugh-Lovell algebra, loading the saved CSV rather than
# reusing statsmodels objects. CSV serialization of Stata float32 nuisance
# covariates warrants a 1e-7 absolute check (far tighter than reporting precision).
cs=['ln_capex','D_ln_capex_missing','boi_year','D_boi_year_missing','bh_ope_cost','D_bh_ope_cost_missing','ln_plant_total_heatoutput']
A=d[cs];A=(A-A.mean())/A.std(ddof=0)
W=np.column_stack([np.ones(len(d)),A.values])
zr=d.Z.values-W@np.linalg.lstsq(W,d.Z.values,rcond=None)[0]
r=pd.read_csv(p/'evidence_outcome_estimates.csv');checks=[]
for y in ['observed','documented_below_1000']:
    yr=d[y].values-W@np.linalg.lstsq(W,d[y].values,rcond=None)[0]
    beta=zr@yr/(zr@zr)
    old=r[(r.scope=='all_active_13')&(r.assignment=='Z')&r.adjusted&(r.outcome==y)].coefficient.iloc[0]
    checks.append(dict(outcome=y,fwl_beta=beta,ols_beta=old,absolute_difference=abs(beta-old),tolerance=1e-7))
    assert abs(beta-old)<1e-7
(p/'independent_algebra_validation.json').write_text(json.dumps(checks,indent=2))
print(s)
print(checks)
