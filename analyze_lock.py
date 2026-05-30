"""
Analyze Demo Lock rankings to quantify Aug Evoker damage misattribution.

Demo Lock damage is ~80% pet/demon damage, so misattribution from
Ebon Might/Prescience on pets is the primary concern.
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

LOCK_BUFF_MULTIPLIERS = {
    "mark_of_the_wild": 1.03,
    "mystic_touch": 1.0285,
    "chaos_brand": 1.013,
    "battle_shout": 1.05,
    "skyfury": 1.03,
}

PLAYER_ABILITIES = {
    "Hand of Gul'dan", "Shadow Bolt", "Demonbolt", "Implosion",
    "Shadowfury", "Drain Life", "Melee",
}

PET_ABILITIES = {
    "Diabolic Ritual", "Dominion of Argus", "Summon Demonic Tyrant",
    "Call Dreadstalkers", "Wild Imp (Inner Demons/To Hell and Back)",
    "Wild Imp (Hand of Gul'dan)", "Summon Charhound",
    "Grimoire: Imp Lord", "Grimoire: Fel Ravager", "Wild Imp",
}

PET_SUBCATS = {
    "Demonic Tyrant": {"Summon Demonic Tyrant"},
    "Call Dreadstalkers": {"Call Dreadstalkers"},
    "Wild Imp (HoG)": {"Wild Imp (Hand of Gul'dan)"},
    "Wild Imp (ID/THB)": {"Wild Imp (Inner Demons/To Hell and Back)"},
    "Diabolic Ritual": {"Diabolic Ritual"},
    "Dominion of Argus": {"Dominion of Argus"},
    "Charhound": {"Summon Charhound"},
    "Grimoire Demons": {"Grimoire: Imp Lord", "Grimoire: Fel Ravager"},
}

KNOWN_FELGUARD_ABILITIES = {"Legion Strike", "Felstorm", "Pursuit", "Axe Toss"}

SUBCAT_ORDER = list(PET_SUBCATS.keys()) + ["Felguard (Main Pet)"]

KNOWN_NON_PET = PLAYER_ABILITIES | {
    "Twilight Barrage", "Eternal Voidsong Chain", "Bombardments",
    "Cloven Soul", "Blight of Tongues", "Curse of Tongues",
    "Curse of Exhaustion", "Howl of Terror", "Banish", "Fear",
    "Breath of Eons", "Fate Mirror", "Temporal Wound",
    "Inferno's Blessing", "Ruination", "Singe Magic",
    "Dominion of Argus: Antoran Jailer",
    "Dominion of Argus: Antoran Inquisitor",
    "Dominion of Argus: Grand Warlock Alythess",
    "Dominion of Argus: Lady Sacrolash",
    "Curse of Weakness", "War Stomp", "Doom",
    "Wicked Reaping", "Soul Anathema", "Devouring Bolt",
    "Summon Gloomhound", "Summon Doomguard",
    "Manifested Demonic Soul",
}


def load_lock_rankings():
    path = os.path.join("data", "lock_rankings.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    df = pd.DataFrame(data)
    return df


def normalize_lock_dps(df):
    df = df.copy()
    df["buff_multiplier"] = df["buffs"].apply(compute_buff_multiplier)
    df["normalized_dps"] = df["dps"] / df["buff_multiplier"]
    return df


def compute_lock_stats(df):
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


def chart_lock_distributions(df):
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

    fig.suptitle("Demo Lock DPS Distributions: Aug vs No-Aug",
                 color=STYLE["accent"], fontsize=15, fontweight="bold", y=1.02)
    fig.tight_layout()
    return fig_to_base64(fig)


def chart_lock_per_dungeon(df):
    dungeons = sorted(df["dungeon"].unique())
    deltas, pcts, ns_aug, ns_noaug = [], [], [], []

    for d in dungeons:
        sub = df[df["dungeon"] == d]
        a = sub[sub["has_aug"]]["normalized_dps"]
        n = sub[~sub["has_aug"]]["normalized_dps"]
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
    avg_delta = sum(deltas) / len(deltas)
    ax.axhline(avg_delta, color=STYLE["accent"], linewidth=1.5, linestyle="--", alpha=0.8)
    ax.text(len(dungeons) - 0.5, avg_delta + 200,
            f"avg: {avg_delta:+,.0f}", color=STYLE["accent"], fontsize=10, ha="right")
    ax.set_ylabel("DPS Delta", color=STYLE["text"], fontsize=11)
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{x:+,.0f}"))
    plt.xticks(rotation=30, ha="right")
    fig.tight_layout()
    return fig_to_base64(fig)


def chart_lock_key_level(df):
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


def classify_ability(name):
    if name in PLAYER_ABILITIES:
        return "player"
    if name in PET_ABILITIES:
        return "pet"
    if name in KNOWN_NON_PET:
        return "other"
    if any(ord(c) > 127 for c in name):
        return None
    return "pet"


def load_lock_breakdowns():
    path = os.path.join("data", "lock_breakdowns.json")
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

    # Categorize abilities per entry
    for idx, row in bdf.iterrows():
        pet_dmg = 0
        player_dmg = 0
        for a in row["abilities"]:
            cat = classify_ability(a["name"])
            if cat == "pet":
                pet_dmg += a["total"]
            elif cat == "player":
                player_dmg += a["total"]
        total = pet_dmg + player_dmg
        bdf.at[idx, "pet_damage"] = pet_dmg
        bdf.at[idx, "player_damage"] = player_dmg
        bdf.at[idx, "pet_pct"] = pet_dmg / total * 100 if total > 0 else 0
        bdf.at[idx, "player_pct"] = player_dmg / total * 100 if total > 0 else 0

    aug = bdf[bdf["has_aug"]]
    noaug = bdf[~bdf["has_aug"]]
    aug_dur = aug["total_damage"] / aug["dps"]
    noaug_dur = noaug["total_damage"] / noaug["dps"]

    cat_stats = {}
    for cat, dmg_col, pct_col in [("pet", "pet_damage", "pet_pct"),
                                    ("player", "player_damage", "player_pct")]:
        aug_dps = (aug[dmg_col] / aug["buff_multiplier"] / aug_dur).mean()
        noaug_dps = (noaug[dmg_col] / noaug["buff_multiplier"] / noaug_dur).mean()
        delta = aug_dps - noaug_dps
        pct = delta / noaug_dps * 100 if noaug_dps else 0
        cat_stats[cat] = {
            "aug_dps": aug_dps, "noaug_dps": noaug_dps,
            "delta": delta, "pct": pct,
            "aug_pct": aug[pct_col].mean(),
            "noaug_pct": noaug[pct_col].mean(),
        }

    # Per-ability DPS comparison
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
        if name in ("Unknown",):
            continue
        aug_dps, aug_n = aug_ab.get(name, (0, 0))
        noaug_dps, noaug_n = noaug_ab.get(name, (0, 0))
        if aug_n + noaug_n < 20:
            continue
        delta = aug_dps - noaug_dps
        cat = classify_ability(name) or "other"
        pct = delta / noaug_dps * 100 if noaug_dps > 0 else (999 if aug_dps > 0 else 0)
        if aug_dps + noaug_dps > 100:
            ability_rows.append({"name": name, "cat": cat, "aug": aug_dps,
                                 "noaug": noaug_dps, "delta": delta, "pct": pct,
                                 "aug_n": aug_n, "noaug_n": noaug_n})
    ability_rows.sort(key=lambda x: -abs(x["delta"]))

    # Pet sub-category breakdown
    pet_subcat_stats = {}
    for label, subset in [("aug", aug), ("noaug", noaug)]:
        subs = defaultdict(float)
        for _, row in subset.iterrows():
            dur = row["total_damage"] / row["dps"]
            bm = compute_buff_multiplier(row["buffs"])
            for a in row["abilities"]:
                dps = a["total"] / bm / dur
                matched = False
                for subcat, names in PET_SUBCATS.items():
                    if a["name"] in names:
                        subs[subcat] += dps
                        matched = True
                        break
                if not matched:
                    if a["name"] in KNOWN_FELGUARD_ABILITIES:
                        subs["Felguard (Main Pet)"] += dps
                    elif a["name"] not in PLAYER_ABILITIES and a["name"] not in KNOWN_NON_PET:
                        if any(ord(c) > 127 for c in a["name"]):
                            subs["Felguard (Main Pet)"] += dps
                        elif a["name"] not in PET_ABILITIES and a["total"] > 100000:
                            subs["Felguard (Main Pet)"] += dps
        n = len(subset)
        pet_subcat_stats[label] = {k: subs[k] / n for k in SUBCAT_ORDER}

    # Charts
    cats = ["Pet (Demons)", "Player (Direct)"]
    aug_pcts = [cat_stats["pet"]["aug_pct"], cat_stats["player"]["aug_pct"]]
    noaug_pcts = [cat_stats["pet"]["noaug_pct"], cat_stats["player"]["noaug_pct"]]
    aug_dps_vals = [cat_stats["pet"]["aug_dps"], cat_stats["player"]["aug_dps"]]
    noaug_dps_vals = [cat_stats["pet"]["noaug_dps"], cat_stats["player"]["noaug_dps"]]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.patch.set_facecolor(STYLE["bg"])
    w = 0.35
    x = range(2)

    ax = axes[0]
    set_dark_style(ax, "Damage Category Proportions (% of total)")
    ax.bar([i - w/2 for i in x], aug_pcts, w, color=STYLE["aug"], alpha=0.85, label="Aug")
    ax.bar([i + w/2 for i in x], noaug_pcts, w, color=STYLE["noaug"], alpha=0.85, label="No Aug")
    ax.set_xticks(list(x))
    ax.set_xticklabels(cats)
    ax.set_ylabel("% of total damage", color=STYLE["text"])
    for i, (a, n) in enumerate(zip(aug_pcts, noaug_pcts)):
        ax.text(i - w/2, a + 0.5, f"{a:.1f}%", ha="center", color=STYLE["text"], fontsize=9)
        ax.text(i + w/2, n + 0.5, f"{n:.1f}%", ha="center", color=STYLE["text"], fontsize=9)
    ax.legend(fontsize=10, facecolor=STYLE["card"], edgecolor=STYLE["grid"], labelcolor=STYLE["text"])

    ax = axes[1]
    set_dark_style(ax, "Normalized DPS by Category")
    ax.bar([i - w/2 for i in x], aug_dps_vals, w, color=STYLE["aug"], alpha=0.85, label="Aug")
    ax.bar([i + w/2 for i in x], noaug_dps_vals, w, color=STYLE["noaug"], alpha=0.85, label="No Aug")
    ax.set_xticks(list(x))
    ax.set_xticklabels(cats)
    ax.set_ylabel("Normalized DPS", color=STYLE["text"])
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v/1000:.0f}k"))
    for i, (a, n) in enumerate(zip(aug_dps_vals, noaug_dps_vals)):
        delta = a - n
        ax.text(i, max(a, n) + 1000, f"Δ={delta:+,.0f}", ha="center",
                color=STYLE["accent"], fontsize=9, fontweight="bold")
    ax.legend(fontsize=10, facecolor=STYLE["card"], edgecolor=STYLE["grid"], labelcolor=STYLE["text"])
    fig.tight_layout()
    cat_chart = fig_to_base64(fig)

    # Per-ability chart
    filtered = [r for r in ability_rows if abs(r["pct"]) < 500][:18]
    fig, ax = plt.subplots(figsize=(14, max(6, len(filtered) * 0.4)))
    fig.patch.set_facecolor(STYLE["bg"])
    set_dark_style(ax, "Per-Ability Normalized DPS Delta (Aug - No-Aug)")
    cat_colors = {"pet": "#e74c3c", "player": "#3498db", "other": "#aaa"}
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
    ax.legend(handles=[Patch(color="#e74c3c", label="Pet/Demon"),
                       Patch(color="#3498db", label="Player/Direct")],
              fontsize=10, facecolor=STYLE["card"], edgecolor=STYLE["grid"],
              labelcolor=STYLE["text"], loc="lower right")
    fig.tight_layout()
    ability_chart = fig_to_base64(fig)

    # Pet sub-category chart
    subcat_names = SUBCAT_ORDER
    aug_sub_vals = [pet_subcat_stats["aug"].get(s, 0) for s in subcat_names]
    noaug_sub_vals = [pet_subcat_stats["noaug"].get(s, 0) for s in subcat_names]

    fig, ax = plt.subplots(figsize=(14, 6))
    fig.patch.set_facecolor(STYLE["bg"])
    set_dark_style(ax, "Pet Sub-Category Normalized DPS")
    xi = range(len(subcat_names))
    ax.bar([i - w/2 for i in xi], aug_sub_vals, w, color=STYLE["aug"], alpha=0.85, label="Aug")
    ax.bar([i + w/2 for i in xi], noaug_sub_vals, w, color=STYLE["noaug"], alpha=0.85, label="No Aug")
    ax.set_xticks(list(xi))
    ax.set_xticklabels(subcat_names, fontsize=8, rotation=25, ha="right")
    ax.set_ylabel("Normalized DPS", color=STYLE["text"])
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v/1000:.0f}k"))
    for i, (a, n) in enumerate(zip(aug_sub_vals, noaug_sub_vals)):
        if n > 0:
            delta = a - n
            pct = delta / n * 100
            ax.text(i, max(a, n) + 200, f"{pct:+.1f}%", ha="center",
                    color=STYLE["accent"], fontsize=8, fontweight="bold")
    ax.legend(fontsize=10, facecolor=STYLE["card"], edgecolor=STYLE["grid"], labelcolor=STYLE["text"])
    fig.tight_layout()
    subcat_chart = fig_to_base64(fig)

    # Uncapped vs Capped AoE analysis
    UNCAPPED_AOE = ["Summon Demonic Tyrant", "Diabolic Ritual", "Dominion of Argus", "Hand of Gul'dan"]
    CAPPED_CLEAVE = ["Wild Imp (Hand of Gul'dan)", "Wild Imp (Inner Demons/To Hell and Back)",
                     "Call Dreadstalkers", "Implosion", "Summon Charhound"]
    ST_FILLER = ["Shadow Bolt", "Demonbolt"]

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

    # Totals per category
    for cat, abilities in [("uncapped", UNCAPPED_AOE), ("capped", CAPPED_CLEAVE), ("st", ST_FILLER)]:
        for label in ["aug", "noaug"]:
            aoe_analysis[cat]["_total_" + label] = sum(
                aoe_analysis[cat][ab][label] for ab in abilities)

    # Wild Imp deep dive
    import statistics as stats_mod
    imp_analysis = {}
    for label, subset_list in [("aug", [row for _, row in aug.iterrows()]),
                                ("noaug", [row for _, row in noaug.iterrows()])]:
        imp_dps = [get_dps_from_row(r, "Wild Imp (Hand of Gul'dan)") +
                   get_dps_from_row(r, "Wild Imp (Inner Demons/To Hell and Back)") for r in subset_list]
        implosion_dps = [get_dps_from_row(r, "Implosion") for r in subset_list]
        norm_dps = [r["dps"] / compute_buff_multiplier(r["buffs"]) for r in subset_list]
        imp_pct = [i / t * 100 for i, t in zip(imp_dps, norm_dps) if t > 0]
        imp_implosion_ratio = [imp / wimp if wimp > 0 else 0
                               for imp, wimp in zip(implosion_dps, imp_dps)]
        imp_analysis[label] = {
            "imp_dps": stats_mod.mean(imp_dps),
            "implosion_dps": stats_mod.mean(implosion_dps),
            "imp_pct": stats_mod.mean(imp_pct),
            "implosion_imp_ratio": stats_mod.mean(imp_implosion_ratio),
            "imp_plus_implosion": stats_mod.mean(imp_dps) + stats_mod.mean(implosion_dps),
        }

    # Imp by dungeon
    imp_by_dungeon = []
    for dg in sorted(bdf["dungeon"].unique()):
        aug_d = [row for _, row in aug[aug["dungeon"] == dg].iterrows()]
        noaug_d = [row for _, row in noaug[noaug["dungeon"] == dg].iterrows()]
        if not aug_d or not noaug_d:
            continue
        aug_imp = [get_dps_from_row(r, "Wild Imp (Hand of Gul'dan)") +
                   get_dps_from_row(r, "Wild Imp (Inner Demons/To Hell and Back)") for r in aug_d]
        noaug_imp = [get_dps_from_row(r, "Wild Imp (Hand of Gul'dan)") +
                     get_dps_from_row(r, "Wild Imp (Inner Demons/To Hell and Back)") for r in noaug_d]
        a_avg = sum(aug_imp) / len(aug_imp)
        n_avg = sum(noaug_imp) / len(noaug_imp)
        delta = a_avg - n_avg
        pct = delta / n_avg * 100 if n_avg > 0 else 0
        imp_by_dungeon.append({
            "dungeon": dg, "aug": a_avg, "noaug": n_avg,
            "delta": delta, "pct": pct,
            "n_aug": len(aug_d), "n_noaug": len(noaug_d),
        })

    # Uncapped vs Capped chart
    uncapped_labels = ["Tyrant\n(Burning Cleave)", "Diabolic\nRitual", "Dominion\nof Argus", "Hand of\nGul'dan"]
    capped_labels = ["Wild Imp\n(HoG)", "Wild Imp\n(ID/THB)", "Dreadstalkers", "Implosion", "Charhound"]

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
    ax.set_xticklabels(uncapped_labels, fontsize=8)
    ax.set_ylabel("Normalized DPS", color=STYLE["text"])
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v/1000:.0f}k"))
    for i, (a, n) in enumerate(zip(aug_vals, noaug_vals)):
        delta = a - n
        pct = delta / n * 100 if n > 0 else 0
        ax.text(i, max(a, n) + 400, f"{pct:+.1f}%", ha="center",
                color=STYLE["accent"], fontsize=9, fontweight="bold")
    ax.legend(fontsize=9, facecolor=STYLE["card"], edgecolor=STYLE["grid"], labelcolor=STYLE["text"])

    ax = axes[1]
    set_dark_style(ax, "Capped/Cleave AoE Sources")
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
        "cat_stats": cat_stats, "ability_rows": filtered,
        "n_aug": len(aug), "n_noaug": len(noaug),
        "pet_subcats": pet_subcat_stats,
        "aoe_analysis": aoe_analysis,
        "imp_analysis": imp_analysis,
        "imp_by_dungeon": imp_by_dungeon,
        "uncapped_abilities": UNCAPPED_AOE,
        "capped_abilities": CAPPED_CLEAVE,
        "st_abilities": ST_FILLER,
    }
    breakdown_charts = {
        "lock_category": cat_chart,
        "lock_abilities": ability_chart,
        "lock_subcats": subcat_chart,
        "lock_aoe": aoe_chart,
    }
    return breakdown_data, breakdown_charts
