from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "out" / "carbon_narrative.csv"
MANIFEST = ROOT / "raw" / "reports" / "manifest.csv"
CACHE = ROOT / "out" / "cache_narrative"


def data():
    return pd.read_csv(OUTPUT, dtype={"code": str})


def narrative(code: str, year: int) -> str:
    return (CACHE / f"{code}_{year}.txt").read_text(encoding="utf-8")


def test_known_financial_table_pollution_is_absent():
    text = narrative("601678", 2025)
    for pollutant in ("固定资产处置收益", "无形资产处置利得", "非货币性资产交换利得"):
        assert pollutant not in text


def test_other_known_table_pollution_is_absent():
    for code, year in (("000818", 2022), ("600346", 2023)):
        text = narrative(code, year)
        for pollutant in ("资产减值", "应收账款", "货币资金"):
            assert pollutant not in text


def test_narrative_digit_density_is_lower_than_table_density():
    df = data()
    narrative_density = df.narr_num_density.dropna()
    table_density = (df.tab_num * 1000 / df.tab_char).dropna()
    assert len(narrative_density) > 0 and len(table_density) > 0
    # "Significantly lower" is operationalized conservatively: the narrative
    # median must be less than half of the table-side median.
    assert narrative_density.median() < 0.5 * table_density.median()


def test_nonempty_narrative_has_sentence():
    df = data()
    assert (df.loc[df.narr_char.notna(), "narr_sent"] >= 1).all()


def test_similarity_bounds():
    df = data()
    for column in ("sim_self_prev_tfidf", "sim_peer_year_tfidf"):
        assert df[column].dropna().between(0, 1).all(), column


def test_shape_keys_and_cache_files():
    df = data()
    manifest = pd.read_csv(MANIFEST, dtype={"code": str})
    manifest = manifest[manifest.year.between(2021, 2025)]
    # narrative extraction covers FY2021-FY2025；2019 2020 the two years added later enter the panel through page-level measures only，
    # and are outside the narrative layer（the paper does not use narrative measures for them），so the assertion is made against the count within that window。
    window = manifest[manifest.year.between(2021, 2025)]
    assert len(df) == len(window) == 3582
    assert not df.duplicated(["code", "year"]).any()
    assert set(zip(df.code, df.year)) == set(zip(manifest.code.str.zfill(6), manifest.year))
    assert all((CACHE / f"{row.code}_{row.year}.txt").is_file() for row in df.itertuples())


def test_empty_narrative_metrics_are_missing_not_zero():
    df = data()
    empty = df.narr_char.isna()
    columns = [
        "narr_sent", "narr_num", "narr_num_density", "narr_qty",
        "narr_qty_density", "narr_text_hash", "sim_self_prev_tfidf",
        "sim_peer_year_tfidf",
    ]
    assert df.loc[empty, columns].isna().all().all()
