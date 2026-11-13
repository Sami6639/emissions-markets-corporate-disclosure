# -*- coding: utf-8 -*-
"""Rebuild every table in the paper and write them to out/tables/.

Reproduced by one command: bash run_all.sh
This script depends only on the archived intermediate files in out/, and does not
read the source PDFs, so a referee can reproduce all regression results without
downloading the roughly 10 GB annual report corpus. Page counts under the three
dictionaries come from carbon_disclosure.csv (original),
carbon_disclosure_restricted.csv (restricted) and
carbon_disclosure_namefilt.csv (restricted plus entity-name filter).
"""
from __future__ import annotations

import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "out/tables"
CTRL = ["size", "lev", "roa"]


def load() -> pd.DataFrame:
    d = pd.read_csv(BASE / "out/carbon_disclosure.csv", dtype={"code": str})
    d["P"] = d.hit_pages.fillna("").apply(
        lambda s: 0 if not str(s).strip() else len(str(s).split(";")))
    d["lnP"] = np.log1p(d.P)
    d["anyc"] = (d.compliance_tier >= 1).astype(float)
    d["anyq"] = (d.compliance_tier >= 2).astype(float)
    d["norm"] = d.P / d.n_pages.replace(0, np.nan) * 100
    d["lnpg"] = np.log(d.n_pages.replace(0, np.nan))
    keep = ["code", "year", "P", "lnP", "anyc", "anyq", "norm", "lnpg",
            "n_pages", "compliance_tier"]
    p = pd.read_csv(BASE / "out/panel2.csv", dtype={"code": str})
    p = p.drop(columns=[c for c in ["compliance_tier"] if c in p.columns])
    m = p.merge(d[keep], on=["code", "year"], how="inner")

    for name, col in [("out/carbon_disclosure_restricted.csv", "n_hit_restricted"),
                      ("out/carbon_disclosure_namefilt.csv", "n_hit_namefilt")]:
        f = BASE / name
        if f.exists():
            m = m.merge(pd.read_csv(f, dtype={"code": str})[["code", "year", col]],
                        on=["code", "year"], how="left")

    nv = BASE / "out/carbon_narrative.csv"
    if nv.exists():
        n = pd.read_csv(nv, dtype={"code": str})
        cols = [c for c in ["narr_char", "narr_sent", "narr_num", "narr_num_density",
                            "sim_self_prev_tfidf"] if c in n.columns]
        m = m.merge(n[["code", "year"] + cols], on=["code", "year"], how="left")
        for c in ["narr_char", "narr_sent", "narr_num"]:
            if c in m:
                m[c] = pd.to_numeric(m[c], errors="coerce").fillna(0)

    for c in CTRL:
        m[c] = m[c].clip(m[c].quantile(.01), m[c].quantile(.99))
    return m


def pair(m, treated, control):
    x = m[m.ets_status.isin([treated, control])].copy()
    x["did"] = (x.ets_status == treated).astype(int) * (x.year >= 2024).astype(int)
    return x


def ols_fe(dd, y, xs):
    cols = list(dict.fromkeys([y] + xs + ["code", "year"]))
    dd = dd[cols].dropna().copy()
    for f in ["code", "year"]:
        for v in [y] + xs:
            dd[v] = dd[v] - dd.groupby(f)[v].transform("mean")
    r = sm.OLS(dd[y], sm.add_constant(dd[xs])).fit(
        cov_type="cluster", cov_kwds={"groups": dd["code"]})
    r._n = len(dd)
    return r


def ppml(dd, y, xs):
    q = dd[[y] + xs + ["code", "year"]].dropna()
    X = pd.get_dummies(
        q.assign(c=q.code.astype("category"), yy=q.year.astype("category"))[xs + ["c", "yy"]],
        columns=["c", "yy"], drop_first=True).astype(float)
    r = sm.GLM(q[y], sm.add_constant(X), family=sm.families.Poisson()).fit(
        cov_type="cluster", cov_kwds={"groups": q.code})
    r._n = int(r.nobs)
    return r


