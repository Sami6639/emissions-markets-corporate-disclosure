"""Pre-specified cross-country associations with explicit fixed-effect absorption."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from scipy.stats import t
from statsmodels.stats.multitest import multipletests

ROOT=Path(__file__).resolve().parent; OUT=ROOT/'results'
BASE_X=['national_ets','subnational_ets','carbon_tax','voluntary_ets','ln_gdp_pc','gdp_growth']
def encode(values):return pd.factorize(values,sort=True)[0]

def absorb(a,groups,w,tol=1e-10):
 z=np.asarray(a,dtype=float).copy()
 enc=[encode(g) for g in groups]
 denominators=[np.bincount(g,weights=w) for g in enc]
 for iteration in range(3000):
  old=z.copy()
  for g,den in zip(enc,denominators):
   means=np.column_stack([np.bincount(g,weights=w*z[:,j],minlength=len(den))/den for j in range(z.shape[1])])
   z-=means[g]
  if np.max(np.abs(z-old))<tol:return z,enc,iteration+1
 raise RuntimeError('Fixed effects did not converge')

def absorbed_rank(enc):
 sizes=[int(g.max()+1) for g in enc]
 if len(enc)==1:return sizes[0]
 if len(enc)>2:return sum(sizes)-len(sizes)+1 # conservative upper bound
 n=sum(sizes);parent=np.arange(n)
 def find(x):
  while parent[x]!=x:
   parent[x]=parent[parent[x]];x=parent[x]
  return x
 for a,b in np.unique(np.column_stack([enc[0],enc[1]+sizes[0]]),axis=0):
  ra,rb=find(int(a)),find(int(b))
  if ra!=rb:parent[ra]=rb
 components=len({find(i) for i in range(n)})
 return n-components

def fit(data,outcome='s12',xs=BASE_X,effects=('country','industry_year'),cluster='policy_cluster',equal_country=False,trends=False,label='primary'):
 needed=[outcome,*xs,*effects,cluster,'firm','country','year']
 d=data.dropna(subset=list(set(needed))).copy()
 # Singleton fixed-effect cells contain no within-cell identification.
 removed=0
 while len(d):
  ok=np.ones(len(d),dtype=bool)
  for e in effects:ok &= d.groupby(e)[e].transform('size').to_numpy()>1
  if ok.all():break
  removed+=int((~ok).sum());d=d.loc[ok].copy()
 w=(1/d.groupby(['country','year']).firm.transform('size')).to_numpy() if equal_country else np.ones(len(d))
 w=w/w.mean()
 x=d[list(xs)].to_numpy(dtype=float);names=list(xs)
 if trends:
  cd=pd.get_dummies(d.country,dtype=float)
  for name in cd.columns:
   x=np.column_stack([x,cd[name].to_numpy()*(d.year.to_numpy()-2013)]);names.append('trend_'+name)
 a=np.column_stack([d[outcome].to_numpy(float),x])
 z,enc,it=absorb(a,[d[g].to_numpy() for g in effects],w)
 y=z[:,0];x=z[:,1:]
 xw=x*np.sqrt(w)[:,None];yw=y*np.sqrt(w)
 b,_,rank,_=np.linalg.lstsq(xw,yw,rcond=1e-9)
 resid=y-x@b
 bread=np.linalg.pinv(xw.T@xw,rcond=1e-10)
 g=encode(d[cluster]);G=int(g.max()+1);N=len(d);kr=absorbed_rank(enc)+rank
 if N<=kr or G<3:raise RuntimeError((label,'insufficient support',N,kr,G))
 scores=np.column_stack([np.bincount(g,weights=w*x[:,j]*resid,minlength=G) for j in range(x.shape[1])])
 V=bread@(scores.T@scores)@bread*G/(G-1)*(N-1)/(N-kr)
 se=np.sqrt(np.clip(np.diag(V),0,None));crit=t.ppf(.975,G-1)
 rows=[]
 for j,name in enumerate(names[:len(xs)]):
  estimable=np.linalg.norm(x[:,j])>1e-8
  rows.append(dict(model=label,outcome=outcome,term=name,beta=b[j] if estimable else np.nan,se=se[j] if estimable else np.nan,lo=b[j]-crit*se[j] if estimable else np.nan,hi=b[j]+crit*se[j] if estimable else np.nan,p=2*t.sf(abs(b[j]/se[j]),G-1) if estimable and se[j]>0 else np.nan,n=N,firms=d.firm.nunique(),countries=d.country.nunique(),clusters=G,df_cluster=G-1,absorbed_rank=kr-rank,slope_rank=rank,effects=' + '.join(effects),singleton_removed=removed,iterations=it,weighted=equal_country,linear_trends=trends,out_of_range_fit=float(((d[outcome].to_numpy(float)-resid<0)|(d[outcome].to_numpy(float)-resid>1)).mean())))
 return pd.DataFrame(rows),dict(d=d,x=x,y=y,w=w,b=b,resid=resid,names=names,cov=V,enc=enc,g=g,G=G,N=N,kr=kr,effects=effects,cluster=cluster)

def restricted_wild_cluster(info,B=9999,seed=20261113,target='national_ets'):
 """Exact linear algebra for the Rademacher restricted wild cluster bootstrap-t.
 Reabsorbs fixed effects for each cluster shock basis, hence also for every draw.
 """
 x,y,w=info['x'],info['y'],info['w'];j=info['names'].index(target)
 other=[k for k in range(x.shape[1]) if k!=j]
 br=np.linalg.lstsq(x[:,other]*np.sqrt(w)[:,None],y*np.sqrt(w),rcond=1e-9)[0]
 ur=y-x[:,other]@br;g=info['g'];G=info['G']
 raw=ur[:,None]*(g[:,None]==np.arange(G)[None,:])
 v,_,_=absorb(raw,info['enc'],w)
 bread=np.linalg.pinv((x*w[:,None]).T@x,rcond=1e-10)
 noise=bread@((x*w[:,None]).T@v)
 resid_basis=v-x@noise
 h=np.vstack([bread[j]@(x[g==k].T@(w[g==k,None]*resid_basis[g==k])) for k in range(G)])
 rng=np.random.default_rng(seed);signs=rng.choice([-1.,1.],size=(G,B))
 correction=G/(G-1)*(info['N']-1)/(info['N']-info['kr'])
 se=np.sqrt(correction*np.sum((h@signs)**2,axis=0))
 ts=(noise[j]@signs)/se
 observed=float(info['b'][j]/np.sqrt(info['cov'][j,j]))
 tolerance=1e-10*max(1.,abs(observed))
 p=float((1+np.sum(np.abs(ts)>=abs(observed)-tolerance))/(B+1))
 return {'p_wcr':p,'draws':B,'seed':seed,'t_observed':observed,'tail_tolerance':tolerance,'bootstrap':'restricted Rademacher cluster bootstrap-t; null coefficient zero','clusters':G},dict(signs=signs,noise=noise,resid_basis=resid_basis,restricted_residual=ur,restricted_beta=br,other=other)

def main():
 d=pd.read_parquet(OUT/'analysis_panel_private.parquet')
 alt=pd.read_parquet(OUT/'alternative_frame_private.parquet')
 complete=d.dropna(subset=BASE_X)
 models=[];rob=[]
 for label,eff,tr in [('Between-country comparison',('industry_group','year'),False),('Primary country effects',('country','industry_year'),False),('Firm effects',('firm','industry_year'),False),('Country trends',('country','industry_year'),True)]:
  r,detail=fit(complete,effects=eff,trends=tr,label=label);models.append(r);print(label,r[r.term.eq('national_ets')][['beta','se','p','n','clusters']].to_dict('records'),flush=True)
  if label=='Primary country effects':primary_detail=detail
 primary=models[1].copy()
 boot=[]
 q,_=restricted_wild_cluster(primary_detail);q['outcome']='s12';boot.append(q)
 for outcome in ['s1','s2','s3','s123']:
  r,detail=fit(complete,outcome=outcome,label='Secondary scopes');models.append(r)
  q,_=restricted_wild_cluster(detail);q['outcome']=outcome;boot.append(q)
 secondary=pd.concat(models[4:]);sel=secondary.term.eq('national_ets');secondary.loc[sel,'p_holm']=multipletests(secondary.loc[sel,'p'],method='holm')[1]
 boot=pd.DataFrame(boot);boot.loc[boot.outcome.ne('s12'),'p_wcr_holm']=multipletests(boot.loc[boot.outcome.ne('s12'),'p_wcr'],method='holm')[1];boot.to_csv(OUT/'restricted_wild_cluster_inference.csv',index=False)
 het=complete.assign(sub_intensive=complete.subnational_ets*complete.intensive,tax_intensive=complete.carbon_tax*complete.intensive,voluntary_intensive=complete.voluntary_ets*complete.intensive)
 r,_=fit(het,xs=['ets_intensive','sub_intensive','tax_intensive','voluntary_intensive'],effects=('firm','country_year','industry_year'),label='Sector differential');models.append(r)
 full1015=d[d.year.between(2015,2024)].groupby('firm').year.nunique();balanced_ids=full1015[full1015==10].index
 specs=[('Primary',complete,False,False),('2010-2024',complete[complete.year>=2010],False,False),('2015-2024',complete[complete.year>=2015],False,False),('Exclude China',complete[complete.country.ne('China')],False,False),('Exclude European ETS family',complete[~complete.is_europe],False,False),('Exclude AU CA MX',complete[~complete.country.isin(['Australia','Canada','Mexico'])],False,False),('Alternative coverage frame',alt.dropna(subset=BASE_X),False,False),('Balanced 2015-2024',complete[complete.firm.isin(balanced_ids)&complete.year.between(2015,2024)],False,False),('Equal country-year weights',complete,True,False),('Country clusters',complete,False,True)]
 for label,z,eq,cc in specs:
  r,_=fit(z,label=label,equal_country=eq,cluster='country' if cc else 'policy_cluster');rob.append(r);print('sensitivity',label,r[r.term.eq('national_ets')][['beta','p','n','clusters']].to_dict('records'),flush=True)
 # Year-end exposure vs lagged policy context, retaining the same outcome definition.
 prev=pd.read_csv(OUT/'country_year_policy.csv');prev['year']+=1
 cols=['national_ets','subnational_ets','carbon_tax','voluntary_ets']
 lag=d.drop(columns=cols).merge(prev[['country','year',*cols]],on=['country','year'],how='left',validate='many_to_one')
 r,_=fit(lag,label='Previous-year regulatory context');rob.append(r)
 r,_=fit(complete[complete.year.eq(complete.end_year)],label='Matching fiscal and calendar end years');rob.append(r)
 # Transparent support checks; no specification is selected by its p-value.
 loo=[]
 for country in sorted(complete.policy_cluster.unique()):
  r,_=fit(complete[complete.policy_cluster.ne(country)],label='Leave one policy family out')
  r=r[r.term.eq('national_ets')].copy();r['omitted']=country;loo.append(r)
 pd.concat(loo).to_csv(OUT/'leave_one_policy_family_out.csv',index=False)
 lb=pd.concat(loo).beta.to_numpy();G=len(lb);cv3se=float(np.sqrt((G-1)/G*np.sum((lb-lb.mean())**2)));pb=float(primary.loc[primary.term.eq('national_ets'),'beta'].iloc[0]);cv3={'method':'delete-one-policy-family cluster jackknife, centered at mean leave-one-out coefficient','clusters':G,'se':cv3se,'beta':pb,'lo':pb-t.ppf(.975,G-1)*cv3se,'hi':pb+t.ppf(.975,G-1)*cv3se,'p':float(2*t.sf(abs(pb/cv3se),G-1))};(OUT/'cluster_jackknife_inference.json').write_text(json.dumps(cv3,indent=2))
 allmodels=pd.concat(models,ignore_index=True);allmodels.to_csv(OUT/'model_estimates.csv',index=False)
 secondary.to_csv(OUT/'secondary_scope_estimates.csv',index=False)
 pd.concat(rob).to_csv(OUT/'sensitivity_estimates.csv',index=False)
 # Descriptive tables retain the entire eligible disclosure archive, before macro-control deletion.
 for z,name in [(d,'full'),(complete,'model')]:
  z.groupby('country').agg(firms=('firm','nunique'),n=('firm','size'),year_min=('year','min'),year_max=('year','max'),s1=('s1','mean'),s2=('s2','mean'),s12=('s12','mean'),s3=('s3','mean'),s123=('s123','mean'),national_ets_share=('national_ets','mean')).to_csv(OUT/f'country_coverage_{name}.csv')
 d.assign(region=np.select([d.country.eq('China'),d.is_europe],['China','European ETS family'],default='Other countries')).groupby(['region','year']).agg(firms=('firm','nunique'),n=('firm','size'),s1=('s1','mean'),s2=('s2','mean'),s12=('s12','mean'),s3=('s3','mean'),s123=('s123','mean')).to_csv(OUT/'regional_annual_disclosure.csv')
 d.groupby(['context','year']).agg(n=('firm','size'),s12=('s12','mean'),s3=('s3','mean')).to_csv(OUT/'context_annual_disclosure.csv')
 d.groupby('context').agg(firms=('firm','nunique'),countries=('country','nunique'),n=('firm','size'),s1=('s1','mean'),s2=('s2','mean'),s12=('s12','mean'),s3=('s3','mean'),s123=('s123','mean')).to_csv(OUT/'context_descriptive.csv')
 d.groupby('year').agg(firms=('firm','nunique'),countries=('country','nunique'),n=('firm','size'),s12=('s12','mean'),s3=('s3','mean')).to_csv(OUT/'annual_sample.csv')
 # Independent check against a conventional dummy-variable least-squares fit on a deterministically selected subset.
 import statsmodels.formula.api as smf
 check=complete[complete.country.isin(['China','Japan','United States','Germany','United Kingdom','France','South Korea']) & complete.year.ge(2010)].copy()
 cr,detail=fit(check,label='Validation',effects=('country','year'))
 check['s12']=check.s12.astype(float)
 f=smf.ols('s12 ~ '+' + '.join(BASE_X)+' + C(country) + C(year)',data=check).fit(cov_type='cluster',cov_kwds={'groups':check.policy_cluster,'use_correction':True},use_t=True)
 bdelta=float(abs(cr.set_index('term').loc[BASE_X,'beta'].to_numpy()-f.params[BASE_X].to_numpy()).max())
 sedelta=float(abs(cr.set_index('term').loc[BASE_X,'se'].to_numpy()-f.bse[BASE_X].to_numpy()).max())
 assert bdelta<1e-7 and sedelta<1e-7,(bdelta,sedelta)
 # Validate the bootstrap reabsorption against an explicit dummy-variable refit.
 _,bd=restricted_wild_cluster(detail,B=3)
 sign=bd['signs'][:,0];u=bd['restricted_residual'];pseudo=check.s12.to_numpy()-u+u*sign[detail['g']]
 bc=check.copy();bc['pseudo']=pseudo
 bf=smf.ols('pseudo ~ '+' + '.join(BASE_X)+' + C(country) + C(year)',data=bc).fit(cov_type='cluster',cov_kwds={'groups':bc.policy_cluster,'use_correction':True},use_t=True)
 fastbeta=float(bd['noise'][0]@sign);fastres=bd['resid_basis']@sign
 bread=np.linalg.pinv((detail['x']*detail['w'][:,None]).T@detail['x'],rcond=1e-10)
 scores=np.vstack([detail['x'][detail['g']==k].T@fastres[detail['g']==k] for k in range(detail['G'])]);vv=bread@(scores.T@scores)@bread*detail['G']/(detail['G']-1)*(len(check)-1)/(len(check)-detail['kr'])
 boot_beta_error=float(abs(fastbeta-bf.params['national_ets']));boot_se_error=float(abs(np.sqrt(vv[0,0])-bf.bse['national_ets']))
 assert boot_beta_error<1e-7 and boot_se_error<1e-7,(boot_beta_error,boot_se_error)
 summary={'frame_n':len(d),'frame_firms':d.firm.nunique(),'frame_countries':d.country.nunique(),'complete_controls_n':len(complete),'missing_controls':len(d)-len(complete),'china_firms':d[d.country.eq('China')].firm.nunique(),'china_n':int(d.country.eq('China').sum()),'primary':primary[primary.term.eq('national_ets')].to_dict('records')[0],'balanced_firms':len(balanced_ids),'independent_dummy_ols_max_beta_error':bdelta,'independent_dummy_ols_max_se_error':sedelta,'independent_dummy_validation_n':len(check),'main_outcome_rate':float(d.s12.mean()),'scope3_rate':float(d.s3.mean()),'loo_beta_min':float(pd.concat(loo).beta.min()),'loo_beta_max':float(pd.concat(loo).beta.max()),'negative_control_warning':'Carbon trading context is not firm eligibility and associations do not establish effects.'}
 summary.update({'wild_cluster_primary':boot[boot.outcome.eq('s12')].to_dict('records')[0],'cluster_jackknife':cv3,'bootstrap_dummy_validation_beta_error':boot_beta_error,'bootstrap_dummy_validation_se_error':boot_se_error})
 (OUT/'analysis_summary.json').write_text(json.dumps(summary,indent=2,default=lambda x:int(x) if isinstance(x,np.integer) else float(x)))
 print(json.dumps(summary,indent=2),flush=True)
if __name__=='__main__':main()
