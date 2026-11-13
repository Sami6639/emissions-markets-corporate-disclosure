"""Post-primary measurement audit. Does not replace frozen primary estimands."""
from pathlib import Path
import json
import pandas as pd
import numpy as np
import statsmodels.api as sm
R=Path(__file__).resolve().parent; S=R/'analysis/pollution_markets_rct_20261112'; O=R/'audit_results';O.mkdir(exist_ok=True)
a=pd.read_stata(next((R/'audit_sources').glob('CEMS_2018*dta')),convert_categoricals=False)
b=pd.read_stata(S/'raw/BaselineCovariates.dta',convert_categoricals=False);b['Z']=b.orig_assignment_gargee.eq('Treatment').astype(int)
p=pd.read_parquet(S/'results/all318_monthly_evidence_panel.parquet')
cs=['ln_capex','D_ln_capex_missing','boi_year','D_boi_year_missing','bh_ope_cost','D_bh_ope_cost_missing','ln_plant_total_heatoutput']
assert not a.duplicated(['composite_id','date']).any()
assert set(a.gpcb_id)==set(b.gpcb_id)
a['period']=a.date.dt.to_period('M').dt.to_timestamp();a.loc[a.date.dt.day.lt(16),'period']-=pd.DateOffset(months=1);a['period']+=pd.Timedelta(days=15)
a['wk']=((a.date-pd.Timestamp('2018-12-31')).dt.days//7)+1
inter=a.wk.between(65,93)|a.wk.isin([99,100])
keepers=set(a.loc[a.period.ge('2019-07-16')&~inter&a.pm_mass_rule0.notna(),'gpcb_id'])
assert len(keepers)==292
# Source drops whole never-measured plants, not individual stacks.
s=a[a.gpcb_id.isin(keepers)].copy()
assert s.composite_id.nunique()==310
s['valid_hours']=np.where(s.D_vctransmitting_rule0.eq(0),0,s.tot_report_hrs)
s['weekmean']=s.groupby(['composite_id','wk']).pm_mass_rule0.transform('mean')
s['monthmean']=s.groupby(['composite_id','period']).pm_mass_rule0.transform('mean')
s['imp']=(24-s.valid_hours)*s.weekmean.fillna(s.monthmean)
s.loc[s.date.between('2019-10-26','2019-11-03')&s.imp.notna(),'imp']=0
s['actual']=s.pm_mass_rule0*s.valid_hours
s['validated']=(s.actual+s.imp).fillna(s.imp)
g=s.groupby(['composite_id','gpcb_id','period']).validated
smass=g.sum(min_count=1).rename('mass').reset_index(); smiss=g.apply(lambda z:z.isna().any()).to_numpy(); smass.loc[smiss,'mass']=np.nan
g=smass.groupby(['gpcb_id','period']).mass
pmass=g.sum(min_count=1).rename('reconstructed').reset_index();pmiss=g.apply(lambda z:z.isna().any()).to_numpy();pmass.loc[pmiss,'reconstructed']=np.nan
v=p.merge(pmass,left_on=['gpcb_id','month16'],right_on=['gpcb_id','period'],how='left',validate='one_to_one')
avail_match=v.reconstructed.notna().eq(v.Y_rule0.notna()).all()
max_abs=(v.reconstructed-v.Y_rule0).abs().max(); max_rel=((v.reconstructed-v.Y_rule0).abs()/(1+v.Y_rule0.abs())).max()
# Raw coverage is a fraction of listed sensor-stack hours, not an accuracy score.
a['raw_hours_share']=a.tot_report_hrs.fillna(0)/24
a['valid_hours_share']=np.where(a.D_vctransmitting_rule0.eq(1),a.tot_report_hrs.fillna(0)/24,0)
assert a[['raw_hours_share','valid_hours_share']].ge(0).all().all() and a[['raw_hours_share','valid_hours_share']].le(1.000001).all().all()
cover=a.groupby(['gpcb_id','period'])[['raw_hours_share','valid_hours_share']].mean().reset_index()
p=p.merge(cover,left_on=['gpcb_id','month16'],right_on=['gpcb_id','period'],how='left',validate='one_to_one')
assert p.raw_hours_share.notna().all()
days=a.groupby('period').date.nunique().rename('days_in_window').reset_index();p=p.merge(days,on='period',validate='many_to_one')
p['documented_30day_1000']=(p.Y_rule0.notna()&(p.Y_rule0*30/p.days_in_window).le(1000)).astype(int)
def estimate(f,y,interaction=False):
 X=f[['Z']+cs].astype(float).copy()
 for c in cs:X[c]=(X[c]-X[c].mean())/X[c].std(ddof=0)
 if interaction:
  for c in cs:X[c+'_xZ']=X[c]*X.Z
 X=sm.add_constant(X);fit=sm.OLS(f[y].astype(float),X).fit(cov_type='HC2',use_t=True);lo,hi=fit.conf_int().loc['Z']
 return dict(coefficient=fit.params.Z,se=fit.bse.Z,lo=lo,hi=hi,p=fit.pvalues.Z,n=int(fit.nobs),treated_mean=f.loc[f.Z.eq(1),y].mean(),control_mean=f.loc[f.Z.eq(0),y].mean())
ys=['observed','documented_below_1000','documented_30day_1000','raw_hours_share','valid_hours_share'];rows=[]
for label,z in [('all_13',p),('omit_partial_final_12',p[p.month16.lt('2021-03-16')]),('real_only_10',p[p.Mock1.eq(0)&p.Mock2.eq(0)])]:
 f=z.groupby('gpcb_id')[ys].mean().reset_index().merge(b[['gpcb_id','Z']+cs],validate='one_to_one')
 for y in ys:
  rows.append(dict(scope=label,outcome=y,model='additive',**estimate(f,y)))
 if label=='all_13':
  for y in ys[:2]:rows.append(dict(scope=label,outcome=y,model='fully_interacted',**estimate(f,y,True)))
res=pd.DataFrame(rows);res.to_csv(O/'measurement_sensitivity.csv',index=False)
p.to_parquet(O/'coverage_extended_panel.parquet',index=False)
p.groupby(['month16','Z'])[['observed','documented_below_1000','raw_hours_share','valid_hours_share']].agg(['mean','std','count']).to_csv(O/'period_arm_summaries.csv')
# Transparent balance summary, not a criterion for selecting adjustment variables.
bal=[]
for c in cs:
 t=b.loc[b.Z.eq(1),c].astype(float);co=b.loc[b.Z.eq(0),c].astype(float)
 flag={'ln_capex':'D_ln_capex_missing','boi_year':'D_boi_year_missing','bh_ope_cost':'D_bh_ope_cost_missing'}.get(c)
 obs=b if flag is None else b[b[flag].eq(0)]
 ot=obs.loc[obs.Z.eq(1),c].astype(float);oc=obs.loc[obs.Z.eq(0),c].astype(float)
 bal.append(dict(variable=c,treated_mean=t.mean(),control_mean=co.mean(),standardized_difference=(t.mean()-co.mean())/np.sqrt((t.var(ddof=1)+co.var(ddof=1))/2),observed_treated_mean=ot.mean(),observed_control_mean=oc.mean(),observed_standardized_difference=(ot.mean()-oc.mean())/np.sqrt((ot.var(ddof=1)+oc.var(ddof=1))/2),observed_treated_n=len(ot),observed_control_n=len(oc)))
pd.DataFrame(bal).to_csv(O/'baseline_balance.csv',index=False)
audit={'secondary_post_primary_audit':True,'source_daily_rows':len(a),'source_plants':a.gpcb_id.nunique(),'source_stacks':a.composite_id.nunique(),'source_days':a.date.nunique(),'retained_plants_in_original_mass_pipeline':len(keepers),'retained_stacks':s.composite_id.nunique(),'whole_plants_removed_not_individual_stacks':True,'monthly_availability_matches':bool(avail_match),'mass_max_absolute_difference_kg':float(max_abs),'mass_max_relative_difference':float(max_rel),'mass_reconstruction_within_float32_tolerance':bool(max_rel<1e-5),'terminal_window_days':int(p.loc[p.month16.eq('2021-03-16'),'days_in_window'].iloc[0]),'coverage_missing_after_full_join':int(p.raw_hours_share.isna().sum()),'primary_estimands_unchanged':True}
(O/'measurement_audit.json').write_text(json.dumps(audit,indent=2));days.to_csv(O/'window_lengths.csv',index=False)
print(json.dumps(audit,indent=2));print(res.round(6).to_string(index=False))
assert avail_match and max_rel<1e-5
