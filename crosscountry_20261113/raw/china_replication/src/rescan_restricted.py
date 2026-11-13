# -*- coding: utf-8 -*-
"""Rescan flagged pages under a restricted dictionary to test whether the main result rests on false positives.

Motivation: the original dictionary includes the standalone term for quota and an
unbounded match on the acronym CEA. Steel, cement and aluminium smelting are
precisely the three sectors subject to the heaviest non-carbon quota regulation,
including capacity-swap quotas, crude steel output control and export quotas, and
the acronym matches unrelated Latin strings. False positives are denser in the
treated sectors and move with the commodity cycle, which makes the measurement
error correlated with the interaction term and requires a separate test.

Key property: the restricted vocabulary is a strict subset of the original with
additional conditions, so a restricted hit page must also be an original hit page.
Only the text of the originally flagged pages therefore needs to be retrieved, not
the whole PDF. The script asserts n_hit_restricted <= n_hit_original on every row
and exits non-zero if that is violated.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import fitz
import pandas as pd

BASE = Path(__file__).resolve().parent.parent

# ， KEYWORDS，
UNCOND = ("碳排放配额", "碳排放权资产", "碳排放权", "碳交易", "碳资产",
          "核证自愿减排", "CCER")
# ， CEA
CN_CARBON = re.compile(r"碳排放|碳交易|碳资产|碳市场")
# CEA ， CEAs、OCEAN
CEA_RE = re.compile(r"(?<![A-Za-z])CEA(?![A-Za-z])")
QUOTA = "配额"


def classify(text: str) -> str:
    """Return one of hit, drop_quota, drop_cea or none.

    hit         the page carries an unconditional carbon term, or a standalone
                CEA corroborated by a Chinese carbon term
    drop_quota  the page was flagged by the original rule only through the bare
                quota term
    drop_cea    the page was flagged only through CEA, without corroboration
    none        neither the restricted nor the original rule should flag it,
                which should not arise in normal operation
    """
    if any(k in text for k in UNCOND):
        return "hit"
    if CEA_RE.search(text):
        return "hit" if CN_CARBON.search(text) else "drop_cea"
    if QUOTA in text:
        return "drop_quota"
    # the original rule matched "cea" ， CEAs、OCEAN 。
    # the restricted rule rejects it， CEA ，。
    if "cea" in text.lower():
        return "drop_cea"
    return "none"


def parse_pages(v) -> list[int]:
    s = "" if v is None else str(v).strip()
    if not s or s.lower() == "nan":
        return []
    return [int(x) for x in s.split(";") if x.strip().isdigit()]


def main() -> int:
    disc = pd.read_csv(BASE / "out/carbon_disclosure.csv", dtype={"code": str})
    out_path = BASE / "out/carbon_disclosure_restricted.csv"
    done = {}
    if out_path.exists():
        prev = pd.read_csv(out_path, dtype={"code": str})
        done = {(r.code, int(r.year)): r for r in prev.itertuples()}

    rows, missing, n = [], 0, len(disc)
    for i, r in enumerate(disc.itertuples(), 1):
        key = (r.code, int(r.year))
        if key in done:
            p = done[key]
            rows.append({"code": p.code, "year": int(p.year), "n_pages": p.n_pages,
                         "hit_pages_restricted": ("" if pd.isna(p.hit_pages_restricted)
                                                  else p.hit_pages_restricted),
                         "n_hit_restricted": int(p.n_hit_restricted),
                         "n_hit_original": int(p.n_hit_original),
                         "drop_quota_only": int(p.drop_quota_only),
                         "drop_cea_only": int(p.drop_cea_only)})
            continue

        pages = parse_pages(r.hit_pages)
        rec = {"code": r.code, "year": int(r.year), "n_pages": r.n_pages,
               "hit_pages_restricted": "", "n_hit_restricted": 0,
               "n_hit_original": len(pages), "drop_quota_only": 0, "drop_cea_only": 0}
        if pages:
            pdf = BASE / "raw/reports" / f"{r.code}_{int(r.year)}.pdf"
            if not pdf.exists():
                missing += 1
            else:
                keep = []
                try:
                    with fitz.open(pdf) as doc:
                        for pno in pages:
                            if pno < 1 or pno > doc.page_count:
                                continue
                            t = doc.load_page(pno - 1).get_text()
                            c = classify(t)
                            if c == "hit":
                                keep.append(pno)
                            elif c == "drop_quota":
                                rec["drop_quota_only"] += 1
                            elif c == "drop_cea":
                                rec["drop_cea_only"] += 1
                except Exception as e:
                    print(f"[warn] {pdf.name}: {type(e).__name__}", flush=True)
                    keep = pages          # on read failure keep the page, so as not to manufacture a spurious decline
                rec["hit_pages_restricted"] = ";".join(str(x) for x in keep)
                rec["n_hit_restricted"] = len(keep)
        rows.append(rec)

        if i % 250 == 0:
            pd.DataFrame(rows).to_csv(out_path, index=False, encoding="utf-8-sig")
            print(f"[save] {i}/{n}", flush=True)

    d = pd.DataFrame(rows)
    d.to_csv(out_path, index=False, encoding="utf-8-sig")

    bad = int((d.n_hit_restricted > d.n_hit_original).sum())
    print(f"[done] {len(d)} 行；缺 PDF {missing} 份；违反单调性 {bad} 行")
    print(f"  原命中页合计 {int(d.n_hit_original.sum())}，受限后 {int(d.n_hit_restricted.sum())}，"
          f"剔除 {int(d.n_hit_original.sum() - d.n_hit_restricted.sum())}")
    print(f"  其中仅含裸「配额」{int(d.drop_quota_only.sum())} 页，"
          f"CEA 无中文碳词佐证 {int(d.drop_cea_only.sum())} 页")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
