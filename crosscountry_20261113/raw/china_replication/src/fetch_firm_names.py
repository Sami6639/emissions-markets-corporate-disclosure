# -*- coding: utf-8 -*-
"""Retrieve the registered names of listed firms for use in entity matching.
"""
import time
import argparse
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
import pandas as pd
import akshare as ak


def load_done(path):
    if Path(path).exists():
        d = pd.read_csv(path, dtype={"code": str})
        return d, set(d["code"])
    return pd.DataFrame(columns=["code", "full_name", "industry", "main_business"]), set()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="raw/firm/firm_names.csv")
    ap.add_argument("--sleep", type=float, default=0.25)
    args = ap.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    codes = ak.stock_info_a_code_name()
    codes["code"] = codes["code"].astype(str).str.zfill(6)
    # （8/4 ）， A
    codes = codes[codes["code"].str.match(r"^(60|68|00|30)")]
    print(f"[plan] 沪深 A 股 {len(codes)} 只", flush=True)

    done_df, done = load_done(out)
    todo = [c for c in codes["code"] if c not in done]
    print(f"[plan] 已完成 {len(done)}，待抓 {len(todo)}", flush=True)

    rows, fails = [], []
    for i, code in enumerate(todo, 1):
        try:
            d = ak.stock_profile_cninfo(symbol=code)
            r = d.iloc[0]
            rows.append({
                "code": code,
                "full_name": r.get("公司名称"),
                "industry": r.get("所属行业"),
                "main_business": str(r.get("主营业务"))[:200],
            })
        except Exception as e:
            fails.append(f"{code}:{type(e).__name__}")
        if i % 200 == 0 or i == len(todo):
            cur = pd.concat([done_df, pd.DataFrame(rows)], ignore_index=True)
            cur.to_csv(out, index=False, encoding="utf-8-sig")
            print(f"[save] {i}/{len(todo)}  累计 {len(cur)}  失败 {len(fails)}", flush=True)
        time.sleep(args.sleep)

    cur = pd.concat([done_df, pd.DataFrame(rows)], ignore_index=True)
    cur = cur.drop_duplicates(subset=["code"], keep="last")
    cur.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"[done] 共 {len(cur)} 家，失败 {len(fails)}", flush=True)
    if fails:
        Path(out.parent / "firm_names_failed.txt").write_text(
            "\n".join(fails), encoding="utf-8")


if __name__ == "__main__":
    main()
