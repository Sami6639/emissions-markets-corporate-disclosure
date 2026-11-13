from pathlib import Path
import pandas as pd,urllib.request,concurrent.futures,time,hashlib
P=Path(__file__).resolve().parent;R=P/'cninfo';s=pd.read_csv(P/'china_2021_design_sample.csv',dtype={'code':str});valid=set()
for t in [0,1]:valid.update(s[s.treated.eq(t)].sort_values('code').code.head(10))
m=pd.read_csv(R/'report_manifest.csv',dtype={'code':str});m=m[m.year.isin([2017,2018])|(m.code.isin(valid)&m.year.isin([2019,2021]))]
import sys
if len(sys.argv)>1:m=m.head(int(sys.argv[1]))
todo=m[~m.apply(lambda x:(R/'pdf'/f'{x.code}_{x.year}.pdf').exists(),axis=1)].copy()
def fetch(r):
 f=R/'pdf'/f'{r.code}_{r.year}.pdf';t=time.time()
 if f.exists():return {'code':r.code,'year':r.year,'status':'already present'}
 try:
  b=urllib.request.urlopen(urllib.request.Request(r.url,headers={'User-Agent':'Mozilla/5.0','Referer':'https://www.cninfo.com.cn/'}),timeout=75).read();assert b.startswith(b'%PDF');f.write_bytes(b);return {'code':r.code,'year':r.year,'status':'ok','bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'seconds':time.time()-t}
 except Exception as e:return {'code':r.code,'year':r.year,'status':repr(e),'seconds':time.time()-t}
res=[]
with concurrent.futures.ThreadPoolExecutor(4) as ex:
 for i,r in enumerate(ex.map(fetch,todo.itertuples()),1):
  res.append(r);print(i,'/',len(todo),r,flush=True)
pd.DataFrame(res).to_csv(R/'retry_results.csv',index=False)
