# -*- coding: utf-8 -*-
"""Full results for the valuation design that was attempted and abandoned, cited in Section 6.

Retained in the replication package so that every figure quoted in the paper for
the finding that entry did not change firm value can be recomputed.
"""
from __future__ import annotations
import sys, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, statsmodels.api as sm

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "out/tables"
CTRL = ["size", "lev", "roa"]


def fe(dd, y, xs):
    dd = dd[[y] + xs + ["code", "year"]].dropna().copy()
    for f in ["code", "year"]:
        for v in [y] + xs:
            dd[v] = dd[v] - dd.groupby(f)[v].transform("mean")
    r = sm.OLS(dd[y], sm.add_constant(dd[xs])).fit(
        cov_type="cluster", cov_kwds={"groups": dd.code})
    r._n = len(dd)
    return r


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    p = pd.read_csv(BASE / "out/panel2.csv", dtype={"code": str})
    for c in ["tobinq", "mtb", "size", "lev", "roa"]:
        p[c] = p[c].clip(p[c].quantile(.01), p[c].quantile(.99))
    rows = []

    def add(lab, treated, control, y):
        x = p[p.ets_status.isin([treated, control])].copy()
        x["did"] = (x.ets_status == treated).astype(int) * (x.year >= 2024).astype(int)
        r = fe(x, y, ["did"] + CTRL)
        rows.append({"specification": lab, "outcome": y,
                     "coef": round(float(r.params["did"]), 4),
                     "se": round(float(r.bse["did"]), 4),
                     "t": round(float(r.tvalues["did"]), 2),
                     "p": round(float(r.pvalues["did"]), 4), "n": r._n})

    for y in ["tobinq", "mtb"]:
        add("expansion vs never covered", "expansion", "control", y)
        add("placebo: covered since 2021 vs never covered", "always", "control", y)
        add("within covered: expansion vs covered since 2021", "expansion", "always", y)

    sub = p[p.grant_scaled.notna()]
    r = fe(sub, "tobinq", ["grant_scaled"] + CTRL)
    rows.append({"specification": "carbon exposure / total assets", "outcome": "tobinq",
                 "coef": round(float(r.params["grant_scaled"]), 4),
                 "se": round(float(r.bse["grant_scaled"]), 4),
                 "t": round(float(r.tvalues["grant_scaled"]), 2),
                 "p": round(float(r.pvalues["grant_scaled"]), 4), "n": r._n})

    # measurement validation：implied emission intensity against the official benchmark
    f = pd.read_csv(BASE / "out/firm_operations.csv", dtype={"code": str})
    b = pd.read_csv(BASE / "out/benchmark_power.csv")
    bench = float(b[(b.year == 2023) & (b.category == "I")].output_benchmark.iloc[0])
    inten = f.implied_intensity.dropna()
    both = f[(f.gen_total_mwh.notna()) & (f.coal_consumption.notna())]
    net = p.netpos_scaled.dropna()
    diag = pd.DataFrame([
        {"item": "implied intensity, median", "value": round(float(inten.median()), 4),
         "n": len(inten)},
        {"item": "2023 Class I benchmark", "value": bench, "n": ""},
        {"item": "generation and coal jointly observable, firm-years",
         "value": len(both), "n": both.code.nunique()},
        {"item": "net position computable, firm-years", "value": len(net), "n": ""},
        {"item": "net position, median share of opening assets (%)",
         "value": round(float(net.median()) * 100, 3), "n": ""}])

    pd.DataFrame(rows).to_csv(OUT / "tabF_valuation.csv", index=False, encoding="utf-8-sig")
    diag.to_csv(OUT / "tabG_exposure_diagnostics.csv", index=False, encoding="utf-8-sig")
    print(pd.DataFrame(rows).to_string(index=False))
    print()
    print(diag.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
