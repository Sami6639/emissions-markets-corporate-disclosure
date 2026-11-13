# -*- coding: utf-8 -*-
"""Assemble the research panel and compute the unrecognised net allowance position.

Measurement of the net position
  Allowances A = electricity generated x benchmark
  Emissions   E = electricity generated x realised intensity, where the realised
                  intensity is converted from coal consumption per unit supplied:
                  intensity = coal (g/kWh) x 2.66 / 1000
  Net position A - E = electricity generated x (benchmark - realised intensity)
This avoids relying on emissions figures that firms rarely publish. The factor
2.66 is the CO2 emission coefficient of one tonne of standard coal equivalent.
Validation: 300 g/kWh converts to 0.798 tCO2/MWh, close to the 2023 Class I
benchmark of 0.7950, as the benchmark is itself calibrated to the sector average.

Coverage status follows out/sample_definition.csv:
  always    power and heat, and firms operating captive plants, covered from 2021
  expansion steel, cement and aluminium smelting, covered from compliance year 2024
  control   petrochemicals, chemicals, coal and paper, not yet covered
"""
import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).resolve().parent.parent
COAL_FACTOR = 2.66 / 1000        # g/kWh -> tCO2/MWh
YEAREND_PRICE = {2021: 54.22, 2022: 55.00, 2023: 79.42, 2024: 97.49, 2025: 74.63}


def main():
    samp = pd.read_csv(BASE / "out/sample_definition.csv", dtype={"code": str})
    fin = pd.read_csv(BASE / "raw/firm/financials.csv", dtype={"code": str})
    px = pd.read_csv(BASE / "raw/firm/yearend_price.csv", dtype={"code": str})
    bench = pd.read_csv(BASE / "out/benchmark_power.csv")
    ops_p = BASE / "out/firm_operations.csv"
    ops = pd.read_csv(ops_p, dtype={"code": str}) if ops_p.exists() else pd.DataFrame()

    d = fin.merge(px, on=["code", "year"], how="left").merge(samp, on="code", how="inner")
    d["shares"] = d["share_capital"]
    d["mktcap"] = d["yearend_close"] * d["shares"]
    # ，，
    # roa ，。
    d = d.sort_values(["code", "year"])
    d["ta_lag"] = d.groupby("code")["total_assets"].shift(1)
    d = d[(d["year"] >= 2021) & (d["year"] <= 2025)].copy()

    #
    bm = (bench[bench["benchmark_type"] == "gross_power"]
          .groupby("year")["output_benchmark"].median().to_dict())
    if len(ops):
        cols = [c for c in ["code", "year", "gen_total_mwh", "coal_consumption",
                            "implied_intensity", "steel_output", "cement_output",
                            "alu_output"] if c in ops.columns]
        d = d.merge(ops[cols], on=["code", "year"], how="left")
    for c in ["gen_total_mwh", "coal_consumption", "implied_intensity"]:
        if c not in d.columns:
            d[c] = np.nan

    d["benchmark"] = d["year"].map(bm)
    d.loc[d["implied_intensity"].isna() & d["coal_consumption"].notna(),
          "implied_intensity"] = d["coal_consumption"] * COAL_FACTOR

    d["allowance_t"] = d["gen_total_mwh"] * d["benchmark"]
    d["emission_t"] = d["gen_total_mwh"] * d["implied_intensity"]
    d["net_pos_t"] = d["allowance_t"] - d["emission_t"]

    d["cea_price"] = d["year"].map(YEAREND_PRICE)
    d["grant_scaled"] = d["allowance_t"] * d["cea_price"] / d["ta_lag"]
    d["oblig_scaled"] = d["emission_t"] * d["cea_price"] / d["ta_lag"]
    d["netpos_scaled"] = d["net_pos_t"] * d["cea_price"] / d["ta_lag"]

    #
    d["treated_exp"] = (d["ets_status"] == "expansion").astype(int)
    d["covered"] = d["ets_status"].isin(["always", "expansion"]).astype(int)
    d["post_exp"] = (d["year"] >= 2024).astype(int)
    d["did"] = d["treated_exp"] * d["post_exp"]

    #
    d["size"] = np.log(d["total_assets"])
    d["lev"] = d["total_liab"] / d["total_assets"]
    d["roa"] = d["net_profit"] / d["ta_lag"]
    d["tobinq"] = (d["mktcap"] + d["total_liab"]) / d["total_assets"]
    d["mtb"] = d["mktcap"] / d["parent_equity"]

    disc_p = BASE / "out/carbon_disclosure.csv"
    if disc_p.exists():
        disc = pd.read_csv(disc_p, dtype={"code": str})
        keep = [c for c in ["code", "year", "compliance_tier", "qty_free",
                            "trading_income", "trading_expense"] if c in disc.columns]
        d = d.merge(disc[keep], on=["code", "year"], how="left")

    d.to_csv(BASE / "out/panel2.csv", index=False, encoding="utf-8-sig")
    print(f"面板 {len(d)} 行 / {d['code'].nunique()} 家 / {int(d['year'].min())}-{int(d['year'].max())}")
    print("\n分组:")
    print(d.groupby("ets_status")["code"].nunique().to_string())
    print("\n关键变量非空:")
    for c in ["tobinq", "gen_total_mwh", "coal_consumption", "allowance_t",
              "netpos_scaled", "compliance_tier"]:
        if c in d.columns:
            print(f"  {c:18s} {d[c].notna().sum():5d}")
    if d["netpos_scaled"].notna().any():
        s = d["netpos_scaled"].dropna()
        print(f"\n净头寸占期初总资产: 中位 {s.median()*100:.3f}%  "
              f"区间 [{s.min()*100:.2f}%, {s.max()*100:.2f}%]  n={len(s)}")


if __name__ == "__main__":
    main()
