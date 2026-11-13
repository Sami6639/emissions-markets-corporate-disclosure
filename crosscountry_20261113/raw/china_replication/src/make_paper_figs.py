# -*- coding: utf-8 -*-
"""Produce the three figures used in the paper, in black and white for single-column layout.

Figure 1  the two margins side by side: the share of reports with any carbon
          content and the share stating any allowance quantity, by year
Figure 2  event studies for both entry events, four panels
Figure 3  robustness: the extensive-margin estimate under three dictionaries, and
          the count outcome across specifications
"""
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
FIG = BASE / "out/figures"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9,
                     "axes.linewidth": 0.8, "savefig.dpi": 400})

LAB = {"always": "Covered since 2021", "expansion": "2024 cohort",
       "control": "Never covered"}
MK = {"always": ("o", "-"), "expansion": ("s", "-"), "control": ("^", "--")}


def load():
    d = pd.read_csv(BASE / "out/carbon_disclosure.csv", dtype={"code": str})
    d["P"] = d.hit_pages.fillna("").apply(
        lambda s: 0 if not str(s).strip() else len(str(s).split(";")))
    nf = pd.read_csv(BASE / "out/carbon_disclosure_namefilt.csv", dtype={"code": str})
    d = d.merge(nf[["code", "year", "n_hit_namefilt"]], on=["code", "year"], how="left")
    d["mention"] = (d.n_hit_namefilt > 0).astype(float)
    d["qty"] = (d.compliance_tier >= 2).astype(float)
    st = (pd.read_csv(BASE / "out/panel2.csv", dtype={"code": str})
          .groupby("code").ets_status.first())
    return d.merge(st, on="code", how="inner")


def fig1(m):
    g = m.groupby(["ets_status", "year"]).agg(mention=("mention", "mean"),
                                              qty=("qty", "mean")).reset_index()
    fig, ax = plt.subplots(1, 2, figsize=(7.2, 2.9))
    for k in ["always", "expansion", "control"]:
        t = g[g.ets_status == k].sort_values("year")
        mk, ls = MK[k]
        ax[0].plot(t.year, t.mention * 100, ls, marker=mk, color="black",
                   ms=4, lw=1.1, mfc="white" if k != "always" else "black",
                   label=LAB[k])
        ax[1].plot(t.year, t.qty * 100, ls, marker=mk, color="black",
                   ms=4, lw=1.1, mfc="white" if k != "always" else "black")
    for a, ttl, yl in [(ax[0], "(a) Any carbon content", "Share of reports (%)"),
                       (ax[1], "(b) Any allowance quantity", "Share of reports (%)")]:
        a.set_title(ttl, fontsize=9)
        a.set_ylabel(yl); a.set_xlabel("Financial year")
        a.spines[["top", "right"]].set_visible(False)
        a.set_xticks(range(2019, 2026))
        for yr in (2021, 2024):
            a.axvline(yr - 0.5, color="0.55", lw=0.7, ls=":")
    ax[0].legend(frameon=False, fontsize=7.5, loc="upper left",
                 bbox_to_anchor=(0.02, 0.99), handlelength=2.2)
    ax[0].set_ylim(-3, 88)
    ax[1].set_ylim(-0.3, 6.5)
    fig.tight_layout()
    for e in ("png", "pdf"):
        fig.savefig(FIG / f"figure1_two_margins.{e}", bbox_inches="tight")
    plt.close(fig)


