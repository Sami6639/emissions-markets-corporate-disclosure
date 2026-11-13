"""Regenerate the four main-paper figures from published analysis outputs."""
from pathlib import Path
import shutil
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT = Path(__file__).resolve().parent
P = ROOT / 'crosscountry_20261113'
C = P / 'causal'
Q = C / 'results'
I = ROOT / 'manuscript_20261113/analysis/pollution_markets_rct_20261112/results'
A = ROOT / 'manuscript_20261113/audit_results'
O = ROOT / 'figures'
O.mkdir(exist_ok=True)
ir = pd.read_csv(I / 'evidence_outcome_estimates.csv')
ia = pd.read_csv(A / 'measurement_sensitivity.csv')
transition = pd.read_csv(Q / 'transition_event_study.csv')
reg = pd.read_csv(P / 'results/regional_annual_disclosure.csv')
last = reg[reg.year.eq(2024)]
def E(out='observed', scope='all_active_13', assignment='Z', adjust=True):
    return ir[(ir.scope==scope)&(ir.outcome==out)&(ir.assignment==assignment)&(ir.adjusted==adjust)].iloc[0]
def U(out, scope='all_13', model='additive'):
    return ia[(ia.scope==scope)&(ia.outcome==out)&(ia.model==model)].iloc[0]
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42})
def savefig(fig,n):
 fig.savefig(O/f'Figure_{n}.png',dpi=250,bbox_inches='tight');fig.savefig(O/f'Figure_{n}.pdf',bbox_inches='tight');plt.close(fig)
z=[E(),U('raw_hours_share'),U('valid_hours_share'),E('documented_below_1000')];fig,ax=plt.subplots(figsize=(7.1,3.8));y=np.arange(4);v=np.array([a.coefficient for a in z])*100
ax.errorbar(v,y,xerr=np.array([[a.coefficient-a.lo for a in z],[a.hi-a.coefficient for a in z]])*100,fmt='o',color='#164B72',capsize=4);ax.set_yticks(y,['Monthly estimate available','Raw monitoring hours','Valid calibrated hours','Available estimate ≤1,000 kg']);ax.invert_yaxis();ax.axvline(0,color='.5',lw=.8);ax.set_xlim(0,37);ax.set_xlabel('Assignment effect (percentage points; 95% interval)');ax.grid(axis='x',alpha=.15);fig.tight_layout();savefig(fig,1)
for n,name in [(2,'China_Reporting_Trajectories'),(3,'China_Event_Study')]:
 for ext in ['png','pdf']:shutil.copy2(C/'figures'/f'{name}.{ext}',O/f'Figure_{n}.{ext}')
# Show the previously omitted transition year as a diagnostic; do not replace the primary coefficient.
te=transition.copy();te['year']=te.term.str.extract(r'(\d+)$').astype(int)
fig,ax=plt.subplots(figsize=(7.1,4.2));ax.axhline(0,color='.45',lw=.8);ax.axvspan(2019.6,2020.4,color='.93')
ax.errorbar(te.year,te.beta*100,yerr=np.vstack([(te.beta-te.sim_lo)*100,(te.sim_hi-te.beta)*100]),fmt='none',ecolor='#B6C6D1',capsize=4,lw=1.8,label='95% simultaneous intervals')
ax.errorbar(te.year,te.beta*100,yerr=np.vstack([(te.beta-te.lo)*100,(te.hi-te.beta)*100]),fmt='o',color='#164B72',capsize=3,lw=2,label='95% pointwise intervals')
tr=te[te.year.eq(2020)];ax.scatter(tr.year,tr.beta*100,color='#BD613A',s=36,zorder=5);ax.scatter([2019],[0],marker='s',color='black',s=22)
ax.set_xticks(range(2017,2024));ax.set_ylabel('Change relative to FY2019 (percentage points)');ax.set_xlabel('Financial year; FY2020 filings predate trading launch');ax.legend(frameon=False,fontsize=9,loc='upper left');ax.grid(axis='y',alpha=.15);fig.tight_layout();savefig(fig,3)
fig,ax=plt.subplots(figsize=(7.1,3.9));g=last.copy();x=np.arange(len(g));w=.34
for off,col,label,color in [(-w/2,'s12','Scopes 1 and 2','#164B72'),(w/2,'s3','Scope 3','#BD613A')]:
 bars=ax.bar(x+off,g[col]*100,w,label=label,color=color)
 for bar in bars:ax.text(bar.get_x()+bar.get_width()/2,bar.get_height()+1,f'{bar.get_height():.1f}',ha='center',fontsize=9)
ax.set_xticks(x,[str(s).replace('European ETS family','European ETS\nfamily').replace('Other jurisdictions','Other\njurisdictions') for s in g.region]);ax.set_ylim(0,112);ax.set_ylabel('Archive field coverage (%)');ax.legend(frameon=False,loc='upper center',bbox_to_anchor=(.5,1.17),ncol=2);ax.grid(axis='y',alpha=.15);fig.tight_layout();savefig(fig,4)
