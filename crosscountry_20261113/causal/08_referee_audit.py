"""Targeted post-primary referee audit: cluster leverage and sector support.
No model selection: retain all sector diagnostics, including insufficient-support cases.
CR2 is computed with full fixed-effect projection under identity working covariance.
The target-specific unbiasedness identity is checked, including singular within-cluster FE.
"""
from pathlib import Path
import importlib.util,json
import numpy as np,pandas as pd
from scipy.stats import t
P=Path(__file__).resolve().parent;O=P/'results';spec=importlib.util.spec_from_file_location('base',P.parent/'02_analyze.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
def cr2(x,y,g,index=0):
 pinv=np.linalg.pinv(x,rcond=1e-10);H=x@pinv;H=(H+H.T)/2;M=np.eye(len(y))-H;u=M@y;a=pinv[index];beta=float(a@y);vec=[];scores=[];details=[];err=[]
 for group in sorted(set(g)):
  ix=np.flatnonzero(g==group);mgg=M[np.ix_(ix,ix)];l,V=np.linalg.eigh(mgg);assert l.min()>-1e-8
  ok=l>1e-9;Ag=(V[:,ok]/np.sqrt(l[ok]))@V[:,ok].T
  q=Ag@a[ix];v=M[:,ix]@q;vec.append(v);scores.append(float(q@u[ix]));err.append(float(abs(q@mgg@q-a[ix]@a[ix])))
  details.append({'cluster':group,'n':len(ix),'target_information_share':float(a[ix]@a[ix]/(a@a)),'cr2_score':scores[-1],'positive_residual_directions':int(ok.sum())})
 V=np.stack(vec);K=V@V.T;expected=float(np.trace(K));target=float(a@a);assert abs(expected-target)<1e-9,(expected,target)
 var=float(np.sum(np.square(scores)));se=var**.5;df=float(expected**2/np.sum(K*K));crit=float(t.ppf(.975,df))
 return {'beta':beta,'se_cr2':se,'df_satterthwaite':df,'lo':beta-crit*se,'hi':beta+crit*se,'p':float(2*t.sf(abs(beta/se),df)),'clusters':len(set(g)),'full_design_rank':int(np.linalg.matrix_rank(x,tol=1e-8)),'working_model_variance':target,'expected_cr2_variance':expected,'max_cluster_unbiasedness_error':max(err)},pd.DataFrame(details)
# Closed-form validation: singleton clusters reduce CR2 to the HC2 mean estimator.
y0=np.array([2.,5.,1.,7.,4.,8.,6.,3.,9.,0.]);r0,_=cr2(np.ones((10,1)),y0,np.arange(10));assert abs(r0['se_cr2']-y0.std(ddof=1)/np.sqrt(10))<1e-12;assert abs(r0['df_satterthwaite']-9)<1e-10
D=pd.read_csv(O/'primary_estimation_panel.csv',dtype={'code':str,'firm':str});y=D.mention.to_numpy(float);g=D.province.to_numpy();X=np.column_stack([D.did.to_numpy(float),*[pd.get_dummies(D[c],dtype=float).to_numpy() for c in ['firm','sector_year','province_year']]])
r,lev=cr2(X,y,g)
principal=pd.read_csv(O/'national_ets_estimates.csv').query("model == 'Primary' and term == 'did'").iloc[0]
assert abs(r['beta']-principal.beta)<1e-9
r['method']='Full-design CR2 with identity working covariance and Satterthwaite reference; supplemental inference, not a new primary model'
r['timing']='Post-primary referee audit; not prespecified'
r['closed_form_validation_se_error']=abs(r0['se_cr2']-y0.std(ddof=1)/np.sqrt(10));r['closed_form_validation_df_error']=abs(r0['df_satterthwaite']-9)
# Equivalent residualized regressor: treatment weights diagnose the target contrast.
f,info=base.fit(D,outcome='mention',xs=['did'],effects=('firm','sector_year','province_year'),cluster='province');a=info['x'][:,0];w=a/(a@a);weights=D[['code','year','province','industry','treated','post']].copy();weights['ols_outcome_weight']=w;weights['treated_post_weight']=w*D.did.to_numpy();weights.to_csv(O/'treatment_effect_weights.csv',index=False)
r['treated_post_weight_sum']=float(weights.treated_post_weight.sum());r['negative_treated_post_cells']=int((weights.treated_post_weight < -1e-9).sum());r['negative_treated_post_weight_sum']=float(weights.loc[weights.treated_post_weight < -1e-9,'treated_post_weight'].sum());r['positive_information_clusters']=int(lev.target_information_share.gt(1e-8).sum());r['max_cluster_information_share']=float(lev.target_information_share.max());r['information_effective_clusters']=float(1/np.sum(lev.target_information_share**2))
# Cluster-jackknife sensitivity uses all previously computed omitted-province models.
l=pd.read_csv(O/'leave_one_province_out.csv');b=l.beta.to_numpy();G=len(b);sj=float(np.sqrt((G-1)/G*np.sum((b-b.mean())**2)));r['jackknife']={'se':sj,'df':G-1,'lo':r['beta']-t.ppf(.975,G-1)*sj,'hi':r['beta']+t.ppf(.975,G-1)*sj,'p':float(2*t.sf(abs(r['beta']/sj),G-1))}
lev.to_csv(O/'cluster_leverage.csv',index=False);(O/'small_cluster_audit.json').write_text(json.dumps(r,indent=2,ensure_ascii=False));print('SMALL CLUSTERS',json.dumps(r,indent=2,ensure_ascii=False),flush=True)
rows=[]
for sector in sorted(D.industry.unique()):
 for mode in ['Only','Exclude']:
  z=D[D.industry.eq(sector) if mode=='Only' else D.industry.ne(sector)].copy();label=mode+' '+sector
  try:
   fit,ii=base.fit(z,outcome='mention',xs=['did'],effects=('firm','sector_year','province_year'),cluster='province',label=label)
   q=fit.iloc[0].to_dict();q['reportable']=bool(np.isfinite(q['beta']))
   if q['reportable']:
    boot,_=base.restricted_wild_cluster(ii,target='did');q['wild_p']=boot['p_wcr'];q['status']='estimated'
   else:q['status']='Treatment has no remaining within-effect variation'
  except (RuntimeError,ValueError,IndexError) as e:q={'model':label,'reportable':False,'status':str(e),'n_before_fit':len(z),'firms_before_fit':z.code.nunique()}
  q.update(sector=sector,mode=mode);rows.append(q);print('SECTOR',q,flush=True)
pd.DataFrame(rows).to_csv(O/'sector_support_audit.csv',index=False)
