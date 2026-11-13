# -*- coding: utf-8 -*-
"""Main tables on the seven-year panel, 2019 to 2025.

Two entry events are studied: power generation in 2021 and steel, cement and
aluminium smelting in 2024. The comparison group in both cases is firms never
covered by the national market. The primary outcome is an indicator for the annual
report containing any carbon content. Results for the carbon page count are
reported alongside it, together with their sensitivity to functional form.
"""
from __future__ import annotations
import sys, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, statsmodels.api as sm
from scipy import stats

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "out/tables"
DICTS = [("original", "P", "anyc"), ("restricted", "n_hit_restricted", "anyc_r"),
         ("name-filtered", "n_hit_namefilt", "anyc_nf")]


def load():
    d = pd.read_csv(BASE / "out/carbon_disclosure.csv", dtype={"code": str})
    d["P"] = d.hit_pages.fillna("").apply(
        lambda s: 0 if not str(s).strip() else len(str(s).split(";")))
    d["anyc"] = (d.P > 0).astype(float)
    d["anyq"] = (d.compliance_tier >= 2).astype(float)
    for f, c in [("out/carbon_disclosure_restricted.csv", "n_hit_restricted"),
                 ("out/carbon_disclosure_namefilt.csv", "n_hit_namefilt")]:
        d = d.merge(pd.read_csv(BASE / f, dtype={"code": str})[["code", "year", c]],
                    on=["code", "year"], how="left")
    d["anyc_r"] = (d.n_hit_restricted > 0).astype(float)
    d["anyc_nf"] = (d.n_hit_namefilt > 0).astype(float)
    st = (pd.read_csv(BASE / "out/panel2.csv", dtype={"code": str})
          .groupby("code").ets_status.first())
    return d.merge(st, on="code", how="inner")


def lpm(dd, y, xs):
    dd = dd[[y] + xs + ["code", "year"]].dropna().copy()
    for f in ["code", "year"]:
        for v in [y] + xs:
            dd[v] = dd[v] - dd.groupby(f)[v].transform("mean")
    r = sm.OLS(dd[y], sm.add_constant(dd[xs])).fit(
        cov_type="cluster", cov_kwds={"groups": dd.code})
    r._n = len(dd)
    return r


def ppml(dd, y, xs):
    q = dd[[y] + xs + ["code", "year"]].dropna()
    X = pd.get_dummies(q.assign(c=q.code.astype("category"),
                                yy=q.year.astype("category"))[xs + ["c", "yy"]],
                       columns=["c", "yy"], drop_first=True).astype(float)
    X = X.loc[:, X.std() > 0]
    mod = sm.GLM(q[y], sm.add_constant(X), family=sm.families.Poisson())
    # IRLS（statsmodels ， Poisson ）， lbfgs；
    # ， 0.01 ，。
    try:
        r = mod.fit(cov_type="cluster", cov_kwds={"groups": q.code})
        alt = mod.fit(method="lbfgs", maxiter=500,
                      cov_type="cluster", cov_kwds={"groups": q.code})
        r._converged = abs(float(r.params[xs[0]]) - float(alt.params[xs[0]])) < 0.01
    except Exception:
        r = mod.fit(method="lbfgs", maxiter=500,
                    cov_type="cluster", cov_kwds={"groups": q.code})
        r._converged = False
    r._n = int(r.nobs)
    return r


def rec(ev, dic, out, est, r, k="did"):
    return {"event": ev, "dictionary": dic, "outcome": out, "estimator": est,
            "coef": round(float(r.params[k]), 4), "se": round(float(r.bse[k]), 4),
            "stat": round(float(r.tvalues[k]), 2), "p": round(float(r.pvalues[k]), 4),
            "ratio": round(float(np.exp(r.params[k])), 3) if est == "PPML" else "",
            "converged": getattr(r, "_converged", True), "n": r._n}


