# -*- coding: utf-8 -*-
"""Define the estimation sample and the treatment groups by sector.

Coverage by the national market is determined by sector together with annual
direct emissions of at least 26,000 tCO2e. Listed firms in these sectors are
almost all far above that threshold, so defining coverage by industry
classification is more reliable than assembling provincial rosters, and it makes
the treatment definition correspond one to one with the policy text:
  power and heat            covered from July 2021 (always treated)
  steel, cement, aluminium  covered from compliance year 2024 (expansion cohort,
                            work plan published 26 March 2025)
  petrochemicals, chemicals, coal, paper   not yet covered, scheduled for 2027
The roster match serves as a cross-check: any firm matched to the 2019-2020
roster must fall inside a covered group.
"""
import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
GROUPS = {
    "power":    (r"电力|热力",                    "always",   2021),
    "steel":    (r"黑色金属冶炼",                  "expansion", 2024),
    "cement":   (r"非金属矿物制品",                "expansion", 2024),
    "aluminum": (r"有色金属冶炼",                  "expansion", 2024),
    "chemical": (r"石油加工|化学原料|化学制品|石油和天然气", "control", None),
    "coal":     (r"煤炭开采",                      "control", None),
    "paper":    (r"造纸",                          "control", None),
}

def main():
    f = pd.read_csv(BASE / "raw/firm/firm_names.csv", dtype={"code": str})
    f["industry"] = f["industry"].fillna("")
    rows = []
    for g, (pat, status, yr) in GROUPS.items():
        s = f[f["industry"].str.contains(pat, regex=True)]
        for _, r in s.iterrows():
            rows.append({"code": r["code"], "full_name": r["full_name"],
                         "industry_raw": r["industry"], "sector": g,
                         "ets_status": status, "ets_year": yr})
    d = pd.DataFrame(rows).drop_duplicates(subset=["code"], keep="first")

    m = pd.read_csv(BASE / "out/emitter_firm_match.csv", dtype=str)
    matched = set(m.loc[m["stock_code"].notna(), "stock_code"])
    d["in_2019_list"] = d["code"].isin(matched).astype(int)

    # ：「」****。
    # 。，
    # ， DiD 。
    # 2019-2020 ， 2021 。
    cap = (d["in_2019_list"] == 1) & (d["ets_status"] == "control")
    d.loc[cap, "captive_power"] = 1
    d.loc[cap, "ets_status"] = "always"
    d.loc[cap, "ets_year"] = 2021
    d["captive_power"] = d["captive_power"].fillna(0).astype(int)

    d.to_csv(BASE / "out/sample_definition.csv", index=False, encoding="utf-8-sig")
    print(f"样本 {len(d)} 家")
    print(d.groupby(["ets_status", "sector"]).size().to_string())
    print()
    print(f"自备电厂改判：{int(d['captive_power'].sum())} 家非电力行业企业因在名录内改判为处理组")
    print(d[d["captive_power"] == 1].groupby("sector").size().to_string())
    print()
    bad = d[(d["in_2019_list"] == 1) & (d["ets_status"] == "control")]
    print(f"名录内但仍在对照组：{len(bad)} 家（应为 0）")

if __name__ == "__main__":
    main()
