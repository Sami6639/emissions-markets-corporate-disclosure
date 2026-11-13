# -*- coding: utf-8 -*-
"""Plot the event studies for both entry events, four panels.
"""
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
d = pd.read_csv(BASE / "out/tables/tabB_event_studies.csv")
d = d[d.year.astype(str).str.isdigit()].copy()
d["year"] = d.year.astype(int)

panels = [("2021 power entry", "any carbon content", 2021, 2019),
          ("2021 power entry", "any allowance quantity", 2021, 2019),
          ("2024 expansion", "any carbon content", 2024, 2019),
          ("2024 expansion", "any allowance quantity", 2024, 2019)]
fig, axes = plt.subplots(2, 2, figsize=(9.4, 6.2))
for ax, (ev, out, entry, base) in zip(axes.ravel(), panels):
    t = d[(d.event == ev) & (d.outcome == out)].sort_values("year")
    if t.empty:
        ax.set_visible(False)
        continue
    x = [base] + list(t.year)
    y = [0.0] + list(t.coef.astype(float))
    e = [0.0] + list(t.se.astype(float))
    ax.errorbar(x, y, yerr=[1.96 * v for v in e], fmt="o-", color="black",
                ecolor="0.55", capsize=3, lw=1.2, ms=4)
    ax.axhline(0, color="0.3", lw=0.8)
    ax.axvline(entry - 0.5, color="0.3", lw=0.8, ls="--")
    ax.set_title(f"{ev} — {out}", fontsize=9)
    ax.set_xticks(x)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_ylabel("Coefficient")
for ax in axes[1]:
    ax.set_xlabel("Financial year")
fig.tight_layout()
for ext in ("png", "pdf"):
    fig.savefig(BASE / f"out/figures/fig5_two_events.{ext}", dpi=300, bbox_inches="tight")
print("[done] fig5_two_events")
