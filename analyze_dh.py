"""
Analyze Havoc DH rankings to quantify Aug Evoker damage misattribution.

Havoc DH damage is ~100% direct player damage (no pets), split between
uncapped AoE (Immolation Aura, Eye Beam/Demonsurge) and capped cleave
(Blade Dance/Death Sweep, Glaive Tempest).
"""

import json
import os
import sys
import base64
from io import BytesIO
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import pandas as pd
import numpy as np

from analyze import (
    compute_buff_multiplier, fig_to_base64, set_dark_style,
    BUFF_MULTIPLIERS, STYLE,
)

UNCAPPED_AOE = ["Immolation Aura", "Demonsurge", "Eye Beam"]
CAPPED_CLEAVE = ["Death Sweep", "Blade Dance", "Glaive Tempest", "Trail of Ruin",
                 "Burning Blades", "The Hunt"]
ST_FILLER = ["Annihilation", "Chaos Strike", "Demon Blades", "Melee", "Throw Glaive"]


def load_dh_rankings():
    path = os.path.join("data", "dh_rankings.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    df = pd.DataFrame(data)
    return df


def normalize_dh_dps(df):
    df = df.copy()
    df["buff_multiplier"] = df["buffs"].apply(compute_buff_multiplier)
    df["normalized_dps"] = df["dps"] / df["buff_multiplier"]
    return df


def compute_dh_stats(df):
    aug = df[df["has_aug"]]
    noaug = df[~df["has_aug"]]

    raw_delta = aug["dps"].mean() - noaug["dps"].mean()
    raw_pct = raw_delta / noaug["dps"].mean() * 100
    norm_delta = aug["normalized_dps"].mean() - noaug["normalized_dps"].mean()
    norm_pct = norm_delta / noaug["normalized_dps"].mean() * 100

    dungeon_stats = []
    for d in sorted(df["dungeon"].unique()):
        sub = df[df["dungeon"] == d]
        da = sub[sub["has_aug"]]
        dn = sub[~sub["has_aug"]]
        if len(da) < 3 or len(dn) < 3:
            continue
        delta = da["normalized_dps"].mean() - dn["normalized_dps"].mean()
        pct = delta / dn["normalized_dps"].mean() * 100
        dungeon_stats.append({
            "dungeon": d, "delta": delta, "pct": pct,
            "n_aug": len(da), "n_noaug": len(dn),
        })

    kl_stats = []
    for kl in sorted(df["key_level"].unique()):
        ka = df[(df["has_aug"]) & (df["key_level"] == kl)]
        kn = df[(~df["has_aug"]) & (df["key_level"] == kl)]
        if len(ka) >= 5 and len(kn) >= 5:
            delta = ka["normalized_dps"].mean() - kn["normalized_dps"].mean()
            pct = delta / kn["normalized_dps"].mean() * 100
            kl_stats.append({"key": kl, "delta": delta, "pct": pct,
                             "n_aug": len(ka), "n_noaug": len(kn)})

    buff_freq = {}
    for bn in BUFF_MULTIPLIERS:
        buff_freq[bn] = {
            "aug": aug["buffs"].apply(lambda b: b.get(bn, False)).mean() * 100,
            "noaug": noaug["buffs"].apply(lambda b: b.get(bn, False)).mean() * 100,
        }

    return {
        "total": len(df), "n_aug": len(aug), "n_noaug": len(noaug),
        "aug_raw_mean": aug["dps"].mean(), "noaug_raw_mean": noaug["dps"].mean(),
        "raw_delta": raw_delta, "raw_pct": raw_pct,
        "aug_norm_mean": aug["normalized_dps"].mean(),
        "noaug_norm_mean": noaug["normalized_dps"].mean(),
        "norm_delta": norm_delta, "norm_pct": norm_pct,
        "aug_buff_mult": aug["buff_multiplier"].mean(),
        "noaug_buff_mult": noaug["buff_multiplier"].mean(),
        "dungeon_stats": dungeon_stats,
        "kl_stats": kl_stats,
        "buff_freq": buff_freq,
    }


def chart_dh_distributions(df):
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    fig.patch.set_facecolor(STYLE["bg"])

    aug = df[df["has_aug"]]
    noaug = df[~df["has_aug"]]

    for ax, col, title in [
        (axes[0], "dps", "Raw DPS (as logged)"),
        (axes[1], "normalized_dps", "Buff-Normalized DPS"),
        (axes[2], "normalized_dps", "Normalized DPS — Overlaid"),
    ]:
        set_dark_style(ax, title)
        lo = int(min(aug[col].min(), noaug[col].min()) // 5000 * 5000)
        hi = int(max(aug[col].max(), noaug[col].max()) // 5000 * 5000) + 10000
        bins = range(lo, hi, 5000)
        if title.startswith("Normalized DPS"):
            ax.hist(aug[col], bins=bins, alpha=0.6, color=STYLE["aug"],
                    label=f"Aug (n={len(aug)})", density=True)
            ax.hist(noaug[col], bins=bins, alpha=0.6, color=STYLE["noaug"],
                    label=f"No Aug (n={len(noaug)})", density=True)
        else:
            ax.hist(aug[col], bins=bins, alpha=0.6, color=STYLE["aug"],
                    label=f"Aug (n={len(aug)})")
            ax.hist(noaug[col], bins=bins, alpha=0.6, color=STYLE["noaug"],
                    label=f"No Aug (n={len(noaug)})")
        ax.legend(fontsize=9, facecolor=STYLE["card"], edgecolor=STYLE["grid"],
                  labelcolor=STYLE["text"])
        ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{x/1000:.0f}k"))
        ax.set_xlabel("DPS", color=STYLE["text"], fontsize=10)

    fig.suptitle("Havoc DH DPS Distributions: Aug vs No-Aug",
                 color=STYLE["accent"], fontsize=15, fontweight="bold", y=1.02)
    fig.tight_layout()
    return fig_to_base64(fig)


def chart_dh_per_dungeon(df):
    dungeons = sorted(df["dungeon"].unique())
    deltas, pcts, ns_aug, ns_noaug = [], [], [], []

    for d in dungeons:
        sub = df[df["dungeon"] == d]
        a = sub[sub["has_aug"]]["normalized_dps"]
        n = sub[~sub["has_aug"]]["normalized_dps"]
        if len(a) < 3 or len(n) < 3:
            continue
        delta = a.mean() - n.mean()
        pct = delta / n.mean() * 100
        deltas.append(delta)
        pcts.append(pct)
        ns_aug.append(len(a))
        ns_noaug.append(len(n))

    fig, ax = plt.subplots(figsize=(14, 6))
    fig.patch.set_facecolor(STYLE["bg"])
    set_dark_style(ax, "Buff-Normalized DPS Delta per Dungeon (Aug - No-Aug)")

    short_names = [d.replace("Seat of the Triumvirate", "Seat of Triumv.")
                    .replace("Algeth'ar Academy", "Algeth'ar Acad.") for d in dungeons]
    colors = [STYLE["aug"] if d > 0 else STYLE["noaug"] for d in deltas]
    bars = ax.bar(short_names, deltas, color=colors, alpha=0.85)

    for bar, pct, na, nn in zip(bars, pcts, ns_aug, ns_noaug):
        y = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, y + 150,
                f"{pct:+.1f}%\n({na}/{nn})",
                ha="center", va="bottom", color=STYLE["text"], fontsize=8)

    ax.axhline(0, color=STYLE["text"], linewidth=0.5, alpha=0.3)
    avg_delta = sum(deltas) / len(deltas) if deltas else 0
    ax.axhline(avg_delta, color=STYLE["accent"], linewidth=1.5, linestyle="--", alpha=0.8)
    ax.text(len(dungeons) - 0.5, avg_delta + 200,
            f"avg: {avg_delta:+,.0f}", color=STYLE["accent"], fontsize=10, ha="right")
    ax.set_ylabel("DPS Delta", color=STYLE["text"], fontsize=11)
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{x:+,.0f}"))
    plt.xticks(rotation=30, ha="right")
    fig.tight_layout()
    return fig_to_base64(fig)


def chart_dh_key_level(df):
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.patch.set_facecolor(STYLE["bg"])

    ax = axes[0]
    set_dark_style(ax, "Normalized DPS by Key Level")
    for label, subset, color in [("Aug", df[df["has_aug"]], STYLE["aug"]),
                                  ("No Aug", df[~df["has_aug"]], STYLE["noaug"])]:
        grouped = subset.groupby("key_level")["normalized_dps"]
        means = grouped.mean()
        stds = grouped.std()
        counts = grouped.count()
        valid = counts >= 5
        ax.errorbar(means.index[valid], means[valid], yerr=stds[valid]/counts[valid]**0.5,
                     fmt="o-", color=color, label=label, capsize=4, linewidth=2, markersize=6)
    ax.legend(fontsize=10, facecolor=STYLE["card"], edgecolor=STYLE["grid"],
              labelcolor=STYLE["text"])
    ax.set_xlabel("Key Level", color=STYLE["text"])
    ax.set_ylabel("Normalized DPS", color=STYLE["text"])
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{x/1000:.0f}k"))

    ax = axes[1]
    set_dark_style(ax, "Sample Count by Key Level")
    for label, subset, color in [("Aug", df[df["has_aug"]], STYLE["aug"]),
                                  ("No Aug", df[~df["has_aug"]], STYLE["noaug"])]:
        counts = subset.groupby("key_level").size()
        ax.bar(counts.index - 0.15 if label == "Aug" else counts.index + 0.15,
               counts.values, width=0.3, color=color, alpha=0.85, label=label)
    ax.legend(fontsize=10, facecolor=STYLE["card"], edgecolor=STYLE["grid"],
              labelcolor=STYLE["text"])
    ax.set_xlabel("Key Level", color=STYLE["text"])
    ax.set_ylabel("Count", color=STYLE["text"])
    fig.tight_layout()
    return fig_to_base64(fig)


def load_dh_breakdowns():
    path = os.path.join("data", "dh_breakdowns.json")
    if not os.path.exists(path):
        return None, None

    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    bdf = pd.DataFrame(data)
    bdf["buff_multiplier"] = bdf["buffs"].apply(compute_buff_multiplier)

    aug = bdf[bdf["has_aug"]]
    noaug = bdf[~bdf["has_aug"]]

    aug_dur = aug["total_damage"] / aug["dps"]
    noaug_dur = noaug["total_damage"] / noaug["dps"]

    def agg(subset):
        totals = defaultdict(lambda: {"total": 0, "count": 0})
        for _, row in subset.iterrows():
            dur = row["total_damage"] / row["dps"]
            bm = compute_buff_multiplier(row["buffs"])
            for a in row["abilities"]:
                dps = a["total"] / bm / dur
                totals[a["name"]]["total"] += dps
                totals[a["name"]]["count"] += 1
        return {n: (i["total"] / i["count"], i["count"]) for n, i in totals.items()}

    aug_ab = agg(aug)
    noaug_ab = agg(noaug)

    all_names = set(aug_ab) | set(noaug_ab)
    ability_rows = []
    for name in all_names:
        if any(ord(c) > 127 for c in name):
            continue
        if name == "Unknown":
            continue
        aug_dps, aug_n = aug_ab.get(name, (0, 0))
        noaug_dps, noaug_n = noaug_ab.get(name, (0, 0))
        if aug_n + noaug_n < 20:
            continue
        delta = aug_dps - noaug_dps
        pct = delta / noaug_dps * 100 if noaug_dps > 0 else (999 if aug_dps > 0 else 0)
        cat = classify_dh_ability(name)
        if aug_dps + noaug_dps > 100:
            ability_rows.append({"name": name, "cat": cat, "aug": aug_dps,
                                 "noaug": noaug_dps, "delta": delta, "pct": pct,
                                 "aug_n": aug_n, "noaug_n": noaug_n})
    ability_rows.sort(key=lambda x: -abs(x["delta"]))

    # AoE category analysis
    def get_dps_from_row(row, name):
        dur = row["total_damage"] / row["dps"]
        bm = compute_buff_multiplier(row["buffs"])
        for a in row["abilities"]:
            if a["name"] == name:
                return a["total"] / bm / dur
        return 0

    aoe_analysis = {"uncapped": {}, "capped": {}, "st": {}}
    for label, subset in [("aug", aug), ("noaug", noaug)]:
        for ab in UNCAPPED_AOE:
            vals = [get_dps_from_row(row, ab) for _, row in subset.iterrows()]
            aoe_analysis["uncapped"].setdefault(ab, {})[label] = sum(vals) / len(vals)
        for ab in CAPPED_CLEAVE:
            vals = [get_dps_from_row(row, ab) for _, row in subset.iterrows()]
            aoe_analysis["capped"].setdefault(ab, {})[label] = sum(vals) / len(vals)
        for ab in ST_FILLER:
            vals = [get_dps_from_row(row, ab) for _, row in subset.iterrows()]
            aoe_analysis["st"].setdefault(ab, {})[label] = sum(vals) / len(vals)

    for cat, abilities in [("uncapped", UNCAPPED_AOE), ("capped", CAPPED_CLEAVE), ("st", ST_FILLER)]:
        for label in ["aug", "noaug"]:
            aoe_analysis[cat]["_total_" + label] = sum(
                aoe_analysis[cat][ab][label] for ab in abilities)

    # Per-ability chart
    filtered = [r for r in ability_rows if abs(r["pct"]) < 500][:18]
    fig, ax = plt.subplots(figsize=(14, max(6, len(filtered) * 0.4)))
    fig.patch.set_facecolor(STYLE["bg"])
    set_dark_style(ax, "Per-Ability Normalized DPS Delta (Aug - No-Aug)")
    cat_colors = {"uncapped_aoe": "#e74c3c", "capped_cleave": "#f39c12",
                  "st": "#3498db", "other": "#aaa"}
    names = [r["name"] for r in filtered]
    deltas = [r["delta"] for r in filtered]
    colors = [cat_colors.get(r["cat"], "#aaa") for r in filtered]
    ax.barh(range(len(names)), deltas, color=colors, alpha=0.85)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=9)
    ax.set_xlabel("DPS Delta", color=STYLE["text"])
    ax.axvline(0, color=STYLE["text"], linewidth=0.5, alpha=0.5)
    ax.invert_yaxis()
    for i, (d, r) in enumerate(zip(deltas, filtered)):
        ax.text(d + (50 if d >= 0 else -50), i, f"{d:+,.0f} ({r['pct']:+.1f}%)",
                va="center", ha="left" if d >= 0 else "right", color=STYLE["text"], fontsize=8)
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color="#e74c3c", label="Uncapped AoE"),
                       Patch(color="#f39c12", label="Capped Cleave"),
                       Patch(color="#3498db", label="Single Target")],
              fontsize=10, facecolor=STYLE["card"], edgecolor=STYLE["grid"],
              labelcolor=STYLE["text"], loc="lower right")
    fig.tight_layout()
    ability_chart = fig_to_base64(fig)

    # AoE category chart
    uncapped_labels = ["Immolation\nAura", "Demonsurge", "Eye Beam"]
    capped_labels = ["Death\nSweep", "Blade\nDance", "Glaive\nTempest",
                     "Trail of\nRuin", "Burning\nBlades", "The Hunt"]

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    fig.patch.set_facecolor(STYLE["bg"])
    w = 0.35

    ax = axes[0]
    set_dark_style(ax, "Uncapped AoE Sources")
    xi = range(len(UNCAPPED_AOE))
    aug_vals = [aoe_analysis["uncapped"][ab]["aug"] for ab in UNCAPPED_AOE]
    noaug_vals = [aoe_analysis["uncapped"][ab]["noaug"] for ab in UNCAPPED_AOE]
    ax.bar([i - w/2 for i in xi], aug_vals, w, color=STYLE["aug"], alpha=0.85, label="Aug")
    ax.bar([i + w/2 for i in xi], noaug_vals, w, color=STYLE["noaug"], alpha=0.85, label="No Aug")
    ax.set_xticks(list(xi))
    ax.set_xticklabels(uncapped_labels, fontsize=9)
    ax.set_ylabel("Normalized DPS", color=STYLE["text"])
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v/1000:.0f}k"))
    for i, (a, n) in enumerate(zip(aug_vals, noaug_vals)):
        delta = a - n
        pct = delta / n * 100 if n > 0 else 0
        ax.text(i, max(a, n) + 400, f"{pct:+.1f}%", ha="center",
                color=STYLE["accent"], fontsize=9, fontweight="bold")
    ax.legend(fontsize=9, facecolor=STYLE["card"], edgecolor=STYLE["grid"], labelcolor=STYLE["text"])

    ax = axes[1]
    set_dark_style(ax, "Capped Cleave Sources")
    xi = range(len(CAPPED_CLEAVE))
    aug_vals = [aoe_analysis["capped"][ab]["aug"] for ab in CAPPED_CLEAVE]
    noaug_vals = [aoe_analysis["capped"][ab]["noaug"] for ab in CAPPED_CLEAVE]
    ax.bar([i - w/2 for i in xi], aug_vals, w, color=STYLE["aug"], alpha=0.85, label="Aug")
    ax.bar([i + w/2 for i in xi], noaug_vals, w, color=STYLE["noaug"], alpha=0.85, label="No Aug")
    ax.set_xticks(list(xi))
    ax.set_xticklabels(capped_labels, fontsize=8)
    ax.set_ylabel("Normalized DPS", color=STYLE["text"])
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v/1000:.0f}k"))
    for i, (a, n) in enumerate(zip(aug_vals, noaug_vals)):
        delta = a - n
        pct = delta / n * 100 if n > 0 else 0
        color = STYLE["accent"] if delta >= 0 else "#E17055"
        ax.text(i, max(a, n) + 200, f"{pct:+.1f}%", ha="center",
                color=color, fontsize=9, fontweight="bold")
    ax.legend(fontsize=9, facecolor=STYLE["card"], edgecolor=STYLE["grid"], labelcolor=STYLE["text"])
    fig.tight_layout()
    aoe_chart = fig_to_base64(fig)

    breakdown_data = {
        "ability_rows": filtered,
        "n_aug": len(aug), "n_noaug": len(noaug),
        "aoe_analysis": aoe_analysis,
    }
    breakdown_charts = {
        "dh_abilities": ability_chart,
        "dh_aoe": aoe_chart,
    }
    return breakdown_data, breakdown_charts


def classify_dh_ability(name):
    if name in UNCAPPED_AOE:
        return "uncapped_aoe"
    if name in CAPPED_CLEAVE:
        return "capped_cleave"
    if name in ST_FILLER:
        return "st"
    return "other"
