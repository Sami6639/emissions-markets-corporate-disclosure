"""Reconstruct source dictionaries unchanged; add preperiod from public PDFs."""
from pathlib import Path
import importlib.util,concurrent.futures,json,hashlib,re
import pandas as pd,fitz
P=Path(__file__).resolve().parent; SRC=P.parent/'raw/china_replication'; R=P/'cninfo'
def load(name,file):
 spec=importlib.util.spec_from_file_location(name,file);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
nf=load('namefilt',SRC/'src/rescan_namefilter.py');rr=load('restricted',SRC/'src/rescan_restricted.py')
registry=pd.read_csv(P/'official_2225_entities.csv'); entity_pattern=re.compile('|'.join(re.escape(x) for x in sorted(registry.entity_name.unique(),key=len,reverse=True)))
def one(p):
 code,year=p.stem.split('_'); rows=[]; hits=[];restr=[]; nchars=0; entity_hits=set()
 try:
  with fitz.open(p) as d:
   npages=len(d)
   for n,page in enumerate(d,1):
    text=page.get_text();nchars+=len(text.strip())
    if int(year)==2018:
     for em in entity_pattern.finditer(re.sub(r'\s+','',text)):
      entity_hits.add(em.group());rows.append({'code':code,'year':int(year),'page':n,'snippet':'ROSTER ENTITY: '+em.group()+' | '+re.sub(r'\s+','',text)[max(0,em.start()-180):em.end()+250]})
    if rr.classify(text)=='hit':
     restr.append(n)
     if nf.page_hits(text):
      hits.append(n)
      for m in nf.KEY.finditer(text):
       if not nf.NAME_TAIL.match(text[m.end():m.end()+24]):
        rows.append({'code':code,'year':int(year),'page':n,'snippet':text[max(0,m.start()-150):m.end()+200]});break
  if nchars<5000:return {'code':code,'year':int(year),'error':'insufficient extractable text','n_chars':nchars},[]
  return {'code':code,'year':int(year),'n_pages':npages,'n_chars':nchars,'n_hit_restricted':len(restr),'n_hit_namefilt':len(hits),'hit_pages_namefilt':';'.join(map(str,hits)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'roster_entities_mentioned':';'.join(sorted(entity_hits))},rows
 except Exception as e:return {'code':code,'year':int(year),'error':repr(e)},[]
if __name__=='__main__':
 out=[];sn=[];files=sorted((R/'pdf').glob('*.pdf'))
 with concurrent.futures.ProcessPoolExecutor(4) as ex:
  for i,(a,b) in enumerate(ex.map(one,files),1):
   out.append(a);sn+=b
   if i%40==0:print('parsed',i,'/',len(files),flush=True)
 d=pd.DataFrame(out);d.to_csv(R/'extracted_pages.csv',index=False);pd.DataFrame(sn).to_csv(R/'flagged_page_snippets.csv',index=False)
 old=pd.read_csv(SRC/'out/carbon_disclosure_namefilt.csv',dtype={'code':str})
 chk=d.merge(old,on=['code','year'],suffixes=('_new','_archive'))
 chk['count_match']=chk.n_hit_namefilt_new.eq(chk.n_hit_namefilt_archive)
 chk['presence_match']=chk.n_hit_namefilt_new.gt(0).eq(chk.n_hit_namefilt_archive.gt(0))
 chk.to_csv(R/'archive_reconstruction_audit.csv',index=False)
 print('AUDIT',len(chk),'count disagreements',int((~chk.count_match).sum()),'presence disagreements',int((~chk.presence_match).sum()),flush=True)
 print('finished',len(d),'errors',int(d.get('error',pd.Series(dtype=str)).notna().sum()),flush=True)
