# -*- coding: utf-8 -*-
"""Match key emitting entities to listed A-share firms.

The difficulty is that entities on the roster are usually plants or subsidiaries
whose names differ from the listed parent. Three typical forms occur:
  (a) plant       the listed firm's full name appears within the entity name
  (b) subsidiary  only the group's brand element appears
  (c) unrelated   no literal overlap, resolvable only by hand or by external
                  ownership data

Matching therefore proceeds in three tiers and the hit rate is reported by tier,
with the third tier left for manual review. Missing a match is preferable to
making a wrong one: a false match places an uncovered firm in the treatment group
and contaminates the identification directly.
"""
import re
import argparse
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
import pandas as pd

BASE = Path(__file__).resolve().parent.parent

# ，
SUFFIX = ("股份有限公司", "有限责任公司", "有限公司", "集团公司", "总公司", "公司")
BIZ = ("发电", "电力", "电业", "能源", "热电", "供热", "电厂", "钢铁", "钢铁集团",
       "水泥", "建材", "铝业", "铝", "冶炼", "化工", "环保", "新能源", "控股", "集团",
       "实业", "科技", "股份", "国际", "投资", "开发", "工业", "制造")
# ，
GEO = ("北京", "天津", "上海", "重庆", "河北", "山西", "内蒙古", "辽宁", "吉林",
       "黑龙江", "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北",
       "湖南", "广东", "广西", "海南", "四川", "贵州", "云南", "西藏", "陕西",
       "甘肃", "青海", "宁夏", "新疆", "中国", "华北", "华东", "华中", "华南",
       "西北", "东北", "西南")

# 、，
TOO_COMMON = {"电力", "能源", "发电", "热电", "钢铁", "水泥", "铝业", "化工",
              "建材", "环保", "新能源", "国际", "集团", "控股", "投资", "实业",
              "科技", "工业", "中国", "华能", "国电", "大唐", "华电"}


def norm(s):
    """Normalise a name: fold full-width to half-width forms, strip whitespace, reconcile common variant characters, and remove parenthetical notes."""
    if not isinstance(s, str):
        return ""
    s = s.strip()
    s = re.sub(r"[（(][^）)]*[）)]", "", s)     #
    s = re.sub(r"[\s　]+", "", s)
    trans = str.maketrans("ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ",
                          "ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    return s.translate(trans)


def brand_core(full_name):
    """Extract the brand element from a listed firm's registered name.

    A full name is reduced first to its distinctive compound and then to a
    shorter group name. Candidates are returned in descending order of how
    distinctive they are.
    """
    s = norm(full_name)
    for suf in SUFFIX:
        if s.endswith(suf):
            s = s[: -len(suf)]
            break
    cands = [s]
    # ，
    t = s
    for _ in range(3):
        changed = False
        for b in sorted(BIZ, key=len, reverse=True):
            if t.endswith(b) and len(t) - len(b) >= 2:
                t = t[: -len(b)]
                changed = True
                break
        if changed and t not in cands:
            cands.append(t)
        if not changed:
            break
    #
    out = []
    for c in cands:
        out.append(c)
        for g in sorted(GEO, key=len, reverse=True):
            if c.startswith(g) and len(c) - len(g) >= 2:
                out.append(c[len(g):])
                break
    seen, res = set(), []
    for c in out:
        if len(c) >= 2 and c not in seen:
            seen.add(c)
            res.append(c)
    return res


def is_generic(token):
    """Test whether a brand element consists only of sector words and place names, and is therefore not distinctive.

    This is the critical gate in this module. Compounds built purely from
    generic words would, if allowed through, attach the plants of one national
    group to an unrelated listed firm whose name shares those words. A false
    match is far more damaging than a missed one, because it places an
    uncovered firm in the treatment group and contaminates the identification.
    """
    t = token
    for w in sorted(set(BIZ) | set(GEO) | {"发展", "投资", "能源", "电力", "集团"},
                    key=len, reverse=True):
        t = t.replace(w, "")
    return len(t) < 2          # ，


def match(emitters, firms):
    """Three-tier matching. Returns a detailed table carrying the tier and the evidence for each hit."""
    firms = firms.copy()
    firms["full_norm"] = firms["full_name"].map(norm)
    firms = firms[firms["full_norm"].str.len() >= 4]

    # ，
    tok2firms = {}
    for _, r in firms.iterrows():
        for c in brand_core(r["full_name"]):
            if len(c) >= 4 and c not in TOO_COMMON and not is_generic(c):
                tok2firms.setdefault(c, set()).add(r["code"])

    # ；
    code2name = dict(zip(firms["code"], firms["full_name"]))
    brand_index = [(c, next(iter(s)), code2name[next(iter(s))])
                   for c, s in tok2firms.items() if len(s) == 1]
    brand_index.sort(key=lambda x: -len(x[0]))

    full_map = {r["full_norm"]: (r["code"], r["full_name"])
                for _, r in firms.iterrows()}
    full_sorted = sorted(full_map.keys(), key=len, reverse=True)

    rows = []
    for _, e in emitters.iterrows():
        name = norm(e["entity_name"])
        hit = None

        # ：（）
        for fn in full_sorted:
            if fn in name:
                code, full = full_map[fn]
                hit = (1, code, full, fn)
                break

        # ：（）
        if hit is None:
            for c, code, full in brand_index:
                if c in name:
                    hit = (2, code, full, c)
                    break

        rows.append({
            "seq": e.get("seq"),
            "province": e.get("province"),
            "entity_name": e["entity_name"],
            "uscc": e.get("unified_social_credit_code"),
            "tier": hit[0] if hit else 3,
            "stock_code": hit[1] if hit else None,
            "listed_full_name": hit[2] if hit else None,
            "matched_on": hit[3] if hit else None,
        })
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--emitters", default="out/key_emitters_2019_2020.csv")
    ap.add_argument("--firms", default="raw/firm/firm_names.csv")
    ap.add_argument("--out", default="out/emitter_firm_match.csv")
    args = ap.parse_args()

    em = pd.read_csv(BASE / args.emitters, dtype=str)
    fm = pd.read_csv(BASE / args.firms, dtype={"code": str})
    fm = fm.dropna(subset=["full_name"])
    print(f"名单主体 {len(em)}  上市公司 {len(fm)}")

    res = match(em, fm)
    res.to_csv(BASE / args.out, index=False, encoding="utf-8-sig")

    n = len(res)
    for t in (1, 2, 3):
        k = (res["tier"] == t).sum()
        print(f"  第{t}层 {k:5d}  {k/n*100:5.1f}%")
    linked = res[res["stock_code"].notna()]
    print(f"命中合计 {len(linked)} 家次，对应上市公司 {linked['stock_code'].nunique()} 家")
    print("\n覆盖排名前 12 的上市公司：")
    top = (linked.groupby(["stock_code", "listed_full_name"])
           .size().sort_values(ascending=False).head(12))
    for (code, full), c in top.items():
        print(f"  {code}  {str(full)[:34]:36s} {c:4d} 家控排单位")


if __name__ == "__main__":
    main()
