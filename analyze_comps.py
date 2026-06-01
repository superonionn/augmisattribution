"""Analyze Aug damage by party composition (which DPS classes are present)."""
import json
import os
import base64
import statistics
from io import BytesIO
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

from analyze import STYLE, fig_to_base64, set_dark_style

TANK_HEAL_SPECS = {
    "Guardian", "Protection", "Blood", "Brewmaster", "Vengeance",
    "Mistweaver", "Holy", "Restoration", "Discipline", "Preservation",
    "Augmentation",
}

DPS_CLASS_LABELS = {
    "DeathKnight": "DK",
    "DemonHunter": "DH",
    "Warlock": "Lock",
    "Mage": "Mage",
    "Rogue": "Rogue",
    "Hunter": "Hunter",
    "Monk": "Monk",
    "Warrior": "Warrior",
    "Paladin": "Paladin",
    "Druid": "Druid",
    "Priest": "Priest",
    "Shaman": "Shaman",
    "Evoker": "Evoker",
}

COMP_COLORS = {
    "DH+DK": "#e74c3c",
    "DK+Lock": "#3498db",
    "DH+Lock": "#2ecc71",
}

REATTRIB_ABILITIES = {
    "Ebon Might", "Shifting Sands", "Prescience", "Bombardments",
    "Breath of Eons", "Fate Mirror", "Inferno's Blessing",
}

NOISE_ABILITIES = {
    "Shadow of the Empyrean Requiem", "Echo of the Evercurse (Soulcatcher's Charm)",
    "Wraps of Cosmic Madness", "Beacon of Lightblind Wrath",
    "Twilight Barrage", "Prismatic Focusing Iris", "Devouring Bolt",
    "Eternal Voidsong Chain", "Chi Wave", "Sleep Walk", "Chrono Flames",
    "Disintegrate", "Landslide", "Blistering Scales",
}


def get_dps_in_comp(comp):
    """Return sorted list of DPS class short names from a comp list."""
    dps = []
    for p in comp:
        if p.get("spec") in TANK_HEAL_SPECS:
            continue
        label = DPS_CLASS_LABELS.get(p.get("class", ""), p.get("class", "?"))
        dps.append(label)
    return sorted(dps)


def load_aug_comp_data():
    """Load all Aug perspective data and classify by comp."""
    all_entries = []
    for fname in ["aug_with_dk.json", "aug_with_lock.json", "aug_with_dh.json"]:
        path = os.path.join("data", fname)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            all_entries.extend(json.load(f))

    seen = set()
    unique = []
    for e in all_entries:
        key = (e["report_code"], e["fight_id"])
        if key not in seen:
            seen.add(key)
            unique.append(e)

    return unique


def classify_comps(entries):
    """Classify entries into comp buckets like 'DK+DH', 'DK+Lock', etc."""
    comps = {}
    for e in entries:
        dps = get_dps_in_comp(e.get("comp", []))
        comp_key = "+".join(dps) if dps else "Unknown"
        if comp_key not in comps:
            comps[comp_key] = []
        comps[comp_key].append(e)
    return comps


def compute_comp_stats(entries):
    """Compute Aug DPS statistics for a group of entries."""
    if not entries:
        return None
    dps_vals = [e["aug_dps"] for e in entries]
    n = len(dps_vals)
    mean = statistics.mean(dps_vals)
    median = statistics.median(dps_vals)
    return {
        "count": n,
        "mean_dps": mean,
        "median_dps": median,
        "min_dps": min(dps_vals),
        "max_dps": max(dps_vals),
        "stdev": statistics.stdev(dps_vals) if n > 1 else 0,
        "mean_key": statistics.mean([e["key_level"] for e in entries]),
    }


def get_main_comps(comps, min_count=20):
    """Return the three meta comps if they have enough data."""
    main = {}
    for key in ["DH+DK", "DK+Lock", "DH+Lock"]:
        if key in comps and len(comps[key]) >= min_count:
            main[key] = comps[key]
    return main


