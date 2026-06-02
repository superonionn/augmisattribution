"""Comp-controlled analysis: compare DPS with and without Aug,
controlling for healer (RSham vs MW) and tank (Bear vs Brew).

Key insight: no-aug comps MUST play RSham (lust requirement),
while aug comps usually play MW. Windfury inflates melee in RSham groups,
but melee is ~1% of DK DPS so it's negligible.
"""
import json
import sys
import statistics
import base64
from io import BytesIO
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

from analyze import STYLE, fig_to_base64, set_dark_style, compute_buff_multiplier

# Abilities known to be AoE (affected by pull size)
DK_AOE = {"Graveyard", "Epidemic", "Death and Decay", "Pestilence", "Raise Abomination"}
# Abilities known to be ST
DK_ST = {"Scourge Strike", "Death Coil", "Necrotic Coil", "Soul Reaper"}
# Pet abilities (naming varies)
DK_PET = {"Raise Dead", "未知目标", "Sweeping Claws", "Infected Claws", "Lesser Ghoul",
           "Claw", "Halazzi's Claws"}


def classify_comp(comp):
    """Return (tank_class, healer_spec, dps_classes) from a comp."""
    tank = healer_spec = None
    dps = []
    for p in comp:
        spec = p.get("spec", "")
        cls = p.get("class", "")
        if spec in ("Guardian", "Protection", "Blood", "Brewmaster", "Vengeance"):
            tank = cls
        elif spec in ("Mistweaver", "Holy", "Restoration", "Discipline", "Preservation"):
            healer_spec = spec
        elif spec == "Augmentation":
            continue
        else:
            dps.append(cls)
    return tank, healer_spec, sorted(dps)


def load_dk_with_comps():
    """Load DK breakdowns joined with comp info from rankings."""
    with open("data/breakdowns.json", encoding="utf-8") as f:
        dk_data = json.load(f)
    with open("data/rankings.json", encoding="utf-8") as f:
        dk_rankings = json.load(f)

    comp_lookup = {}
    for r in dk_rankings:
        comp_lookup[(r["player"], r["dungeon"])] = r.get("comp", [])

    for entry in dk_data:
        entry["comp"] = comp_lookup.get((entry["player"], entry["dungeon"]), [])
        entry["tank"], entry["healer_spec"], entry["dps_partners"] = classify_comp(entry["comp"])
    return dk_data


def ability_breakdown(entries):
    """Compute mean DPS per ability across entries, normalized for buffs."""
    totals = defaultdict(list)
    for row in entries:
        bm = compute_buff_multiplier(row["buffs"])
        dur = row["total_damage"] / row["dps"] if row["dps"] > 0 else 0
        if dur <= 0:
            continue
        for a in row["abilities"]:
            totals[a["name"]].append(a["total"] / bm / dur)
    return {n: statistics.mean(v) for n, v in totals.items() if len(v) >= 8}


def aoe_st_ratio(entry):
    """Compute AoE/ST ratio for a single entry (pull-size proxy)."""
    dur = entry["total_damage"] / entry["dps"] if entry["dps"] > 0 else 0
    if dur <= 0:
        return None
    bm = compute_buff_multiplier(entry["buffs"])
    aoe = st = 0
    for a in entry["abilities"]:
        dps = a["total"] / bm / dur
        if a["name"] in DK_AOE:
            aoe += dps
        elif a["name"] in DK_ST:
            st += dps
    return aoe / st if st > 100 else None


