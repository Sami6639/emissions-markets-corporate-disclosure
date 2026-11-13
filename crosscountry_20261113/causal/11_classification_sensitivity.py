"""Exact fixed-design point-estimate bounds under binary outcome recoding.

This post-primary sensitivity is not an estimated error rate, a confidence
interval, a human-validation result, or a correction to the observed outcomes.
Sample, treatment, fixed effects and all 480 original rows remain fixed.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from scipy.optimize import linprog

P=Path(__file__).resolve().parent
O=P/'results'
d=pd.read_csv(O/'primary_estimation_panel.csv',dtype={'code':str,'firm':str})
assert len(d)==480 and not d[['code','year']].duplicated().any()
y=d.mention.to_numpy(float)
assert set(y)=={0.,1.}
X=np.column_stack([d.did.to_numpy(float),*[pd.get_dummies(d[c],dtype=float).to_numpy() for c in ['firm','sector_year','province_year']]])
pinv=np.linalg.pinv(X,rcond=1e-10)
w=pinv[0]
beta=float(w@y)
primary=pd.read_csv(O/'national_ets_estimates.csv').query("model == 'Primary' and term == 'did'").iloc[0]
assert abs(beta-primary.beta)<1e-10
saved=pd.read_csv(O/'treatment_effect_weights.csv',dtype={'code':str})
assert d[['code','year']].equals(saved[['code','year']])
assert np.max(np.abs(w-saved.ols_outcome_weight.to_numpy()))<1e-9
change=w*(1.-2.*y)
down=np.flatnonzero(change < -1e-12)
up=np.flatnonzero(change > 1e-12)
down=down[np.argsort(change[down],kind='stable')]
up=up[np.argsort(-change[up],kind='stable')]
lo=np.r_[beta,beta+np.cumsum(change[down])]
cross=np.flatnonzero(lo<=0.)
assert len(cross)
k_star=int(cross[0])
rows=[];patterns=[];max_lp_error=0.;max_refit_error=0.
for k in [0,1,2,5,10,24,25,48]:
    lower=float(beta+change[down[:k]].sum())
    upper=float(beta+change[up[:k]].sum())
    # Independent linear-program solutions verify both cardinality-constrained extrema.
    for sign,expected in [(1.,lower),(-1.,upper)]:
        lp=linprog(sign*change,A_ub=np.ones((1,len(y))),b_ub=[k],bounds=(0,1),method='highs')
        assert lp.success,lp.message
        error=abs(beta+sign*lp.fun-expected)
        max_lp_error=max(max_lp_error,error)
        assert error<1e-9
    for name,indices,expected in [('lower',down[:k],lower),('upper',up[:k],upper)]:
        yy=y.copy();yy[indices]=1.-yy[indices]
        refit=float(np.linalg.lstsq(X,yy,rcond=1e-10)[0][0])
        max_refit_error=max(max_refit_error,abs(refit-expected))
        assert abs(refit-expected)<1e-9
        for i in indices:
            patterns.append({'error_budget':k,'endpoint':name,'code':d.iloc[i].code,'year':int(d.iloc[i].year),'observed':int(y[i]),'hypothetical':int(yy[i]),'coefficient_change':float(change[i])})
    rows.append({'max_recoded_reports':k,'share_of_480_percent':100*k/len(y),'lower_coefficient':lower,'upper_coefficient':upper,'lower_pp':100*lower,'upper_pp':100*upper})
pd.DataFrame(rows).to_csv(O/'classification_error_bounds.csv',index=False)
pd.DataFrame(patterns).to_csv(O/'classification_error_extreme_patterns.csv',index=False)
details=d[['code','year','province','treated','post']].copy()
details['observed_content']=y.astype(int);details['outcome_weight']=w;details['flip_change']=change
details.to_csv(O/'classification_error_weights.csv',index=False)
summary={
 'status':'Post-primary fixed-design sensitivity; no outcome recoding applied to the main analysis',
 'unit':'firm-year annual report', 'n':len(y),'firms':int(d.code.nunique()),
 'observed_positive':int(y.sum()),'baseline_beta':beta,
 'smallest_budget_allowing_nonpositive_coefficient':k_star,
 'threshold_share_percent':100*k_star/len(y),
 'lower_at_previous_budget':float(lo[k_star-1]),'lower_at_threshold':float(lo[k_star]),
 'scope':'At most k arbitrary binary-outcome flips over all 480 rows; treatment and full design fixed',
 'interpretation':'Exact deterministic coefficient envelopes, not confidence intervals or estimated misclassification rates',
 'validation':{'max_linear_program_error':max_lp_error,'max_full_dummy_OLS_refit_error':max_refit_error,'max_weight_difference_from_absorbed_regression':float(np.max(np.abs(w-saved.ols_outcome_weight.to_numpy())))},
 'formula':'beta=sum(w_i*y_i); delta_i=w_i*(1-2*y_i). Lower/upper add at most k negative/positive deltas in most adverse order.'
}
(O/'classification_error_summary.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2))
print(pd.DataFrame(rows).to_string(index=False))
