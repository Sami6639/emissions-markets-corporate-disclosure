from pathlib import Path
import importlib.util,json
import pandas as pd,numpy as np
from scipy.stats import t,f
P=Path(__file__).resolve().parent;O=P/'results';O.mkdir(exist_ok=True);SRC=P.parent/'raw/china_replication';R=P/'cninfo'
spec=importlib.util.spec_from_file_location('est',P.parent/'02_analyze.py');est=importlib.util.module_from_spec(spec);spec.loader.exec_module(est)
s=pd.read_csv(P/'china_2021_design_sample.csv',dtype={'code':str})
pre=pd.read_csv(R/'extracted_pages.csv',dtype={'code':str}); pre=pre[pre.year.isin([2017,2018])].copy()
if 'error' in pre:pre=pre[pre.error.isna()]
old=pd.read_csv(SRC/'out/carbon_disclosure_namefilt.csv',dtype={'code':str});pcount=pd.read_csv(SRC/'out/carbon_disclosure.csv',dtype={'code':str})[['code','year','n_pages','compliance_tier']];old=old.merge(pcount,on=['code','year'],validate='one_to_one');old=old[old.year.isin([2019,2021,2022,2023])]
d=pd.concat([pre,old],ignore_index=True).merge(s,on='code',validate='many_to_one')
meta=pd.read_csv(R/'report_manifest.csv',dtype={'code':str});meta['filing_date']=pd.to_datetime(meta.timestamp,unit='ms',utc=True);d=d.merge(meta[['code','year','filing_date','url','announcement_id']],on=['code','year'],how='left',validate='one_to_one')
assert not d.duplicated(['code','year']).any()
# Sector comparability uses pre-policy (2019) industry, not the source archive's contemporary labels.
valid_industries=['化学原料及化学制品制造业','煤炭开采和洗选业','造纸及纸制品业']
d=d[d.industry.isin(valid_industries)].copy()
# Missing publication metadata is not assumed to establish timing.
d=d[d.filing_date.notna()].copy();d=d[((d.year.le(2019))&(d.filing_date<'2020-12-01'))|((d.year.ge(2021))&(d.filing_date>'2021-07-16'))]
# Apply the two documented source-page adjudications to all relevant samples.
# The untouched source-dictionary outcome remains an explicit sensitivity.
d['archive_n_hit_namefilt']=d.n_hit_namefilt;d['archive_hit_pages_namefilt']=d.hit_pages_namefilt;d['archive_mention']=d.n_hit_namefilt.gt(0).astype(float);d['semantic_correction']=False
corrections=pd.read_csv(P/'submission_audit/adjudicated_classification_discrepancies.csv',dtype={'code':str})
for r in corrections.itertuples():
 ix=d.code.eq(r.code)&d.year.eq(r.year);assert ix.sum()==1
 d.loc[ix,'n_hit_namefilt']=int(r.semantic_presence);d.loc[ix,'semantic_correction']=True
 d.loc[ix,'hit_pages_namefilt']={'A024':'44','A026':''}[r.audit_id]
d['firm']=d.code;d['country']='China';d['post']=d.year.ge(2021).astype(int);d['did']=d.treated*d.post;d['mention']=d.n_hit_namefilt.gt(0).astype(float);d['mention_restricted']=d.n_hit_restricted.gt(0).astype(float);d['log_pages']=np.log(d.n_pages);d['log_carbon_pages']=np.log1p(d.n_hit_namefilt);d['sector_year']=d.industry+'|'+d.year.astype(str);d['province_year']=d.province+'|'+d.year.astype(str);d['logassets2019']=np.log(d.TA)
for c in ['logassets2019','DA_lev','ROA']:
 d[c]=(d[c]-d[c].mean())/d[c].std()
