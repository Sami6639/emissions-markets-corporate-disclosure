"""Build an audit-ready disclosure panel. No outcome regressions in this stage."""
from pathlib import Path
import pandas as pd
import numpy as np
import json, hashlib, datetime, re

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'results'; OUT.mkdir(exist_ok=True)
RAW=ROOT/'raw'; SRC=ROOT/'lseg'/'2000_2025'
aliases={'United States of America':'United States','Korea; Republic (S. Korea)':'South Korea','Russian Federation':'Russia','Turkey':'Türkiye','Czech Republic':'Czechia','Slovak Republic':'Slovakia','Vietnam':'Viet Nam'}
EU2005=['Austria','Belgium','Cyprus','Czechia','Denmark','Estonia','Finland','France','Germany','Greece','Hungary','Ireland','Italy','Latvia','Lithuania','Luxembourg','Malta','Netherlands','Poland','Portugal','Slovakia','Slovenia','Spain','Sweden','United Kingdom']
EUother={'Bulgaria':2007,'Romania':2007,'Croatia':2013,'Iceland':2008,'Liechtenstein':2008,'Norway':2005}
EUFAMILY=set(EU2005)|set(EUother)|{'Switzerland'}
frames=[]
for name in ['environment_energy_metrics.parquet','reported_emissions.parquet']:
 d=pd.read_parquet(SRC/name);d['input_file']=name;frames.append(d)
d=pd.concat(frames,ignore_index=True)
d['country']=d.country.replace(aliases)
d['date']=pd.to_datetime(d.period_end,errors='coerce')
d['calendar_year']=d.date.dt.year
key=['organization_id','fiscal_year','field']
# Exact field values and fiscal endpoints must agree across duplicate instruments.
dups=d.groupby(key,dropna=False).agg(n=('field','size'),nv=('value_text','nunique'),np=('period_end','nunique'))
bad=dups[(dups.nv>1)|(dups.np>1)].reset_index()
bad.to_csv(OUT/'conflicting_field_keys.csv',index=False)
if len(bad):
 d=d.merge(bad[key].assign(conflict=1),on=key,how='left');d=d[d.conflict.isna()].drop(columns='conflict')
d=d.sort_values(['organization_id','fiscal_year','field','ric'],na_position='last').drop_duplicates(key)
idcols=['organization_id','name','country','economic_sector','industry_group','isin','lei','ric']
idconf=d.groupby('organization_id')[['country','economic_sector','industry_group']].nunique(dropna=True)
unstable=idconf[(idconf>1).any(axis=1)].index.tolist()
idconf.loc[unstable].to_csv(OUT/'ambiguous_identity_counts.csv')
identity=d.sort_values('fiscal_year').groupby('organization_id')[idcols[1:]].last().reset_index()
identity.to_csv(OUT/'organization_identity_private.csv',index=False)
fykey=['organization_id','fiscal_year']
periods=d.groupby(fykey).agg(date=('date','first'),date_n=('date','nunique'))
pv=d.pivot(index=fykey,columns='field',values='value_numeric')
pt=d.pivot(index=fykey,columns='field',values='value_text')
panel=periods.join(pv.add_prefix('num_')).join(pt[['TR.PolicyWaterEfficiency','TR.PolicyEnergyEfficiency']].add_prefix('txt_')).reset_index().merge(identity,on='organization_id',validate='many_to_one')
panel['end_year']=panel.date.dt.year
panel['year']=panel.fiscal_year
panel['anchor_water']=panel['txt_TR.PolicyWaterEfficiency'].isin(['True','False'])
panel['anchor_energy']=panel['txt_TR.PolicyEnergyEfficiency'].isin(['True','False'])
panel['valid_period']=(panel.date_n==1)&panel.year.between(2002,2024)&(panel.end_year-panel.fiscal_year).isin([0,1])
panel['valid_identity']=~panel.organization_id.isin(unstable)&panel.country.notna()&panel.economic_sector.notna()&panel.industry_group.notna()
panel['nonfinancial']=~panel.economic_sector.eq('Financials')
scopes={'s1':'TR.CO2DirectScope1','s2':'TR.CO2IndirectScope2','s3':'TR.CO2IndirectScope3','total':'TR.CO2EmissionTotal'}
for name,field in scopes.items():
 v=panel['num_'+field];panel[name]=np.isfinite(v)&(v>=0)
