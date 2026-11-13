from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "out" / "carbon_text_similarity.csv"
MANIFEST = ROOT / "raw" / "reports" / "manifest.csv"
SIM_COLUMNS = [
    f"{base}_{method}"
    for base in ("sim_self_prev", "sim_peer_year", "sim_all_year")
    for method in ("jaccard", "tfidf")
]


def data():
    return pd.read_csv(OUTPUT, dtype={"code": str})


def test_similarity_bounds():
    df = data()
    for col in SIM_COLUMNS:
        assert df[col].dropna().between(0, 1).all(), col


def test_self_similarity_exceeds_peer_similarity():
    df = data()
    for method in ("jaccard", "tfidf"):
        self_median = df[f"sim_self_prev_{method}"].median()
        peer_median = df[f"sim_peer_year_{method}"].median()
        assert self_median > peer_median, (method, self_median, peer_median)


def test_empty_carbon_text_has_only_missing_metrics():
    df = data()
    metric_columns = SIM_COLUMNS + ["n_char", "n_sent", "n_num"]
    empty = df["n_char"].isna()
    assert df.loc[empty, metric_columns].isna().all().all()


def test_row_count_matches_manifest():
    # the boilerplate measure shares the narrative window， FY2021-FY2025，see test_narrative。
    manifest = pd.read_csv(MANIFEST)
    window = manifest[manifest.year.between(2021, 2025)]
    assert len(data()) == len(window) == 3582
