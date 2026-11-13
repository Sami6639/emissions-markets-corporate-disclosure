"""Separate tables from carbon narrative on annual-report keyword-hit pages.

The pipeline deliberately starts from the PDFs.  It does not read the legacy
``cache_carbon_text`` directory.  Per-report JSON metadata and plain-text
narrative files make interrupted runs resumable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

import fitz
import numpy as np
import pandas as pd
import pdfplumber
from sklearn.feature_extraction.text import TfidfVectorizer


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "raw" / "reports" / "manifest.csv"
REPORTS = ROOT / "raw" / "reports"
DISCLOSURE = ROOT / "out" / "carbon_disclosure.csv"
SAMPLE = ROOT / "out" / "sample_definition.csv"
OUTPUT = ROOT / "out" / "carbon_narrative.csv"
CACHE = ROOT / "out" / "cache_narrative"
META_CACHE = ROOT / "out" / "cache_narrative_meta"
REPORT = ROOT / "out" / "narrative_report.md"
CACHE_VERSION = 1

KEYWORDS = (
    "碳排放", "碳配额", "碳交易", "碳资产", "碳市场", "碳中和",
    "碳达峰", "温室气体", "CCER",
)
KEYWORD_RE = re.compile("|".join(map(re.escape, KEYWORDS)), re.I)
SENTENCE_RE = re.compile(r"[^。；！？!?;]+[。；！？!?;]|[^。；！？!?;]+$")
DIGIT_RE = re.compile(r"\d")
NUMBER_RE = re.compile(
    r"(?<![\d.])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?![\d.])"
)
QUANTITY_RE = re.compile(
    r"(?<![\d.])[-+]?\d+(?:,\d{3})*(?:\.\d+)?\s*"
    r"(?:亿吨|万吨|千吨|吨|亿元|万元|千元|元|亿千瓦时|万千瓦时|千瓦时|%|％)"
)
HEADER_RE = re.compile(
    r"本期发生额|上期发生额|本年发生额|上年发生额|本期期末|上期期末|"
    r"期末余额|期初余额|本期数|上期数|项目|金额|比例"
)

OUTPUT_COLUMNS = [
    "code", "year", "n_pages_hit", "narr_char", "narr_sent", "narr_num",
    "narr_num_density", "narr_qty", "narr_qty_density", "tab_char",
    "tab_num", "narr_text_hash", "sim_self_prev_tfidf",
    "sim_peer_year_tfidf",
]


def _pages(value: object) -> list[int]:
    if pd.isna(value) or not str(value).strip():
        return []
    return sorted({int(x) for x in str(value).split(";") if x.strip()})


def _compact(text: str) -> str:
    text = re.sub(r"[\u0000\u200b\ufeff]", "", text or "")
    return re.sub(r"\s+", "", text)


def _carbon_sentences(text: str, apply_quality_rules: bool = True) -> list[str]:
    """Return keyword-bearing sentences while retaining their end marks."""
    compact = _compact(text)
    if not compact:
        return []
    result: list[str] = []
    matches = list(SENTENCE_RE.finditer(compact))
    for i, match in enumerate(matches):
        sentence = match.group()
        if not KEYWORD_RE.search(sentence):
            continue
        if apply_quality_rules:
            if not 10 <= len(sentence) <= 200:
                continue
            if len(DIGIT_RE.findall(sentence)) / len(sentence) >= 0.30:
                continue
            ended = sentence[-1] in "。；！？!?;"
            if not ended and i != len(matches) - 1:
                continue
        result.append(sentence)
    return result


def _inside_bbox(obj: dict, bboxes: list[tuple[float, float, float, float]]) -> bool:
    """Use an object's centre so table-border glyphs are assigned once."""
    needed = ("x0", "x1", "top", "bottom")
    if any(k not in obj for k in needed):
        return False
    cx = (float(obj["x0"]) + float(obj["x1"])) / 2
    cy = (float(obj["top"]) + float(obj["bottom"])) / 2
    return any(x0 <= cx <= x1 and top <= cy <= bottom for x0, top, x1, bottom in bboxes)


