"""Extract carbon-allowance disclosures from annual-report PDFs.

PyMuPDF performs the complete page scan.  pdfplumber is deliberately opened
only for keyword-hit pages and supplies table rows when a PDF's text stream is
not in reading order.  Empty values mean "not disclosed"; disclosed zeroes are
retained as numeric zeroes.
"""

from __future__ import annotations

import argparse
import math
import re
from pathlib import Path

import fitz
import pandas as pd
import pdfplumber


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "raw" / "reports"
OUTPUT = ROOT / "out" / "carbon_disclosure.csv"
REPORT = ROOT / "out" / "carbon_disclosure_report.md"
SAMPLE_DEFINITION = ROOT / "out" / "sample_definition.csv"

COLUMNS = [
    "code", "year", "n_pages", "hit_pages", "trading_income",
    "trading_expense", "income_items", "expense_items", "mention_context",
    "carbon_asset_balance", "qty_open", "qty_free",
    "qty_purchased", "qty_other_inc", "qty_surrender", "qty_sold",
    "qty_other_dec", "qty_close", "verified_emission", "compliance_tier",
]
VALUE_COLUMNS = COLUMNS[4:-1]

KEYWORDS = (
    "碳排放配额", "碳排放权", "碳排放权资产", "配额", "CEA", "碳交易",
    "碳资产", "核证自愿减排", "CCER",
)
CARBON_CONTEXT = re.compile(r"碳排放配额|碳排放权|(?<![A-Za-z])CEA(?![A-Za-z])", re.I)
NUM = r"(?:\(\s*[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s*\)|[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)"
NUM_RE = re.compile(NUM)

LABELS = {
    "trading_income": ["碳排放配额交易收入", "碳排放权交易收入", "碳配额交易收入", "碳排放权资产处置收益", "出售碳排放配额收益", "碳资产处置损益"],
    "trading_expense": ["碳排放配额交易费用", "碳排放权交易费用", "碳配额交易费用", "碳排放权资产处置损失", "碳排放权资产使用损失"],
    "carbon_asset_balance": ["碳排放权资产", "碳排放配额资产"],
    "qty_open": ["本期期初碳排放配额", "期初碳排放配额", "期初配额"],
    "qty_free": ["免费分配取得的配额", "免费分配取得"],
    "qty_purchased": ["购入取得的配额", "购入取得"],
    "qty_other_inc": ["其他方式增加的配额", "其他方式增加"],
    "qty_surrender": ["履约使用的配额", "履约使用"],
    "qty_sold": ["出售的配额", "出售配额"],
    "qty_other_dec": ["其他方式减少的配额", "其他方式减少"],
    "qty_close": ["本期期末碳排放配额", "期末碳排放配额", "期末配额"],
}

AMOUNT_ITEM_RE = re.compile(
    r"(?:出售)?(?:碳排放(?:权|配额)?|碳资产)[^\d\t\r\n]{0,8}?"
    r"(?:收益|损失|收入|费用|损益)"
)


def _number(token: str, multiplier: float = 1.0):
    token = token.strip()
    negative = token.startswith("(") and token.endswith(")")
    token = token.strip("() ").replace(",", "")
    try:
        value = float(token) * multiplier
    except ValueError:
        return None
    if negative:
        value = -abs(value)
    return int(value) if value.is_integer() else value


def _unit_multiplier(text: str, kind: str) -> float:
    """Normalise amounts reported in units of ten thousand yuan to yuan, and quantities reported in units of ten thousand tonnes to tonnes."""
    compact = re.sub(r"\s+", "", text[:1600])
    if kind == "amount":
        return 10_000.0 if re.search(r"单位[：:]?人民币?万元|金额单位[：:]?万元", compact) else 1.0
    return 10_000.0 if re.search(r"数量.{0,8}单位[：:]?万吨|单位[：:]?万吨", compact) else 1.0


