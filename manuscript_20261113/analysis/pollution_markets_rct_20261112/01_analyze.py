"""Secondary analysis of Greenstone et al. (2025), not a new experiment.
Keep all 318 eligible plants in evidence-outcome denominators.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import scipy.stats as st
import statsmodels.api as sm
import statsmodels.formula.api as smf
from statsmodels.stats.multitest import multipletests

R=Path(__file__).resolve().parent;O=R/'results'
b=pd.read_stata(R/'raw/BaselineCovariates.dta',convert_categoricals=False)
m=pd.read_stata(R/'raw/Master ETS In-sample - Plants (318i).dta',convert_categoricals=False)
raw=pd.read_stata(R/'raw/Rule0_Panel.dta',convert_categoricals=False)
covs=['ln_capex','D_ln_capex_missing','boi_year','D_boi_year_missing','bh_ope_cost','D_bh_ope_cost_missing','ln_plant_total_heatoutput']
assert len(b)==len(m)==318 and not b.gpcb_id.duplicated().any()
assert not raw.duplicated(['gpcb_id','month16']).any()
assert b[covs].notna().all().all()
b['Z']=(b.orig_assignment_gargee=='Treatment').astype(int)
assert b.Z.sum()==160 and b.D_treatment.sum()==162
active=raw.D_interregnum.eq(0)&(raw.post_mock1.eq(1)|raw.post_mock2.eq(1))
times=raw.loc[active,['month16','Mock1','Mock2']].drop_duplicates()
assert len(times)==13
panel=b.merge(times,how='cross').merge(raw[['gpcb_id','month16','Y_rule0','Y_rule1']],on=['gpcb_id','month16'],how='left',validate='one_to_one')
panel['observed']=panel.Y_rule0.notna().astype(int)
for q in [500,1000,2000]:
    panel[f'documented_below_{q}']=(panel.Y_rule0.notna() & panel.Y_rule0.le(q)).astype(int)
panel['missing']=1-panel.observed
panel.to_parquet(O/'all318_monthly_evidence_panel.parquet',index=False)

def estimate(a,y,z='Z',adjust=True):
    cs=covs if adjust else []
    X=sm.add_constant(a[[z]+cs].astype(float),has_constant='add')
    # Center and scale nuisance covariates for numerical conditioning.
    # This leaves treatment coefficients and fitted values unchanged.
    for c in cs:
        X[c]=(X[c]-X[c].mean())/X[c].std(ddof=0)
    fit=sm.OLS(a[y].astype(float),X).fit(cov_type='HC2',use_t=True)
    lo,hi=fit.conf_int().loc[z]
    return dict(coefficient=fit.params[z],se=fit.bse[z],p=fit.pvalues[z],lo=lo,hi=hi,n=int(fit.nobs),treated_mean=a.loc[a[z].eq(1),y].mean(),control_mean=a.loc[a[z].eq(0),y].mean())

ys=['observed','documented_below_1000','documented_below_500','documented_below_2000']
scopes={'all_active_13':panel,'real_only_10':panel[panel.Mock1.eq(0)&panel.Mock2.eq(0)],'restart_real_4':panel[panel.month16>=pd.Timestamp('2020-12-16')]}
rows=[];boundrows=[];summ=[]
for scope,a in scopes.items():
    f=a.groupby('gpcb_id')[ys+['missing']].mean().reset_index().merge(b[['gpcb_id','Z','D_treatment']+covs],validate='one_to_one')
    assert len(f)==318
    f.to_csv(O/(scope+'_plant_outcomes.csv'),index=False)
    for z in ['Z','D_treatment']:
        for adj in [True,False]:
            for y in ys:
                rows.append(dict(scope=scope,assignment=z,adjusted=adj,outcome=y,**estimate(f,y,z,adj)))
        for q in [500,1000,2000]:
            y='documented_below_'+str(q)
            tr=f[f[z].eq(1)];co=f[f[z].eq(0)]
            # Per-plant missing-outcome support bounds, not imputations.
            L=tr[y].mean()-(co[y]+co['missing']).mean()
            U=(tr[y]+tr['missing']).mean()-co[y].mean()
            def diff_se(x,v):
                a1=x.var(ddof=1)/len(x);a0=v.var(ddof=1)/len(v)
                df=(a1+a0)**2/(a1*a1/(len(x)-1)+a0*a0/(len(v)-1))
                return np.sqrt(a1+a0),df
            sl,dfl=diff_se(tr[y],co[y]+co['missing']);su,dfu=diff_se(tr[y]+tr['missing'],co[y])
            boundrows.append(dict(scope=scope,assignment=z,threshold_kg=q,lower=L,upper=U,outer95_lower=L-st.t.ppf(.975,dfl)*sl,outer95_upper=U+st.t.ppf(.975,dfu)*su,meaning='Worst-case monthly-missingness bounds conditional on authors Rule0 measurement construction and eligible318 frame'))
    summ.append(dict(scope=scope,months=a.month16.nunique(),plants=a.gpcb_id.nunique(),rows=len(a),observed_months=int(a.observed.sum())))

r=pd.DataFrame(rows)
mask=r.scope.eq('all_active_13')&r.assignment.eq('Z')&r.adjusted&r.outcome.isin(ys[:2])
r.loc[mask,'holm_coprimary_p']=multipletests(r.loc[mask,'p'],method='holm')[1]
r.to_csv(O/'evidence_outcome_estimates.csv',index=False)
pd.DataFrame(boundrows).to_csv(O/'missing_outcome_probability_bounds.csv',index=False)
pd.DataFrame(summ).to_csv(O/'sample_coverage.csv',index=False)

# Direct reproduction of original Table III (columns 2, 6, 8).
reps=[]
for rule,target in [('0',-.193),('A',-.282),('B',-.316)]:
    a=pd.read_stata(R/f'raw/Rule{rule}_Panel.dta',convert_categoricals=False)
    a=a[a.D_interregnum.eq(0)&(a.post_mock1.eq(1)|a.post_mock2.eq(1))].dropna(subset=['lnY_rule0']+covs).copy()
    a['date_code']=a.month16.dt.strftime('%Y-%m')
    f=smf.ols('lnY_rule0 ~ D_treatment + '+' + '.join(covs)+' + C(date_code)',a).fit(cov_type='cluster',cov_kwds={'groups':a.gpcb_id},use_t=True)
    lo,hi=f.conf_int().loc['D_treatment'];beta=f.params['D_treatment']
    reps.append(dict(rule=rule,coefficient=beta,se=f.bse['D_treatment'],p=f.pvalues['D_treatment'],lo=lo,hi=hi,percent=100*np.expm1(beta),percent_lo=100*np.expm1(lo),percent_hi=100*np.expm1(hi),n=int(f.nobs),plants=a.gpcb_id.nunique(),published_rounded=target,rounding_match=abs(beta-target)<.0006,attribution='Replication of Greenstone et al.2025, NOT new finding'))
pd.DataFrame(reps).to_csv(O/'published_result_replication.csv',index=False)
assert all(x['rounding_match'] for x in reps)

# Inference stability: leave one plant out, primary outcomes, original assignment.
f=pd.read_csv(O/'all_active_13_plant_outcomes.csv')
loo=[]
for id in f.gpcb_id:
    a=f[f.gpcb_id.ne(id)]
    for y in ys[:2]:
        z=estimate(a,y)
        loo.append(dict(omitted_plant=int(id),outcome=y,coefficient=z['coefficient'],p=z['p']))
pd.DataFrame(loo).to_csv(O/'leave_one_plant_out.csv',index=False)

v={'source':'Greenstone et al.(2025), Harvard Dataverse DOI10.7910/DVN/PDFDKR v1.2','original_experiment':False,'eligible_plants':318,'original_assignment_counts':{str(k):int(v) for k,v in b.Z.value_counts().items()},'official_assignment_counts':{str(k):int(v) for k,v in b.D_treatment.value_counts().items()},'assignment_discrepancies':int(b.Z.ne(b.D_treatment).sum()),'never_in_monthly_panel':int((~b.gpcb_id.isin(raw.gpcb_id)).sum()),'unrecorded_firm_months_not_dropped':int(panel.Y_rule0.isna().sum()),'plant_month_keys_unique':not panel.duplicated(['gpcb_id','month16']).any(),'physical_missing_values_replaced_by_zero':False,'replication_coefficients_match':True,'primary_models_all318':bool((r.loc[mask,'n']==318).all())}
(O/'data_validation.json').write_text(json.dumps(v,indent=2))
print('PRIMARY\n',r.loc[mask].to_string(index=False))
print('SENSITIVITY\n',r[r.assignment.eq('Z')&r.adjusted].to_string(index=False))
print('BOUNDS\n',pd.DataFrame(boundrows).query("assignment=='Z'").to_string(index=False))
print('REPLICATION\n',pd.DataFrame(reps).to_string(index=False))