def run_comp_controlled_analysis():
    """Main analysis: Aug(Bear+MW) vs NoAug(Bear+RSham+meta DPS)."""
    dk_data = load_dk_with_comps()

    # Split into controlled groups
    aug_bear_mw = [e for e in dk_data if e["has_aug"] and e["tank"] == "Druid"
                   and e["healer_spec"] == "Mistweaver"]
    aug_bear_rsham = [e for e in dk_data if e["has_aug"] and e["tank"] == "Druid"
                      and e["healer_spec"] == "Restoration"]
    noaug_bear_rsham = [e for e in dk_data if not e["has_aug"] and e["tank"] == "Druid"
                        and e["healer_spec"] == "Restoration"
                        and ("DemonHunter" in e["dps_partners"] or "Warlock" in e["dps_partners"])]
    noaug_all = [e for e in dk_data if not e["has_aug"] and e["tank"] == "Druid"
                 and e["healer_spec"] == "Restoration"]

    stats = {
        "aug_bear_mw": len(aug_bear_mw),
        "aug_bear_rsham": len(aug_bear_rsham),
        "noaug_bear_rsham_meta": len(noaug_bear_rsham),
        "noaug_bear_rsham_all": len(noaug_all),
    }

    # Ability comparison: focus on AoE under-stripping
    aug_ab = ability_breakdown(aug_bear_mw)
    noaug_ab = ability_breakdown(noaug_bear_rsham)

    # Categorize deltas
    ability_deltas = []
    for name in set(aug_ab) | set(noaug_ab):
        a = aug_ab.get(name, 0)
        n = noaug_ab.get(name, 0)
        if a + n < 300:
            continue
        diff = a - n
        pct = diff / n * 100 if n > 0 else 0
        category = "aoe" if name in DK_AOE else "st" if name in DK_ST else "pet" if name in DK_PET else "other"
        note = ""
        if name == "Melee":
            note = "Windfury confound (negligible)"
            category = "windfury"
        ability_deltas.append({
            "name": name, "aug_dps": a, "noaug_dps": n,
            "delta": diff, "pct": pct, "category": category, "note": note,
        })
    ability_deltas.sort(key=lambda x: -abs(x["delta"]))

    # Pull size comparison
    aug_ratios = [r for r in (aoe_st_ratio(e) for e in aug_bear_mw) if r is not None]
    noaug_ratios = [r for r in (aoe_st_ratio(e) for e in noaug_bear_rsham) if r is not None]

    pullsize = {
        "aug_mean_ratio": statistics.mean(aug_ratios) if aug_ratios else 0,
        "noaug_mean_ratio": statistics.mean(noaug_ratios) if noaug_ratios else 0,
        "aug_median_ratio": statistics.median(aug_ratios) if aug_ratios else 0,
        "noaug_median_ratio": statistics.median(noaug_ratios) if noaug_ratios else 0,
    }

    # Category totals
    cat_totals = {"aoe": [0, 0], "st": [0, 0], "pet": [0, 0], "other": [0, 0]}
    for d in ability_deltas:
        cat = d["category"] if d["category"] in cat_totals else "other"
        cat_totals[cat][0] += d["aug_dps"]
        cat_totals[cat][1] += d["noaug_dps"]

    # Total DPS (excl melee)
    aug_total = sum(d["aug_dps"] for d in ability_deltas if d["category"] != "windfury")
    noaug_total = sum(d["noaug_dps"] for d in ability_deltas if d["category"] != "windfury")
    melee_aug = sum(d["aug_dps"] for d in ability_deltas if d["category"] == "windfury")
    melee_noaug = sum(d["noaug_dps"] for d in ability_deltas if d["category"] == "windfury")

    totals = {
        "aug_total": aug_total + melee_aug,
        "noaug_total": noaug_total + melee_noaug,
        "aug_excl_melee": aug_total,
        "noaug_excl_melee": noaug_total,
        "delta": aug_total - noaug_total,
        "delta_pct": (aug_total - noaug_total) / noaug_total * 100 if noaug_total else 0,
    }

    # Charts
    charts = {}
    charts["ability_bars"] = _chart_ability_bars(ability_deltas)
    charts["pullsize_hist"] = _chart_pullsize(aug_ratios, noaug_ratios)
    charts["category_bars"] = _chart_categories(cat_totals)

    return {
        "stats": stats,
        "ability_deltas": ability_deltas,
        "pullsize": pullsize,
        "totals": totals,
        "cat_totals": cat_totals,
        "charts": charts,
    }