def _first_after_label(text: str, labels: list[str], kind: str):
    """Return the first current-period value following a row label."""
    # Prefer pdfplumber's explicit cells.  An empty first data cell is a
    # disclosed blank, not zero and not permission to borrow a later cell.
    for line in text.splitlines():
        if "\t" not in line:
            continue
        cells = line.split("\t")
        for label in sorted(labels, key=len, reverse=True):
            for i, cell in enumerate(cells[:-1]):
                cell_clean = re.sub(r"^[1-4][．.]|^[（(][1-3][）)]", "", cell)
                if cell_clean != label:
                    continue
                first = cells[i + 1].strip()
                n = NUM_RE.fullmatch(first)
                if not n:
                    return None
                return _number(first, _unit_multiplier(text[max(0, text.find(line) - 1400):], kind))
    if kind == "amount" and any(label.endswith("资产") for label in labels):
        # A balance is accepted only from an explicit table row.  Narrative
        # phrases such as "asset disposal income" are not balance evidence.
        return None
    for label in sorted(labels, key=len, reverse=True):
        for match in re.finditer(re.escape(label), text):
            if kind == "amount" and label.endswith("资产"):
                suffix = text[match.end():match.end() + 8]
                if re.match(r"处置|使用|交易|收益|损失", suffix):
                    continue
            tail = text[match.end():match.end() + 260]
            # Stop before a following row/heading so its value cannot leak in.
            stop = re.search(
                r"\n\s*(?:[1-4][．.]|[（(][1-3][）)]|项目|合计|小计|其他说明|"
                r"本期|期初|期末|免费|购入|履约|出售)", tail
            )
            if stop:
                tail = tail[:stop.start()]
            n = NUM_RE.search(tail)
            if n:
                page_context = text[max(0, match.start() - 1400):match.end() + 300]
                return _number(n.group(), _unit_multiplier(page_context, kind))
    return None


def _table_text(pdf_path: Path, pages: list[int], fitz_texts: list[str]) -> dict[int, str]:
    """Extract tables only on keyword-hit pages (page numbers are one-based)."""
    result: dict[int, str] = {}
    if not pages:
        return result
    with pdfplumber.open(pdf_path) as pdf:
        for pno in pages:
            # Parsing narrative-only hit pages is costly and cannot add row values.
            t = fitz_texts[pno - 1]
            if not any(x in t for x in tuple(sum(LABELS.values(), [])) + ("碳排放配额变动情况", "实际排放量", "核查排放量")):
                continue
            try:
                tables = pdf.pages[pno - 1].extract_tables()
            except Exception:
                continue
            rows = []
            for table in tables or []:
                for row in table or []:
                    # Whitespace inside a cell is layout wrapping; tabs separate
                    # columns and newlines separate rows.
                    cells = [re.sub(r"\s+", "", str(c)) for c in row if c is not None]
                    rows.append("\t".join(cells))
            if rows:
                result[pno] = "\n".join(rows)
    return result


def _verified_emission(text: str):
    patterns = [
        rf"(?:经核查|核查确认|实际)(?:的)?(?:碳)?排放量(?:为|：|:)?\s*({NUM})\s*(万)?吨",
        rf"(?:碳)?排放量(?:为|：|:)?\s*({NUM})\s*(万)?吨(?:二氧化碳当量)?",
    ]
    for pattern in patterns:
        m = re.search(pattern, re.sub(r"\s+", "", text))
        if m:
            return _number(m.group(1), 10_000.0 if m.group(2) else 1.0)
    return None


def _amount_items(text: str) -> tuple[list[str], list[str], dict[str, float | int | None]]:
    """Find carbon-related P&L labels as a regex family, retaining raw labels."""
    income, expense = [], []
    values: dict[str, float | int | None] = {}
    for match in AMOUNT_ITEM_RE.finditer(text):
        label = re.sub(r"\s+", "", match.group())
        bucket = expense if re.search(r"损失|费用$", label) else income
        if label not in bucket:
            bucket.append(label)
        if label not in values:
            values[label] = _first_after_label(text, [label], "amount")
    return income, expense, values


