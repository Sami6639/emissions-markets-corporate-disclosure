# -*- coding: utf-8 -*-
"""Add an entity-name filter on top of the restricted dictionary and re-estimate.

Hand reading of 30 pages flagged under the restricted dictionary found seven false
positives, all sharing one pattern: the term for carbon asset appearing inside the
registered name of a related party, in related-party transaction schedules,
consolidation scopes and director biographies, with no bearing on the firm's own
carbon activity. Those false positives are concentrated in the annual reports of
the state power groups, which populate the comparison cohort.

This script disregards a keyword occurrence when it is immediately followed by the
components of a company name. A page counts only if it carries at least one
occurrence outside an entity name. The output, n_hit_namefilt, is used for
robustness.
"""
from __future__ import annotations
import re, sys
from pathlib import Path
import fitz, pandas as pd

BASE = Path(__file__).resolve().parent.parent
KEY = re.compile(r"碳排放配额|碳排放权资产|碳排放权|碳交易|碳资产|核证自愿减排|CCER"
                 r"|(?<![A-Za-z])CEA(?![A-Za-z])")
# a keyword followed by these components is treated as part of a company name
NAME_TAIL = re.compile(r"^[\s]{0,2}(管理|经营|运营|开发|技术|服务|咨询|投资)?"
                       r"[\s]{0,2}(技术|服务)?[\s]{0,2}(（[^）]{0,8}）)?"
                       r"[\s]{0,2}(有限|股份)?[\s]{0,2}(责任)?[\s]{0,2}公司")


def page_hits(text: str) -> bool:
    """Whether the page carries at least one carbon keyword outside an entity name."""
    for m in KEY.finditer(text):
        if not NAME_TAIL.match(text[m.end():m.end() + 24]):
            return True
    return False


def main() -> int:
    r = pd.read_csv(BASE / "out/carbon_disclosure_restricted.csv", dtype={"code": str})
    out = BASE / "out/carbon_disclosure_namefilt.csv"
    rows = []
    for i, t in enumerate(r.itertuples(), 1):
        pages = [int(x) for x in str(t.hit_pages_restricted).split(";") if x.strip().isdigit()]
        keep = []
        if pages:
            pdf = BASE / "raw/reports" / f"{t.code}_{int(t.year)}.pdf"
            if pdf.exists():
                try:
                    with fitz.open(pdf) as doc:
                        for p in pages:
                            if 1 <= p <= doc.page_count and page_hits(doc.load_page(p - 1).get_text()):
                                keep.append(p)
                except Exception:
                    keep = pages
            else:
                keep = pages
        rows.append({"code": t.code, "year": int(t.year),
                     "n_hit_restricted": int(t.n_hit_restricted),
                     "n_hit_namefilt": len(keep),
                     "hit_pages_namefilt": ";".join(map(str, keep))})
        if i % 500 == 0:
            print(f"[{i}/{len(r)}]", flush=True)
    d = pd.DataFrame(rows)
    d.to_csv(out, index=False, encoding="utf-8-sig")
    bad = int((d.n_hit_namefilt > d.n_hit_restricted).sum())
    print(f"[done] {len(d)} 行；违反单调性 {bad}；受限 {int(d.n_hit_restricted.sum())} 页 "
          f"→ 名过滤后 {int(d.n_hit_namefilt.sum())} 页")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
