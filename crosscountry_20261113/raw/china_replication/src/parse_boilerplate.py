"""Extract keyword-bearing carbon sentences and measure boilerplate similarity.

Only pages listed in ``out/carbon_disclosure.csv:hit_pages`` are opened.  The
extracted corpus is cached per firm-year so interrupted runs can resume without
reading completed PDFs again.
"""

from __future__ import annotations

import argparse
import itertools
import json
import re
from pathlib import Path

import fitz
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

try:
    import jieba

    jieba.setLogLevel(20)
    HAS_JIEBA = True
except ImportError:  # pragma: no cover - exercised only in minimal environments
    jieba = None
    HAS_JIEBA = False


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "raw" / "reports" / "manifest.csv"
REPORTS = ROOT / "raw" / "reports"
DISCLOSURE = ROOT / "out" / "carbon_disclosure.csv"
SAMPLE = ROOT / "out" / "sample_definition.csv"
CACHE = ROOT / "out" / "cache_carbon_text"
OUTPUT = ROOT / "out" / "carbon_text_similarity.csv"
REPORT = ROOT / "out" / "boilerplate_report.md"

KEYWORDS = ("碳排放", "碳配额", "碳交易", "碳资产", "碳市场", "碳中和", "碳达峰", "温室气体")
KEYWORD_RE = re.compile("|".join(map(re.escape, KEYWORDS)))
SENTENCE_END_RE = re.compile(r"(?<=[。！？!?；;])\s*")
NUMBER_RE = re.compile(r"(?<!\d)(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?!\d)")
SIM_BASES = ("sim_self_prev", "sim_peer_year", "sim_all_year")
SIM_COLUMNS = tuple(f"{base}_{method}" for base in SIM_BASES for method in ("jaccard", "tfidf"))


def _pages(value: object) -> list[int]:
    if pd.isna(value) or not str(value).strip():
        return []
    return sorted({int(x) for x in str(value).split(";") if x.strip()})


def _sentences(text: str) -> list[str]:
    # PDF line breaks usually represent visual wrapping, not sentence endings.
    text = re.sub(r"[\u0000\u200b\ufeff]", "", text)
    text = re.sub(r"\s+", "", text)
    if not text:
        return []
    return [s for s in SENTENCE_END_RE.split(text) if s and KEYWORD_RE.search(s)]


def extract_carbon_text(pdf_path: Path, hit_pages: list[int]) -> tuple[str, int]:
    """Return joined carbon sentences and their count from one-based pages."""
    if not hit_pages:
        return "", 0
    pieces: list[str] = []
    with fitz.open(pdf_path) as doc:
        for pno in hit_pages:
            if not 1 <= pno <= len(doc):
                raise ValueError(f"page {pno} outside 1..{len(doc)} in {pdf_path.name}")
            pieces.extend(_sentences(doc[pno - 1].get_text("text") or ""))
    return "\n".join(pieces), len(pieces)


def _load_or_extract(code: str, year: int, filename: str, hit_pages: list[int]) -> tuple[str, int]:
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE / f"{code}_{year}.json"
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("hit_pages") == hit_pages:
                text = str(cached.get("text", ""))
                return text, int(cached.get("n_sent", len(text.splitlines()) if text else 0))
        except (OSError, ValueError, TypeError):
            pass
    text, n_sent = extract_carbon_text(REPORTS / filename, hit_pages)
    payload = {"hit_pages": hit_pages, "n_sent": n_sent, "text": text}
    cache_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return text, n_sent


def _char_ngrams(text: str, n: int = 3) -> set[str]:
    compact = re.sub(r"\s+", "", text)
    return {compact[i:i + n] for i in range(max(0, len(compact) - n + 1))}


def _jaccard(a: set[str], b: set[str]) -> float | None:
    if not a or not b:
        return None
    return len(a & b) / len(a | b)


def _tokenize(text: str) -> list[str]:
    compact = re.sub(r"\s+", "", text)
    if HAS_JIEBA:
        return [x.strip() for x in jieba.cut(compact) if x.strip()]
    return [compact[i:i + 2] for i in range(max(0, len(compact) - 1))]