def fig2():
    d = pd.read_csv(BASE / "out/tables/tabB_event_studies.csv")
    d = d[d.year.astype(str).str.isdigit()].copy()
    d["year"] = d.year.astype(int)
    panels = [("2024 expansion", "any carbon content", 2024,
               "(a) 2024 entry — any carbon content"),
              ("2024 expansion", "any allowance quantity", 2024,
               "(b) 2024 entry — any allowance quantity"),
              ("2021 power entry", "any carbon content", 2021,
               "(c) 2021 entry — any carbon content"),
              ("2021 power entry", "any allowance quantity", 2021,
               "(d) 2021 entry — any allowance quantity")]
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.0))
    for a, (ev, out, entry, ttl) in zip(axes.ravel(), panels):
        t = d[(d.event == ev) & (d.outcome == out)].sort_values("year")
        x = [2019] + list(t.year)
        y = [0.0] + list(t.coef.astype(float))
        e = [0.0] + list(t.se.astype(float))
        a.errorbar(x, y, yerr=[1.96 * v for v in e], fmt="o-", color="black",
                   ecolor="0.6", capsize=2.5, lw=1.0, ms=3.5)
        a.axhline(0, color="0.35", lw=0.8)
        a.axvline(entry - 0.5, color="0.35", lw=0.9, ls="--")
        a.set_title(ttl, fontsize=8.5)
        a.set_xticks(x)
        a.spines[["top", "right"]].set_visible(False)
        a.set_ylabel("Coefficient", fontsize=8)
    for a in axes[1]:
        a.set_xlabel("Financial year", fontsize=8)
    fig.tight_layout()
    for e in ("png", "pdf"):
        fig.savefig(FIG / f"figure2_event_studies.{e}", bbox_inches="tight")
    plt.close(fig)


def fig3():
    a = pd.read_csv(BASE / "out/tables/tabA_main_two_events.csv")
    ext = a[a.outcome == "any carbon content"]
    cnt = a[(a.outcome == "carbon pages") |
            (a.outcome == "carbon pages + linear trend") |
            (a.outcome == "log(1+pages)")]
    fig, ax = plt.subplots(1, 2, figsize=(7.2, 3.0))
    dicts = ["original", "restricted", "name-filtered"]
    for j, ev in enumerate(["2024 expansion", "2021 power entry"]):
        t = ext[ext.event == ev].set_index("dictionary").loc[dicts]
        off = -0.12 if j == 0 else 0.12
        ax[0].errorbar([i + off for i in range(3)], t.coef,
                       yerr=1.96 * t.se, fmt="os"[j] + "", color="black",
                       ecolor="0.6", capsize=3, ms=5,
                       mfc="black" if j == 0 else "white", ls="none",
                       label=ev)
    ax[0].axhline(0, color="0.35", lw=0.8)
    ax[0].set_xticks(range(3))
    ax[0].set_xticklabels(["Original", "Restricted", "Name-filtered"], fontsize=8)
    ax[0].set_ylabel("Coefficient on entry")
    ax[0].set_title("(a) Extensive margin, three dictionaries", fontsize=9)
    ax[0].legend(frameon=False, fontsize=7.5, loc="upper left")
    ax[0].spines[["top", "right"]].set_visible(False)

    lab, val, err = [], [], []
    for _, r in cnt[cnt.event == "2024 expansion"].iterrows():
        nm = {"carbon pages": r.dictionary, "carbon pages + linear trend": "with trend",
              "log(1+pages)": "log(1+P)"}.get(r.outcome, r.outcome)
        lab.append(nm); val.append(r.coef); err.append(1.96 * r.se)
    ax[1].errorbar(range(len(val)), val, yerr=err, fmt="o", color="black",
                   ecolor="0.6", capsize=3, ms=5, ls="none")
    ax[1].axhline(0, color="0.35", lw=0.8)
    ax[1].set_xticks(range(len(lab)))
    ax[1].set_xticklabels(lab, rotation=30, ha="right", fontsize=7.5)
    ax[1].set_ylabel("Coefficient")
    ax[1].set_title("(b) Count outcome, 2024 entry", fontsize=9)
    ax[1].spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    for e in ("png", "pdf"):
        fig.savefig(FIG / f"figure3_robustness.{e}", bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    m = load()
    fig1(m); fig2(); fig3()
    print("[done] figure1_two_margins / figure2_event_studies / figure3_robustness")
