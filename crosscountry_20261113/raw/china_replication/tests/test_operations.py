from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from parse_operations import (
    apply_coal_gate,
    apply_generation_gates,
    convert_capacity_to_mw,
    convert_generation_to_mwh,
)


def test_unit_conversions():
    assert convert_generation_to_mwh(1, "亿千瓦时") == 100000
    assert convert_capacity_to_mw(1, "万千瓦") == 10
    assert convert_generation_to_mwh(1, "兆瓦时") == 1


def test_generation_gates():
    assert apply_generation_gates(6e8, None) == (None, None, "macro_scale")
    assert apply_generation_gates(1_000_000, 100)[2] == "utilization_out_of_range"
    generation, hours, reason = apply_generation_gates(1_000_000, 200)
    assert generation == 1_000_000
    assert hours == 5000
    assert reason is None


def test_coal_gate():
    assert apply_coal_gate(199)[2] == "coal_out_of_range"
    coal, intensity, reason = apply_coal_gate(300)
    assert coal == 300
    assert intensity == 0.798
    assert reason is None


def test_output_structure():
    manifest = pd.read_csv(ROOT / "raw/reports/manifest.csv", dtype={"code": str})
    data = pd.read_csv(ROOT / "out/firm_operations.csv", dtype={"code": str})
    assert not data.duplicated(["code", "year"]).any()
    missing = [f for f in manifest.file if not (ROOT / "raw/reports" / f).is_file()]
    assert len(missing) <= 4
    assert {"coal_consumption", "unit_coal", "implied_intensity", "src_section",
            "utilization_hours", "reject_reason", "raw_snippet"}.issubset(data.columns)
    assert data.loc[data.gen_total.notna(), "unit_gen"].notna().all()


def test_generation_is_reasonable():
    data = pd.read_csv(ROOT / "out/firm_operations.csv", dtype={"code": str})
    values = data.gen_total_mwh.dropna()
    assert ((values > 0) & (values < 6e8)).all()
    hours = data.utilization_hours.dropna()
    assert hours.between(500, 8760).all()


def test_coal_is_reasonable():
    data = pd.read_csv(ROOT / "out/firm_operations.csv", dtype={"code": str})
    assert data.coal_consumption.dropna().between(200, 500).all()
    assert data.implied_intensity.dropna().between(0.5, 1.4).all()


def test_huaneng_2025_generation():
    data = pd.read_csv(ROOT / "out/firm_operations.csv", dtype={"code": str})
    row = data[(data.code.str.zfill(6) == "600011") & (data.year == 2025)].iloc[0]
    assert abs(row.gen_total_mwh - 463114000) / 463114000 <= 0.01


def test_known_macro_generation_is_rejected():
    data = pd.read_csv(ROOT / "out/firm_operations.csv", dtype={"code": str})
    cases = [("601088", 2025), ("601088", 2024), ("000690", 2024),
             ("000027", 2023), ("000531", 2025)]
    for code, year in cases:
        row = data[(data.code.str.zfill(6) == code) & (data.year == year)].iloc[0]
        assert pd.isna(row.gen_total_mwh), (code, year, row.gen_total_mwh)


def test_output_matches_manifest_pdf_count():
    data = pd.read_csv(ROOT / "out/firm_operations.csv", dtype={"code": str})
    manifest = pd.read_csv(ROOT / "raw/reports/manifest.csv", dtype={"code": str})
    data_keys = set(zip(data.code.str.zfill(6), data.year))
    manifest_keys = set(zip(manifest.code.str.zfill(6), manifest.year))
    assert data_keys <= manifest_keys