def event(m, treated, entry, upto=None):
    n = m[m.ets_status.isin([treated, "control"])].copy()
    if upto:
        n = n[n.year <= upto]
    n["tr"] = (n.ets_status == treated).astype(int)
    n["did"] = n.tr * (n.year >= entry).astype(int)
    n["trend"] = n.tr * (n.year - n.year.min())
    return n


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    m = load()
    rows, evs = [], []

    for lab, treated, entry, upto in [("2021 power entry", "always", 2021, 2023),
                                      ("2024 expansion", "expansion", 2024, None)]:
        n = event(m, treated, entry, upto)
        for dic, cnt, ext in DICTS:
            rows.append(rec(lab, dic, "any carbon content", "LPM", lpm(n, ext, ["did"])))
            rows.append(rec(lab, dic, "carbon pages", "PPML", ppml(n, cnt, ["did"])))
        rows.append(rec(lab, "original", "carbon pages + linear trend", "PPML",
                        ppml(n, "P", ["did", "trend"])))
        rows.append(rec(lab, "original", "any allowance quantity", "LPM",
                        lpm(n, "anyq", ["did"])))
        rows.append(rec(lab, "original", "log(1+pages)", "OLS",
                        lpm(n.assign(lnP=np.log1p(n.P)), "lnP", ["did"])))
        rows.append(rec(lab, "original", "log(1+pages) + linear trend", "OLS",
                        lpm(n.assign(lnP=np.log1p(n.P)), "lnP", ["did", "trend"])))
        # balanced panel: keep only firms filing in every year of the window，removing compositional change from firms entering the sample
        need = n.year.nunique()
        cnt = n.groupby("code").year.nunique()
        bal = n[n.code.isin(cnt[cnt == need].index)]
        for dic, cnt_col, ext_col in DICTS:
            rows.append(rec(lab, dic + ", balanced panel", "any carbon content", "LPM",
                            lpm(bal, ext_col, ["did"])))
        rows.append(rec(lab, "original, balanced panel", "any allowance quantity", "LPM",
                        lpm(bal, "anyq", ["did"])))

        yrs = sorted(y for y in n.year.unique() if y != n.year.min())
        for y in yrs:
            n[f"d{y}"] = n.tr * (n.year == y).astype(int)
        ks = [f"d{y}" for y in yrs]
        for out, col, est in [("any carbon content", "anyc_nf", "LPM"),
                              ("carbon pages", "P", "PPML"),
                              ("any allowance quantity", "anyq", "LPM")]:
            try:
                r = lpm(n, col, ks) if est == "LPM" else ppml(n, col, ks)
            except Exception:
                continue
            for y in yrs:
                k = f"d{y}"
                evs.append({"event": lab, "outcome": out, "year": y,
                            "pre": int(y < entry),
                            "coef": round(float(r.params[k]), 4),
                            "se": round(float(r.bse[k]), 4),
                            "p": round(float(r.pvalues[k]), 4)})
            pre = [f"d{y}" for y in yrs if y < entry]
            if pre:
                t = (r.f_test(",".join(f"{k}=0" for k in pre)) if est == "LPM"
                     else r.wald_test(",".join(f"{k}=0" for k in pre), scalar=True))
                stat = float(getattr(t, "fvalue", getattr(t, "statistic", np.nan)))
                evs.append({"event": lab, "outcome": out, "year": "joint pre-trend",
                            "pre": 1, "coef": round(stat, 3), "se": "",
                            "p": round(float(t.pvalue), 4)})

    pd.DataFrame(rows).to_csv(OUT / "tabA_main_two_events.csv", index=False,
                              encoding="utf-8-sig")
    pd.DataFrame(evs).to_csv(OUT / "tabB_event_studies.csv", index=False,
                             encoding="utf-8-sig")

    rate = (m.groupby(["ets_status", "year"])
            .agg(reports=("code", "size"), mention=("anyc_nf", "mean"),
                 pages=("P", "mean"), quantity=("anyq", "mean")).round(4))
    rate.to_csv(OUT / "tabC_rates_by_year.csv", encoding="utf-8-sig")

    q = m.pivot_table(index="year", columns="ets_status", values="anyq",
                      aggfunc=["sum", "size"])
    q.to_csv(OUT / "tabD_quantity_counts.csv", encoding="utf-8-sig")

    # Pooled exact test on the mandated margin, over the whole window rather than
    # a single year on each side, so the figure quoted in the text is reproducible.
    exact_rows = []
    for lab, treated, entry in [("2024 expansion", "expansion", 2024),
                                ("2021 power entry", "always", 2021)]:
        x = m[m.ets_status == treated]
        pre, post = x[x.year < entry], x[x.year >= entry]
        table = [[int(post.anyq.sum()), len(post) - int(post.anyq.sum())],
                 [int(pre.anyq.sum()), len(pre) - int(pre.anyq.sum())]]
        exact_rows.append({"event": lab,
                     "pre_disclosing": int(pre.anyq.sum()), "pre_reports": len(pre),
                     "post_disclosing": int(post.anyq.sum()), "post_reports": len(post),
                     "fisher_pooled_p": round(float(stats.fisher_exact(table)[1]), 4)})
    pd.DataFrame(exact_rows).to_csv(OUT / "tabH_quantity_exact_test.csv", index=False,
                                    encoding="utf-8-sig")

    d = pd.DataFrame(rows)
    print(d[d.outcome == "any carbon content"][
        ["event", "dictionary", "coef", "stat", "p", "n"]].to_string(index=False))
    print(f"\n[done] 写入 {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
