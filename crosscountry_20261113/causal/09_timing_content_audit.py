"""Post-primary timing and semantic validation. No re-selection for significance.
Run --prepare once (network), then --timing to regenerate published timing outputs.
Semantic judgments are inspectable source-page decisions, not a second human rater.
"""
from pathlib import Path
import argparse, json, hashlib, urllib.request, concurrent.futures, importlib.util, re, http.client
import numpy as np
import pandas as pd
import fitz
P=Path(__file__).resolve().parent; B=P.parent; A=P/'submission_audit'; A.mkdir(exist_ok=True)
Q=P/'results'; PDF=P/'cninfo/pdf'; PDF.mkdir(exist_ok=True)
def module(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
est=module('est',B/'02_analyze.py')
nf=module('nf',B/'raw/china_replication/src/rescan_namefilter.py')
rr=module('rr',B/'raw/china_replication/src/rescan_restricted.py')
main=pd.read_csv(Q/'primary_estimation_panel.csv',dtype={'code':str,'firm':str})
meta=pd.read_csv(P/'cninfo/report_manifest.csv',dtype={'code':str})
def select():
 if (A/'semantic_selection.csv').exists():
  return pd.read_csv(A/'semantic_selection.csv',dtype={'code':str,'firm':str})
 d=main.copy();d['period']=np.where(d.year.le(2019),'2017-2019','2021-2023')
 d['order']=d.apply(lambda z:hashlib.sha256(f'20261113-semantic|{z.code}|{z.year}'.encode()).hexdigest(),axis=1)
 rows=[]
 for (t,per,pos),g in d.groupby(['treated','period','mention']):
  n=(12 if t==1 and per=='2021-2023' else len(g)) if pos else 6
  rows.append(g.sort_values('order').head(n))
 s=pd.concat(rows).sort_values('order').reset_index(drop=True);s['audit_id']=[f'A{i:03}' for i in range(1,len(s)+1)]
 s.to_csv(A/'semantic_selection.csv',index=False)
 protocol={'date':'2026-11-13','status':'Post-primary; selection rules fixed before new source-page coding',
 'selection':'Census of three pre-period positives and seven comparison post positives; hash-first twelve treated post positives; hash-first six negatives in each arm-period stratum.',
 'seed_string':'20261113-semantic','unit':'report','n':len(s),
 'categories':{'G':'Generic carbon-market/accounting policy, without firm-specific participation details','F':'Firm-specific carbon-market participation, compliance or management information, without reported allowance amounts','Q':'Firm-specific allowance balances, acquisitions, surrender or transactions with quantitative amounts in tonnes or currency','0':'No carbon-market information located in the reviewed passages','U':'Unresolved; must not be counted as validated'},
 'coding':'Highest supported category Q>F>G>0, with source pages and decision rationale. Carbon goals, general emissions and a company name alone are outside the market-content construct.',
 'search_scope':'Every PDF page scanned with a broader carbon/allowance/trading expression; contextual passages reviewed. Negative review is search-assisted, not exhaustive independent human reading.',
 'blinding':'Coding packets omit treatment and extracted outcome columns; company/year may be inferred from report text. One AI-assisted review, no independent human raters or inter-rater reliability claim.',
 'inference':'Diagnostic selected sample; not an estimate of population numerical-disclosure prevalence or an exhaustive false-negative rate. Original primary indicator and model are retained unless verified extraction errors require correction.'}
 (A/'semantic_protocol.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2))
 return s
def fetch(r):
 p=PDF/f'{r["code"]}_{r["year"]}.pdf'
 try:
  if not p.exists():
   # Bounded verified byte ranges avoid truncated full-file responses.
   chunks=[];offset=0;total=None
   while total is None or offset<total:
    end=offset+524287 if total is None else min(offset+524287,total-1)
    req=urllib.request.Request(r['url'],headers={'User-Agent':'Mozilla/5.0','Referer':'https://www.cninfo.com.cn/','Range':f'bytes={offset}-{end}'})
    for attempt in range(3):
     try:
      with urllib.request.urlopen(req,timeout=40) as z:
       cr=z.headers.get('Content-Range','');status=z.status
       try:piece=z.read()
       except http.client.IncompleteRead as err:
        if status!=206:raise
        piece=err.partial
      if status==200 and offset==0:chunks=[piece];offset=len(piece);total=offset;break
      match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',cr)
      if not match or int(match[1])!=offset or not 0<len(piece)<=int(match[2])+1-offset:raise ValueError('Invalid byte range')
      total=int(match[3]);chunks.append(piece);offset+=len(piece);break
     except Exception:
      if attempt==2:raise
   b=b''.join(chunks)
   if not b.startswith(b'%PDF'):raise ValueError('not PDF')
   p.write_bytes(b)
  b=p.read_bytes()
  with fitz.open(p) as doc:
   chars=0;hits=[]
   for i,page in enumerate(doc,1):
    txt=page.get_text();chars+=len(txt.strip())
    if rr.classify(txt)=='hit' and nf.page_hits(txt):hits.append(i)
   if chars<5000:raise ValueError('insufficient text')
   return {**r,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'pages':len(doc),'n_chars':chars,'new_hits':len(hits),'hit_pages':';'.join(map(str,hits)),'error':''}
 except Exception as e:return {**r,'error':str(e)}
def prepare():
 s=select();t=meta[meta.year.eq(2020)&meta.code.isin(main.code)].copy();t['filing_date']=pd.to_datetime(t.timestamp,unit='ms',utc=True)
 t['before_launch']=t.filing_date.lt('2021-07-16');t.to_csv(A/'transition_metadata.csv',index=False)
 tasks=pd.concat([s[['code','year','url']],t.loc[t.before_launch,['code','year','url']]]).drop_duplicates(['code','year']).to_dict('records')
 out=[];cached={}
 if (A/'source_reconstruction.csv').exists():
  previous=pd.read_csv(A/'source_reconstruction.csv',dtype={'code':str}).fillna({'error':''})
  cached={(r['code'],r['year']):r for r in previous.to_dict('records') if not r['error'] and (PDF/f'{r["code"]}_{r["year"]}.pdf').exists()}
 todo=[r for r in tasks if (r['code'],r['year']) not in cached]
 out=[cached[(r['code'],r['year'])] for r in tasks if (r['code'],r['year']) in cached]
 with concurrent.futures.ThreadPoolExecutor(6) as ex:
  for i,r in enumerate(ex.map(fetch,todo),1):
   out.append(r)
   pd.DataFrame(out).to_csv(A/'source_reconstruction.csv',index=False)
   if i%5==0:print('source audit',len(out),'/',len(tasks),'errors',sum(bool(x['error']) for x in out),flush=True)
 pd.DataFrame(out).to_csv(A/'source_reconstruction.csv',index=False)
 if any(r['error'] for r in out):raise RuntimeError('Source failures: inspect source_reconstruction.csv; do not silently exclude')
 print('PREPARED',len(tasks),flush=True)
 # Broader search independent of the restricted source dictionary.
 broad=re.compile(r'碳|排放[权權]|排[污放]配[额額]|温室[气氣][体體]|\b(?:ETS|CEA|CCER)\b',re.I)
 evidence=[];packets=[]
 for r in s.to_dict('records'):
  chunks=[]
  with fitz.open(PDF/f'{r["code"]}_{r["year"]}.pdf') as doc:
   for i,page in enumerate(doc,1):
    text=page.get_text();matches=list(broad.finditer(text))
    intervals=[]
    for m in matches:
     # Exclude clearly chemical carbon materials only from the compact packet, not evidence CSV.
     a=max(0,m.start()-150);b=min(len(text),m.end()+350)
     if intervals and a<=intervals[-1][1]:intervals[-1][1]=max(b,intervals[-1][1])
     else:intervals.append([a,b])
    for a,b in intervals:
     passage=text[a:b]
     evidence.append({'audit_id':r['audit_id'],'page':i,'text':passage})
     if re.search(r'碳.{0,4}(?:交易|排放|配额|配額|资产|資產|中和|减排)|排放[权權]|温室[气氣][体體]|\b(?:ETS|CEA|CCER)\b',re.sub(r'\s+','',passage),re.I):chunks.append(f'PAGE {i}: '+passage)
  packets.append({'audit_id':r['audit_id'],'passages':chunks})
 pd.DataFrame(evidence).to_csv(A/'semantic_source_passages.csv',index=False)
 (A/'semantic_coding_packets.json').write_text(json.dumps(packets,ensure_ascii=False,indent=2))
 print('PACKETS',len(packets),sum(len(x['passages']) for x in packets),flush=True)
def timing():
 t=pd.read_csv(A/'transition_metadata.csv',dtype={'code':str});v=pd.read_csv(A/'source_reconstruction.csv',dtype={'code':str});v=v[v.year.eq(2020)]
 t=t[t.before_launch].merge(v[['code','year','new_hits','sha256','error']],on=['code','year'],validate='one_to_one');assert len(t)==77 and t.error.isna().all()
 old=pd.read_csv(B/'raw/china_replication/out/carbon_disclosure_namefilt.csv',dtype={'code':str});t=t.merge(old[['code','year','n_hit_namefilt']],on=['code','year'],validate='one_to_one');t['presence_matches_archive']=t.new_hits.gt(0).eq(t.n_hit_namefilt.gt(0));t.to_csv(A/'transition_source_validation.csv',index=False)
 base=main.drop_duplicates('code')[['code','firm','country','treated','province','industry']]
 t=t.merge(base,on='code',validate='one_to_one');t['mention']=t.new_hits.gt(0).astype(float);t['sector_year']=t.industry+'|2020';t['province_year']=t.province+'|2020';t['post']=0;t['did']=0
 d=pd.concat([main,t],ignore_index=True);xs=[]
 for year in [2017,2018,2020,2021,2022,2023]:
  k=f'event_{year}';d[k]=d.treated*d.year.eq(year);xs.append(k)
 ev,info=est.fit(d,outcome='mention',xs=xs,effects=('firm','sector_year','province_year'),cluster='province',label='Transition event study, reference 2019')
 from scipy.stats import t as td
 crit=td.ppf(1-.05/(2*len(xs)),info['G']-1);ev['sim_lo']=ev.beta-crit*ev.se;ev['sim_hi']=ev.beta+crit*ev.se;ev.to_csv(Q/'transition_event_study.csv',index=False)
 rows=[]
 for label,years in [('2020 baseline versus 2021-2023',[2020,2021,2022,2023]),('2019 baseline versus 2021-2023, same firms',[2019,2021,2022,2023]),('Original periods, same firms',[2017,2018,2019,2021,2022,2023])]:
  a=d[d.code.isin(t.code)&d.year.isin(years)].copy();a['did']=a.treated*a.year.ge(2021)
  r,inf=est.fit(a,outcome='mention',xs=['did'],effects=('firm','sector_year','province_year'),cluster='province',label=label);rows.append(r)
 pd.concat(rows).to_csv(Q/'transition_baseline_sensitivity.csv',index=False)
 summary={'status':'post-primary exploratory timing sensitivity','main_sample':80,'timing_valid_transition_reports':77,'treated':int(t.treated.sum()),'controls':int((1-t.treated).sum()),'late_reports_excluded':2,'missing_source_2020':1,'reconstructed_matches':int(t.presence_matches_archive.sum()),'source_reports_reconstructed':len(t),'interpretation':'2017 framework, 2020 accounting rules and December 2020 allocation precede July 2021 trading. The 2020 baseline is already exposed to preparations and allocation; its contrast is incremental, not an untreated-baseline ATT.'}
 (Q/'transition_audit.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary));print(pd.concat(rows)[['model','beta','lo','hi','p','n','firms']].to_string(index=False))
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--prepare',action='store_true');ap.add_argument('--timing',action='store_true');args=ap.parse_args()
 if args.prepare:prepare()
 if args.timing:timing()