def row(label, r, k="did", kind="ols"):
    ci = r.conf_int().loc[k]
    return {"specification": label, "coef": round(float(r.params[k]), 4),
            "se": round(float(r.bse[k]), 4),
            "stat": round(float(r.tvalues[k]), 2),
            "stat_type": "z" if kind == "ppml" else "t",
            "p": round(float(r.pvalues[k]), 4),
            "ci_low": round(float(ci[0]), 4), "ci_high": round(float(ci[1]), 4),
            "ratio": round(float(np.exp(r.params[k])), 3) if kind == "ppml" else "",
            "n": r._n}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    m = load()
    n = pair(m, "expansion", "always")

    # 1
    t1 = m.groupby("ets_status").agg(firms=("code", "nunique"), reports=("code", "size"))
    t1.loc["estimation sample"] = [n.code.nunique(), len(n)]
    t1.to_csv(OUT / "tab1_sample.csv", encoding="utf-8-sig")

    # 2
    b = m[(m.year == 2023) & (m.ets_status.isin(["expansion", "always"]))]
    rows = []
    for v in ["size", "lev", "roa", "tobinq", "lnP"]:
        x = b[b.ets_status == "expansion"][v].dropna()
        y = b[b.ets_status == "always"][v].dropna()
        t, p = stats.ttest_ind(x, y, equal_var=False)
        rows.append({"variable": v, "expansion": round(x.mean(), 4),
                     "always": round(y.mean(), 4),
                     "diff": round(x.mean() - y.mean(), 4),
                     "t": round(t, 2), "p": round(p, 4)})
    pd.DataFrame(rows).to_csv(OUT / "tab2_balance.csv", index=False, encoding="utf-8-sig")

    # 3
    t3 = m.groupby("ets_status").agg(
        firms=("code", "nunique"), reports=("code", "size"),
        mention_rate=("anyc", "mean"), mean_carbon_pages=("P", "mean"),
        any_quantity_rate=("anyq", "mean")).round(4)
    t3.to_csv(OUT / "tab3_descriptive.csv", encoding="utf-8-sig")

    # 4
    rows = [row("PPML, carbon pages", ppml(n, "P", ["did"] + CTRL), kind="ppml"),
            row("log(1+P), no controls", ols_fe(n, "lnP", ["did"])),
            row("log(1+P), with controls", ols_fe(n, "lnP", ["did"] + CTRL)),
            row("Any allowance quantity (LPM)", ols_fe(n, "anyq", ["did"] + CTRL)),
            row("Extensive margin", ols_fe(n, "anyc", ["did"] + CTRL)),
            row("Intensive margin", ols_fe(n[n.P > 0], "lnP", ["did"] + CTRL)),
            row("Normalized (carbon pages %)", ols_fe(n, "norm", ["did"] + CTRL)),
            row("Placebo: ln(total pages)", ols_fe(n, "lnpg", ["did"] + CTRL))]
    pd.DataFrame(rows).to_csv(OUT / "tab4_main.csv", index=False, encoding="utf-8-sig")

    # 5
    ct = pd.crosstab(m.year, m.ets_status, values=m.anyq, aggfunc="sum").fillna(0).astype(int)
    tot = pd.crosstab(m.year, m.ets_status)
    t5 = (ct.astype(str) + "/" + tot.astype(str))
    a = m[(m.ets_status == "expansion") & (m.year < 2024)]
    b2 = m[(m.ets_status == "expansion") & (m.year >= 2024)]
    tab = [[int(b2.anyq.sum()), len(b2) - int(b2.anyq.sum())],
           [int(a.anyq.sum()), len(a) - int(a.anyq.sum())]]
    t5.loc["fisher_exact_p"] = ["", "", round(stats.fisher_exact(tab)[1], 4)]
    t5.to_csv(OUT / "tab5_quantity_counts.csv", encoding="utf-8-sig")

    # 6
    e = n.copy()
    for y in [2022, 2023, 2024, 2025]:
        e[f"d{y}"] = (e.ets_status == "expansion").astype(int) * (e.year == y).astype(int)
    ks = [f"d{y}" for y in [2022, 2023, 2024, 2025]]
    rp = ppml(e, "P", ks + CTRL)
    ro = ols_fe(e, "lnP", ks + CTRL)
    rows = []
    for k in ks:
        rows.append({"year": k[1:],
                     "ppml_coef": round(float(rp.params[k]), 4),
                     "ppml_se": round(float(rp.bse[k]), 4),
                     "ppml_p": round(float(rp.pvalues[k]), 4),
                     "ppml_ratio": round(float(np.exp(rp.params[k])), 3),
                     "log_coef": round(float(ro.params[k]), 4),
                     "log_se": round(float(ro.bse[k]), 4),
                     "log_p": round(float(ro.pvalues[k]), 4)})
    w = rp.wald_test("d2022=0,d2023=0", scalar=True)
    f = ro.f_test("d2022=0,d2023=0")
    rows.append({"year": "joint pre-trend",
                 "ppml_coef": f"chi2={float(w.statistic):.3f}",
                 "ppml_p": round(float(w.pvalue), 4),
                 "log_coef": f"F={float(f.fvalue):.3f}",
                 "log_p": round(float(f.pvalue), 4)})
    pd.DataFrame(rows).to_csv(OUT / "tab6_event_study.csv", index=False, encoding="utf-8-sig")

    # 7
    rows = [row("Preferred, PPML", ppml(n, "P", ["did"] + CTRL), kind="ppml"),
            row("Preferred, log", ols_fe(n, "lnP", ["did"] + CTRL)),
            row("Placebo always vs never, PPML",
                ppml(pair(m, "always", "control"), "P", ["did"] + CTRL), kind="ppml"),
            row("Contamination always vs never, log",
                ols_fe(pair(m, "always", "control"), "lnP", ["did"] + CTRL)),
            row("Direct expansion vs never, PPML",
                ppml(pair(m, "expansion", "control"), "P", ["did"] + CTRL), kind="ppml"),
            row("Direct expansion vs never, log",
                ols_fe(pair(m, "expansion", "control"), "lnP", ["did"] + CTRL))]
    cap = set(m[(m.ets_status == "always") & (m.get("captive_power", 0) == 1)].code)
    if cap:
        rows.append(row("Excluding 61 captive-power controls, PPML",
                        ppml(n[~n.code.isin(cap)], "P", ["did"] + CTRL), kind="ppml"))
        rows.append(row("Captive-power controls only, PPML",
                        ppml(n[n.code.isin(cap) | (n.ets_status == "expansion")],
                             "P", ["did"] + CTRL), kind="ppml"))
    pd.DataFrame(rows).to_csv(OUT / "tab7_comparison_group.csv", index=False,
                              encoding="utf-8-sig")

    # 8
    rows = []
    for lab, col in [("original", "P"), ("restricted", "n_hit_restricted"),
                     ("restricted+name filter", "n_hit_namefilt")]:
        if col not in n.columns:
            continue
        universe = {"P": "out/carbon_disclosure.csv",
                    "n_hit_restricted": "out/carbon_disclosure_restricted.csv",
                    "n_hit_namefilt": "out/carbon_disclosure_namefilt.csv"}[col]
        u = pd.read_csv(BASE / universe, dtype={"code": str})
        if col == "P":
            tot = int(u.hit_pages.fillna("").apply(
                lambda s: 0 if not str(s).strip() else len(str(s).split(";"))).sum())
        else:
            tot = int(u[col].sum())
        rows.append({**row(f"PPML, {lab}", ppml(n, col, ["did"] + CTRL), kind="ppml"),
                     "pages_retained": tot})
        pl = pair(m, "always", "control")
        rows.append(row(f"Placebo, {lab}", ppml(pl, col, ["did"] + CTRL), kind="ppml"))
        z = n.copy()
        z["lnx"] = np.log1p(z[col])
        rows.append(row(f"log(1+P), {lab}", ols_fe(z, "lnx", ["did"] + CTRL)))
    pd.DataFrame(rows).to_csv(OUT / "tab8_dictionaries.csv", index=False,
                              encoding="utf-8-sig")

    # 9
    rows = []
    for sec in ["steel", "cement", "aluminum"]:
        sub = n[(n.sector == sec) | (n.ets_status == "always")]
        rows.append({**row(f"{sec}, original", ppml(sub, "P", ["did"] + CTRL), kind="ppml"),
                     "firms": int(n[(n.ets_status == "expansion") &
                                    (n.sector == sec)].code.nunique())})
        for lab, col in [("restricted", "n_hit_restricted"),
                         ("name-filtered", "n_hit_namefilt")]:
            if col in n.columns:
                rows.append(row(f"{sec}, {lab}", ppml(sub, col, ["did"] + CTRL), kind="ppml"))
    st = set(n[(n.ets_status == "expansion") & (n.sector == "steel")].code)
    rows.append(row("excluding steel, original",
                    ppml(n[~n.code.isin(st)], "P", ["did"] + CTRL), kind="ppml"))
    pd.DataFrame(rows).to_csv(OUT / "tab9_sectors.csv", index=False, encoding="utf-8-sig")

    # 10
    if "narr_sent" in n.columns:
        rows = [row("narrative sentences", ppml(n, "narr_sent", ["did"] + CTRL), kind="ppml"),
                row("narrative characters", ppml(n, "narr_char", ["did"] + CTRL), kind="ppml"),
                row("numerals in narrative", ppml(n, "narr_num", ["did"] + CTRL), kind="ppml")]
        pd.DataFrame(rows).to_csv(OUT / "tab10_narrative.csv", index=False,
                                  encoding="utf-8-sig")

    #
    codes = sorted(set(n[n.ets_status == "expansion"].code))
    loo = []
    for c in codes:
        try:
            r = ppml(n[n.code != c], "P", ["did"] + CTRL)
            loo.append({"dropped": c, "coef": round(float(r.params["did"]), 4),
                        "p": round(float(r.pvalues["did"]), 4)})
        except Exception:
            pass
    L = pd.DataFrame(loo)
    L.to_csv(OUT / "tab11_leave_one_out.csv", index=False, encoding="utf-8-sig")

    print(f"[done] {len(list(OUT.glob('*.csv')))} 张表写入 {OUT}")
    print(f"  留一法 {len(L)} 次，系数 [{L.coef.min():.4f}, {L.coef.max():.4f}]，"
          f"p<0.05 比例 {(L.p < 0.05).mean():.3f}")


if __name__ == "__main__":
    main()