need=[2017,2018,2019,2021,2022,2023];good=d.groupby('code').year.nunique();balanced_initial=d[d.code.isin(good[good.eq(6)].index)].copy(); mentions=pd.read_csv(R/'extracted_pages.csv',dtype={'code':str}); suspect=set(mentions.loc[mentions.year.eq(2018)&mentions.roster_entities_mentioned.notna(),'code']); excluded_controls=set(s.loc[s.treated.eq(0)&s.code.isin(suspect),'code']); s[s.code.isin(excluded_controls)].to_csv(O/'comparison_affiliation_exclusions.csv',index=False); balanced=balanced_initial[~balanced_initial.code.isin(excluded_controls)].copy(); d_clean=d[~d.code.isin(excluded_controls)].copy();d.to_csv(O/'all_observed_report_panel.csv',index=False);balanced.to_csv(O/'primary_balanced_report_panel.csv',index=False)
flow={'design_companies':len(s),'design_treated':int(s.treated.sum()),'observed_rows':len(d),'observed_companies':d.code.nunique(),'balanced_rows':len(balanced),'balanced_companies':balanced.code.nunique(),'balanced_treated':balanced.loc[balanced.treated.eq(1),'code'].nunique(),'provinces':balanced.province.nunique(),'years':need}
print('FLOW',flow,flush=True);(O/'sample_flow.json').write_text(json.dumps(flow,indent=2))
rows=[];boots=[];prim=None
for label,a,y,effects,cl in [
 ('Primary',balanced,'mention',('firm','sector_year','province_year'),'province'),
 ('Original source dictionary',balanced,'archive_mention',('firm','sector_year','province_year'),'province'),
 ('Firm clustering',balanced,'mention',('firm','sector_year','province_year'),'firm'),
 ('Initially defined controls',balanced_initial,'mention',('firm','sector_year','province_year'),'province'),
 ('Unbalanced',d_clean,'mention',('firm','sector_year','province_year'),'province'),
 ('Restricted dictionary',balanced,'mention_restricted',('firm','sector_year','province_year'),'province'),
 ('Carbon page count log1p',balanced,'log_carbon_pages',('firm','sector_year','province_year'),'province'),
 ('Report length negative control',balanced,'log_pages',('firm','sector_year','province_year'),'province'),
 ('Firm and year effects',balanced,'mention',('firm','year'),'province')]:
 r,info=est.fit(a,outcome=y,xs=['did'],effects=effects,cluster=cl,label=label);rows.append(r)
 if label=='Primary':prim=info
 if cl=='province':
  b,_=est.restricted_wild_cluster(info,target='did');b.update(model=label,outcome=y);boots.append(b)
 print(label,r[['beta','lo','hi','p','n','firms','clusters']].to_dict('records'),flush=True)
# Covariates fixed at 2019, never contemporaneous mediator controls.
a=balanced.copy();xs=['did']
for c in ['logassets2019','DA_lev','ROA']:
 for yr in [2018,2019,2021,2022,2023]:
  k=c+'_'+str(yr);a[k]=a[c]*(a.year==yr);xs.append(k)
r,info=est.fit(a,outcome='mention',xs=xs,effects=('firm','sector_year','province_year'),cluster='province',label='Baseline covariates by year');rows.append(r);b,_=est.restricted_wild_cluster(info,target='did');b.update(model='Baseline covariates by year',outcome='mention');boots.append(b)
pd.concat(rows).to_csv(O/'national_ets_estimates.csv',index=False);pd.DataFrame(boots).to_csv(O/'national_ets_wild_inference.csv',index=False)
# Event study, common treatment date: no staggered-adoption contamination.
a=balanced.copy();xs=[]
for yr in [2017,2018,2021,2022,2023]:
 k='event_'+str(yr);a[k]=a.treated*a.year.eq(yr);xs.append(k)
