"""Summarize recorded AI-assisted source-page judgments; never infer labels from effects."""
from pathlib import Path
import json
import pandas as pd
P=Path(__file__).resolve().parent;A=P/'submission_audit';Q=P/'results'
# Decisions fixed from source-page context before joining the original indicator.
decisions={
 1:('0','','No carbon-market passage located in the broader source search.'),
 2:('0','','No carbon-market passage located in the broader source search.'),
 3:('0','','No carbon-market passage located in the broader source search.'),
 4:('0','','No carbon-market passage located in the broader source search.'),
 5:('0','','No carbon-market passage located in the broader source search.'),
 6:('0','','No carbon-market passage located in the broader source search.'),
 7:('Q','138;171;173','Carbon allowance assets, sale income and purchase cash outflows have monetary amounts. No claim of a complete physical allowance reconciliation.'),
 8:('0','','No carbon-market passage located in the broader source search.'),
 9:('0','46','General pesticide-sector policy mentions reducing greenhouse gases, without a carbon-market item.'),
 10:('0','','No carbon-market passage located in the broader source search.'),
 11:('0','','No carbon-market passage located in the broader source search.'),
 12:('0','','No carbon-market passage located in the broader source search.'),
 13:('0','','No carbon-market passage located in the broader source search.'),
 14:('0','','No carbon-market passage located in the broader source search.'),
 15:('0','','No carbon-market passage located in the broader source search.'),
 16:('0','','No carbon-market passage located in the broader source search.'),
 17:('0','','No carbon-market passage located in the broader source search.'),
 18:('0','59;67;127;165','Physical greenhouse-gas reporting and generic pollutant-discharge rights appear, without identified carbon-market content. Non-carbon pollutant rights are outside the construct.'),
 19:('0','','No carbon-market passage located in the broader source search.'),
 20:('Q','176;177;194','Allowance sale income and cash receipts are quantified; related-party disclosures identify an allowance transaction. Carbon-service company names alone are not the basis for this code.'),
 21:('F','38;39','The firm identifies its power facility as covered by national allowance management and distinguishes other activities. Physical emissions are not coded as allowance quantities.'),
 22:('0','','No carbon-market passage located in the broader source search.'),
 23:('0','53','Company greenhouse-gas accounting and internal data-management plans appear without a market-specific participation or allowance item.'),
 24:('G','44;66;73;142;174','Industry outlook links the carbon-trading market to photovoltaic demand. Other passages give physical emissions and non-carbon pollution rights; no company-specific carbon-market transaction is established.'),
 25:('Q','162;173;175','Carbon-emission-right liabilities and expenses are reported in currency. Amounts are reported values, not independently verified obligations.'),
 26:('0','79;198;199','Carbon-asset wording occurs in a related-party service-provider name. Its procurement fee does not establish an allowance transaction; name-only mentions remain excluded.'),
 27:('0','','No carbon-market passage located in the broader source search.'),
 28:('Q','36;42;129;143','The report describes first-cycle compliance and gives allowance shortfalls, purchase quantities, unit prices and transaction amounts. Their accuracy is not certified by this content code.'),
 29:('F','11;12','The company links its process-related carbon savings to prospective trading revenues. This is a company-specific expectation, not evidence of completed transactions.'),
 30:('F','15;74','The report describes opening online carbon trading and identifies a thermal-power facility as a national-market member. No allowance amount is established in the inspected market passages.'),
 31:('Q','176','The allowance-expense line contains a comparative-period monetary amount; content presence is not restricted to a nonzero current-period transaction.'),
 32:('0','','No carbon-market passage located in the broader source search.'),
 33:('0','52','Energy-efficiency upgrades and physical carbon reductions are described without a market-specific item.'),
 34:('Q','185','A carbon-allowance expense is reported in currency in the non-operating expense table.'),
 35:('Q','58;185','Company-specific carbon-market preparations and a monetary receipt from carbon-emission rights are disclosed.'),
 36:('Q','28;190','Carbon-management plans and monetary income and expenses for emission rights are disclosed.'),
 37:('Q','56;192','The report lists an applicable carbon rule and a monetary carbon-emission-right asset item. The code does not interpret this as a complete allowance inventory.'),
 38:('Q','24;69','A voluntary forest-carbon credit purchase of 3036 tonnes is described. This is quantitative carbon-market content, not national-ETS allowance surrender or a complete reconciliation.'),
 39:('F','31','A subsidiary registration includes carbon-emission-right trading in its business scope. Registration is company-specific information but not proof of actual transactions.'),
 40:('G','10','The industry and policy background cites the carbon-trading management rule and its commencement, without a company-specific transaction.'),
 41:('G','62','The carbon-trading management rule is included in a general list of applicable environmental laws.'),
 42:('F','55','The company explicitly states that it is not a covered carbon-trading enterprise. This is company-specific market information, not positive evidence of participation.'),
 43:('F','73','The company describes prospective integration of resource management and carbon trading into its strategy; completed trading is not established.'),
 44:('F','12','The company discusses prospective sales of surplus carbon indicators linked to its production process. The physical process intensity is not an allowance transaction quantity.'),
 45:('G','65','The carbon-trading rule appears in a general list of applicable environmental regulation.'),
 46:('G','10','Industry background attributes energy-storage demand partly to carbon-market pressure; battery output figures are not carbon-market transaction amounts.')}
