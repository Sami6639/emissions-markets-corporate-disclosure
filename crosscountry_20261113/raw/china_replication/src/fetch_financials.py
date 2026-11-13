# -*- coding: utf-8 -*-
"""Retrieve financial statement items and year-end market data from the statements filed with the annual reports.
"""
import time
import argparse
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
import pandas as pd
import akshare as ak

BASE = Path(__file__).resolve().parent.parent

BS_COLS = {
    "TOTAL_ASSETS": "total_assets",
    "TOTAL_LIABILITIES": "total_liab",
    "TOTAL_EQUITY": "total_equity",
    "TOTAL_PARENT_EQUITY": "parent_equity",
    "SHARE_CAPITAL": "share_capital",
    "MONETARYFUNDS": "cash",
    "FIXED_ASSET": "fixed_asset",
    "INTANGIBLE_ASSET": "intangible_asset",
    "OTHER_CURRENT_ASSET": "other_current_asset",
}
IS_COLS = {
    "TOTAL_OPERATE_INCOME": "revenue",
    "OPERATE_PROFIT": "operate_profit",
    "NETPROFIT": "net_profit",
    "PARENT_NETPROFIT": "parent_net_profit",
    "NONBUSINESS_INCOME": "nonbiz_income",
    "NONBUSINESS_EXPENSE": "nonbiz_expense",
}


def pick(df, mapping, code):
    """Select columns from the statement extract and reshape to an annual long format, keeping only 31 December period ends."""
    if df is None or len(df) == 0:
        return None
    d = df.copy()
    d["REPORT_DATE"] = pd.to_datetime(d["REPORT_DATE"], errors="coerce")
    d = d[d["REPORT_DATE"].dt.strftime("%m-%d") == "12-31"]
    if d.empty:
        return None
    keep = {k: v for k, v in mapping.items() if k in d.columns}
    out = d[["REPORT_DATE"] + list(keep)].rename(columns=keep)
    out["year"] = out["REPORT_DATE"].dt.year
    out["code"] = code
    return out.drop(columns=["REPORT_DATE"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--match", default="out/emitter_firm_match.csv")
    ap.add_argument("--out", default="raw/firm/financials.csv")
    ap.add_argument("--px", default="raw/firm/yearend_price.csv")
    ap.add_argument("--sleep", type=float, default=0.3)
    args = ap.parse_args()

    m = pd.read_csv(BASE / args.match, dtype=str)
    codes = sorted(m.loc[m["stock_code"].notna(), "stock_code"].unique())
    print(f"[plan] {len(codes)} 家", flush=True)

    outp, pxp = BASE / args.out, BASE / args.px
    outp.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if outp.exists():
        done = set(pd.read_csv(outp, dtype={"code": str})["code"])

    fin_rows, px_rows, fails = [], [], []
    for i, code in enumerate(codes, 1):
        if code in done:
            continue
        sym = ("SH" if code.startswith("6") else "SZ") + code
        try:
            bs = pick(ak.stock_balance_sheet_by_report_em(symbol=sym), BS_COLS, code)
            time.sleep(args.sleep)
            is_ = pick(ak.stock_profit_sheet_by_report_em(symbol=sym), IS_COLS, code)
            if bs is not None and is_ is not None:
                fin_rows.append(bs.merge(is_, on=["code", "year"], how="outer"))
            elif bs is not None:
                fin_rows.append(bs)
            else:
                fails.append(f"{code}:empty_bs")
        except Exception as e:
            fails.append(f"{code}:fin:{type(e).__name__}")
        time.sleep(args.sleep)

        # 。 push2his ，
        # stock_zh_a_hist ProxyError； baostock 。
        try:
            pfx = "sh" if code.startswith("6") else "sz"
            h = ak.stock_zh_a_daily(symbol=pfx + code,
                                    start_date="20201201", end_date="20261231",
                                    adjust="")
            if h is not None and len(h):
                h["date"] = pd.to_datetime(h["date"])
                h["year"] = h["date"].dt.year
                ye = h.sort_values("date").groupby("year").tail(1)
                for _, r in ye.iterrows():
                    px_rows.append({"code": code, "year": int(r["year"]),
                                    "yearend_date": r["date"].date(),
                                    "yearend_close": r["close"]})
            else:
                fails.append(f"{code}:empty_px")
        except Exception as e:
            fails.append(f"{code}:px:{type(e).__name__}")
        time.sleep(args.sleep)

        if i % 20 == 0:
            if fin_rows:
                pd.concat(fin_rows, ignore_index=True).to_csv(
                    outp, index=False, encoding="utf-8-sig")
            if px_rows:
                pd.DataFrame(px_rows).to_csv(pxp, index=False, encoding="utf-8-sig")
            print(f"[save] {i}/{len(codes)}  财务 {len(fin_rows)}  行情 {len(px_rows)}  失败 {len(fails)}",
                  flush=True)

    if fin_rows:
        fin = pd.concat(fin_rows, ignore_index=True)
        fin.to_csv(outp, index=False, encoding="utf-8-sig")
        print(f"[done] 财务 {len(fin)} 行 / {fin['code'].nunique()} 家", flush=True)
    if px_rows:
        px = pd.DataFrame(px_rows)
        px.to_csv(pxp, index=False, encoding="utf-8-sig")
        print(f"[done] 年末行情 {len(px)} 行 / {px['code'].nunique()} 家", flush=True)
    if fails:
        (outp.parent / "financials_failed.txt").write_text("\n".join(fails),
                                                           encoding="utf-8")
        print(f"[done] 失败 {len(fails)}", flush=True)


if __name__ == "__main__":
    main()
