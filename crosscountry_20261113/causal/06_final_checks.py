from pathlib import Path
import importlib.util,json,itertools,hashlib
import pandas as pd,numpy as np
P=Path(__file__).resolve().parent;O=P/'results';spec=importlib.util.spec_from_file_location('e',P.parent/'02_analyze.py');e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
d=pd.read_csv(O/'primary_estimation_panel.csv',dtype={'code':str,'firm':str});r,i=e.fit(d,outcome='mention',xs=['did'],effects=('firm','sector_year','province_year'),cluster='province',label='primary')
_,b=e.restricted_wild_cluster(i,B=1,target='did');x=i['x'];w=i['w'];g=i['g'];bread=np.linalg.pinv((x*w[:,None]).T@x,rcond=1e-10);h=np.vstack([bread[0]@(x[g==k].T@(w[g==k,None]*b['resid_basis'][g==k])) for k in range(i['G'])]);S=np.array(list(itertools.product([-1.,1.],repeat=i['G']))).T;co=i['G']/(i['G']-1)*(i['N']-1)/(i['N']-i['kr']);ss=np.sqrt(co*np.sum((h@S)**2,axis=0));ts=(b['noise'][0]@S)/ss;tobs=i['b'][0]/np.sqrt(i['cov'][0,0]);p=float(np.mean(np.abs(ts)>=abs(tobs)-1e-10));en={'all_sign_patterns':S.shape[1],'enumerated_restricted_wild_p':p,'t_observed':float(tobs),'note':'Exhaustive wild-cluster sign enumeration under the bootstrap null, not a randomized-treatment test.'};(O/'enumerated_wild_inference.json').write_text(json.dumps(en,indent=2))
rows=[]
for prov in sorted(d.province.unique()):
 z=d[d.province.ne(prov)];rr,ii=e.fit(z,outcome='mention',xs=['did'],effects=('firm','sector_year','province_year'),cluster='province',label='Omit province');a=rr.iloc[0].to_dict();a['omitted_province']=prov;rows.append(a)
pd.DataFrame(rows).to_csv(O/'leave_one_province_out.csv',index=False)
# Pre-policy covariate balance; descriptive standardized differences, not hypothesis testing.
bas=d.drop_duplicates('code');rows=[]
for col in ['logassets2019','DA_lev','ROA']:
 a=bas.loc[bas.treated.eq(1),col];b0=bas.loc[bas.treated.eq(0),col];rows.append({'covariate':col,'treated_mean_standardized':a.mean(),'control_mean_standardized':b0.mean(),'standardized_difference':(a.mean()-b0.mean())/np.sqrt((a.var(ddof=1)+b0.var(ddof=1))/2)})
pd.DataFrame(rows).to_csv(O/'baseline_balance.csv',index=False)
# LSEG overlap of the independently identified China treatment sample.
lm=pd.DataFrame(columns=['code','treated'])
if (P.parent/'lseg/2000_2025/environment_energy_metrics.parquet').exists() and (P.parent/'results/analysis_panel_private.parquet').exists():
 raw=pd.read_parquet(P.parent/'lseg/2000_2025/environment_energy_metrics.parquet');ids=raw.loc[raw.country.eq('China'),['organization_id','ric']].drop_duplicates();ids['code']=ids.ric.str.extract(r'^(\d{6})\.(?:SZ|SS)$');ids=ids.dropna(subset=['code']).drop_duplicates(['organization_id','code']);lseg=pd.read_parquet(P.parent/'results/analysis_panel_private.parquet').query("country=='China'");lm=lseg.merge(ids,on='organization_id').merge(bas[['code','treated']],on='code');lm=lm[lm.year.isin([2017,2018,2019,2021,2022,2023])];lm.to_csv(O/'lseg_overlap_panel_private.csv',index=False)
# Freeze source and analysis fingerprints, including prospective protocol amendment.
files=[P/'china_2021_protocol.json',P/'china_2021_protocol_amendment.json',P/'cninfo/complete_download_manifest.csv',P/'cninfo/extracted_pages.csv',P/'official_2225_entities.csv',O/'primary_estimation_panel.csv'];(O/'file_hashes.json').write_text(json.dumps({str(f.relative_to(P)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files},indent=2))
print('ENUMERATION',en);print('LEAVE ONE',pd.DataFrame(rows).to_string(index=False));loo=pd.read_csv(O/'leave_one_province_out.csv');print('LOO range',loo.beta.min(),loo.beta.max(),'maxp',loo.p.max());print('LSEG overlap',len(lm),lm.code.nunique(),lm[lm.treated.eq(1)].code.nunique());print('BALANCE',pd.read_csv(O/'baseline_balance.csv').to_string(index=False))
