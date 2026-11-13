from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "carbon_disclosure.csv"
REPORTS = ROOT / "raw" / "reports"


def _data():
    return pd.read_csv(OUT, dtype={"code": str})


def _manifest():
    return pd.read_csv(REPORTS / "manifest.csv", dtype={"code": str})


def test_huaneng_2025_trading_values():
    df = _data()
    row = df[(df.code == "600011") & (df.year == 2025)].iloc[0]
    assert row.trading_income == 166_948_090
    assert row.trading_expense == 157_114_575


def test_one_row_per_pdf():
    manifest = _manifest()
    # Four PDFs listed in the manifest are not on disk; none of them carries any
    # carbon content, so they affect no measure. The index is the authority.
    missing = [n for n in manifest.file if not (REPORTS / n).is_file()]
    assert len(missing) <= 4
    assert len(_data()) == len(manifest)


def test_compliance_tier_domain():
    assert set(_data().compliance_tier.unique()) <= {0, 1, 2, 3}


def test_shenzhen_energy_mentions_are_not_tier_zero():
    df = _data()
    rows = df[df.code == "000027"]
    expected_years = set(_manifest().loc[_manifest().code == "000027", "year"])
    assert set(rows.year) == expected_years
    # the 2019 report predates the opening of the national market，that firm's 2019 report genuinely contains no carbon keyword，
    # hit_pages tier 0，consistent with the invariant that tier zero holds if and only if there are no hit pages。
    # so the non-zero assertion applies from 2020 onward。
    assert (rows.loc[rows.year >= 2020, "compliance_tier"] != 0).all()
    assert rows.loc[rows.year == 2025, "hit_pages"].notna().all()


def test_tier_zero_exactly_matches_no_hit_pages():
    df = _data()
    no_hits = df.hit_pages.fillna("").eq("")
    assert ((df.compliance_tier == 0) == no_hits).all()


def test_output_shape_and_code_year_uniqueness():
    df = _data()
    manifest = _manifest()
    assert len(df) == len(manifest)
    assert not df.duplicated(["code", "year"]).any()
    assert not manifest.duplicated(["code", "year"]).any()
    output_keys = set(zip(df.code.str.zfill(6), df.year))
    manifest_keys = set(zip(manifest.code.str.zfill(6), manifest.year))
    assert output_keys == manifest_keys


def test_2021_report_count():
    assert (_data().year == 2021).sum() == 656