def _chart_ability_bars(deltas):
    """Horizontal bar chart of biggest ability deltas, colored by category."""
    cat_colors = {
        "aoe": "#e74c3c",
        "st": "#3498db",
        "pet": "#9b59b6",
        "other": "#95a5a6",
        "windfury": "#f39c12",
    }

    # Top 12 by absolute delta
    top = [d for d in deltas if d["category"] != "windfury"][:12]
    top.reverse()

    fig, ax = plt.subplots(figsize=(9, 5.5))
    fig.patch.set_facecolor(STYLE["bg"])
    set_dark_style(ax, "Per-Ability Delta: Aug(Bear+MW) vs NoAug(Bear+RSham)")

    names = [d["name"] for d in top]
    values = [d["delta"] for d in top]
    colors = [cat_colors.get(d["category"], "#999") for d in top]

    y_pos = range(len(names))
    ax.barh(y_pos, values, color=colors, alpha=0.8)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(names, fontsize=9, color=STYLE["text"])
    ax.axvline(0, color=STYLE["grid"], linewidth=0.8)
    ax.set_xlabel("DPS Delta (Aug - NoAug)", color=STYLE["text"])

    for i, (v, d) in enumerate(zip(values, top)):
        label = f"{v:+,.0f} ({d['pct']:+.1f}%)"
        ax.text(v + (50 if v >= 0 else -50), i, label,
                va="center", ha="left" if v >= 0 else "right",
                fontsize=8, color=STYLE["text"])

    # Legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor="#e74c3c", label="AoE (pull-size sensitive)"),
        Patch(facecolor="#3498db", label="ST"),
        Patch(facecolor="#9b59b6", label="Pet"),
        Patch(facecolor="#95a5a6", label="Other"),
    ]
    ax.legend(handles=legend_elements, loc="lower right",
              facecolor=STYLE["card"], edgecolor=STYLE["grid"], labelcolor=STYLE["text"], fontsize=8)

    fig.tight_layout()
    return fig_to_base64(fig)


def _chart_pullsize(aug_ratios, noaug_ratios):
    """Histogram comparing AoE/ST ratio distributions."""
    fig, ax = plt.subplots(figsize=(8, 4))
    fig.patch.set_facecolor(STYLE["bg"])
    set_dark_style(ax, "Pull Size Proxy: AoE/ST Ratio Distribution")

    bins = np.linspace(0, max(max(aug_ratios), max(noaug_ratios)) * 0.9, 25)
    ax.hist(aug_ratios, bins=bins, alpha=0.6, color=STYLE["accent"], label="Aug (Bear+MW)", edgecolor="none")
    ax.hist(noaug_ratios, bins=bins, alpha=0.6, color="#e74c3c", label="NoAug (Bear+RSham)", edgecolor="none")

    ax.axvline(statistics.mean(aug_ratios), color=STYLE["accent"], linestyle="--", linewidth=1.5)
    ax.axvline(statistics.mean(noaug_ratios), color="#e74c3c", linestyle="--", linewidth=1.5)

    ax.set_xlabel("AoE/ST Ratio (higher = bigger pulls)", color=STYLE["text"])
    ax.set_ylabel("Count", color=STYLE["text"])
    ax.legend(facecolor=STYLE["card"], edgecolor=STYLE["grid"], labelcolor=STYLE["text"])
    fig.tight_layout()
    return fig_to_base64(fig)