def chart_comp_dps_bars(main_comps):
    """Bar chart comparing Aug mean/median DPS across comps."""
    comp_order = [k for k in ["DH+DK", "DK+Lock", "DH+Lock"] if k in main_comps]
    if not comp_order:
        return ""

    stats_list = [compute_comp_stats(main_comps[k]) for k in comp_order]
    labels = [f"Aug + {k}" for k in comp_order]
    means = [s["mean_dps"] for s in stats_list]
    medians = [s["median_dps"] for s in stats_list]
    colors = [COMP_COLORS.get(k, "#999") for k in comp_order]

    x = np.arange(len(labels))
    width = 0.35

    fig, ax = plt.subplots(figsize=(8, 4.5))
    fig.patch.set_facecolor(STYLE["bg"])
    set_dark_style(ax, "Aug Credited DPS by Party Comp")

    bars1 = ax.bar(x - width / 2, means, width, label="Mean", color=colors, alpha=0.85)
    bars2 = ax.bar(x + width / 2, medians, width, label="Median", color=colors, alpha=0.45)

    for bar, val in zip(bars1, means):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1500,
                f"{val:,.0f}", ha="center", va="bottom", color=STYLE["text"], fontsize=10, fontweight="bold")
    for bar, val in zip(bars2, medians):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1500,
                f"{val:,.0f}", ha="center", va="bottom", color="#aaa", fontsize=9)

    for i, s in enumerate(stats_list):
        ax.text(i, 0, f"n={s['count']}", ha="center", va="top",
                color="#888", fontsize=9, transform=ax.get_xaxis_transform())

    ax.set_xticks(x)
    ax.set_xticklabels(labels, color=STYLE["text"])
    ax.set_ylabel("Aug DPS", color=STYLE["text"])
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_ylim(0, max(means) * 1.18)
    ax.legend(facecolor=STYLE["card"], edgecolor=STYLE["grid"], labelcolor=STYLE["text"])
    fig.tight_layout()

    return fig_to_base64(fig)


def chart_comp_distributions(main_comps):
    """Overlapping histograms of Aug DPS by comp."""
    comp_order = [k for k in ["DH+DK", "DK+Lock", "DH+Lock"] if k in main_comps]
    if not comp_order:
        return ""

    fig, ax = plt.subplots(figsize=(8, 4.5))
    fig.patch.set_facecolor(STYLE["bg"])
    set_dark_style(ax, "Aug DPS Distribution by Party Comp")

    for k in comp_order:
        dps_vals = [e["aug_dps"] for e in main_comps[k]]
        ax.hist(dps_vals, bins=30, alpha=0.5, label=f"Aug + {k}",
                color=COMP_COLORS.get(k, "#999"), edgecolor="none")

    ax.set_xlabel("Aug DPS", color=STYLE["text"])
    ax.set_ylabel("Count", color=STYLE["text"])
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v / 1000:.0f}k"))
    ax.legend(facecolor=STYLE["card"], edgecolor=STYLE["grid"], labelcolor=STYLE["text"])
    fig.tight_layout()

    return fig_to_base64(fig)


def chart_comp_ability_breakdown(main_comps):
    """Grouped bar showing reattrib vs own DPS by comp."""
    comp_order = [k for k in ["DH+DK", "DK+Lock", "DH+Lock"] if k in main_comps]
    if not comp_order:
        return ""

    reattrib_vals = []
    own_vals = []
    for k in comp_order:
        r_dps = []
        o_dps = []
        for row in main_comps[k]:
            dur = row.get("duration_s", 0)
            if dur <= 0:
                continue
            r = sum(a["total"] / dur for a in row.get("abilities", [])
                    if a["name"] in REATTRIB_ABILITIES)
            o = sum(a["total"] / dur for a in row.get("abilities", [])
                    if a["name"] not in REATTRIB_ABILITIES and a["name"] not in NOISE_ABILITIES)
            r_dps.append(r)
            o_dps.append(o)
        reattrib_vals.append(statistics.mean(r_dps) if r_dps else 0)
        own_vals.append(statistics.mean(o_dps) if o_dps else 0)

    labels = [f"Aug + {k}" for k in comp_order]
    x = np.arange(len(labels))
    width = 0.35

    fig, ax = plt.subplots(figsize=(8, 4.5))
    fig.patch.set_facecolor(STYLE["bg"])
    set_dark_style(ax, "Reattributed vs Own Damage by Comp")

    bars1 = ax.bar(x - width / 2, reattrib_vals, width, label="Reattributed",
                   color="#e74c3c", alpha=0.8)
    bars2 = ax.bar(x + width / 2, own_vals, width, label="Own Damage",
                   color="#3498db", alpha=0.8)

    for bar, val in zip(bars1, reattrib_vals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1000,
                f"{val:,.0f}", ha="center", va="bottom", color="#e74c3c", fontsize=9)
    for bar, val in zip(bars2, own_vals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1000,
                f"{val:,.0f}", ha="center", va="bottom", color="#3498db", fontsize=9)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, color=STYLE["text"])
    ax.set_ylabel("DPS", color=STYLE["text"])
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.legend(facecolor=STYLE["card"], edgecolor=STYLE["grid"], labelcolor=STYLE["text"])
    fig.tight_layout()

    return fig_to_base64(fig)


