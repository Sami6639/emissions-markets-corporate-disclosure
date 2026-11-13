"""Fail-fast checks for carbon-market data sources."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Sequence

import numpy as np
import pandas as pd


class DataQualityError(ValueError):
    """Raised when apparently valid input fails a data-quality invariant."""


def assert_nonempty(df: pd.DataFrame, name: str, min_rows: int = 1) -> None:
    """Catch APIs/files that succeed silently but return an empty/truncated frame."""
    actual = len(df)
    if actual < min_rows:
        raise DataQualityError(f"{name}: actual rows={actual}; expected rows>={min_rows}")


def assert_max_date(
    df: pd.DataFrame, date_col: str, name: str, max_lag_days: int
) -> None:
    """Catch a silently frozen price feed whose rows stop at an old date."""
    assert_columns(df, [date_col], name)
    dates = pd.to_datetime(df[date_col], errors="coerce", utc=True)
    latest = dates.max()
    now = pd.Timestamp(datetime.now(timezone.utc))
    lag = float("inf") if pd.isna(latest) else (now - latest).total_seconds() / 86400
    if pd.isna(latest) or lag > max_lag_days:
        actual = "NaT" if pd.isna(latest) else latest.isoformat()
        raise DataQualityError(
            f"{name}: actual max_date={actual}, lag_days={lag}; "
            f"expected lag_days<={max_lag_days}"
        )


def assert_unique_count(
    df: pd.DataFrame, key_col: str, expected: int, name: str
) -> None:
    """Catch CNINFO pagination silently wrapping pageNum>100 back to page 1."""
    assert_columns(df, [key_col], name)
    actual = int(df[key_col].nunique(dropna=True))
    if actual != expected:
        raise DataQualityError(
            f"{name}: actual unique {key_col}={actual}; expected={expected}"
        )


def assert_columns(df: pd.DataFrame, required_cols: Iterable[str], name: str) -> None:
    """Catch an upstream redesign that silently renames or removes columns."""
    required = list(required_cols)
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise DataQualityError(
            f"{name}: actual columns={list(df.columns)}; expected required columns={required}; "
            f"missing={missing}"
        )


def assert_missing_rate(
    df: pd.DataFrame, col: str, max_rate: float, name: str
) -> None:
    """Catch a feed that returns rows but silently blanks a critical field."""
    assert_columns(df, [col], name)
    actual = float(df[col].isna().mean()) if len(df) else 1.0
    if actual > max_rate:
        raise DataQualityError(
            f"{name}: actual missing_rate({col})={actual:.6f}; expected<={max_rate:.6f}"
        )


def assert_no_duplicates(
    df: pd.DataFrame, key_cols: Sequence[str], name: str
) -> None:
    """Catch duplicated records caused by overlapping pages or repeated ingestion."""
    keys = list(key_cols)
    assert_columns(df, keys, name)
    actual = int(df.duplicated(keys, keep=False).sum())
    if actual:
        raise DataQualityError(
            f"{name}: actual duplicate rows={actual} for keys={keys}; expected=0"
        )


def reconcile(
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    keys: Sequence[str],
    value_col: str,
    name: str,
    rel_tol: float = 0.005,
    min_overlap: float = 0.98,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Catch plausible but wrong values by reconciling two sources and their coverage."""
    keys = list(keys)
    required = keys + [value_col]
    assert_columns(df_a, required, f"{name}.source_a")
    assert_columns(df_b, required, f"{name}.source_b")
    assert_no_duplicates(df_a, keys, f"{name}.source_a")
    assert_no_duplicates(df_b, keys, f"{name}.source_b")

    merged = df_a[required].merge(
        df_b[required], on=keys, how="inner", suffixes=("_a", "_b")
    )
    denominator = max(len(df_a), len(df_b), 1)
    overlap = len(merged) / denominator
    if overlap < min_overlap:
        raise DataQualityError(
            f"{name}: actual overlap={overlap:.6f} ({len(merged)}/{denominator}); "
            f"expected>={min_overlap:.6f}"
        )

    a = pd.to_numeric(merged[f"{value_col}_a"], errors="coerce")
    b = pd.to_numeric(merged[f"{value_col}_b"], errors="coerce")
    scale = np.maximum(np.maximum(a.abs(), b.abs()), np.finfo(float).eps)
    merged["relative_difference"] = (a - b).abs() / scale
    bad_mask = a.isna() | b.isna() | (merged["relative_difference"] > rel_tol)
    bad_rows = merged.loc[bad_mask].copy()
    bad_rate = len(bad_rows) / max(len(merged), 1)
    if bad_rate > 0.01:
        raise DataQualityError(
            f"{name}: actual bad_rate={bad_rate:.6f} ({len(bad_rows)}/{len(merged)}), "
            f"rel_tol={rel_tol}; expected bad_rate<=0.010000"
        )
    return merged, bad_rows