def _add_jaccard(df: pd.DataFrame, grams: list[set[str]]) -> None:
    df["sim_self_prev_jaccard"] = np.nan
    lookup = {(r.code, int(r.year)): i for i, r in df[["code", "year"]].iterrows()}
    for i, row in df.iterrows():
        j = lookup.get((row["code"], int(row["year"]) - 1))
        if j is not None:
            value = _jaccard(grams[i], grams[j])
            if value is not None:
                df.at[i, "sim_self_prev_jaccard"] = value

    df["sim_peer_year_jaccard"] = np.nan
    df["sim_all_year_jaccard"] = np.nan
    for _, idx_obj in df.groupby("year", sort=False).groups.items():
        idx = [int(i) for i in idx_obj if grams[int(i)]]
        sums_all = {i: 0.0 for i in idx}
        counts_all = {i: 0 for i in idx}
        sums_peer = {i: 0.0 for i in idx}
        counts_peer = {i: 0 for i in idx}
        for i, j in itertools.combinations(idx, 2):
            value = _jaccard(grams[i], grams[j])
            assert value is not None
            sums_all[i] += value; sums_all[j] += value
            counts_all[i] += 1; counts_all[j] += 1
            if pd.notna(df.at[i, "sector"]) and df.at[i, "sector"] == df.at[j, "sector"]:
                sums_peer[i] += value; sums_peer[j] += value
                counts_peer[i] += 1; counts_peer[j] += 1
        for i in idx:
            if counts_all[i]:
                df.at[i, "sim_all_year_jaccard"] = sums_all[i] / counts_all[i]
            if counts_peer[i]:
                df.at[i, "sim_peer_year_jaccard"] = sums_peer[i] / counts_peer[i]


def _add_tfidf(df: pd.DataFrame, texts: list[str]) -> None:
    for base in SIM_BASES:
        df[f"{base}_tfidf"] = np.nan
    nonempty = [i for i, text in enumerate(texts) if text]
    if not nonempty:
        return
    vectorizer = TfidfVectorizer(tokenizer=_tokenize, token_pattern=None, lowercase=False, norm="l2")
    matrix = vectorizer.fit_transform([texts[i] for i in nonempty])
    pos = {idx: p for p, idx in enumerate(nonempty)}
    lookup = {(r.code, int(r.year)): i for i, r in df[["code", "year"]].iterrows()}
    for i in nonempty:
        j = lookup.get((df.at[i, "code"], int(df.at[i, "year"]) - 1))
        if j in pos:
            df.at[i, "sim_self_prev_tfidf"] = float(matrix[pos[i]].multiply(matrix[pos[j]]).sum())

    for _, idx_obj in df.groupby("year", sort=False).groups.items():
        idx = [int(i) for i in idx_obj if int(i) in pos]
        if len(idx) < 2:
            continue
        rows = [pos[i] for i in idx]
        similarities = (matrix[rows] @ matrix[rows].T).toarray()
        for local_i, i in enumerate(idx):
            other = np.arange(len(idx)) != local_i
            df.at[i, "sim_all_year_tfidf"] = float(similarities[local_i, other].mean())
            peer = np.array([
                k != local_i and pd.notna(df.at[i, "sector"]) and df.at[j, "sector"] == df.at[i, "sector"]
                for k, j in enumerate(idx)
            ])
            if peer.any():
                df.at[i, "sim_peer_year_tfidf"] = float(similarities[local_i, peer].mean())


def _describe(series: pd.Series) -> tuple[str, str, str, str, str]:
    x = pd.to_numeric(series, errors="coerce").dropna()
    if x.empty:
        return ("—",) * 5
    values = tuple(f"{v:.4f}" for v in (x.mean(), x.quantile(.25), x.median(), x.quantile(.75)))
    return (*values, str(len(x)))


