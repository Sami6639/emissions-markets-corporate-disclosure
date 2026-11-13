"""Post-estimation balance check prompted by a large baseline size difference.
Not a replacement primary estimand; the overlap-population effect is reported separately.
"""
from pathlib import Path
import pandas as pd,numpy as np,json
import statsmodels.api as sm
from scipy.stats import t
P=Path(__file__).resolve().parent;O=P/'results';d=pd.read_csv(O/'primary_estimation_panel.csv',dtype={'code':str});b=d.drop_duplicates('code').set_index('code');c=d.groupby(['code','post']).mention.mean().unstack();b['delta']=c[1]-c[0]
cols=['logassets2019','DA_lev','ROA'];X=pd.concat([b[cols],pd.get_dummies(b.industry,drop_first=True,dtype=float)],axis=1);X=sm.add_constant(X);x=X.to_numpy(float);T=b.treated.to_numpy(float);Y=b.delta.to_numpy(float)
psfit=sm.GLM(T,x,family=sm.families.Binomial()).fit(maxiter=200,tol=1e-10);assert psfit.converged
p=psfit.predict(x);w1=T*(1-p);w0=(1-T)*p;mu1=(w1@Y)/w1.sum();mu0=(w0@Y)/w0.sum();beta=mu1-mu0
k=x.shape[1];A=np.zeros((k+2,k+2));A[:k,:k]=x.T@(p[:,None]*(1-p[:,None])*x);A[k,:k]=np.sum((T*p*(1-p)*(Y-mu1))[:,None]*x,axis=0);A[k+1,:k]=-np.sum(((1-T)*p*(1-p)*(Y-mu0))[:,None]*x,axis=0);A[k,k]=w1.sum();A[k+1,k+1]=w0.sum();scores=np.column_stack([x*(T-p)[:,None],w1*(Y-mu1),w0*(Y-mu0)]);clusters=b.province.to_numpy();S=np.array([scores[clusters==g].sum(axis=0) for g in sorted(set(clusters))]);inv=np.linalg.pinv(A,rcond=1e-10);G=len(S);V=inv@(S.T@S)@inv.T*G/(G-1);contrast=np.r_[np.zeros(k),1.,-1.];se=np.sqrt(contrast@V@contrast);crit=t.ppf(.975,G-1)
b['propensity']=p;b['overlap_weight']=w1+w0;b.reset_index().to_csv(O/'overlap_weights.csv',index=False)
balance=[]
for j,col in enumerate(X.columns):
 if col=='const':continue
 m1=w1@x[:,j]/w1.sum();m0=w0@x[:,j]/w0.sum();v1=w1@((x[:,j]-m1)**2)/w1.sum();v0=w0@((x[:,j]-m0)**2)/w0.sum();balance.append({'covariate':col,'smd_after':(m1-m0)/np.sqrt((v1+v0)/2) if v1+v0>1e-10 else None})
pd.DataFrame(balance).to_csv(O/'overlap_balance.csv',index=False)
r={'estimand':'Effect for firms with overlap in baseline size, leverage, profitability and industry; not all treated firms','beta':float(beta),'se_joint_estimation':float(se),'lo':float(beta-crit*se),'hi':float(beta+crit*se),'p':float(2*t.sf(abs(beta/se),G-1)),'firms':len(b),'treated':int(T.sum()),'province_clusters':G,'effective_treated':float(w1.sum()**2/(w1@w1)),'effective_controls':float(w0.sum()**2/(w0@w0)),'ps_min':float(p.min()),'ps_max':float(p.max()),'max_abs_smd_after':float(pd.DataFrame(balance).smd_after.abs().max()),'ps_converged':bool(psfit.converged),'timing':'Post-estimation sensitivity prompted by baseline balance audit, not prespecified','inference':'Joint logistic propensity and weighted-mean estimating equations; province-cluster sandwich and t(G-1). No province-by-year effects in this separate weighted contrast.'};(O/'overlap_result.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))
