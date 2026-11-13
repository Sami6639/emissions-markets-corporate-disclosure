from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from src.carbon_price import parse_quote_text
from src.validators import (
    DataQualityError,
    assert_columns,
    assert_max_date,
    assert_missing_rate,
    assert_no_duplicates,
    assert_nonempty,
    assert_unique_count,
    reconcile,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"


def test_power_benchmark_values_and_accounting_basis():
    df = pd.read_csv(OUT / "benchmark_power.csv", dtype={"category": str})
    expected = {
        2019: {"I": 0.877, "II": 0.979, "III": 1.146, "IV": 0.392},
        2021: {"I": 0.8218, "II": 0.8773, "III": 0.9350, "IV": 0.3920},
        2022: {"I": 0.8177, "II": 0.8729, "III": 0.9303, "IV": 0.3901},
        2023: {"I": 0.7950, "II": 0.8090, "III": 0.8285, "IV": 0.3305},
        2024: {"I": 0.7910, "II": 0.8049, "III": 0.8244, "IV": 0.3288},
    }
    for year, values in expected.items():
        actual = df[df.year == year].set_index("category")["output_benchmark"]
        for category, value in values.items():
            assert actual[category] == pytest.approx(value)

    heat_2019 = df[df.year == 2019].set_index("category")["heat_benchmark"]
    assert heat_2019[["I", "II", "III"]].tolist() == pytest.approx([0.126] * 3)
    assert heat_2019["IV"] == pytest.approx(0.059)
    assert set(df[df.year <= 2022].benchmark_type) == {"supply_power"}
    assert set(df[df.year >= 2023].benchmark_type) == {"gross_power"}


def test_three_sector_parameters_and_scope():
    sectors = pd.read_csv(OUT / "benchmark_three_sectors.csv")
    alpha = pd.read_csv(OUT / "alpha_table.csv")
    assert alpha.alpha_min.min() == pytest.approx(-0.03)
    assert alpha.alpha_max.max() == pytest.approx(0.03)
    aluminium = sectors.loc[sectors.sector == "铝冶炼", "covered_gases"].iloc[0]
    assert "CF4" in aluminium and "C2F6" in aluminium
    assert sectors.scope_note.str.contains("仅直接排放，不含外购电力热力间接排放", regex=False).all()


def test_key_emitters_shape_codes_and_provinces():
    df = pd.read_csv(OUT / "key_emitters_2019_2020.csv", dtype=str)
    assert 2200 <= len(df) <= 2250
    assert df.unified_social_credit_code.notna().mean() >= 0.95
    assert 25 <= df.province.nunique() <= 35


QUOTE = (
    "开盘价51.24元/吨，最高价51.90元/吨，最低价50.34元/吨，收盘价51.25元/吨，"
    "收盘价较前一日上涨0.02%。今日挂牌协议交易成交量897,326吨，成交额39,867,729.29元；"
    "大宗协议交易成交量2,003,259吨，成交额86,377,518.45元；单向竞价成交量100,000吨，"
    "成交额4,475,000.00元。今日全国碳排放配额总成交量3,000,585吨，总成交额130,720,247.74元。"
)


def test_quote_parser_real_fixture():
    quote = parse_quote_text(QUOTE, "2021-07-16")
    assert quote["open"] == pytest.approx(51.24)
    assert quote["high"] == pytest.approx(51.90)
    assert quote["low"] == pytest.approx(50.34)
    assert quote["close"] == pytest.approx(51.25)
    assert quote["total_volume"] == 3_000_585
    assert quote["total_amount"] == pytest.approx(130_720_247.74)
    assert quote["listing_volume"] == 897_326
    assert quote["block_amount"] == pytest.approx(86_377_518.45)
    assert quote["auction_volume"] == 100_000


def test_quote_parser_missing_is_none():
    quote = parse_quote_text("<p>收盘价50.00元/吨</p>", "2024-01-01")
    assert quote["close"] == 50.0
    assert quote["open"] is None
    assert quote["total_volume"] is None


def test_validators_success_and_failure_paths():
    now = datetime.now(timezone.utc)
    good = pd.DataFrame({"id": [1, 2], "date": [now, now], "value": [10.0, 20.0]})
    assert_nonempty(good, "good", 2)
    assert_max_date(good, "date", "good", 1)
    assert_unique_count(good, "id", 2, "good")
    assert_columns(good, ["id", "value"], "good")
    assert_missing_rate(good, "value", 0, "good")
    assert_no_duplicates(good, ["id"], "good")
    merged, bad = reconcile(good, good.copy(), ["id"], "value", "good")
    assert len(merged) == 2 and bad.empty

    checks = [
        lambda: assert_nonempty(good.iloc[0:0], "empty"),
        lambda: assert_max_date(pd.DataFrame({"d": [now - timedelta(days=10)]}), "d", "old", 1),
        lambda: assert_unique_count(good, "id", 3, "wrapped"),
        lambda: assert_columns(good, ["missing"], "changed"),
        lambda: assert_missing_rate(pd.DataFrame({"x": [None]}), "x", 0.5, "blank"),
        lambda: assert_no_duplicates(pd.DataFrame({"id": [1, 1]}), ["id"], "dup"),
    ]
    for check in checks:
        with pytest.raises(DataQualityError, match="actual.*expected"):
            check()


def test_reconcile_rejects_low_overlap_and_excess_mismatch():
    a = pd.DataFrame({"id": range(100), "v": [1.0] * 100})
    b = pd.DataFrame({"id": range(2, 102), "v": [1.0] * 100})
    with pytest.raises(DataQualityError, match="actual overlap=.*expected"):
        reconcile(a, b, ["id"], "v", "coverage", min_overlap=0.99)
    b = a.copy()
    b.loc[:1, "v"] = 2.0
    with pytest.raises(DataQualityError, match="actual bad_rate=.*expected"):
        reconcile(a, b, ["id"], "v", "values")


def test_all_four_outputs_exist_and_are_nonempty():
    names = ["benchmark_power.csv", "benchmark_three_sectors.csv", "alpha_table.csv",
             "key_emitters_2019_2020.csv"]
    for name in names:
        path = OUT / name
        assert path.exists() and path.stat().st_size > 0
        assert not pd.read_csv(path).empty