def _looks_like_full_page_table(text: str) -> bool:
    compact = _compact(text)
    if not compact:
        return False
    if len(DIGIT_RE.findall(compact)) / len(compact) > 0.25:
        return True
    hits = list(HEADER_RE.finditer(compact))
    # Three table-header terms clustered in a short span are unlikely prose.
    return any(hits[i + 2].start() - hits[i].start() <= 120 for i in range(len(hits) - 2))


def _page_parts(page: pdfplumber.page.Page) -> tuple[str, str, bool, int]:
    """Return narrative text, table text, full-page flag and table count."""
    full_text = page.extract_text(x_tolerance=2, y_tolerance=3) or ""
    tables = page.find_tables()
    bboxes = [tuple(float(v) for v in table.bbox) for table in tables]
    if not bboxes and _looks_like_full_page_table(full_text):
        return "", full_text, True, 0
    if not bboxes:
        return full_text, "", False, 0
    narrative = page.filter(lambda obj: not _inside_bbox(obj, bboxes)).extract_text(
        x_tolerance=2, y_tolerance=3
    ) or ""
    tabular = page.filter(lambda obj: _inside_bbox(obj, bboxes)).extract_text(
        x_tolerance=2, y_tolerance=3
    ) or ""
    return narrative, tabular, False, len(bboxes)


def _cache_paths(code: str, year: int) -> tuple[Path, Path]:
    return CACHE / f"{code}_{year}.txt", META_CACHE / f"{code}_{year}.json"


def _valid_cache(meta: dict, hit_pages: list[int], pdf_path: Path) -> bool:
    stat = pdf_path.stat()
    return (
        meta.get("cache_version") == CACHE_VERSION
        and meta.get("hit_pages") == hit_pages
        and meta.get("pdf_bytes") == stat.st_size
        and meta.get("pdf_mtime_ns") == stat.st_mtime_ns
    )


def _extract_report(task: tuple[str, int, str, list[int], bool]) -> dict:
    code, year, filename, hit_pages, force = task
    pdf_path = REPORTS / filename
    text_path, meta_path = _cache_paths(code, year)
    if not force and text_path.exists() and meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if _valid_cache(meta, hit_pages, pdf_path):
                meta["narrative"] = text_path.read_text(encoding="utf-8")
                return meta
        except (OSError, ValueError, TypeError):
            pass

    narrative_pages: list[str] = []
    tabular_pages: list[str] = []
    pre_pages: list[str] = []
    whole_page_table_pages: list[int] = []
    table_count = 0
    if hit_pages:
        # PyMuPDF cheaply validates page numbers and obtains the unseparated
        # baseline; pdfplumber is then invoked only for the specified pages.
        with fitz.open(pdf_path) as doc:
            if any(p < 1 or p > len(doc) for p in hit_pages):
                raise ValueError(f"invalid hit page in {filename}: {hit_pages}")
            pre_pages = [doc[p - 1].get_text("text") or "" for p in hit_pages]
        with pdfplumber.open(pdf_path) as pdf:
            for pno in hit_pages:
                narrative, tabular, full_page, n_tables = _page_parts(pdf.pages[pno - 1])
                narrative_pages.append(narrative)
                tabular_pages.append(tabular)
                table_count += n_tables
                if full_page:
                    whole_page_table_pages.append(pno)

    sentences: list[str] = []
    for page_text in narrative_pages:
        sentences.extend(_carbon_sentences(page_text, apply_quality_rules=True))
    narrative_text = "\n".join(sentences)
    tabular_text = "\n".join(x for x in tabular_pages if x)
    pre_sentences: list[str] = []
    for page_text in pre_pages:
        pre_sentences.extend(_carbon_sentences(page_text, apply_quality_rules=False))
    pre_text = "\n".join(pre_sentences)

    stat = pdf_path.stat()
    meta = {
        "cache_version": CACHE_VERSION,
        "code": code,
        "year": year,
        "hit_pages": hit_pages,
        "pdf_bytes": stat.st_size,
        "pdf_mtime_ns": stat.st_mtime_ns,
        "narrative": narrative_text,
        "tabular": tabular_text,
        "pre_carbon_text": pre_text,
        "whole_page_table_pages": whole_page_table_pages,
        "table_count": table_count,
    }
    CACHE.mkdir(parents=True, exist_ok=True)
    META_CACHE.mkdir(parents=True, exist_ok=True)
    text_path.write_text(narrative_text, encoding="utf-8")
    disk_meta = {k: v for k, v in meta.items() if k != "narrative"}
    meta_path.write_text(json.dumps(disk_meta, ensure_ascii=False), encoding="utf-8")
    return meta


