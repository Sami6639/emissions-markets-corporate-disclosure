# -*- coding: utf-8 -*-
"""Plot the event study under the count model and the log specification side by side, to show how functional form changes the reading.
"""
from pathlib import Path
import warnings

warnings.filterwarnings("ignore")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
d = pd.read_csv(BASE / "out/tables/tab6_event_study.csv")
d = d[d.year.astype(str).str.isdigit()].copy()
d["year"] = d.year.astype(int)

fig, ax = plt.subplots(1, 2, figsize=(9.2, 3.6), sharex=True)
for a, (c, se, ttl) in zip(ax, [("ppml_coef", "ppml_se", "Count model (PPML)"),
                                ("log_coef", "log_se", "log(1 + pages), OLS")]):
    y = pd.concat([pd.Series([0.0]), d[c]]).astype(float).values
    e = pd.concat([pd.Series([0.0]), d[se]]).astype(float).values
    x = [2021] + list(d.year)
    a.errorbar(x, y, yerr=1.96 * e, fmt="o-", color="black", ecolor="0.55",
               capsize=3, lw=1.2, ms=4)
    a.axhline(0, color="0.3", lw=0.8)
    a.axvline(2023.5, color="0.3", lw=0.8, ls="--")
    a.set_title(ttl, fontsize=10)
    a.set_xticks(x)
    a.set_xlabel("Financial year")
    a.spines[["top", "right"]].set_visible(False)
ax[0].set_ylabel("Coefficient relative to 2021")
fig.tight_layout()
for ext in ("png", "pdf"):
    fig.savefig(BASE / f"out/figures/fig4_event_study.{ext}", dpi=300, bbox_inches="tight")
print("[done] fig4_event_study 已重画（计数模型 vs 对数模型）")