def _mention_context(texts: list[str], hits: list[int]) -> str:
    """Return the first keyword-bearing source line, capped at 80 characters."""
    for pno in hits:
        for line in texts[pno - 1].splitlines():
            clean = line.strip()
            if clean and any(k.lower() in clean.lower() for k in KEYWORDS):
                return clean[:80]
    return ""


def parse_pdf(pdf_path: Path, code: str, year: int) -> dict:
    row = {c: None for c in COLUMNS}
    row.update(code=code, year=int(year))
    doc = fitz.open(pdf_path)
    texts, hits = [], []
    for i, page in enumerate(doc):
        text = page.get_text("text") or ""
        texts.append(text)
        if any(k.lower() in text.lower() for k in KEYWORDS):
            hits.append(i + 1)
    row["n_pages"] = len(doc)
    row["hit_pages"] = ";".join(map(str, hits))
    row["mention_context"] = _mention_context(texts, hits)
    doc.close()

    table_by_page = _table_text(pdf_path, hits, texts)
    combined_pages = []
    for pno in hits:
        combined_pages.append(texts[pno - 1])
        if pno in table_by_page:
            combined_pages.append(table_by_page[pno])
    text = "\n".join(combined_pages)

    for field in ("trading_income", "trading_expense", "carbon_asset_balance"):
        row[field] = _first_after_label(text, LABELS[field], "amount")
    income_items, expense_items, item_values = _amount_items(text)
    row["income_items"] = ";".join(income_items)
    row["expense_items"] = ";".join(expense_items)
    if row["trading_income"] is None:
        row["trading_income"] = next((item_values[x] for x in income_items if item_values[x] is not None), None)
    if row["trading_expense"] is None:
        row["trading_expense"] = next((item_values[x] for x in expense_items if item_values[x] is not None), None)
    for field in [c for c in VALUE_COLUMNS if c.startswith("qty_")]:
        row[field] = _first_after_label(text, LABELS[field], "quantity")
    row["verified_emission"] = _verified_emission(text)

    has_qty = any(row[c] is not None for c in VALUE_COLUMNS if c.startswith("qty_"))
    compact = re.sub(r"\s+", "", text)
    four_sections = all(re.search(p, compact) for p in (
        r"期初碳排放配额", r"本期增加的?碳排放配额",
        r"本期减少的?碳排放配额", r"期末碳排放配额",
    ))
    if not hits:
        row["compliance_tier"] = 0
    elif four_sections:
        row["compliance_tier"] = 3
    elif has_qty:
        row["compliance_tier"] = 2
    else:
        row["compliance_tier"] = 1
    assert (row["compliance_tier"] == 0) == (not row["hit_pages"])
    return row