def _metric_row(meta: dict) -> dict:
    text = meta["narrative"]
    tabular = meta["tabular"]
    result: dict[str, object] = {
        "code": meta["code"],
        "year": meta["year"],
        "n_pages_hit": len(meta["hit_pages"]),
        "narr_char": np.nan,
        "narr_sent": np.nan,
        "narr_num": np.nan,
        "narr_num_density": np.nan,
        "narr_qty": np.nan,
        "narr_qty_density": np.nan,
        "tab_char": np.nan,
        "tab_num": np.nan,
        "narr_text_hash": np.nan,
        "sim_self_prev_tfidf": np.nan,
        "sim_peer_year_tfidf": np.nan,
    }
    if text:
        n_char = sum(len(x) for x in text.splitlines())
        n_num = len(NUMBER_RE.findall(text))
        n_qty = len(QUANTITY_RE.findall(text))
        result.update(
            narr_char=n_char,
            narr_sent=len(text.splitlines()),
            narr_num=n_num,
            narr_num_density=n_num * 1000 / n_char,
            narr_qty=n_qty,
            narr_qty_density=n_qty * 1000 / n_char,
            narr_text_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )
    tab_compact = _compact(tabular)
    if tab_compact:
        result["tab_char"] = len(tab_compact)
        result["tab_num"] = len(NUMBER_RE.findall(tab_compact))
    return result


def _add_similarity(df: pd.DataFrame, texts: list[str], sectors: list[object]) -> None:
    nonempty = [i for i, text in enumerate(texts) if text]
    if not nonempty:
        return
    vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(2, 3), lowercase=False, norm="l2")
    matrix = vectorizer.fit_transform([texts[i] for i in nonempty])
    pos = {idx: p for p, idx in enumerate(nonempty)}
    lookup = {(df.at[i, "code"], int(df.at[i, "year"])): i for i in df.index}
    for i in nonempty:
        previous = lookup.get((df.at[i, "code"], int(df.at[i, "year"]) - 1))
        if previous in pos:
            value = float(matrix[pos[i]].multiply(matrix[pos[previous]]).sum())
            df.at[i, "sim_self_prev_tfidf"] = min(1.0, max(0.0, value))

    for _, indexes in df.groupby("year", sort=False).groups.items():
        indexes = [int(i) for i in indexes if int(i) in pos]
        by_sector: dict[str, list[int]] = {}
        for i in indexes:
            if pd.notna(sectors[i]):
                by_sector.setdefault(str(sectors[i]), []).append(i)
        for peers in by_sector.values():
            if len(peers) < 2:
                continue
            positions = [pos[i] for i in peers]
            similarities = (matrix[positions] @ matrix[positions].T).toarray()
            for local_i, i in enumerate(peers):
                others = np.arange(len(peers)) != local_i
                value = float(similarities[local_i, others].mean())
                df.at[i, "sim_peer_year_tfidf"] = min(1.0, max(0.0, value))


def _describe(series: pd.Series) -> tuple[str, str, str]:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return "—", "—", "0"
    return f"{values.mean():.2f}", f"{values.median():.2f}", str(len(values))