def _chart_categories(cat_totals):
    """Grouped bar: AoE vs ST vs Pet category totals."""
    cats = ["aoe", "st", "pet"]
    labels = ["AoE", "ST", "Pet"]
    aug_vals = [cat_totals[c][0] for c in cats]
    noaug_vals = [cat_totals[c][1] for c in cats]

    x = np.arange(len(labels))
    width = 0.35

    fig, ax = plt.subplots(figsize=(7, 4))
    fig.patch.set_facecolor(STYLE["bg"])
    set_dark_style(ax, "DPS by Category: Aug vs NoAug (comp-controlled)")

    bars1 = ax.bar(x - width / 2, aug_vals, width, label="Aug (Bear+MW)",
                   color=STYLE["accent"], alpha=0.8)
    bars2 = ax.bar(x + width / 2, noaug_vals, width, label="NoAug (Bear+RSham)",
                   color="#e74c3c", alpha=0.8)

    for bar, val in zip(bars1, aug_vals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 500,
                f"{val:,.0f}", ha="center", fontsize=9, color=STYLE["text"])
    for bar, val in zip(bars2, noaug_vals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 500,
                f"{val:,.0f}", ha="center", fontsize=9, color="#e74c3c")

    # Delta annotations
    for i, (a, n) in enumerate(zip(aug_vals, noaug_vals)):
        pct = (a - n) / n * 100 if n else 0
        ax.text(i, max(a, n) + 3000, f"{pct:+.1f}%", ha="center", fontsize=10,
                color="#00B894" if pct > 0 else "#E17055", fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(labels, color=STYLE["text"])
    ax.set_ylabel("DPS", color=STYLE["text"])
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v / 1000:.0f}k"))
    ax.legend(facecolor=STYLE["card"], edgecolor=STYLE["grid"], labelcolor=STYLE["text"])
    fig.tight_layout()
    return fig_to_base64(fig)


if __name__ == "__main__":
    results = run_comp_controlled_analysis()

    s = results["stats"]
    print(f"Groups:")
    print(f"  Aug + Bear + MW:           {s['aug_bear_mw']} runs")
    print(f"  Aug + Bear + RSham:        {s['aug_bear_rsham']} runs")
    print(f"  NoAug + Bear + RSham (meta DPS): {s['noaug_bear_rsham_meta']} runs")
    print(f"  NoAug + Bear + RSham (all):      {s['noaug_bear_rsham_all']} runs")

    t = results["totals"]
    print(f"\nTotal DPS: Aug={t['aug_total']:,.0f}  NoAug={t['noaug_total']:,.0f}  "
          f"Delta={t['delta']:+,.0f} ({t['delta_pct']:+.1f}%)")
    print(f"  (excl melee: Aug={t['aug_excl_melee']:,.0f}  NoAug={t['noaug_excl_melee']:,.0f})")

    p = results["pullsize"]
    print(f"\nPull size (AoE/ST ratio):")
    print(f"  Aug mean: {p['aug_mean_ratio']:.2f}  NoAug mean: {p['noaug_mean_ratio']:.2f}  "
          f"Delta: {p['aug_mean_ratio'] - p['noaug_mean_ratio']:+.2f}")

    print(f"\nTop ability deltas (excl melee):")
    print(f"  {'Ability':<25} {'Cat':<6} {'Aug':>8} {'NoAug':>8} {'Delta':>8} {'%':>7}")
    print("  " + "-" * 68)
    for d in results["ability_deltas"][:15]:
        if d["category"] == "windfury":
            continue
        print(f"  {d['name']:<25} {d['category']:<6} {d['aug_dps']:>8,.0f} {d['noaug_dps']:>8,.0f} "
              f"{d['delta']:>+8,.0f} {d['pct']:>+6.1f}%")

    # Windfury note
    melee = next((d for d in results["ability_deltas"] if d["name"] == "Melee"), None)
    if melee:
        print(f"\n  Melee: Aug={melee['aug_dps']:,.0f} NoAug={melee['noaug_dps']:,.0f} "
              f"Delta={melee['delta']:+,.0f} ({melee['pct']:+.1f}%)")
        print(f"  Note: NoAug groups always have RSham (Windfury). Melee is <1% of total DPS — negligible.")

    print(f"\nCategory summary:")
    for cat, (a, n) in results["cat_totals"].items():
        if a + n < 100:
            continue
        pct = (a - n) / n * 100 if n else 0
        print(f"  {cat:<8}: Aug={a:>8,.0f}  NoAug={n:>8,.0f}  Delta={a-n:>+8,.0f} ({pct:+.1f}%)")