def chart_comp_keylevel(main_comps):
    """Line chart: Aug DPS by key level for each comp."""
    comp_order = [k for k in ["DH+DK", "DK+Lock", "DH+Lock"] if k in main_comps]
    if not comp_order:
        return ""

    fig, ax = plt.subplots(figsize=(8, 4.5))
    fig.patch.set_facecolor(STYLE["bg"])
    set_dark_style(ax, "Aug DPS by Key Level & Party Comp")

    for k in comp_order:
        by_key = defaultdict(list)
        for e in main_comps[k]:
            by_key[e["key_level"]].append(e["aug_dps"])
        keys_sorted = sorted(by_key.keys())
        means = [statistics.mean(by_key[kl]) for kl in keys_sorted]
        counts = [len(by_key[kl]) for kl in keys_sorted]
        ax.plot(keys_sorted, means, "o-", label=f"Aug + {k}",
                color=COMP_COLORS.get(k, "#999"), linewidth=2, markersize=6)
        for kl, m, c in zip(keys_sorted, means, counts):
            if c >= 5:
                ax.annotate(f"n={c}", (kl, m), textcoords="offset points",
                            xytext=(0, 10), ha="center", fontsize=7, color="#888")

    ax.set_xlabel("Key Level", color=STYLE["text"])
    ax.set_ylabel("Aug DPS", color=STYLE["text"])
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v / 1000:.0f}k"))
    ax.legend(facecolor=STYLE["card"], edgecolor=STYLE["grid"], labelcolor=STYLE["text"])
    fig.tight_layout()

    return fig_to_base64(fig)


def compute_reattrib_by_comp(main_comps):
    """Compute reattributed vs own DPS for each comp."""
    results = {}
    for comp_key in ["DH+DK", "DK+Lock", "DH+Lock"]:
        if comp_key not in main_comps:
            continue
        entries = main_comps[comp_key]
        reattrib_dps_vals = []
        own_dps_vals = []
        for row in entries:
            dur = row.get("duration_s", 0)
            if dur <= 0:
                continue
            r_total = sum(a["total"] / dur for a in row.get("abilities", [])
                         if a["name"] in REATTRIB_ABILITIES)
            o_total = sum(a["total"] / dur for a in row.get("abilities", [])
                         if a["name"] not in REATTRIB_ABILITIES and a["name"] not in NOISE_ABILITIES)
            reattrib_dps_vals.append(r_total)
            own_dps_vals.append(o_total)
        r_mean = statistics.mean(reattrib_dps_vals) if reattrib_dps_vals else 0
        o_mean = statistics.mean(own_dps_vals) if own_dps_vals else 0
        total = r_mean + o_mean
        results[comp_key] = {
            "reattrib_mean": r_mean,
            "own_mean": o_mean,
            "reattrib_pct": r_mean / total * 100 if total else 0,
        }
    return results


def load_comp_analysis():
    """Main entry point: load data, compute stats, generate charts."""
    entries = load_aug_comp_data()
    if not entries:
        return None

    comps = classify_comps(entries)
    main = get_main_comps(comps, min_count=15)
    if not main:
        return None

    stats = {}
    for comp_key, ents in main.items():
        stats[comp_key] = compute_comp_stats(ents)

    charts = {}
    charts["comp_bars"] = chart_comp_dps_bars(main)
    charts["comp_dist"] = chart_comp_distributions(main)
    charts["comp_abilities"] = chart_comp_ability_breakdown(main)
    charts["comp_keylevel"] = chart_comp_keylevel(main)

    reattrib = compute_reattrib_by_comp(main)

    return {
        "stats": stats,
        "charts": charts,
        "reattrib": reattrib,
        "total_entries": len(entries),
    }


if __name__ == "__main__":
    entries = load_aug_comp_data()
    print(f"Total Aug entries: {len(entries)}")
    comps = classify_comps(entries)
    print(f"\nComp distribution (top 15):")
    for comp, ents in sorted(comps.items(), key=lambda x: -len(x[1]))[:15]:
        stats = compute_comp_stats(ents)
        print(f"  {comp}: {stats['count']} entries, "
              f"mean={stats['mean_dps']:,.0f}, median={stats['median_dps']:,.0f}, "
              f"avg key={stats['mean_key']:.1f}")