def _write_report(df: pd.DataFrame) -> None:
    total = len(df)
    counts = df["compliance_tier"].value_counts().reindex(range(4), fill_value=0)
    lines = ["# 碳排放配额披露合规率报告", "", f"共处理 **{total}** 份年度报告。", "", "## 合规分级", "", "| 等级 | 公司年度数 | 占比 |", "|---:|---:|---:|"]
    for tier, count in counts.items():
        lines.append(f"| {tier} | {count} | {count / total:.2%} |")
    lines += ["", "口径：tier 0 为全文无关键词命中；tier 1 有关键词命中但未抽到配额数量；tier 2 抽到部分配额数量；tier 3 的表中期初、增加、减少、期末四段齐全。", "", "## 三组披露对比", ""]
    sample = pd.read_csv(SAMPLE_DEFINITION, dtype={"code": str})
    sample["code"] = sample["code"].str.zfill(6)
    grouped = df.assign(code=df["code"].astype(str).str.zfill(6)).merge(
        sample[["code", "ets_status"]], on="code", how="left", validate="many_to_one"
    )
    group_names = {"always": "始终纳入", "expansion": "扩容纳入", "control": "未纳入"}
    lines += ["| 组别 | 报告数 | 公司数 | tier 0 | tier 1 | tier 2 | tier 3 | 提及率 | 数量披露率 |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    group_stats = {}
    for status in ("always", "expansion", "control"):
        group = grouped[grouped["ets_status"] == status]
        gc = group["compliance_tier"].value_counts().reindex(range(4), fill_value=0)
        mention_rate = group["compliance_tier"].ne(0).mean()
        qty_rate = group["compliance_tier"].isin([2, 3]).mean()
        group_stats[status] = (int(group["compliance_tier"].ne(0).sum()), len(group))
        lines.append(
            f"| {group_names[status]} | {len(group)} | {group['code'].nunique()} | "
            f"{gc[0]} | {gc[1]} | {gc[2]} | {gc[3]} | {mention_rate:.2%} | {qty_rate:.2%} |"
        )
    unmapped = grouped["ets_status"].isna()
    if unmapped.any():
        lines += ["", f"注：另有 **{int(unmapped.sum())}** 份报告（**{grouped.loc[unmapped, 'code'].nunique()}** 家公司）不在三组行业样本定义中，计入全样本总表和年度趋势，但不计入上述三组比较。"]

    def two_proportion_p(left: tuple[int, int], right: tuple[int, int]) -> float:
        x1, n1 = left
        x2, n2 = right
        pooled = (x1 + x2) / (n1 + n2)
        se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
        return math.erfc(abs(x1 / n1 - x2 / n2) / se / math.sqrt(2))

    p_always = two_proportion_p(group_stats["control"], group_stats["always"])
    p_expansion = two_proportion_p(group_stats["control"], group_stats["expansion"])
    control_rate = group_stats["control"][0] / group_stats["control"][1]
    always_rate = group_stats["always"][0] / group_stats["always"][1]
    expansion_rate = group_stats["expansion"][0] / group_stats["expansion"][1]
    lines += ["", "提及率定义为 tier 1–3 占比；数量披露率定义为 tier 2–3 占比。", "", f"两比例 z 检验显示，未纳入组提及率显著低于始终纳入组（{control_rate:.2%} vs {always_rate:.2%}，双侧 p={p_always:.2e}），也显著低于扩容纳入组（{control_rate:.2%} vs {expansion_rate:.2%}，双侧 p={p_expansion:.2e}）。该检验以公司年度为观测单位，未调整同一公司的年度内相关性。", "", "## 与上一轮 1461 份对比", "", "上一轮 tier 0/1/2/3 分布为 **783/651/14/13**（占比 53.59%/44.56%/0.96%/0.89%）；本轮分布见报告开头总表。", "", "### 与最初 369 份样本对比", "", "369 份时经校正的 tier 0/1/2/3 分布为 **112/241/6/10**（占比 30.35%/65.31%/1.63%/2.71%）。", "", "**更正声明：更早版本的 295/56/8/10 是因分级逻辑错误产生的作废结果，不得再引用。**", "", "## 逐年趋势", "", "| 年份 | 报告数 | tier 0 | tier 1 | tier 2 | tier 3 | 提及率 | 数量披露率 |", "|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for year, group in df.groupby("year", sort=True):
        yc = group["compliance_tier"].value_counts().reindex(range(4), fill_value=0)
        mention_rate = group["compliance_tier"].ne(0).mean()
        qty_rate = group["compliance_tier"].isin([2, 3]).mean()
        lines.append(f"| {year} | {len(group)} | {yc[0]} | {yc[1]} | {yc[2]} | {yc[3]} | {mention_rate:.2%} | {qty_rate:.2%} |")
    lines += ["", "369 份样本的完整披露率为：2023 年 0.83%、2024 年 1.63%、2025 年 5.60%。", "", "## 按公司数计算的合规率", ""]
    company_max = df.groupby("code")["compliance_tier"].max()
    company_total = len(company_max)
    company_complete = int((company_max == 3).sum())
    company_any_qty = int(company_max.isin([2, 3]).sum())
    lines += [
        f"共 **{company_total}** 家公司；曾有至少一年完整披露（tier 3）的公司 **{company_complete}** 家，按公司数计算的完整披露合规率为 **{company_complete / company_total:.2%}**。",
        "",
        f"曾有至少一年披露任一配额数量（tier 2–3）的公司 **{company_any_qty}** 家，按公司数计算的任一数量披露率为 **{company_any_qty / company_total:.2%}**。",
    ]
    lines += ["", "## 完整变动表（tier 3）公司", ""]
    complete = df[df.compliance_tier == 3].sort_values(["year", "code"])
    if complete.empty:
        lines.append("无。")
    else:
        lines += ["| 股票代码 | 年份 | 命中页 |", "|---|---:|---|"]
        for r in complete.itertuples():
            lines.append(f"| {r.code} | {r.year} | {r.hit_pages} |")
    qty_cols = [c for c in VALUE_COLUMNS if c.startswith("qty_")]
    lines += ["", "## 数量字段非空率", "", "| 字段 | 非空数 | 非空率 |", "|---|---:|---:|"]
    for c in qty_cols + ["verified_emission"]:
        n = int(df[c].notna().sum())
        lines.append(f"| {c} | {n} | {n / total:.2%} |")
    lines += ["", "## 解析策略与局限", "", "程序先用 PyMuPDF 逐页扫描全文并记录关键词页，再仅对可能含数值行的命中页用 pdfplumber 补充表格文本。优先取行标签后的第一个数，作为本年度/本期值；千分位、括号负数和负号均已标准化。页面明示“万元”或“万吨”时分别乘以 10,000 转成元或吨。", "", "可能漏抽的情形包括：扫描图像无文本层、字体编码损坏、表格跨页且标题与数值分离、行列阅读顺序异常、以非标准名称披露，以及数字未紧跟行标签。本程序不会把未抽到的字段写成 0；CSV 空值代表未披露/未抽到，0 仅代表原文明示为零。", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="development-only maximum number of PDFs")
    parser.add_argument("--fresh", action="store_true", help="ignore an existing checkpoint")
    args = parser.parse_args()
    manifest = pd.read_csv(REPORTS / "manifest.csv", dtype={"code": str})
    manifest["code"] = manifest.code.str.zfill(6)
    if args.limit:
        manifest = manifest.iloc[:args.limit]

    done: dict[str, dict] = {}
    if OUTPUT.exists() and not args.fresh:
        old = pd.read_csv(OUTPUT, dtype={"code": str})
        for r in old.to_dict("records"):
            done[f"{str(r['code']).zfill(6)}_{int(r['year'])}"] = r

    rows = []
    for i, r in enumerate(manifest.itertuples(index=False), 1):
        key = f"{r.code}_{int(r.year)}"
        if key in done:
            row = done[key]
        else:
            row = parse_pdf(REPORTS / r.file, r.code, int(r.year))
        rows.append(row)
        # Every completed row is a durable checkpoint.
        if key not in done:
            pd.DataFrame(rows, columns=COLUMNS).to_csv(OUTPUT, index=False, encoding="utf-8-sig")
        if i % 20 == 0 or i == len(manifest):
            print(f"processed {i}/{len(manifest)}", flush=True)
    df = pd.DataFrame(rows, columns=COLUMNS)
    assert ((df["compliance_tier"] == 0) == df["hit_pages"].fillna("").eq("")).all()
    assert len(df) == len(manifest)
    assert not df.duplicated(["code", "year"]).any()
    df.to_csv(OUTPUT, index=False, encoding="utf-8-sig")
    _write_report(df)


if __name__ == "__main__":
    main()