rows=[{'audit_id':f'A{i:03}','semantic_category':v[0],'reviewed_pdf_pages':v[1],'coding_rationale':v[2],'review_method':'AI-assisted single source-page review; broad text-search scope'} for i,v in decisions.items()]
codes=pd.DataFrame(rows);codes.to_csv(A/'semantic_decisions.csv',index=False)
sel=pd.read_csv(A/'semantic_selection.csv',dtype={'code':str,'firm':str})
source=pd.read_csv(A/'source_reconstruction.csv',dtype={'code':str})
assert len(codes)==46 and set(codes.semantic_category)<=set('0GFQ')
d=sel.drop(columns=['sha256','pages','n_chars','error'],errors='ignore').merge(codes,on='audit_id',validate='one_to_one').merge(source[['code','year','sha256','pages','n_chars','new_hits','error']],on=['code','year'],validate='one_to_one')
assert len(d)==46 and d.error.isna().all()
d['semantic_presence']=d.semantic_category.ne('0').astype(int)
d['source_presence']=d.new_hits.gt(0).astype(int)
d['semantic_agrees']=d.semantic_presence.eq(d.mention)
d['reconstruction_agrees']=d.source_presence.eq(d.mention)
d['numerical_subtype']=d.audit_id.map({'A038':'voluntary forest-carbon credit quantity','A028':'allowance quantities and currency'}).fillna('')
d.loc[d.semantic_category.eq('Q')&d.numerical_subtype.eq(''),'numerical_subtype']='monetary carbon-right or allowance item'
keep=['audit_id','code','year','treated','period','mention','n_hit_namefilt','new_hits','semantic_category','semantic_presence','semantic_agrees','reconstruction_agrees','numerical_subtype','reviewed_pdf_pages','coding_rationale','review_method','url','filing_date','sha256','pages','n_chars']
d[keep].to_csv(A/'semantic_validated_records.csv',index=False)
summary={'status':'post-primary diagnostic, not population accuracy or prevalence','n_reports':len(d),'positive_reviewed':int(d.mention.sum()),'negative_reviewed':int((1-d.mention).sum()),'category_counts':d.semantic_category.value_counts().to_dict(),'positive_by_category':d[d.mention.eq(1)].semantic_category.value_counts().to_dict(),'negative_by_category':d[d.mention.eq(0)].semantic_category.value_counts().to_dict(),'semantic_agreement':int(d.semantic_agrees.sum()),'reconstruction_agreement':int(d.reconstruction_agrees.sum()),'unresolved':0,'independent_human_raters':0,'reviewer_type':'AI assistant; source-page decisions available for author verification','q_interpretation':'Numerical carbon-market item, including one voluntary-credit purchase; not full regulated-allowance reconciliation'}
(Q/'semantic_audit_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
print(json.dumps(summary,ensure_ascii=False,indent=2))
assert d.reconstruction_agrees.all()
# Source review identified and adjudicated these two errors independently of coefficient size.
dis=d[~d.semantic_agrees].copy();assert set(dis.audit_id)=={'A024','A026'}
dis[['audit_id','code','year','mention','semantic_presence','reviewed_pdf_pages','coding_rationale']].to_csv(A/'adjudicated_classification_discrepancies.csv',index=False)
import importlib.util
spec=importlib.util.spec_from_file_location('est',P.parent/'02_analyze.py');est=importlib.util.module_from_spec(spec);spec.loader.exec_module(est)
panel=pd.read_csv(Q/'primary_estimation_panel.csv',dtype={'code':str,'firm':str})
panel['source_mention']=panel.get('archive_mention',panel.mention)
for z in dis.itertuples():
 ix=panel.code.eq(z.code)&panel.year.eq(z.year);assert ix.sum()==1;panel.loc[ix,'mention']=z.semantic_presence
r,info=est.fit(panel,outcome='mention',xs=['did'],effects=('firm','sector_year','province_year'),cluster='province',label='Two source-adjudicated classifications corrected')
w,_=est.restricted_wild_cluster(info,target='did');r['wild_p']=w['p_wcr'];r.to_csv(Q/'semantic_correction_sensitivity.csv',index=False)
panel.to_csv(A/'semantic_corrected_sensitivity_panel.csv',index=False)
summary['adjudicated_false_positive']=1;summary['adjudicated_false_negative']=1;summary['correction_sensitivity']=r.iloc[0].to_dict()
(Q/'semantic_audit_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
print('ERROR-CORRECTED SENSITIVITY',r[['beta','lo','hi','p','wild_p']].to_dict('records'))