panel['s12']=panel.s1&panel.s2
panel['s123']=panel.s1&panel.s2&panel.s3
panel['scope_count']=panel[['s1','s2','s3']].sum(axis=1)
panel['intensive']=panel.economic_sector.isin(['Energy','Basic Materials','Utilities']).astype(int)
panel['policy_cluster']=panel.country.where(~panel.country.isin(EUFAMILY),'European ETS family')
panel['is_europe']=panel.country.isin(EUFAMILY)
panel['firm']=panel.organization_id.astype(str)
panel['industry_year']=panel.industry_group.astype(str)+'|'+panel.year.astype(str)
panel['country_year']=panel.country.astype(str)+'|'+panel.year.astype(str)

# Reconstruct annual country regulatory context from the World Bank instrument archive.
wb=RAW/'worldbank_carbon_pricing_2026.xlsx'
meta=pd.read_excel(wb,sheet_name='Compliance_Gen Info',header=4)
em=pd.read_excel(wb,sheet_name='Compliance_Emissions',header=2).set_index('Name of the initiative')
meta.to_csv(OUT/'worldbank_instrument_metadata.csv',index=False)
country_alias={"Korea, Rep.":'South Korea','Taiwan, China':'Taiwan','Czech Republic':'Czechia','Slovak Republic':'Slovakia','Russian Federation':'Russia','United States of America':'United States'}
nat_ets={'Australia':['Australia CPM','Australia Safeguard Mechanism'],'Canada':['Canada federal OBPS'],'China':['China national ETS'],'Indonesia':['Indonesia ETS'],'Kazakhstan':['Kazakhstan ETS'],'South Korea':['Korea ETS'],'Mexico':['Mexico ETS'],'New Zealand':['New Zealand ETS'],'Switzerland':['Switzerland ETS'],'Montenegro':['Montenegro ETS']}
subs={'United States':['ETS_US_','ETS_RGGI'],'China':['ETS_CN_'],'Canada':['ETS_CA_'],'Japan':['ETS_JP_'],'Russia':['ETS_RU_']}
def active(name,y):
 if name not in em.index or y not in em.columns:return False
 z=em.loc[name,y]
 if isinstance(z,pd.Series):z=z.max()
 return bool(pd.notna(z) and z>0)
pol=[]
for country in sorted(panel.country.dropna().unique()):
 for y in range(2002,2025):
  names=[];subnames=[];taxnames=[]
  if country in EU2005 and y>=2005:names=['EU ETS' if country!='United Kingdom' or y<=2020 else 'UK ETS']
  if country in EUother and y>=EUother[country]:names=['Norway national ETS' if country=='Norway' and y<2008 else 'EU ETS']
  for name in nat_ets.get(country,[]):
   if active(name,y):names.append(name)
  # The coverage series retains MRV years during the Kazakhstan trading suspension.
  if country=='Kazakhstan' and y in [2016,2017]:names=[]
  for _,r in meta.iterrows():
   uid=str(r['Unique ID']);name=str(r['Instrument name']);jur=country_alias.get(str(r['Jurisdiction covered']).strip(),str(r['Jurisdiction covered']).strip())
   if r['Type']=='Carbon tax' and jur==country and active(name,y):taxnames.append(name)
   if r['Type']=='ETS' and any(uid.startswith(pre) for pre in subs.get(country,[])) and active(name,y):subnames.append(name)
  # Japan's voluntary GX pilot is distinguished from mandatory ETS context (starts 2026).
  voluntary=int(country=='Japan' and y>=2023)
  pol.append(dict(country=country,year=y,national_ets=int(bool(names)),subnational_ets=int(bool(subnames)),carbon_tax=int(bool(taxnames)),voluntary_ets=voluntary,national_instruments='; '.join(names),subnational_instruments='; '.join(subnames),tax_instruments='; '.join(taxnames)))
policy=pd.DataFrame(pol);policy.to_csv(OUT/'country_year_policy.csv',index=False)
panel=panel.merge(policy,on=['country','year'],how='left',validate='many_to_one')
panel['context']=np.select([panel.national_ets.eq(1),panel.subnational_ets.eq(1)],['National or supranational ETS','Subnational ETS only'],default='No mandatory ETS recorded')
panel['ets_intensive']=panel.national_ets*panel.intensive

