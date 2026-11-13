# -*- coding: utf-8 -*-
"""Retrieve daily quotations from the national carbon market.

Source: Shanghai Environment and Energy Exchange, https://www.cneeex.com/qgtpfqjy/mrgk/{year}n/
Static HTML, no authentication. Two pitfalls have to be avoided:
1. The annual index page carries a fixed sidebar of links, so a list cannot be
   identified from the /c/ link pattern alone. Entries must be filtered on the
   exact bulletin title prefix followed by the date.
2. Paginated index_N.shtml pages keep returning HTTP 200 past the last page, so
   iteration must stop when a page yields no new entries rather than on status.
"""
import re
import time
import json
import argparse
from pathlib import Path

import requests

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36")
HEADERS = {"User-Agent": UA}
BASE = "https://www.cneeex.com"

# ：，，
ITEM_RE = re.compile(
    r'href="(/c/(\d{4}-\d{2}-\d{2})/(\d+)\.shtml)"[^>]*>\s*'
    r'【CEA】全国碳市场每日综合价格行情及成交信息(\d{8})'
)

# （see「58 .23/」），
# ，。
NUM = r"([\d,]+(?:\s*\.\s*\d+)?)"


def _f(s):
    """Convert a thousands-separated numeral to float; return None when absent, since zero and missing carry different meanings and must not be conflated."""
    if s is None:
        return None
    return float(re.sub(r"[,\s]", "", s))


def collect_index(year, session, sleep=0.4, max_pages=80):
    """Enumerate every bulletin link for a given year. Returns a list of (date, url_id)."""
    found = {}
    for page in range(1, max_pages + 1):
        suffix = "" if page == 1 else f"index_{page}.shtml"
        url = f"{BASE}/qgtpfqjy/mrgk/{year}n/{suffix}"
        r = session.get(url, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            break
        r.encoding = r.apparent_encoding
        new = 0
        for _, d_link, aid, d_title in ITEM_RE.findall(r.text):
            # ，
            if d_link.replace("-", "") != d_title:
                raise RuntimeError(f"日期不一致 link={d_link} title={d_title}")
            if d_link not in found:
                found[d_link] = aid
                new += 1
        if new == 0:
            break          # 200，
        time.sleep(sleep)
    return found


def parse_quote(text, date):
    """Parse a bulletin. Fields that cannot be extracted return None and are never filled with zero.

    The bulletin takes more than one form, so each field is extracted
    independently and a complete set of four prices is not required:
    A  ordinary day: open, high, low and close all present.
    B  no-trade day: a closing price is quoted with no open, high or low, and
       the traded volume is a genuine zero.
    C  block-trade-only day: open and close only, with no high or low, because
       the listed-agreement market did not trade.
    D  one trade type absent: the bulletin states that there was no listed
       agreement trading or no one-way auction, again a genuine zero.

    Zero and missing must be kept apart. Recording the volume on a no-trade day
    as missing would cause it to be dropped in later liquidity work and would
    distort the estimated carbon beta.
    """
    t = re.sub(r"<[^>]+>", " ", text)
    t = re.sub(r"\s+", " ", t)
    out = {"date": date, "no_trade": 0}

    if re.search(r"今日全国碳市场无成交", t):
        out["no_trade"] = 1

    # ，
    for key, label in (("open", "开盘价"), ("high", "最高价"),
                       ("low", "最低价"), ("close", "收盘价")):
        m = re.search(rf"{label}{NUM}元/吨", t)
        out[key] = _f(m.group(1)) if m else None

    for key, label in (("listed", "挂牌协议交易"),
                       ("block", "大宗协议交易"),
                       ("auction", "单向竞价")):
        m = re.search(rf"{label}成交量{NUM}吨，成交额{NUM}元", t)
        if m:
            out[f"{key}_volume"] = _f(m.group(1))
            out[f"{key}_amount"] = _f(m.group(2))
        elif out["no_trade"] or re.search(rf"今日无{label}", t):
            out[f"{key}_volume"] = 0.0     # ，
            out[f"{key}_amount"] = 0.0
        else:
            out[f"{key}_volume"] = None
            out[f"{key}_amount"] = None

    m = re.search(rf"总成交量{NUM}吨，总成交额{NUM}元", t)
    if m:
        out["total_volume"] = _f(m.group(1))
        out["total_amount"] = _f(m.group(2))
    elif out["no_trade"]:
        out["total_volume"] = 0.0
        out["total_amount"] = 0.0
    else:
        out["total_volume"] = None
        out["total_amount"] = None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", default="2021,2022,2023,2024,2025,2026")
    ap.add_argument("--out", default="raw/cea")
    ap.add_argument("--sleep", type=float, default=0.35)
    args = ap.parse_args()

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()

    index = {}
    for y in args.years.split(","):
        got = collect_index(int(y), session, args.sleep)
        index.update(got)
        print(f"[index] {y}n  {len(got):>4} 条  累计 {len(index)}", flush=True)

    (outdir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")

    rows, miss = [], []
    for i, (date, aid) in enumerate(sorted(index.items()), 1):
        url = f"{BASE}/c/{date}/{aid}.shtml"
        try:
            r = session.get(url, headers=HEADERS, timeout=30)
            r.encoding = r.apparent_encoding
            rec = parse_quote(r.text, date)
            if rec["close"] is None:
                miss.append(date)
            rows.append(rec)
        except Exception as e:
            miss.append(f"{date}:{type(e).__name__}")
        if i % 100 == 0:
            print(f"[fetch] {i}/{len(index)}", flush=True)
        time.sleep(args.sleep)

    import csv
    cols = ["date", "no_trade", "open", "high", "low", "close",
            "listed_volume", "listed_amount", "block_volume", "block_amount",
            "auction_volume", "auction_amount", "total_volume", "total_amount"]
    with open(outdir / "cea_daily.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    print(f"[done] 共 {len(rows)} 行，收盘价缺失 {len(miss)} 条")
    if miss:
        (outdir / "missing.txt").write_text("\n".join(map(str, miss)), encoding="utf-8")


if __name__ == "__main__":
    main()
