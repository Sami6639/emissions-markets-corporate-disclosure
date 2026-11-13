"""Fetch public CNINFO metadata and pre-period PDFs, without credentials."""
from pathlib import Path
import urllib.request,urllib.parse,json,concurrent.futures,re,time,hashlib
import pandas as pd
P=Path(__file__).resolve().parent; R=P/'cninfo';R.mkdir(exist_ok=True);(R/'pdf').mkdir(exist_ok=True);(R/'metadata').mkdir(exist_ok=True)
H={'User-Agent':'Mozilla/5.0','Referer':'https://www.cninfo.com.cn/'}
def get(url,data=None):
 for k in range(2):
  try:return urllib.request.urlopen(urllib.request.Request(url,headers=H,data=data),timeout=40).read()
  except Exception:
   if k:raise
   time.sleep(1)
reg=R/'register.json'
if not reg.exists():reg.write_bytes(get('https://www.cninfo.com.cn/new/data/szse_stock.json'))
org={str(x['code']).zfill(6):x['orgId'] for x in json.loads(reg.read_text())['stockList']}
s=pd.read_csv(P/'china_2021_design_sample.csv',dtype={'code':str})
def meta(row):
 code=row.code; f=R/'metadata'/f'{code}.json'
 try:
  if not f.exists():
   d=urllib.parse.urlencode({'pageNum':1,'pageSize':30,'column':'sse' if code.startswith('6') else 'szse','tabName':'fulltext','stock':code+','+org[code],'category':'category_ndbg_szsh','seDate':'2018-01-01~2024-12-31'}).encode();f.write_bytes(get('https://www.cninfo.com.cn/new/hisAnnouncement/query',d))
  j=json.loads(f.read_text());a=j.get('announcements') or []
  if (j.get('totalRecordNum') or 0)>len(a):return code,[],f'pagination required {j.get("totalRecordNum")}/{len(a)}'
  best={}
  for q in a:
   title=re.sub('<[^>]+>','',q.get('announcementTitle',''))
   if any(x in title for x in ['摘要','H股','英文','更正','补充','已取消','问询']):continue
   m=re.search(r'(20\d{2})\s*年\s*年?度报告',title)
   if not m:continue
   y=int(m.group(1)); stamp=q.get('announcementTime') or 0
   if y not in range(2017,2024):continue
   if y not in best or stamp>best[y]['timestamp']:
    best[y]={'code':code,'year':y,'timestamp':stamp,'url':'https://static.cninfo.com.cn/'+q['adjunctUrl'],'announcement_id':q['announcementId'],'title':title}
  return code,list(best.values()),None
 except Exception as e:return code,[],repr(e)
rows=[];errs=[]
with concurrent.futures.ThreadPoolExecutor(4) as ex:
 for i,(code,rs,e) in enumerate(ex.map(meta,s.itertuples()),1):
  rows+=rs
  if e:errs.append({'code':code,'stage':'metadata','error':e})
  if i%20==0:print('metadata',i,len(rows),'errors',len(errs),flush=True)
pd.DataFrame(rows).to_csv(R/'report_manifest.csv',index=False)
# Predetermined reproducibility audit: first ten codes per treatment arm, all 2019 and 2021 reports.
validation=set()
for t in [0,1]:validation.update(s[s.treated.eq(t)].sort_values('code').code.head(10))
tasks=[r for r in rows if r['year'] in [2017,2018] or (r['code'] in validation and r['year'] in [2019,2021])]
def pdf(r):
 f=R/'pdf'/f'{r["code"]}_{r["year"]}.pdf'
 try:
  if not f.exists():
   b=get(r['url']);assert b.startswith(b'%PDF');f.write_bytes(b)
  b=f.read_bytes();return {**r,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'file':f.name},None
 except Exception as e:return r,repr(e)
files=[]
with concurrent.futures.ThreadPoolExecutor(4) as ex:
 for i,(r,e) in enumerate(ex.map(pdf,tasks),1):
  if e:errs.append({'code':r['code'],'year':r['year'],'stage':'pdf','error':e})
  else:files.append(r)
  if i%20==0:
   print('pdf',i,'/',len(tasks),'ok',len(files),'errors',len(errs),flush=True);pd.DataFrame(files).to_csv(R/'download_manifest.csv',index=False)
pd.DataFrame(files).to_csv(R/'download_manifest.csv',index=False);pd.DataFrame(errs).to_csv(R/'download_errors.csv',index=False)
print('DONE',len(rows),len(files),len(errs),flush=True)
