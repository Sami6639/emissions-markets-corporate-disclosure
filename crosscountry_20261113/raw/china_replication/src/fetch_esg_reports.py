# -*- coding: utf-8 -*-
"""Retrieve standalone social responsibility, sustainability and ESG reports.

Purpose: to test for substitution between disclosure channels. If firms move
carbon information into a standalone sustainability report rather than the annual
report, the finding that carbon disclosure in annual reports did not increase
could reflect a change of venue rather than an absence of response. This is the
principal threat to validity in the study and has to be addressed directly.

The disclosure platform's announcement category codes do not work for this report
type, since any category returns the full set of announcements. Retrieval
therefore uses keyword search and filters a second time on the title.
"""
import re
import time
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

KEYS = ["社会责任", "可持续发展", "ESG", "环境、社会"]
# ，「」
TITLE_OK = re.compile(r"(社会责任报告|可持续发展报告|ESG报告|环境、社会(及|与)管治报告|"
                      r"环境、社会和治理报告)")
TITLE_DROP = re.compile(r"(摘要|英文|公告|决议|提示|说明|回复|问询)")
ORG = {}


def load_org(s):
    if ORG:
        return ORG
    r = s.get("http://www.cninfo.com.cn/new/data/szse_stock.json",
              headers={"User-Agent": H["User-Agent"],
                       "Referer": "http://www.cninfo.com.cn/"}, timeout=40)
    for it in r.json().get("stockList") or []:
        ORG[str(it.get("code")).zfill(6)] = it.get("orgId")
    return ORG


def search(s, code, key, se="2021-01-01~2026-12-31"):
    col = "sse" if code.startswith("6") else "szse"
    org = load_org(s).get(code)
    if not org:
        return []
    d = {"pageNum": 1, "pageSize": 30, "column": col, "tabName": "fulltext",
         "stock": f"{code},{org}", "seDate": se, "searchkey": key}
    j = s.post(API, headers=H, data=d, timeout=40).json()
    return j.get("announcements") or []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--match", default="out/sample_definition.csv")
    ap.add_argument("--out", default="raw/esg")
    ap.add_argument("--sleep", type=float, default=0.35)
    ap.add_argument("--download", action="store_true", help="是否下载 PDF")
    args = ap.parse_args()

    outdir = BASE / args.out
    outdir.mkdir(parents=True, exist_ok=True)
    codes = sorted(pd.read_csv(BASE / args.match, dtype={"code": str})["code"].unique())
    print(f"[plan] {len(codes)} 家", flush=True)

    s = requests.Session()
    rows, fails = [], []
    for i, code in enumerate(codes, 1):
        seen = set()
        for key in KEYS:
            try:
                for a in search(s, code, key):
                    t = re.sub(r"<[^>]+>", "", a.get("announcementTitle", ""))
                    if not TITLE_OK.search(t) or TITLE_DROP.search(t):
                        continue
                    aid = a.get("announcementId")
                    if aid in seen:
                        continue
                    seen.add(aid)
                    m = re.search(r"(20\d{2})", t)
                    rows.append({"code": code, "year": int(m.group(1)) if m else None,
                                 "title": t, "url": a.get("adjunctUrl"),
                                 "announcementId": aid})
            except Exception as e:
                fails.append(f"{code}:{key}:{type(e).__name__}")
            time.sleep(args.sleep)
        if i % 25 == 0:
            pd.DataFrame(rows).to_csv(outdir / "esg_index.csv", index=False,
                                      encoding="utf-8-sig")
            print(f"[save] {i}/{len(codes)}  命中 {len(rows)} 份  失败 {len(fails)}",
                  flush=True)

    d = pd.DataFrame(rows).drop_duplicates(subset=["code", "year"], keep="first")
    d.to_csv(outdir / "esg_index.csv", index=False, encoding="utf-8-sig")
    print(f"[done] 报告 {len(d)} 份 / {d['code'].nunique()} 家；失败 {len(fails)}",
          flush=True)

    if args.download:
        got = 0
        for _, r in d.iterrows():
            if not r["url"] or pd.isna(r["year"]):
                continue
            dst = outdir / f"{r['code']}_{int(r['year'])}_esg.pdf"
            if dst.exists() and dst.stat().st_size > 50000:
                got += 1
                continue
            try:
                rr = s.get(STATIC + r["url"],
                           headers={"User-Agent": H["User-Agent"]}, timeout=180)
                if rr.content[:4] == b"%PDF":
                    dst.write_bytes(rr.content)
                    got += 1
            except Exception:
                pass
            time.sleep(args.sleep)
            if got % 50 == 0 and got:
                print(f"[dl] {got}", flush=True)
        print(f"[done] 下载 {got} 份", flush=True)


if __name__ == "__main__":
    main()
