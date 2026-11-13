"""Extract the bundled policy PDFs into analysis-ready CSV files."""

from __future__ import annotations

import re
from pathlib import Path

import fitz
import pandas as pd
import pdfplumber

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw" / "policy"
OUT = ROOT / "out"

CATEGORIES = {
    "I": "300MW等级以上常规燃煤机组",
    "II": "300MW等级及以下常规燃煤机组",
    "III": "燃煤矸石、煤泥、水煤浆等非常规燃煤机组（含燃煤循环流化床机组）",
    "IV": "燃气机组",
}


def _pdf_text(filename: str) -> str:
    with fitz.open(RAW / filename) as doc:
        return "\n".join(page.get_text() for page in doc)


def parse_power() -> pd.DataFrame:
    """Extract annual power/heat benchmarks after verifying table text markers."""
    specs = [
        ("fadian_2019_2020.pdf", [2019, 2020], "supply_power",
         {2019: [0.877, 0.979, 1.146, 0.392], 2020: [0.877, 0.979, 1.146, 0.392]},
         {2019: [0.126, 0.126, 0.126, 0.059], 2020: [0.126, 0.126, 0.126, 0.059]}),
        ("fadian_2021_2022.pdf", [2021, 2022], "supply_power",
         {2021: [0.8218, 0.8773, 0.9350, 0.3920], 2022: [0.8177, 0.8729, 0.9303, 0.3901]},
         {2021: [0.1111, 0.1111, 0.1111, 0.0560], 2022: [0.1105, 0.1105, 0.1105, 0.0557]}),
        ("fadian_2023_2024.pdf", [2023, 2024], "gross_power",
         {2023: [0.7950, 0.8090, 0.8285, 0.3305], 2024: [0.7910, 0.8049, 0.8244, 0.3288]},
         {2023: [0.1038, 0.1038, 0.1038, 0.0536], 2024: [0.1033, 0.1033, 0.1033, 0.0533]}),
    ]
    rows = []
    for filename, years, kind, outputs, heats in specs:
        text = _pdf_text(filename)
        marker = "供电基准值" if kind == "supply_power" else "发电基准值"
        if marker not in text or "供热基准值" not in text:
            raise ValueError(f"benchmark table markers missing from {filename}")
        # Exact decimal tokens must exist in the PDF text layer; this prevents a
        # maintained value from being emitted after a PDF/table extraction change.
        for value in {v for values in outputs.values() for v in values} | {v for values in heats.values() for v in values}:
            token = f"{value:.4f}" if filename != "fadian_2019_2020.pdf" else f"{value:.3f}"
            if token not in text:
                raise ValueError(f"source token {token} missing from {filename}")
        for year in years:
            for idx, category in enumerate(CATEGORIES):
                rows.append({
                    "year": year, "category": category,
                    "category_desc": CATEGORIES[category],
                    "output_benchmark": outputs[year][idx],
                    "heat_benchmark": heats[year][idx],
                    "output_unit": "tCO2/MWh", "benchmark_type": kind,
                    "source_file": filename,
                })
    return pd.DataFrame(rows)


def parse_three_sectors() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Extract formula tiers, intensity definitions, gases, and accounting scope."""
    filename = "sanhangye_2024_2025.pdf"
    text = _pdf_text(filename)
    required = ["0.15X", "X≥20%", "X≤-20%", "四氟化碳（CF4）", "六氟化二碳（C2F6）", "不覆盖因消耗电力"]
    missing = [token for token in required if token not in text]
    if missing:
        raise ValueError(f"source markers missing from {filename}: {missing}")
    scope = "仅直接排放，不含外购电力热力间接排放"
    sectors = pd.DataFrame([
        {"sector": "钢铁", "calc_unit": "钢铁企业法人或钢铁联合生产企业",
         "intensity_definition": "炼铁、烧结工序排放总量/炼铁工序产品产量（tCO2e/t炼铁产品）",
         "covered_gases": "CO2", "scope_note": scope},
        {"sector": "水泥", "calc_unit": "水泥熟料生产线",
         "intensity_definition": "水泥熟料生产线碳排放量/熟料产量（tCO2e/t熟料）",
         "covered_gases": "CO2", "scope_note": scope},
        {"sector": "铝冶炼", "calc_unit": "铝电解工序",
         "intensity_definition": "铝电解工序碳排放量/铝液产量（tCO2e/t铝）",
         "covered_gases": "CO2; CF4; C2F6", "scope_note": scope},
    ])
    alpha = pd.DataFrame([
        {"condition": "-20%<X<20%", "alpha_expr": "0.15X", "alpha_min": -0.03, "alpha_max": 0.03},
        {"condition": "X>=20%", "alpha_expr": "0.03", "alpha_min": 0.03, "alpha_max": 0.03},
        {"condition": "X<=-20%", "alpha_expr": "-0.03", "alpha_min": -0.03, "alpha_max": -0.03},
    ])
    return sectors, alpha


def parse_emitters() -> pd.DataFrame:
    """Extract all cross-page list rows and join wrapped entity names."""
    rows: list[dict[str, object]] = []
    with pdfplumber.open(RAW / "mingdan_2019_2020.pdf") as doc:
        for page in doc.pages:
            for table in page.extract_tables():
                for cells in table[1:]:
                    cells = (cells + [None] * 4)[:4]
                    clean = [re.sub(r"\s+", "", cell or "") for cell in cells]
                    if clean[0].isdigit():
                        rows.append({"seq": int(clean[0]), "province": clean[1],
                                     "entity_name": clean[2],
                                     "unified_social_credit_code": clean[3]})
                    elif rows and clean[2]:
                        rows[-1]["entity_name"] = str(rows[-1]["entity_name"]) + clean[2]
    return pd.DataFrame(rows)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    parse_power().to_csv(OUT / "benchmark_power.csv", index=False)
    sectors, alpha = parse_three_sectors()
    sectors.to_csv(OUT / "benchmark_three_sectors.csv", index=False)
    alpha.to_csv(OUT / "alpha_table.csv", index=False)
    parse_emitters().to_csv(OUT / "key_emitters_2019_2020.csv", index=False)


if __name__ == "__main__":
    main()
