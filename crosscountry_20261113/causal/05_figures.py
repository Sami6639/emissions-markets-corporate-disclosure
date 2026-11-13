from pathlib import Path
import pandas as pd,numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
P=Path(__file__).resolve().parent; O=P/'results';F=P/'figures';F.mkdir(exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'savefig.dpi':300,'pdf.fonttype':42})
blue='#164B72';orange='#BD613A'
def save(fig,name):
 fig.savefig(F/(name+'.png'),bbox_inches='tight',dpi=300);fig.savefig(F/(name+'.pdf'),bbox_inches='tight');plt.close(fig)
e=pd.read_csv(O/'event_study.csv');e['year']=e.term.str.extract(r'(\d+)$').astype(int)
fig,ax=plt.subplots(figsize=(7,4.4));ax.axhline(0,color='0.45',lw=.8);ax.axvspan(2019.6,2020.4,color='0.93');ax.text(2020,.98,'Transition\nexcluded',transform=ax.get_xaxis_transform(),ha='center',va='top',fontsize=8)
ax.errorbar(e.year,e.beta*100,yerr=np.vstack([(e.beta-e.sim_lo)*100,(e.sim_hi-e.beta)*100]),fmt='none',ecolor='#B6C6D1',capsize=4,lw=1.8,label='95% simultaneous intervals')
ax.errorbar(e.year,e.beta*100,yerr=np.vstack([(e.beta-e.lo)*100,(e.hi-e.beta)*100]),fmt='o',color=blue,capsize=3,lw=2,label='95% pointwise intervals');ax.scatter([2019],[0],color='black',marker='s',s=22);ax.set_xticks(range(2017,2024));ax.set_ylabel('Change relative to FY2019 (percentage points)');ax.set_xlabel('Financial year of annual report');ax.legend(loc='best',frameon=False,fontsize=9);ax.grid(axis='y',alpha=.15);fig.tight_layout();save(fig,'China_Event_Study')
g=pd.read_csv(O/'group_year_outcomes.csv');fig,ax=plt.subplots(figsize=(7,4.4))
for tr,label,color in [(1,'Listed on national allocation roster',blue),(0,'Comparison firms',orange)]:
 a=g[g.treated.eq(tr)]
 for yy in [[2017,2018,2019],[2021,2022,2023]]:
  b=a[a.year.isin(yy)];ax.plot(b.year,b.mention*100,'o-',color=color,lw=2,label=label if yy[0]==2017 else None)
ax.set_ylim(0,100);ax.set_xticks(range(2017,2024));ax.axvspan(2019.6,2020.4,color='0.93');ax.set_ylabel('Reports containing carbon-market content (%)');ax.set_xlabel('Financial year of annual report');ax.legend(frameon=False);ax.grid(axis='y',alpha=.15);fig.tight_layout();save(fig,'China_Reporting_Trajectories')
r=pd.read_csv(O/'national_ets_estimates.csv');r=r[r.term.eq('did')];labels=['Primary','Firm clustering','Unbalanced','Restricted dictionary','Baseline covariates by year'];a=r.set_index('model').loc[labels].reset_index();fig,ax=plt.subplots(figsize=(7,4));y=np.arange(len(a));ax.axvline(0,color='0.45',lw=.8);ax.errorbar(a.beta*100,y,xerr=np.vstack([(a.beta-a.lo)*100,(a.hi-a.beta)*100]),fmt='o',color=blue,capsize=3);ax.set_yticks(y,a.model);ax.invert_yaxis();ax.set_xlabel('Estimated effect (percentage points; 95% interval)');ax.grid(axis='x',alpha=.15);fig.tight_layout();save(fig,'China_Estimation_Sensitivity')
print('saved figures',len(list(F.glob('*.pdf'))))
