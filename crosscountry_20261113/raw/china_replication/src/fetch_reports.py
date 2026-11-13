# -*- coding: utf-8 -*-
"""Download the full text of annual reports for the matched listed firms.

Three properties of the disclosure platform's interface, established by testing:
1. pageNum above 100 silently wraps to the first page and still returns 200;
2. pageSize is fixed server side and any other value is ignored;
3. a single query returns at most about 3,000 records.
Queries are therefore issued firm by firm, which keeps each well below the limit,
and results are de-duplicated on the announcement identifier.
"""
import re
import time
import json
import argparse
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
import requests
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
API = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
STATIC = "http://static.cninfo.com.cn/"
H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
     "Content-Type": "application/x-www-form-urlencoded",
     "Referer": "http://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice"}

# keep only full annual reports; drop summaries, H-share versions, corrections and English editions
DROP = ("摘要", "H股", "英文", "更正", "补充", "已取消", "问询", "(修订版)", "修订版")


ORG_CACHE = {}


def load_orgids(session):
    """Fetch the official register to obtain the true orgId.

    The identifier has the form of a market prefix, a zero, and the six-digit
    code. An earlier version concatenated the prefix and the code and omitted
    the intervening zero, which made every Shenzhen query return empty without
    raising an error, presenting as zero failures alongside coverage of only
    about forty percent of firms. The official register is therefore always
    used and the identifier is never constructed by hand.
    """
    if ORG_CACHE:
        return ORG_CACHE
    for u in ("http://www.cninfo.com.cn/new/data/szse_stock.json",):
        r = session.get(u, headers={"User-Agent": H["User-Agent"],
                                    "Referer": "http://www.cninfo.com.cn/"},
                        timeout=40)
        for it in (r.json().get("stockList") or []):
            ORG_CACHE[str(it.get("code")).zfill(6)] = it.get("orgId")
    return ORG_CACHE


def query(session, code, se_date):
    col = "sse" if code.startswith("6") else "szse"
    org = load_orgids(session).get(code)
    if not org:
        raise RuntimeError(f"{code} 未在巨潮清单中找到 orgId")
    d = {"pageNum": 1, "pageSize": 30, "column": col, "tabName": "fulltext",
         "stock": f"{code},{org}", "category": "category_ndbg_szsh",
         "seDate": se_date}
    r = session.post(API, headers=H, data=d, timeout=40)
    j = r.json()
    total = j.get("totalRecordNum") or 0
    anns = j.get("announcements") or []
    seen, out = set(), []
    for a in anns:
        aid = a.get("announcementId")
        if aid in seen:
            continue
        seen.add(aid)
        out.append(a)
    if total and len(out) != total and total <= 30:
        raise RuntimeError(f"{code} 去重后 {len(out)} != 声明 {total}")
    return out


def pick(anns):
    """Select full annual reports, group them by year, and keep the latest version for each year."""
    best = {}
    for a in anns:
        title = a.get("announcementTitle", "")
        title = re.sub(r"<[^>]+>", "", title)
        if any(x in title for x in DROP):
            continue
        # the title appears in two forms：「2025」「2024」，
        m = re.search(r"(20\d{2})\s*年\s*年?度报告", title)
        if not m:
            continue
        y = int(m.group(1))
        ts = a.get("announcementTime") or 0
        if y not in best or ts > best[y][0]:
            best[y] = (ts, a.get("adjunctUrl"), title)
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--match", default="out/emitter_firm_match.csv")
    ap.add_argument("--years", default="2023,2024,2025")
    ap.add_argument("--out", default="raw/reports")
    ap.add_argument("--sleep", type=float, default=0.5)
    # the query window must cover the filing date of the target reports（ 1 6 ），
    # 2019-2020 ，。
    ap.add_argument("--sedate", default="2022-01-01~2026-12-31")
    args = ap.parse_args()

    outdir = BASE / args.out
    outdir.mkdir(parents=True, exist_ok=True)
    want = {int(y) for y in args.years.split(",")}

    m = pd.read_csv(BASE / args.match, dtype=str)
    codes = sorted(m.loc[m["stock_code"].notna(), "stock_code"].unique())
    print(f"[plan] 目标公司 {len(codes)} 家，年份 {sorted(want)}", flush=True)

    s = requests.Session()
    manifest, fails = [], []
    for i, code in enumerate(codes, 1):
        try:
            anns = query(s, code, args.sedate)
            best = pick(anns)
        except Exception as e:
            fails.append(f"{code}:query:{type(e).__name__}")
            continue
        for y, (_, url, title) in sorted(best.items()):
            if y not in want or not url:
                continue
            dst = outdir / f"{code}_{y}.pdf"
            if dst.exists() and dst.stat().st_size > 50000:
                manifest.append({"code": code, "year": y, "file": dst.name,
                                 "title": title, "bytes": dst.stat().st_size})
                continue
            try:
                rr = s.get(STATIC + url, headers={"User-Agent": H["User-Agent"]},
                           timeout=180)
                if rr.content[:4] != b"%PDF":
                    fails.append(f"{code}_{y}:notpdf")
                    continue
                dst.write_bytes(rr.content)
                manifest.append({"code": code, "year": y, "file": dst.name,
                                 "title": title, "bytes": len(rr.content)})
            except Exception as e:
                fails.append(f"{code}_{y}:{type(e).__name__}")
            time.sleep(args.sleep)
        if i % 10 == 0:
            pd.DataFrame(manifest).to_csv(outdir / "manifest.csv",
                                          index=False, encoding="utf-8-sig")
            print(f"[save] {i}/{len(codes)} 家  已下 {len(manifest)} 份  失败 {len(fails)}",
                  flush=True)
        time.sleep(args.sleep)

    pd.DataFrame(manifest).to_csv(outdir / "manifest.csv", index=False,
                                  encoding="utf-8-sig")
    if fails:
        (outdir / "failed.txt").write_text("\n".join(fails), encoding="utf-8")
    print(f"[done] 共 {len(manifest)} 份，失败 {len(fails)}", flush=True)


if __name__ == "__main__":
    main()