r,info=est.fit(a,outcome='mention',xs=xs,effects=('firm','sector_year','province_year'),cluster='province',label='Event study');r.to_csv(O/'event_study.csv',index=False)
idx=[0,1];bp=info['b'][idx];Vp=info['cov'][np.ix_(idx,idx)];wald=float(bp@np.linalg.pinv(Vp)@bp/2);pretest={'F':wald,'df1':2,'df2':info['G']-1,'p':float(f.sf(wald,2,info['G']-1))};
if np.linalg.norm(Vp)<1e-12 or balanced.loc[balanced.year.le(2019),'mention'].nunique()<2:pretest={'status':'Pre-period outcome is at a floor or covariance is degenerate; a parallel-trend significance test is not informative.','F':None,'p':None,'df1':2,'df2':info['G']-1}
(O/'pretrend_test.json').write_text(json.dumps(pretest,indent=2))
# Conservative simultaneous Bonferroni t intervals, all five event coefficients.
c=t.ppf(1-.05/(2*len(xs)),info['G']-1);r['sim_lo']=r.beta-c*r.se;r['sim_hi']=r.beta+c*r.se;r.to_csv(O/'event_study.csv',index=False)
# Worst-case constant differential annual drift, over the 4-year mean time gap.
main=rows[0].iloc[0];sens=[]
for delta in [0,.01,.025,.05]:sens.append({'annual_drift_pp':100*delta,'bias_bound_pp':400*delta,'lo_pp':100*(main.lo-4*delta),'hi_pp':100*(main.hi+4*delta)})
pd.DataFrame(sens).to_csv(O/'drift_sensitivity.csv',index=False)
balanced.groupby(['treated','year']).agg(companies=('code','size'),mention=('mention','mean'),mean_carbon_pages=('n_hit_namefilt','mean'),mean_report_pages=('n_pages','mean')).reset_index().to_csv(O/'group_year_outcomes.csv',index=False)
# Independent explicit-dummy OLS validation, discarding only numerical null singular values.
import statsmodels.api as sm
q=prim['d'];X=pd.concat([q[['did']].reset_index(drop=True),pd.get_dummies(q[['firm','sector_year','province_year']].reset_index(drop=True),drop_first=True,dtype=float)],axis=1);X=sm.add_constant(X).to_numpy(float)
PX=np.linalg.pinv(X,rcond=1e-10);bd=PX@q.mention.to_numpy();ud=q.mention.to_numpy()-X@bd
sc=np.array([PX[1,q.province.to_numpy()==g]@ud[q.province.to_numpy()==g] for g in sorted(q.province.unique())]);G=prim['G'];vd=np.sum(sc**2)*G/(G-1)*(len(q)-1)/(len(q)-prim['kr'])
check={'absorbed_beta':float(prim['b'][0]),'dummy_beta':float(bd[1]),'coefficient_abs_error':float(abs(prim['b'][0]-bd[1])),'absorbed_se':float(np.sqrt(prim['cov'][0,0])),'dummy_se_same_conservative_df':float(np.sqrt(vd)),'se_abs_error':float(abs(np.sqrt(vd)-np.sqrt(prim['cov'][0,0]))),'dummy_exact_rank':int(np.linalg.matrix_rank(X)),'absorbed_conservative_rank':int(prim['kr']),'note':'SVD rcond=1e-10 removes redundant fixed effects. Same conservative CR1 correction used for the independent SE comparison.'}
assert check['coefficient_abs_error']<1e-7 and check['se_abs_error']<1e-7
(O/'independent_validation.json').write_text(json.dumps(check,indent=2))
q.to_csv(O/'primary_estimation_panel.csv',index=False)
flow.update(initial_balanced_companies=int(balanced_initial.code.nunique()),primary_estimation_rows=len(q),primary_estimation_companies=int(q.code.nunique()),primary_estimation_treated=int(q.loc[q.treated.eq(1),'code'].nunique()),primary_estimation_controls=int(q.loc[q.treated.eq(0),'code'].nunique()),primary_estimation_provinces=int(q.province.nunique()),baseline_industry_treated=int(s.loc[s.industry.isin(valid_industries)&s.treated.eq(1),'code'].nunique()))
(O/'sample_flow.json').write_text(json.dumps(flow,indent=2))
q.groupby(['treated','year']).agg(companies=('code','size'),mention=('mention','mean'),mean_carbon_pages=('n_hit_namefilt','mean'),mean_report_pages=('n_pages','mean')).reset_index().to_csv(O/'group_year_outcomes.csv',index=False)
print('PRETREND',pretest,flush=True);print('EVENT',r[['term','beta','se','p','sim_lo','sim_hi']].to_string(index=False),flush=True);print('BOOT',pd.DataFrame(boots).to_string(index=False),flush=True);print('VALIDATION',check,flush=True)
