"""
Analyze per-ability damage breakdowns to identify exactly which parts
of the DK's damage are being misattributed from Aug.

Compares the proportion of damage from pet/direct/disease abilities
between aug and no-aug comps after normalizing for buff differences.
"""

import json
import os
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import pandas as pd
import base64
from io import BytesIO

from analyze import BUFF_MULTIPLIERS, compute_buff_multiplier, STYLE, fig_to_base64, set_dark_style

PLAYER_ABILITIES = {
    "Putrefy", "Graveyard", "Scourge Strike", "Epidemic",
    "Necrotic Coil", "Death Coil", "Melee", "Soul Reaper",
    "Festering Scythe", "Death and Decay", "Festering Strike",
    "Death Strike", "Anti-Magic Shell",
}

DISEASE_ABILITIES = {
    "Virulent Plague", "Dread Plague", "Pestilence",
    "Festering Wound",
}


def load_breakdowns() -> pd.DataFrame:
    path = os.path.join("data", "breakdowns.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    df = pd.DataFrame(data)
    df["buff_multiplier"] = df["buffs"].apply(compute_buff_multiplier)
    df["norm_total"] = df["total_damage"] / df["buff_multiplier"]
    df["norm_pet"] = df["pet_damage"] / df["buff_multiplier"]
    df["norm_direct"] = df["direct_damage"] / df["buff_multiplier"]
    df["norm_disease"] = df["disease_damage"] / df["buff_multiplier"]
    print(f"Loaded {len(df)} breakdowns (aug={df['has_aug'].sum()}, "
          f"no-aug={(~df['has_aug']).sum()})")
    return df


def analyze_categories(df):
    """Compare damage categories between aug and no-aug."""
    aug = df[df["has_aug"]]
    noaug = df[~df["has_aug"]]

    print("\n" + "=" * 70)
    print("  DAMAGE BREAKDOWN ANALYSIS — AUG vs NO-AUG")
    print("=" * 70)

    print(f"\n  Samples: aug={len(aug)}, no-aug={len(noaug)}")

    # Category percentages
    print(f"\n  --- Damage Category Proportions (% of total) ---")
    for cat in ["pet", "direct", "disease"]:
        col = f"{cat}_pct"
        aug_pct = aug[col].mean()
        noaug_pct = noaug[col].mean()
        delta = aug_pct - noaug_pct
        print(f"    {cat:<12s}  Aug: {aug_pct:5.1f}%   No-Aug: {noaug_pct:5.1f}%   Δ: {delta:+5.1f}pp")

    # Normalized absolute damage per category (DPS)
    print(f"\n  --- Normalized Category DPS (damage / duration) ---")
    aug_dur = aug["total_damage"] / aug["dps"]
    noaug_dur = noaug["total_damage"] / noaug["dps"]

    for cat in ["pet", "direct", "disease"]:
        aug_dps = (aug[f"norm_{cat}"] / aug_dur).mean()
        noaug_dps = (noaug[f"norm_{cat}"] / noaug_dur).mean()
        delta = aug_dps - noaug_dps
        pct = delta / noaug_dps * 100 if noaug_dps else 0
        print(f"    {cat:<12s}  Aug: {aug_dps:>9,.0f}   No-Aug: {noaug_dps:>9,.0f}   "
              f"Δ: {delta:>+8,.0f} ({pct:+.1f}%)")


def analyze_per_ability(df):
    """Compare individual ability damage between aug and no-aug."""
    aug = df[df["has_aug"]]
    noaug = df[~df["has_aug"]]

    # Aggregate ability damage across all entries
    def aggregate_abilities(subset):
        totals = defaultdict(lambda: {"total": 0, "count": 0})
        for _, row in subset.iterrows():
            duration_s = row["total_damage"] / row["dps"]
            for a in row["abilities"]:
                dps = a["total"] / duration_s
                totals[a["name"]]["total"] += dps
                totals[a["name"]]["count"] += 1
        # Average DPS per ability
        return {name: info["total"] / info["count"]
                for name, info in totals.items() if info["count"] >= 10}

    aug_abilities = aggregate_abilities(aug)
    noaug_abilities = aggregate_abilities(noaug)

    all_abilities = set(aug_abilities.keys()) | set(noaug_abilities.keys())

    print(f"\n  --- Per-Ability DPS Comparison (sorted by delta) ---")
    print(f"  {'Ability':<30s} {'Cat':<8s} {'Aug DPS':>10s} {'NoAug DPS':>10s} {'Δ DPS':>10s} {'Δ%':>7s}")
    print("  " + "-" * 80)

    rows = []
    for name in all_abilities:
        aug_dps = aug_abilities.get(name, 0)
        noaug_dps = noaug_abilities.get(name, 0)
        delta = aug_dps - noaug_dps
        if name in PLAYER_ABILITIES:
            cat = "direct"
        elif name in DISEASE_ABILITIES:
            cat = "disease"
        else:
            cat = "pet"
        pct = delta / noaug_dps * 100 if noaug_dps > 0 else float("inf")
        rows.append((name, cat, aug_dps, noaug_dps, delta, pct))

    rows.sort(key=lambda x: -abs(x[4]))

    for name, cat, aug_dps, noaug_dps, delta, pct in rows:
        if aug_dps + noaug_dps > 500:
            pct_str = f"{pct:+6.1f}%" if abs(pct) < 1000 else "  new"
            print(f"  {name:<30s} {cat:<8s} {aug_dps:>10,.0f} {noaug_dps:>10,.0f} "
                  f"{delta:>+10,.0f} {pct_str}")

    return rows


def chart_category_comparison(df):
    aug = df[df["has_aug"]]
    noaug = df[~df["has_aug"]]

    cats = ["Pet", "Direct", "Disease"]
    aug_pcts = [aug["pet_pct"].mean(), aug["direct_pct"].mean(), aug["disease_pct"].mean()]
    noaug_pcts = [noaug["pet_pct"].mean(), noaug["direct_pct"].mean(), noaug["disease_pct"].mean()]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.patch.set_facecolor(STYLE["bg"])

    # Left: category proportions
    ax = axes[0]
    set_dark_style(ax, "Damage Category Proportions")
    x = range(len(cats))
    w = 0.35
    ax.bar([i - w/2 for i in x], aug_pcts, w, color=STYLE["aug"], alpha=0.85, label="Aug")
    ax.bar([i + w/2 for i in x], noaug_pcts, w, color=STYLE["noaug"], alpha=0.85, label="No Aug")
    ax.set_xticks(list(x))
    ax.set_xticklabels(cats)
    ax.set_ylabel("% of total damage", color=STYLE["text"])
    ax.legend(fontsize=10, facecolor=STYLE["card"], edgecolor=STYLE["grid"],
              labelcolor=STYLE["text"])

    # Add value labels
    for i, (a, n) in enumerate(zip(aug_pcts, noaug_pcts)):
        ax.text(i - w/2, a + 0.5, f"{a:.1f}%", ha="center", color=STYLE["text"], fontsize=9)
        ax.text(i + w/2, n + 0.5, f"{n:.1f}%", ha="center", color=STYLE["text"], fontsize=9)

    # Right: normalized DPS per category
    ax = axes[1]
    set_dark_style(ax, "Normalized Category DPS")
    aug_dur = aug["total_damage"] / aug["dps"]
    noaug_dur = noaug["total_damage"] / noaug["dps"]
    aug_vals = [(aug["norm_pet"] / aug_dur).mean(),
                (aug["norm_direct"] / aug_dur).mean(),
                (aug["norm_disease"] / aug_dur).mean()]
    noaug_vals = [(noaug["norm_pet"] / noaug_dur).mean(),
                  (noaug["norm_direct"] / noaug_dur).mean(),
                  (noaug["norm_disease"] / noaug_dur).mean()]

    ax.bar([i - w/2 for i in x], aug_vals, w, color=STYLE["aug"], alpha=0.85, label="Aug")
    ax.bar([i + w/2 for i in x], noaug_vals, w, color=STYLE["noaug"], alpha=0.85, label="No Aug")
    ax.set_xticks(list(x))
    ax.set_xticklabels(cats)
    ax.set_ylabel("DPS (normalized)", color=STYLE["text"])
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{x/1000:.0f}k"))
    ax.legend(fontsize=10, facecolor=STYLE["card"], edgecolor=STYLE["grid"],
              labelcolor=STYLE["text"])

    fig.tight_layout()
    return fig_to_base64(fig)


def chart_top_abilities(df, rows):
    """Bar chart of per-ability DPS delta."""
    # Filter to meaningful abilities
    significant = [(n, c, a, na, d, p) for n, c, a, na, d, p in rows
                   if a + na > 1000 and abs(d) > 100][:15]

    if not significant:
        return ""

    fig, ax = plt.subplots(figsize=(14, 7))
    fig.patch.set_facecolor(STYLE["bg"])
    set_dark_style(ax, "Per-Ability DPS Delta (Aug − No-Aug, normalized)")

    names = [r[0] for r in significant]
    deltas = [r[4] for r in significant]
    cats = [r[1] for r in significant]

    cat_colors = {"pet": "#e74c3c", "direct": "#3498db", "disease": "#2ecc71"}
    colors = [cat_colors.get(c, STYLE["text"]) for c in cats]

    bars = ax.barh(range(len(names)), deltas, color=colors, alpha=0.85)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=9)
    ax.set_xlabel("DPS Delta (Aug − No-Aug)", color=STYLE["text"])
    ax.axvline(0, color=STYLE["text"], linewidth=0.5, alpha=0.5)
    ax.invert_yaxis()

    for bar, d in zip(bars, deltas):
        ax.text(bar.get_width() + (100 if d >= 0 else -100),
                bar.get_y() + bar.get_height()/2,
                f"{d:+,.0f}", va="center",
                ha="left" if d >= 0 else "right",
                color=STYLE["text"], fontsize=9)

    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color="#e74c3c", label="Pet"),
                       Patch(color="#3498db", label="Direct"),
                       Patch(color="#2ecc71", label="Disease")],
              fontsize=10, facecolor=STYLE["card"], edgecolor=STYLE["grid"],
              labelcolor=STYLE["text"], loc="lower right")

    fig.tight_layout()
    return fig_to_base64(fig)


def main():
    df = load_breakdowns()
    analyze_categories(df)
    ability_rows = analyze_per_ability(df)

    print("\nGenerating charts...")
    cat_chart = chart_category_comparison(df)
    ability_chart = chart_top_abilities(df, ability_rows)

    # Save charts for inclusion in main report
    charts = {"category": cat_chart, "abilities": ability_chart}
    with open(os.path.join("data", "breakdown_charts.json"), "w") as f:
        json.dump(charts, f)

    print("Charts saved. Run analyze.py to regenerate the full report with breakdowns.")


if __name__ == "__main__":
    main()