# WDI country identification, with explicit spelling concordance.
md=json.loads((RAW/'wdi/country_metadata.json').read_text())[1]
md=[x for x in md if x['region']['id']!='NA']
wdi_names={x['name']:x['id'] for x in md}
iso_alias={'South Korea':'Korea, Rep.','Russia':'Russian Federation','Egypt':'Egypt, Arab Rep.','Iran':'Iran, Islamic Rep.','Taiwan':None,'Hong Kong':'Hong Kong SAR, China','Macau':'Macao SAR, China','Slovakia':'Slovak Republic','Kyrgyzstan':'Kyrgyz Republic','Venezuela':'Venezuela, RB','Türkiye':'Turkiye'}
wdi_names['Turkiye']='TUR'
panel['iso3']=panel.country.map(lambda c:wdi_names.get(iso_alias.get(c,c)))
pd.DataFrame({'country':sorted(panel.country.dropna().unique())}).assign(iso3=lambda z:z.country.map(lambda c:wdi_names.get(iso_alias.get(c,c)))).to_csv(OUT/'country_concordance.csv',index=False)
for indicator,newname in [('NY.GDP.PCAP.KD','gdp_pc'),('NY.GDP.MKTP.KD.ZG','gdp_growth')]:
 rows=[]
 csvs=list((RAW/'wdi'/indicator).glob('API_*.csv'))
 if csvs:
  bulk=pd.read_csv(csvs[0],skiprows=4)
  for _,r in bulk.iterrows():
   for year in range(2002,2025):rows.append({'iso3':r['Country Code'],'year':year,newname:r.get(str(year))})
 for fp in sorted((RAW/'wdi').glob(indicator+'*.json')):
  j=json.loads(fp.read_text());assert isinstance(j,list) and len(j)==2,fp
  assert j[0]['pages']==1,fp
  rows.extend([{'iso3':x['countryiso3code'],'year':int(x['date']),newname:x['value']} for x in j[1]])
 if rows:
  m=pd.DataFrame(rows).drop_duplicates(['iso3','year']);panel=panel.merge(m,on=['iso3','year'],how='left',validate='many_to_one')
 else:panel[newname]=np.nan
panel['ln_gdp_pc']=np.log(panel.gdp_pc.where(panel.gdp_pc>0))
eligible=panel.valid_period&panel.valid_identity&panel.nonfinancial
primary=panel[eligible&panel.anchor_water].copy()
alternative=panel[eligible&(panel.anchor_water|panel.anchor_energy)].copy()
keep=['organization_id','firm','fiscal_year','year','end_year','date','name','country','iso3','economic_sector','industry_group','policy_cluster','is_europe','industry_year','country_year','anchor_water','anchor_energy','s1','s2','s3','s12','s123','total','scope_count','intensive','ets_intensive','national_ets','subnational_ets','carbon_tax','voluntary_ets','context','gdp_pc','ln_gdp_pc','gdp_growth']
primary[keep].to_parquet(OUT/'analysis_panel_private.parquet',index=False)
alternative[keep].to_parquet(OUT/'alternative_frame_private.parquet',index=False)
audit={
 'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'source_rows':sum(len(x) for x in frames),'unique_field_keys':len(d),'conflicting_field_keys':len(bad),'duplicate_field_keys':int((dups.n>1).sum()),'ambiguous_organizations':unstable,
 'candidate_firm_years':len(panel),'period_conflicts':int((panel.date_n!=1).sum()),'eligible_nonfinancial_firm_years':int(eligible.sum()),'primary_n':len(primary),'primary_firms':primary.firm.nunique(),'primary_countries':primary.country.nunique(),'china_n':int(primary.country.eq('China').sum()),'china_firms':primary.loc[primary.country.eq('China'),'firm'].nunique(),'policy_clusters':primary.policy_cluster.nunique(),'wdi_missing':int(primary[['ln_gdp_pc','gdp_growth']].isna().any(axis=1).sum()),
 'firm_fiscal_year_duplicates':int(primary.duplicated(['firm','year']).sum()),'fiscal_end_calendar_year_offsets':int(primary.end_year.ne(primary.year).sum()),'years':[int(primary.year.min()),int(primary.year.max())],
 'unit_counts':d[d.field.isin(scopes.values())].groupby(['field','unit'],dropna=False).size().astype(int).to_dict().__str__(),
 'negative_scope_records':{name:int((d.loc[d.field.eq(field),'value_numeric']<0).sum()) for name,field in scopes.items()},
 'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [SRC/'environment_energy_metrics.parquet',SRC/'reported_emissions.parquet',wb,ROOT/'analysis_protocol.json']}
}
(OUT/'preparation_audit.json').write_text(json.dumps(audit,indent=2))
print(json.dumps(audit,indent=2))
print(primary.groupby('country').agg(firms=('firm','nunique'),n=('firm','size'),s12=('s12','mean'),s3=('s3','mean')).to_string())