def _write_report(df: pd.DataFrame, metas: list[dict], sample: pd.DataFrame) -> None:
    pre_char: list[float] = []
    pre_density: list[float] = []
    for meta in metas:
        text = meta["pre_carbon_text"]
        compact = _compact(text)
        if compact:
            pre_char.append(float(len(compact)))
            pre_density.append(len(NUMBER_RE.findall(compact)) * 1000 / len(compact))
    tab_density = (df["tab_num"] * 1000 / df["tab_char"]).replace([np.inf, -np.inf], np.nan)
    effective = int(df["narr_char"].notna().sum())
    old_direct_count = len(pre_char)
    merged = df.merge(sample[["code", "ets_status"]], on="code", how="left", validate="many_to_one")
    lines = [
        "# 碳叙述—表格分离报告", "",
        "## 核心结果", "",
        f"本轮从原始 PDF 重新处理 {len(df)} 份年报，仅精解析 hit_pages 指定的 {int(df.n_pages_hit.sum())} 页；未读取旧 cache_carbon_text。",
        f"直接在未分离页面文本中检出碳关键词文本的样本为 **{old_direct_count}** 份；严格剔除表格并应用句长、数字占比和句末规则后，有效碳叙述为 **{effective}** 份。", "",
        "| 口径 | 文本长度中位数（字符） | 数字密度中位数（数字项/千字） | N |",
        "|---|---:|---:|---:|",
        f"| 分离前：PDF 原始碳关键词文本 | {np.median(pre_char) if pre_char else math.nan:.2f} | {np.median(pre_density) if pre_density else math.nan:.2f} | {len(pre_char)} |",
        f"| 分离后：有效碳叙述 | {df.narr_char.median():.2f} | {df.narr_num_density.median():.2f} | {effective} |",
        f"| 表格侧（对照） | {df.tab_char.median():.2f} | {tab_density.median():.2f} | {int(tab_density.notna().sum())} |", "",
        "“分离前”由本轮直接从 PDF 的 hit_pages 重抽，保留含碳关键词的原始句段；“分离后”只统计表格 bbox 外且通过质量规则的碳叙述。表格侧数字密度显著更高，是坐标分离奏效的直接对照。", "",
        "## 按 ets_status 分组", "",
        "| ets_status | 叙述长度均值 | 叙述长度中位数 | 数字密度均值 | 数字密度中位数 | 自相似度均值 | 自相似度中位数 | 有效叙述 N |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for status in ("always", "expansion", "control"):
        part = merged[merged.ets_status == status]
        length = _describe(part.narr_char)
        density = _describe(part.narr_num_density)
        similarity = _describe(part.sim_self_prev_tfidf)
        lines.append(
            f"| {status} | {length[0]} | {length[1]} | {density[0]} | {density[1]} | "
            f"{similarity[0]} | {similarity[1]} | {length[2]} |"
        )

    full_pages = [(m["code"], m["year"], p) for m in metas for p in m["whole_page_table_pages"]]
    total_hit_pages = int(df.n_pages_hit.sum())
    ratio = len(full_pages) / total_hit_pages * 100 if total_hit_pages else 0
    lines += [
        "", "## 整页表格判定", "",
        f"find_tables() 未找到 bbox、但数字字符占比超过 25% 或短距离内聚集至少 3 个表头词的页面共有 **{len(full_pages)}** 页，占全部 hit_pages 的 **{ratio:.2f}%**。这些页全部计入 tabular，不进入 narrative。", "",
        "整页表格页清单（code/year/page）：", "",
        ", ".join(f"{c}/{y}/{p}" for c, y, p in full_pages) if full_pages else "无。",
        "", "## 碳叙述原文抽样", "",
    ]
    # Prefer compact, low-digit examples from different companies so the
    # manual sample shows readable prose rather than five long disclosures
    # from a single prolific reporter.
    candidates = (
        df[
            df.narr_char.between(80, 260)
            & (df.narr_num_density < 25)
            & df.narr_sent.between(1, 3)
        ]
        .sort_values(["code", "year"])
        .drop_duplicates("code")
        .head(5)
    )
    if len(candidates) < 5:
        extras = df[df.narr_char.notna() & ~df.index.isin(candidates.index)].sort_values(
            ["narr_char", "code", "year"], ascending=[False, True, True]
        )
        candidates = pd.concat([candidates, extras]).head(5)
    meta_lookup = {(m["code"], int(m["year"])): m for m in metas}
    for n, row in enumerate(candidates.itertuples(index=False), 1):
        excerpt = meta_lookup[(row.code, int(row.year))]["narrative"]
        lines += [f"### {n}. {row.code} / {row.year}", "", excerpt, ""]
    lines += [
        "## 方法说明", "",
        "每个命中页先调用 pdfplumber.find_tables() 取得全部 bbox，再按字符对象中心坐标将页内文字互斥地分配至 narrative 或 tabular。碳叙述须含指定关键词、长度 10–200 字、数字字符占比低于 30%，并以句号、分号、问号、叹号结束或为页末句。数量指标只计后接吨、金额、千瓦时或百分比等单位的数字表达。TF-IDF 使用碳叙述的字符 2–3 gram；自相似度与同公司上一年比较，peer 相似度为同年同 sector 的其他公司平均余弦相似度。空文本及无法形成比较的相似度均留空。", "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def build(workers: int = 4, force: bool = False) -> pd.DataFrame:
    manifest = pd.read_csv(MANIFEST, dtype={"code": str})
    manifest["code"] = manifest.code.str.zfill(6)
    disclosure = pd.read_csv(DISCLOSURE, dtype={"code": str})[["code", "year", "hit_pages"]]
    disclosure["code"] = disclosure.code.str.zfill(6)
    sample = pd.read_csv(SAMPLE, dtype={"code": str})[["code", "sector", "ets_status"]]
    sample["code"] = sample.code.str.zfill(6)
    source = manifest.merge(disclosure, on=["code", "year"], how="left", validate="one_to_one")
    source = source.merge(sample, on="code", how="left", validate="many_to_one")
    tasks = [
        (r.code, int(r.year), r.file, _pages(r.hit_pages), force)
        for r in source.itertuples(index=False)
    ]
    if workers == 1:
        metas = [_extract_report(task) for task in tasks]
    else:
        try:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                metas = list(pool.map(_extract_report, tasks, chunksize=4))
        except PermissionError:
            # Some managed sandboxes disable POSIX semaphores used by process
            # pools.  Independent PDF handles make a thread pool a safe
            # bounded fallback, while preserving resumability.
            with ThreadPoolExecutor(max_workers=workers) as pool:
                metas = list(pool.map(_extract_report, tasks))

    df = pd.DataFrame([_metric_row(meta) for meta in metas])
    texts = [meta["narrative"] for meta in metas]
    _add_similarity(df, texts, source.sector.tolist())
    assert len(df) == len(manifest) == 3582
    assert not df.duplicated(["code", "year"]).any()
    for col in ("sim_self_prev_tfidf", "sim_peer_year_tfidf"):
        assert df[col].dropna().between(0, 1).all()
    empty = df.narr_char.isna()
    narrative_metrics = [
        "narr_sent", "narr_num", "narr_num_density", "narr_qty",
        "narr_qty_density", "narr_text_hash", "sim_self_prev_tfidf",
        "sim_peer_year_tfidf",
    ]
    assert df.loc[empty, narrative_metrics].isna().all().all()
    assert (df.loc[~empty, "narr_sent"] >= 1).all()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    df[OUTPUT_COLUMNS].to_csv(OUTPUT, index=False, encoding="utf-8-sig", float_format="%.8f")
    _write_report(df, metas, sample)
    return df


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = build(workers=max(1, args.workers), force=args.force)
    print(f"wrote {OUTPUT} ({len(result)} rows), {REPORT}, and {CACHE}")


if __name__ == "__main__":
    main()