def _write_report(df: pd.DataFrame, short: list[str]) -> None:
    method_note = "jieba 中文分词" if HAS_JIEBA else "字符 2-gram（环境未安装 jieba，已自动回退）"
    lines = [
        "# 碳文本套话相似度报告", "",
        f"共处理 **{len(df)}** 份年报，其中 {int(df.n_char.notna().sum())} 份抽得碳文本。", "",
        "## 相似度总体分布", "",
        "| 指标 | 均值 | P25 | 中位数 | P75 | N |", "|---|---:|---:|---:|---:|---:|",
    ]
    labels = {"sim_self_prev": "同公司上一年度", "sim_peer_year": "同年度同行业", "sim_all_year": "同年度全样本"}
    for col in SIM_COLUMNS:
        base, method = col.rsplit("_", 1)
        lines.append(f"| {labels[base]}（{method}） | " + " | ".join(_describe(df[col])) + " |")

    lines += ["", "## 按覆盖状态分组", "", "| 组别 | 指标 | 均值 | P25 | 中位数 | P75 | N |", "|---|---|---:|---:|---:|---:|---:|"]
    for status in ("always", "expansion", "control"):
        part = df[df.ets_status == status]
        for col in SIM_COLUMNS:
            lines.append(f"| {status} | {col} | " + " | ".join(_describe(part[col])) + " |")

    lines += ["", "## 逐年趋势", "", "| 年份 | 指标 | 均值 | P25 | 中位数 | P75 | N |", "|---:|---|---:|---:|---:|---:|---:|"]
    for year, part in df.groupby("year", sort=True):
        for col in SIM_COLUMNS:
            lines.append(f"| {year} | {col} | " + " | ".join(_describe(part[col])) + " |")

    density = df["n_num"] / df["n_char"]
    lines += ["", "## 数字密度（n_num / n_char）", "", "该比值以抽得碳文本的字符数为分母；空文本不进入统计。", "", "| 组别 | 年份 | 均值 | P25 | 中位数 | P75 | N |", "|---|---:|---:|---:|---:|---:|---:|"]
    density_df = df.assign(num_density=density)
    for (status, year), part in density_df.groupby(["ets_status", "year"], sort=True, dropna=False):
        lines.append(f"| {status if pd.notna(status) else '未匹配'} | {year} | " + " | ".join(_describe(part.num_density)) + " |")

    self_j = df["sim_self_prev_jaccard"].median()
    peer_j = df["sim_peer_year_jaccard"].median()
    self_t = df["sim_self_prev_tfidf"].median()
    peer_t = df["sim_peer_year_tfidf"].median()
    lines += [
        "", "## 核心比较与实现说明", "",
        f"字符 3-gram Jaccard：同公司上年中位数 **{self_j:.4f}**，同行中位数 **{peer_j:.4f}**。",
        f"TF-IDF 余弦：同公司上年中位数 **{self_t:.4f}**，同行中位数 **{peer_t:.4f}**。", "",
        "Jaccard 使用去空白后的字符级 3-gram 集合；TF-IDF 使用全体非空碳文本拟合词表并作 L2 归一化，分词方案为" + method_note + "。同行和全样本均只在同一年内比较且排除自身；上一年度严格指 year−1。PDF 仅读取 hit_pages 指定页，碳句按中文/英文句末标点切分。", "",
        "空碳文本的计数和全部相似度均保留为空。短于 3 个去空白字符的文本无法构造 3-gram，相关相似度保留为空。", "",
        "## 文本过短清单", "",
    ]
    lines.extend([f"- {x}" for x in short] if short else ["无。"])
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build() -> pd.DataFrame:
    manifest = pd.read_csv(MANIFEST, dtype={"code": str})
    manifest["code"] = manifest["code"].str.zfill(6)
    disclosure = pd.read_csv(DISCLOSURE, dtype={"code": str})[["code", "year", "hit_pages"]]
    disclosure["code"] = disclosure["code"].str.zfill(6)
    sample = pd.read_csv(SAMPLE, dtype={"code": str})[["code", "sector", "ets_status"]]
    sample["code"] = sample["code"].str.zfill(6)
    df = manifest.merge(disclosure, on=["code", "year"], how="left", validate="one_to_one")
    df = df.merge(sample, on="code", how="left", validate="many_to_one")
    texts: list[str] = []
    sent_counts: list[int] = []
    for row in df.itertuples(index=False):
        text, n_sent = _load_or_extract(row.code, int(row.year), row.file, _pages(row.hit_pages))
        texts.append(text)
        sent_counts.append(n_sent)
    nonempty = np.array([bool(x) for x in texts])
    df["n_char"] = [len(x) if x else np.nan for x in texts]
    df["n_sent"] = [n if text else np.nan for text, n in zip(texts, sent_counts)]
    df["n_num"] = [len(NUMBER_RE.findall(x)) if x else np.nan for x in texts]
    grams = [_char_ngrams(x) for x in texts]
    _add_jaccard(df, grams)
    _add_tfidf(df, texts)

    for col in SIM_COLUMNS:
        values = df[col].dropna()
        assert values.between(0, 1 + 1e-12).all(), f"{col} outside [0,1]"
        df[col] = df[col].clip(0, 1)
    empty_cols = list(SIM_COLUMNS) + ["n_char", "n_sent", "n_num"]
    assert df.loc[~nonempty, empty_cols].isna().all().all()
    assert len(df) == len(manifest)

    result_cols = ["code", "year", "sector", "ets_status", "n_char", "n_sent", "n_num", *SIM_COLUMNS]
    result = df[result_cols].copy()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT, index=False, encoding="utf-8-sig", float_format="%.8f")
    short = [f"{df.at[i, 'code']}_{df.at[i, 'year']}" for i, g in enumerate(grams) if texts[i] and not g]
    _write_report(result, short)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    result = build()
    print(f"wrote {OUTPUT} ({len(result)} rows) and {REPORT}")


if __name__ == "__main__":
    main()
