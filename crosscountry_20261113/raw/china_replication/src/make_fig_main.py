# -*- coding: utf-8 -*-
"""Plot the descriptive figures on market prices, benchmarks and disclosure levels.
"""
import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd, statsmodels.api as sm
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams.update({"font.family":"serif","font.serif":["Times New Roman"],
 "axes.unicode_minus":False,"font.size":9,"axes.linewidth":0.8,
 "xtick.direction":"in","ytick.direction":"in","savefig.dpi":400,"figure.autolayout":True})
BASE=Path(__file__).resolve().parent.parent; OUT=BASE/"out/figures"

d=pd.read_csv(BASE/"out/panel2.csv",dtype={"code":str})
disc=pd.read_csv(BASE/"out/carbon_disclosure.csv",dtype={"code":str})
disc["n_hit"]=disc.hit_pages.fillna("").apply(lambda s:0 if not str(s).strip() else len(str(s).split(";")))
d=d.merge(disc[["code","year","n_hit"]],on=["code","year"],how="left")
d=d[d.n_hit.notna()].copy()
for c in ["size","lev","roa"]: d[c]=d[c].clip(d[c].quantile(.01),d[c].quantile(.99))
d["y"]=np.log1p(d.n_hit)
m=d[d.ets_status.isin(["expansion","control"])].copy()

def fe(dd,xs):
    cols=list(dict.fromkeys(["y"]+xs+["code","year"])); dd=dd[cols].dropna().copy()
    for f in ["code","year"]:
        dd["y"]=dd["y"]-dd.groupby(f)["y"].transform("mean")
        for x in xs: dd[x]=dd[x]-dd.groupby(f)[x].transform("mean")
    return sm.OLS(dd["y"],sm.add_constant(dd[xs])).fit(cov_type="cluster",cov_kwds={"groups":dd["code"]})

YRS=[2022,2023,2024,2025]; e=m.copy()
for y in YRS: e[f"y{y}"]=((e.year==y)&(e.treated_exp==1)).astype(int)
r=fe(e,[f"y{y}" for y in YRS]+["size","lev","roa"])
co=[0.0]+[r.params[f"y{y}"] for y in YRS]
se=[0.0]+[r.bse[f"y{y}"] for y in YRS]
xs=[2021]+YRS

fig,(a1,a2)=plt.subplots(1,2,figsize=(7.2,3.1))
a1.axhline(0,color="0.6",lw=0.7)
a1.axvline(2023.5,color="0.5",ls=(0,(3,3)),lw=0.9)
a1.errorbar(xs,co,yerr=[1.96*s for s in se],fmt="o-",color="black",lw=1.0,
            ms=4.5,mfc="white",mew=1.0,capsize=3,elinewidth=0.9)
a1.text(2023.6,max(co)*0.96,"covered from\ncompliance year 2024",fontsize=7,va="top",color="0.25")
a1.set_xticks(xs); a1.set_xlabel("Year"); a1.set_ylabel("Effect on disclosure intensity")
for s in ("top","right"): a1.spines[s].set_visible(False)

g=m.pivot_table(index="year",columns="ets_status",values="n_hit",aggfunc="mean")
a2.plot(g.index,g["expansion"],"o-",color="black",lw=1.1,ms=4.5,mfc="white",mew=1.0,label="Treated (steel, cement, aluminum)")
a2.plot(g.index,g["control"],"s--",color="0.45",lw=1.1,ms=4.0,mfc="white",mew=1.0,label="Control (chemicals, coal, paper)")
a2.axvline(2023.5,color="0.5",ls=(0,(3,3)),lw=0.9)
a2.set_xticks(list(g.index)); a2.set_xlabel("Year"); a2.set_ylabel("Carbon-related pages per report")
a2.legend(frameon=False,fontsize=7.2,loc="upper left")
for s in ("top","right"): a2.spines[s].set_visible(False)

fig.savefig(OUT/"fig4_event_study.png",bbox_inches="tight")
fig.savefig(OUT/"fig4_event_study.pdf",bbox_inches="tight")
print("saved. coef:",[round(c,4) for c in co])
