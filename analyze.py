"""
Analyze Unholy DK rankings to quantify Aug Evoker damage misattribution.

Approach:
1. Load rankings with comp/buff data
2. Group by aug/no-aug
3. Normalize for raid buff differences between groups
4. The residual DPS difference = estimated misattributed aug damage

Generates an HTML report with charts at results/report.html.
"""

import json
import os
import sys
import base64
from io import BytesIO

sys.stdout.reconfigure(encoding="utf-8")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import pandas as pd


# ─────────────────────── Buff multipliers ───────────────────────────────────
#
# Unholy DK damage split (approximate):
#   ~55-60% physical (Scourge Strike phys, Festering Strike, auto, pet melee, Army)
#   ~40-45% shadow/magic (Death Coil, Scourge Strike shadow, diseases, wounds)
#
# Meta (aug) comp typically brings: MotW + Mystic Touch + Chaos Brand
# Phys (no-aug) comp typically brings: Battle Shout + Skyfury (± Mystic Touch)

BUFF_MULTIPLIERS = {
    # Mark of the Wild (Druid): ~3% total damage
    "mark_of_the_wild": 1.03,

    # Mystic Touch (Monk): 5% physical damage taken by enemies.
    # Affects ~57% of DK damage → 0.57 * 0.05 = 2.85% total.
    "mystic_touch": 1.0285,

    # Chaos Brand (DH): 3% magic damage taken by enemies.
    # Affects ~43% of DK damage → 0.43 * 0.03 = 1.29% total.
    "chaos_brand": 1.013,

    # Battle Shout (Warrior): 5% AP → all damage for a melee.
    "battle_shout": 1.05,

    # Skyfury (Shaman): includes mastery + windfury on autos (Sudden Doom procs).
    # Simmed at ~3% DPS for Unholy DK single target.
    "skyfury": 1.03,
}

STYLE = {
    "aug": "#6C5CE7",
    "noaug": "#E17055",
    "bg": "#1a1a2e",
    "card": "#16213e",
    "text": "#e0e0e0",
    "accent": "#00cec9",
    "grid": "#2d3436",
}


# ─────────────────────── Data loading ───────────────────────────────────────

def load_rankings() -> pd.DataFrame:
    path = os.path.join("data", "rankings.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    df = pd.DataFrame(data)
    print(f"Loaded {len(df)} rankings from {df['dungeon'].nunique()} dungeons")
    return df


def compute_buff_multiplier(buffs: dict) -> float:
    multiplier = 1.0
    for buff_name, is_present in buffs.items():
        if is_present and buff_name in BUFF_MULTIPLIERS:
            multiplier *= BUFF_MULTIPLIERS[buff_name]
    return multiplier


def normalize_dps(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["buff_multiplier"] = df["buffs"].apply(compute_buff_multiplier)
    df["normalized_dps"] = df["dps"] / df["buff_multiplier"]
    return df


# ─────────────────────── Chart generation ───────────────────────────────────

def fig_to_base64(fig) -> str:
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                facecolor=STYLE["bg"], edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


def set_dark_style(ax, title=""):
    ax.set_facecolor(STYLE["card"])
    ax.set_title(title, color=STYLE["text"], fontsize=13, fontweight="bold", pad=12)
    ax.tick_params(colors=STYLE["text"], labelsize=9)
    for spine in ax.spines.values():
        spine.set_color(STYLE["grid"])
    ax.grid(axis="y", color=STYLE["grid"], alpha=0.5, linewidth=0.5)


def chart_dps_distributions(df):
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
        if col == "normalized_dps" and title.startswith("Normalized DPS"):
            bins = range(
                int(min(aug[col].min(), noaug[col].min()) // 5000 * 5000),
                int(max(aug[col].max(), noaug[col].max()) // 5000 * 5000) + 10000,
                5000,
            )
            ax.hist(aug[col], bins=bins, alpha=0.6, color=STYLE["aug"],
                    label=f"Aug (n={len(aug)})", density=True)
            ax.hist(noaug[col], bins=bins, alpha=0.6, color=STYLE["noaug"],
                    label=f"No Aug (n={len(noaug)})", density=True)
            ax.legend(fontsize=9, facecolor=STYLE["card"], edgecolor=STYLE["grid"],
                      labelcolor=STYLE["text"])
        else:
            bins = range(
                int(min(aug[col].min(), noaug[col].min()) // 5000 * 5000),
                int(max(aug[col].max(), noaug[col].max()) // 5000 * 5000) + 10000,
                5000,
            )
            if "Raw" in title:
                ax.hist(aug[col], bins=bins, alpha=0.6, color=STYLE["aug"],
                        label=f"Aug (n={len(aug)})")
                ax.hist(noaug[col], bins=bins, alpha=0.6, color=STYLE["noaug"],
                        label=f"No Aug (n={len(noaug)})")
            else:
                ax.hist(aug[col], bins=bins, alpha=0.6, color=STYLE["aug"],
                        label=f"Aug (n={len(aug)})")
                ax.hist(noaug[col], bins=bins, alpha=0.6, color=STYLE["noaug"],
                        label=f"No Aug (n={len(noaug)})")
            ax.legend(fontsize=9, facecolor=STYLE["card"], edgecolor=STYLE["grid"],
                      labelcolor=STYLE["text"])
        ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{x/1000:.0f}k"))
        ax.set_xlabel("DPS", color=STYLE["text"], fontsize=10)

    fig.suptitle("Unholy DK DPS Distributions: Aug vs No-Aug",
                 color=STYLE["accent"], fontsize=15, fontweight="bold", y=1.02)
    fig.tight_layout()
    return fig_to_base64(fig)


def chart_per_dungeon(df):
    dungeons = sorted(df["dungeon"].unique())
    deltas = []
    pcts = []
    ns_aug = []
    ns_noaug = []

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
    set_dark_style(ax, "Buff-Normalized DPS Delta per Dungeon (Aug − No-Aug)")

    short_names = [d.replace("Seat of the Triumvirate", "Seat of Triumv.")
                    .replace("Algeth'ar Academy", "Algeth'ar Acad.") for d in dungeons]

    colors = [STYLE["aug"] if d > 0 else STYLE["noaug"] for d in deltas]
    bars = ax.bar(short_names, deltas, color=colors, alpha=0.85, edgecolor="none")

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


def chart_buff_frequency(df):
    aug = df[df["has_aug"]]
    noaug = df[~df["has_aug"]]

    buffs = list(BUFF_MULTIPLIERS.keys())
    labels = ["Mark of\nthe Wild", "Mystic\nTouch", "Chaos\nBrand",
              "Battle\nShout", "Skyfury"]
    aug_pcts = [aug["buffs"].apply(lambda b: b.get(bn, False)).mean() * 100 for bn in buffs]
    noaug_pcts = [noaug["buffs"].apply(lambda b: b.get(bn, False)).mean() * 100 for bn in buffs]

    fig, ax = plt.subplots(figsize=(12, 5))
    fig.patch.set_facecolor(STYLE["bg"])
    set_dark_style(ax, "Raid Buff Frequency: Aug vs No-Aug Comps")

    x = range(len(buffs))
    w = 0.35
    ax.bar([i - w/2 for i in x], aug_pcts, w, color=STYLE["aug"], alpha=0.85, label="Aug comps")
    ax.bar([i + w/2 for i in x], noaug_pcts, w, color=STYLE["noaug"], alpha=0.85, label="No-Aug comps")

    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_ylabel("% of comps with buff", color=STYLE["text"], fontsize=11)
    ax.set_ylim(0, 110)
    ax.legend(fontsize=10, facecolor=STYLE["card"], edgecolor=STYLE["grid"],
              labelcolor=STYLE["text"])
    fig.tight_layout()
    return fig_to_base64(fig)


def chart_key_level(df):
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.patch.set_facecolor(STYLE["bg"])

    # Left: DPS by key level
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

    # Right: count by key level
    ax = axes[1]
    set_dark_style(ax, "Sample Count by Key Level")
    for label, subset, color in [("Aug", df[df["has_aug"]], STYLE["aug"]),
                                  ("No Aug", df[~df["has_aug"]], STYLE["noaug"])]:
        counts = subset.groupby("key_level").size()
        ax.bar(counts.index - 0.15 if "Aug" == label else counts.index + 0.15,
               counts.values, width=0.3, color=color, alpha=0.85, label=label)
    ax.legend(fontsize=10, facecolor=STYLE["card"], edgecolor=STYLE["grid"],
              labelcolor=STYLE["text"])
    ax.set_xlabel("Key Level", color=STYLE["text"])
    ax.set_ylabel("Count", color=STYLE["text"])

    fig.tight_layout()
    return fig_to_base64(fig)


def chart_comp_comparison(df):
    df = df.copy()
    df["comp_key"] = df["comp"].apply(
        lambda c: " + ".join(sorted(f"{p['class']}-{p['spec']}" for p in c if p["class"] != "DeathKnight"))
    )
    top = df["comp_key"].value_counts().head(8)
    comps = list(top.index)

    fig, ax = plt.subplots(figsize=(14, 6))
    fig.patch.set_facecolor(STYLE["bg"])
    set_dark_style(ax, "Normalized DPS by Comp Archetype (Top 8)")

    avg_dps = []
    colors = []
    labels = []
    for comp in comps:
        sub = df[df["comp_key"] == comp]
        avg = sub["normalized_dps"].mean()
        n = len(sub)
        is_aug = "Evoker-Augmentation" in comp
        avg_dps.append(avg)
        colors.append(STYLE["aug"] if is_aug else STYLE["noaug"])
        short = comp.replace("DemonHunter", "DH").replace("Evoker", "Evo") \
                     .replace("Augmentation", "Aug").replace("Devourer", "Dev") \
                     .replace("Guardian", "Guard").replace("Mistweaver", "MW") \
                     .replace("Brewmaster", "BrM").replace("Restoration", "Resto") \
                     .replace("Discipline", "Disc").replace("Retribution", "Ret") \
                     .replace("Demonology", "Demo").replace("Shadow", "Shadow") \
                     .replace("Paladin", "Pal").replace("Warrior", "War") \
                     .replace("Shaman", "Sham").replace("Warlock", "Lock") \
                     .replace("Priest", "Pri").replace("Monk", "Monk") \
                     .replace("Druid", "Dru")
        labels.append(f"{short}\n(n={n})")

    bars = ax.barh(range(len(comps)), avg_dps, color=colors, alpha=0.85)
    ax.set_yticks(range(len(comps)))
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlabel("Normalized DPS", color=STYLE["text"])
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{x/1000:.0f}k"))
    ax.invert_yaxis()

    for bar, dps in zip(bars, avg_dps):
        ax.text(bar.get_width() + 500, bar.get_y() + bar.get_height()/2,
                f"{dps:,.0f}", va="center", color=STYLE["text"], fontsize=9)

    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=STYLE["aug"], label="Aug comp"),
                       Patch(color=STYLE["noaug"], label="Non-Aug comp")],
              fontsize=10, facecolor=STYLE["card"], edgecolor=STYLE["grid"],
              labelcolor=STYLE["text"], loc="lower right")
    fig.tight_layout()
    return fig_to_base64(fig)


# ─────────────────────── Stats computation ──────────────────────────────────

def compute_stats(df):
    aug = df[df["has_aug"]]
    noaug = df[~df["has_aug"]]

    raw_delta = aug["dps"].mean() - noaug["dps"].mean()
    raw_pct = raw_delta / noaug["dps"].mean() * 100
    norm_delta = aug["normalized_dps"].mean() - noaug["normalized_dps"].mean()
    norm_pct = norm_delta / noaug["normalized_dps"].mean() * 100

    # Per-dungeon
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

    # Key-level matched
    kl_stats = []
    for kl in sorted(df["key_level"].unique()):
        ka = df[(df["has_aug"]) & (df["key_level"] == kl)]
        kn = df[(~df["has_aug"]) & (df["key_level"] == kl)]
        if len(ka) >= 5 and len(kn) >= 5:
            delta = ka["normalized_dps"].mean() - kn["normalized_dps"].mean()
            pct = delta / kn["normalized_dps"].mean() * 100
            kl_stats.append({"key": kl, "delta": delta, "pct": pct,
                             "n_aug": len(ka), "n_noaug": len(kn)})

    # Buff frequencies
    buff_freq = {}
    for bn in BUFF_MULTIPLIERS:
        buff_freq[bn] = {
            "aug": aug["buffs"].apply(lambda b: b.get(bn, False)).mean() * 100,
            "noaug": noaug["buffs"].apply(lambda b: b.get(bn, False)).mean() * 100,
        }

    return {
        "total": len(df), "n_aug": len(aug), "n_noaug": len(noaug),
        "aug_key_mean": aug["key_level"].mean(), "noaug_key_mean": noaug["key_level"].mean(),
        "aug_key_range": (aug["key_level"].min(), aug["key_level"].max()),
        "noaug_key_range": (noaug["key_level"].min(), noaug["key_level"].max()),
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


# ─────────────────────── HTML report ────────────────────────────────────────

def _conclusion_breakdown(breakdown_data):
    if not breakdown_data:
        return ""
    cs = breakdown_data["cat_stats"]
    total_delta = sum(cs[c]["delta"] for c in ["pet", "direct", "disease"])
    if total_delta == 0:
        return ""
    lines = []
    for cat in ["pet", "direct", "disease"]:
        share = cs[cat]["delta"] / total_delta * 100
        lines.append(f"<strong>{cat.title()}</strong>: {cs[cat]['delta']:+,.0f} DPS "
                     f"({cs[cat]['pct']:+.1f}%, {share:.0f}% of total Δ)")
    return f"""
  <p style="font-size:14px; line-height:1.7; margin-top:15px; color:#ccc;">
    <strong style="color:{STYLE['accent']}">Breakdown by damage category:</strong><br>
    {"<br>".join(lines)}
  </p>
  <p style="font-size:13px; line-height:1.6; margin-top:10px; color:#999;">
    Pet damage shows a larger inflation (+4.6%) than direct (+2.7%) or disease (+3.1%),
    and every pet sub-source (main ghoul, army, riders, abomination) is uniformly inflated 3-5%.
    This extra ~1.5% on pets vs other categories suggests incomplete reattribution of
    Ebon Might/Prescience on pet damage specifically.
  </p>
  <p style="font-size:13px; line-height:1.6; margin-top:10px; color:#999;">
    <strong style="color:{STYLE['accent']}">However, pull size is a significant confound.</strong>
    AoE abilities (Epidemic + Graveyard) are +7.0% for aug groups while single-target abilities
    (Death Coil + Necrotic Coil) are -2.4%. This divergence is inconsistent with a flat
    misattribution multiplier. Aug groups appear to pull bigger — especially during Army of the Dead
    burst windows, where Graveyard (AoE, Army) is +10% but Epidemic (AoE, outside Army) is -3%.
    The true misattribution is likely smaller than the headline ~4% figure,
    with pull size and burst window optimization accounting for a significant portion.
  </p>"""


def _generate_pullsize_html(charts, breakdown_data):
    ps = breakdown_data.get("pullsize")
    if not ps:
        return ""

    aug_ps = ps["aug"]
    noaug_ps = ps["noaug"]

    ability_rows_html = ""
    for name, pair_type in [("Epidemic", "AoE"), ("Graveyard", "AoE (Army)"),
                             ("Death Coil", "ST"), ("Necrotic Coil", "ST (Army)")]:
        a = aug_ps["abilities"][name]
        n = noaug_ps["abilities"][name]
        delta = a - n
        pct = delta / n * 100 if n > 0 else 0
        color = "#6C5CE7" if delta > 0 else "#E17055"
        ability_rows_html += f"""
        <tr>
            <td>{name}</td>
            <td>{pair_type}</td>
            <td>{a:,.0f}</td>
            <td>{n:,.0f}</td>
            <td style="color:{color}">{delta:+,.0f}</td>
            <td style="color:{color}">{pct:+.1f}%</td>
        </tr>"""

    aoe_delta = aug_ps["aoe_total"] - noaug_ps["aoe_total"]
    aoe_pct = aoe_delta / noaug_ps["aoe_total"] * 100
    st_delta = aug_ps["st_total"] - noaug_ps["st_total"]
    st_pct = st_delta / noaug_ps["st_total"] * 100

    ratio_delta = (aug_ps["ratio_mean"] - noaug_ps["ratio_mean"]) / noaug_ps["ratio_mean"] * 100

    graveyard_rows = ""
    gbd = breakdown_data.get("graveyard_by_dungeon", [])
    for g in gbd:
        color = "#6C5CE7" if g["delta"] > 0 else "#E17055"
        graveyard_rows += f"""
        <tr>
            <td>{g['dungeon']}</td>
            <td>{g['aug']:,.0f}</td>
            <td>{g['noaug']:,.0f}</td>
            <td style="color:{color}">{g['delta']:+,.0f}</td>
            <td style="color:{color}">{g['pct']:+.1f}%</td>
            <td>{g['n_aug']}</td>
            <td>{g['n_noaug']}</td>
        </tr>"""

    return f"""
<h2>Pull Size Analysis: AoE vs Single-Target</h2>
<p style="color:#888; font-size:13px; margin-bottom:10px;">
  Death Coil becomes Necrotic Coil during Army of the Dead (single-target pair).
  Epidemic becomes Graveyard during Army of the Dead (AoE pair).
  If the DPS delta were pure misattribution (a flat multiplier), both pairs should be inflated equally.
  If pull size is a factor, AoE abilities should be inflated more.
</p>

<div class="chart"><img src="data:image/png;base64,{charts.get('pullsize', '')}"></div>

<table>
  <thead><tr>
    <th>Ability</th><th>Type</th><th>Aug DPS</th><th>No-Aug DPS</th><th>Δ DPS</th><th>Δ%</th>
  </tr></thead>
  <tbody>{ability_rows_html}</tbody>
</table>

<div class="cards" style="margin-top:15px">
  <div class="card">
    <div class="label">AoE Pair Delta</div>
    <div class="value" style="color:#6C5CE7">{aoe_delta:+,.0f}</div>
    <div class="sub">{aoe_pct:+.1f}% (Epidemic + Graveyard)</div>
  </div>
  <div class="card">
    <div class="label">ST Pair Delta</div>
    <div class="value" style="color:#E17055">{st_delta:+,.0f}</div>
    <div class="sub">{st_pct:+.1f}% (Death Coil + Necrotic Coil)</div>
  </div>
</div>

<p style="color:#ccc; font-size:14px; margin-top:15px; line-height:1.6;">
  Aug groups show <strong>{aoe_pct:+.1f}%</strong> more AoE damage but <strong>{st_pct:+.1f}%</strong>
  single-target damage. This divergence is inconsistent with a flat misattribution multiplier
  and strongly suggests aug groups are pulling bigger, especially during Army of the Dead
  burst windows (Graveyard at {aug_ps['abilities']['Graveyard'] - noaug_ps['abilities']['Graveyard']:+,.0f} DPS
  vs Epidemic at {aug_ps['abilities']['Epidemic'] - noaug_ps['abilities']['Epidemic']:+,.0f} DPS).
</p>

<h3 style="color:{STYLE['accent']}; font-size:16px; margin:20px 0 10px;">Graveyard DPS by Dungeon</h3>
<p style="color:#888; font-size:13px; margin-bottom:10px;">
  Graveyard shows the largest single-ability delta (+11.3%). Breaking it down by dungeon
  helps identify where aug groups pull the biggest.
</p>
<table>
  <thead><tr>
    <th>Dungeon</th><th>Aug DPS</th><th>No-Aug DPS</th><th>Δ DPS</th><th>Δ%</th><th>Runs (aug)</th><th>Runs (no-aug)</th>
  </tr></thead>
  <tbody>{graveyard_rows}</tbody>
</table>
"""


def generate_breakdown_html(charts, breakdown_data):
    if not breakdown_data:
        return ""

    cs = breakdown_data["cat_stats"]
    ability_rows = breakdown_data.get("ability_rows", [])
    n_aug = breakdown_data["n_aug"]
    n_noaug = breakdown_data["n_noaug"]

    total_delta = sum(cs[c]["delta"] for c in ["pet", "direct", "disease"])

    cat_table_rows = ""
    for cat in ["pet", "direct", "disease"]:
        s = cs[cat]
        share = s["delta"] / total_delta * 100 if total_delta else 0
        color = "#6C5CE7" if s["delta"] > 0 else "#E17055"
        cat_table_rows += f"""
        <tr>
            <td style="text-transform:capitalize">{cat}</td>
            <td>{s['aug_pct']:.1f}%</td>
            <td>{s['noaug_pct']:.1f}%</td>
            <td>{s['aug_dps']:,.0f}</td>
            <td>{s['noaug_dps']:,.0f}</td>
            <td style="color:{color}">{s['delta']:+,.0f}</td>
            <td style="color:{color}">{s['pct']:+.1f}%</td>
            <td>{share:.0f}%</td>
        </tr>"""

    ability_table_rows = ""
    for r in ability_rows[:15]:
        color = "#6C5CE7" if r["delta"] > 0 else "#E17055"
        cat_color = {"pet": "#e74c3c", "direct": "#3498db", "disease": "#2ecc71"}.get(r["cat"], "#aaa")
        pct_str = f"{r['pct']:+.1f}%" if abs(r["pct"]) < 500 else "new"
        ability_table_rows += f"""
        <tr>
            <td>{r['name']}</td>
            <td><span style="color:{cat_color}">{r['cat']}</span></td>
            <td>{r['aug']:,.0f} <span style="color:#666;font-size:11px">(n={r.get('aug_n','-')})</span></td>
            <td>{r['noaug']:,.0f} <span style="color:#666;font-size:11px">(n={r.get('noaug_n','-')})</span></td>
            <td style="color:{color}">{r['delta']:+,.0f}</td>
            <td style="color:{color}">{pct_str}</td>
        </tr>"""

    # Pet sub-category table
    pet_subcat_html = ""
    pet_subs = breakdown_data.get("pet_subcats")
    if pet_subs:
        pet_sub_rows = ""
        total_pet_delta = 0
        for name in ["Main Ghoul", "Lesser Ghoul", "Army of the Damned",
                      "Rider's Champion", "Raise Abomination"]:
            a = pet_subs["aug"].get(name, 0)
            n = pet_subs["noaug"].get(name, 0)
            delta = a - n
            pct = delta / n * 100 if n > 0 else 0
            total_pet_delta += delta
            color = "#6C5CE7" if delta > 0 else "#E17055"
            note = ""
            if name == "Main Ghoul":
                note = " <span style='color:#666;font-size:11px'>(random ghoul names + Raise Dead)</span>"
            pet_sub_rows += f"""
            <tr>
                <td>{name}{note}</td>
                <td>{a:,.0f}</td>
                <td>{n:,.0f}</td>
                <td style="color:{color}">{delta:+,.0f}</td>
                <td style="color:{color}">{pct:+.1f}%</td>
            </tr>"""
        # Total row
        aug_total = sum(pet_subs["aug"].values())
        noaug_total = sum(pet_subs["noaug"].values())
        total_pct = total_pet_delta / noaug_total * 100 if noaug_total else 0
        pet_sub_rows += f"""
            <tr style="border-top:2px solid {STYLE['grid']};font-weight:bold">
                <td>Total Pet</td>
                <td>{aug_total:,.0f}</td>
                <td>{noaug_total:,.0f}</td>
                <td style="color:#6C5CE7">{total_pet_delta:+,.0f}</td>
                <td style="color:#6C5CE7">{total_pct:+.1f}%</td>
            </tr>"""

        pet_subcat_html = f"""
<h2>Pet Damage Sub-Categories</h2>
<p style="color:#888; font-size:13px; margin-bottom:10px;">
  Breaking down pet damage by source to identify where the extra 4.6% pet delta comes from.
  Every pet source is inflated 3-5% with Aug, consistent with a flat multiplier not being fully stripped.
</p>
<table>
  <thead><tr>
    <th>Pet Source</th><th>Aug DPS</th><th>No-Aug DPS</th><th>Δ DPS</th><th>Δ%</th>
  </tr></thead>
  <tbody>{pet_sub_rows}</tbody>
</table>
"""

    return f"""
<h2>Damage Breakdown Analysis</h2>
<p style="color:#888; font-size:13px; margin-bottom:10px;">
  Analyzing {n_aug + n_noaug} per-fight ability breakdowns ({n_aug} aug, {n_noaug} no-aug) to determine
  which parts of the DK's damage are inflated when playing with Aug.
  All DPS values are buff-normalized.
</p>

<div class="chart"><img src="data:image/png;base64,{charts.get('category', '')}"></div>

<table>
  <thead><tr>
    <th>Category</th><th>Aug %</th><th>No-Aug %</th>
    <th>Aug DPS</th><th>No-Aug DPS</th><th>Δ DPS</th><th>Δ%</th><th>Share of Δ</th>
  </tr></thead>
  <tbody>{cat_table_rows}</tbody>
</table>

{pet_subcat_html}

<h2>Per-Ability DPS Delta</h2>
<p style="color:#888; font-size:13px; margin-bottom:10px;">
  Individual ability comparison (buff-normalized DPS, n = sample count). Sorted by absolute delta.
  <span style="color:#e74c3c">Red = Pet</span>,
  <span style="color:#3498db">Blue = Direct</span>,
  <span style="color:#2ecc71">Green = Disease</span>.
</p>

<div class="chart"><img src="data:image/png;base64,{charts.get('abilities', '')}"></div>

<table>
  <thead><tr>
    <th>Ability</th><th>Type</th><th>Aug DPS (n)</th><th>No-Aug DPS (n)</th><th>Δ DPS</th><th>Δ%</th>
  </tr></thead>
  <tbody>{ability_table_rows}</tbody>
</table>

{_generate_pullsize_html(charts, breakdown_data)}
"""


def generate_html(stats, charts, breakdown_data=None):
    buff_rows = ""
    nice_names = {
        "mark_of_the_wild": "Mark of the Wild",
        "mystic_touch": "Mystic Touch",
        "chaos_brand": "Chaos Brand",
        "battle_shout": "Battle Shout",
        "skyfury": "Skyfury (incl. Windfury)",
    }
    for bn, freq in stats["buff_freq"].items():
        mult = BUFF_MULTIPLIERS[bn]
        buff_rows += f"""
        <tr>
            <td>{nice_names.get(bn, bn)}</td>
            <td>{freq['aug']:.1f}%</td>
            <td>{freq['noaug']:.1f}%</td>
            <td>+{(mult - 1) * 100:.1f}%</td>
        </tr>"""

    dungeon_rows = ""
    for d in stats["dungeon_stats"]:
        color = "#6C5CE7" if d["delta"] > 0 else "#E17055"
        dungeon_rows += f"""
        <tr>
            <td>{d['dungeon']}</td>
            <td style="color: {color}">{d['delta']:+,.0f}</td>
            <td style="color: {color}">{d['pct']:+.1f}%</td>
            <td>{d['n_aug']}</td>
            <td>{d['n_noaug']}</td>
        </tr>"""

    kl_rows = ""
    for kl in stats["kl_stats"]:
        color = "#6C5CE7" if kl["delta"] > 0 else "#E17055"
        kl_rows += f"""
        <tr>
            <td>+{kl['key']}</td>
            <td style="color: {color}">{kl['delta']:+,.0f}</td>
            <td style="color: {color}">{kl['pct']:+.1f}%</td>
            <td>{kl['n_aug']}</td>
            <td>{kl['n_noaug']}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Aug Evoker Misattribution Analysis — Unholy DK</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: {STYLE['bg']}; color: {STYLE['text']}; font-family: 'Segoe UI', system-ui, sans-serif; padding: 20px 40px; }}
  h1 {{ color: {STYLE['accent']}; font-size: 28px; margin-bottom: 5px; }}
  h2 {{ color: {STYLE['accent']}; font-size: 20px; margin: 30px 0 15px; border-bottom: 1px solid {STYLE['grid']}; padding-bottom: 6px; }}
  .subtitle {{ color: #888; font-size: 14px; margin-bottom: 30px; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 15px; margin-bottom: 25px; }}
  .card {{ background: {STYLE['card']}; border-radius: 10px; padding: 18px; }}
  .card .label {{ color: #888; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; }}
  .card .value {{ font-size: 28px; font-weight: bold; margin-top: 5px; }}
  .card .sub {{ color: #888; font-size: 13px; margin-top: 3px; }}
  .aug {{ color: {STYLE['aug']}; }}
  .noaug {{ color: {STYLE['noaug']}; }}
  .accent {{ color: {STYLE['accent']}; }}
  .chart {{ background: {STYLE['card']}; border-radius: 10px; padding: 15px; margin: 15px 0; text-align: center; }}
  .chart img {{ max-width: 100%; border-radius: 6px; }}
  table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
  th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid {STYLE['grid']}; }}
  th {{ color: {STYLE['accent']}; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; }}
  td {{ font-size: 14px; }}
  .conclusion {{ background: linear-gradient(135deg, #16213e, #1a1a40); border: 1px solid {STYLE['accent']}40; border-radius: 12px; padding: 25px; margin: 30px 0; }}
  .conclusion h2 {{ border: none; margin-top: 0; }}
  .methodology {{ background: {STYLE['card']}; border-radius: 10px; padding: 20px; margin: 20px 0; font-size: 13px; color: #aaa; }}
  .methodology h3 {{ color: {STYLE['accent']}; font-size: 15px; margin-bottom: 10px; }}
  .methodology ul {{ margin-left: 20px; }}
  .methodology li {{ margin: 5px 0; }}
</style>
</head>
<body>

<h1>Aug Evoker Damage Misattribution</h1>
<p class="subtitle">Unholy DK — Midnight Season 1 M+ — Top 400 rankings per dungeon across all regions</p>

<div class="cards">
  <div class="card">
    <div class="label">Total Rankings</div>
    <div class="value accent">{stats['total']:,}</div>
    <div class="sub">{stats['n_aug']:,} aug / {stats['n_noaug']:,} no-aug</div>
  </div>
  <div class="card">
    <div class="label">Raw DPS Delta</div>
    <div class="value" style="color: {'#6C5CE7' if stats['raw_delta'] > 0 else '#E17055'}">{stats['raw_delta']:+,.0f}</div>
    <div class="sub">{stats['raw_pct']:+.1f}% (as shown in logs)</div>
  </div>
  <div class="card">
    <div class="label">Buff-Normalized Delta</div>
    <div class="value" style="color: {'#6C5CE7' if stats['norm_delta'] > 0 else '#E17055'}">{stats['norm_delta']:+,.0f}</div>
    <div class="sub">{stats['norm_pct']:+.1f}% (controlling for raid buffs)</div>
  </div>
  <div class="card">
    <div class="label">Estimated Misattribution</div>
    <div class="value accent">{stats['norm_pct']:+.1f}%</div>
    <div class="sub">~{abs(stats['norm_delta']):,.0f} DPS credited to DK instead of Aug</div>
  </div>
</div>

<h2>DPS Distributions</h2>
<div class="chart"><img src="data:image/png;base64,{charts['distributions']}"></div>

<h2>Buff Frequency</h2>
<p style="color:#888; font-size:13px; margin-bottom:10px;">
  Aug comps typically bring MotW + Mystic Touch + Chaos Brand.
  Non-aug comps typically bring Battle Shout + Skyfury (± Mystic Touch).
</p>
<div class="chart"><img src="data:image/png;base64,{charts['buff_freq']}"></div>

<table>
  <thead><tr><th>Buff</th><th>Aug comps</th><th>No-Aug comps</th><th>Estimated DPS effect</th></tr></thead>
  <tbody>{buff_rows}</tbody>
</table>
<p style="color:#888; font-size:12px; margin-top:5px;">
  Average buff multiplier — Aug: {stats['aug_buff_mult']:.4f}x | No-Aug: {stats['noaug_buff_mult']:.4f}x
</p>

<h2>Per-Dungeon Breakdown</h2>
<div class="chart"><img src="data:image/png;base64,{charts['per_dungeon']}"></div>
<table>
  <thead><tr><th>Dungeon</th><th>DPS Delta</th><th>%</th><th>n (aug)</th><th>n (no-aug)</th></tr></thead>
  <tbody>{dungeon_rows}</tbody>
</table>

<h2>Key Level Matched</h2>
<div class="chart"><img src="data:image/png;base64,{charts['key_level']}"></div>
<table>
  <thead><tr><th>Key Level</th><th>DPS Delta</th><th>%</th><th>n (aug)</th><th>n (no-aug)</th></tr></thead>
  <tbody>{kl_rows}</tbody>
</table>

<h2>Comp Archetype Comparison</h2>
<div class="chart"><img src="data:image/png;base64,{charts['comp']}"></div>

{generate_breakdown_html(charts, breakdown_data) if breakdown_data else ''}

<div class="conclusion">
  <h2>Summary</h2>
  <p style="font-size:16px; line-height:1.7;">
    After normalizing for the different raid buffs each comp brings, Unholy DKs playing
    with an Aug Evoker show <strong style="color:{STYLE['accent']}">{stats['norm_delta']:+,.0f} DPS ({stats['norm_pct']:+.1f}%)</strong>
    higher personal DPS than DKs without Aug.
  </p>
  <p style="font-size:14px; line-height:1.7; margin-top:10px; color:#aaa;">
    Since WarcraftLogs is supposed to reattribute Aug-buffed damage back to the Aug,
    this residual represents damage that is being <em>misattributed</em> — it stays on the DK's
    log instead of being credited to the Aug Evoker. At {stats['aug_norm_mean']:,.0f} average normalized DPS,
    this means roughly <strong>{abs(stats['norm_delta']):,.0f} DPS</strong> of the DK's logged damage
    actually belongs to the Aug.
  </p>
  {_conclusion_breakdown(breakdown_data) if breakdown_data else ''}
</div>

<div class="methodology">
  <h3>Methodology</h3>
  <ul>
    <li>Data: Top 400 Unholy DK rankings per dungeon from WarcraftLogs API (characterRankings), across all regions.</li>
    <li>Buff normalization: Each DK's logged DPS is divided by the multiplicative product of all raid buffs present in their comp.
        This produces a "no external buffs" baseline for fair comparison.</li>
    <li>Buff multipliers used:
        MotW=+3%, Mystic Touch=+2.85% (5% phys on 57% phys dmg), Chaos Brand=+1.3% (3% magic on 43% magic dmg),
        Battle Shout=+5%, Skyfury=+3% (mastery + windfury, simmed for UH DK).</li>
    <li>The remaining DPS difference between aug and no-aug groups, after normalization, is the estimated misattributed damage.</li>
    <li>Caveats: Buff multipliers are estimates. Player skill selection bias exists (no-aug DKs who rank this high may be exceptional).
        Small no-aug sample at higher key levels.</li>
  </ul>
</div>

</body>
</html>"""


# ─────────────────────── Main ───────────────────────────────────────────────

def load_breakdowns():
    """Load breakdown data if available, return charts + stats for HTML."""
    path = os.path.join("data", "breakdowns.json")
    if not os.path.exists(path):
        return None, None

    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    bdf = pd.DataFrame(data)
    bdf["buff_multiplier"] = bdf["buffs"].apply(compute_buff_multiplier)

    aug = bdf[bdf["has_aug"]]
    noaug = bdf[~bdf["has_aug"]]

    # Category DPS (normalized)
    aug_dur = aug["total_damage"] / aug["dps"]
    noaug_dur = noaug["total_damage"] / noaug["dps"]

    cat_stats = {}
    for cat in ["pet", "direct", "disease"]:
        aug_dps = (aug[f"{cat}_damage"] / aug["buff_multiplier"] / aug_dur).mean()
        noaug_dps = (noaug[f"{cat}_damage"] / noaug["buff_multiplier"] / noaug_dur).mean()
        delta = aug_dps - noaug_dps
        pct = delta / noaug_dps * 100 if noaug_dps else 0
        cat_stats[cat] = {
            "aug_dps": aug_dps, "noaug_dps": noaug_dps,
            "delta": delta, "pct": pct,
            "aug_pct": aug[f"{cat}_pct"].mean(),
            "noaug_pct": noaug[f"{cat}_pct"].mean(),
        }

    # Per-ability DPS comparison
    PLAYER_ABILITIES = {
        "Putrefy", "Graveyard", "Scourge Strike", "Epidemic",
        "Necrotic Coil", "Death Coil", "Melee", "Soul Reaper",
        "Festering Scythe", "Death and Decay", "Festering Strike",
        "Death Strike", "Anti-Magic Shell",
    }
    DISEASE_ABILITIES_SET = {
        "Virulent Plague", "Dread Plague", "Pestilence", "Festering Wound",
    }
    from collections import defaultdict

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

    aug_ab_raw = agg(aug)
    noaug_ab_raw = agg(noaug)

    all_names = set(aug_ab_raw) | set(noaug_ab_raw)
    ability_rows = []
    for name in all_names:
        if any(ord(c) > 127 for c in name):
            continue
        if name in ("Unknown",):
            continue
        aug_dps, aug_n = aug_ab_raw.get(name, (0, 0))
        noaug_dps, noaug_n = noaug_ab_raw.get(name, (0, 0))
        if aug_n + noaug_n < 50:
            continue
        delta = aug_dps - noaug_dps
        if name in PLAYER_ABILITIES:
            cat = "direct"
        elif name in DISEASE_ABILITIES_SET:
            cat = "disease"
        else:
            cat = "pet"
        pct = delta / noaug_dps * 100 if noaug_dps > 0 else (999 if aug_dps > 0 else 0)
        if aug_dps + noaug_dps > 200:
            ability_rows.append({"name": name, "cat": cat, "aug": aug_dps,
                                 "noaug": noaug_dps, "delta": delta, "pct": pct,
                                 "aug_n": aug_n, "noaug_n": noaug_n})
    ability_rows.sort(key=lambda x: -abs(x["delta"]))

    # Charts
    cats = ["Pet", "Direct", "Disease"]
    aug_pcts = [cat_stats["pet"]["aug_pct"], cat_stats["direct"]["aug_pct"], cat_stats["disease"]["aug_pct"]]
    noaug_pcts = [cat_stats["pet"]["noaug_pct"], cat_stats["direct"]["noaug_pct"], cat_stats["disease"]["noaug_pct"]]
    aug_dps_vals = [cat_stats["pet"]["aug_dps"], cat_stats["direct"]["aug_dps"], cat_stats["disease"]["aug_dps"]]
    noaug_dps_vals = [cat_stats["pet"]["noaug_dps"], cat_stats["direct"]["noaug_dps"], cat_stats["disease"]["noaug_dps"]]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.patch.set_facecolor(STYLE["bg"])
    w = 0.35
    x = range(3)

    ax = axes[0]
    set_dark_style(ax, "Damage Category Proportions (% of total)")
    ax.bar([i - w/2 for i in x], aug_pcts, w, color=STYLE["aug"], alpha=0.85, label="Aug")
    ax.bar([i + w/2 for i in x], noaug_pcts, w, color=STYLE["noaug"], alpha=0.85, label="No Aug")
    ax.set_xticks(list(x)); ax.set_xticklabels(cats)
    ax.set_ylabel("% of total damage", color=STYLE["text"])
    for i, (a, n) in enumerate(zip(aug_pcts, noaug_pcts)):
        ax.text(i - w/2, a + 0.5, f"{a:.1f}%", ha="center", color=STYLE["text"], fontsize=9)
        ax.text(i + w/2, n + 0.5, f"{n:.1f}%", ha="center", color=STYLE["text"], fontsize=9)
    ax.legend(fontsize=10, facecolor=STYLE["card"], edgecolor=STYLE["grid"], labelcolor=STYLE["text"])

    ax = axes[1]
    set_dark_style(ax, "Normalized DPS by Category")
    bars_a = ax.bar([i - w/2 for i in x], aug_dps_vals, w, color=STYLE["aug"], alpha=0.85, label="Aug")
    bars_n = ax.bar([i + w/2 for i in x], noaug_dps_vals, w, color=STYLE["noaug"], alpha=0.85, label="No Aug")
    ax.set_xticks(list(x)); ax.set_xticklabels(cats)
    ax.set_ylabel("Normalized DPS", color=STYLE["text"])
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v/1000:.0f}k"))
    for i, (a, n) in enumerate(zip(aug_dps_vals, noaug_dps_vals)):
        delta = a - n
        ax.text(i, max(a, n) + 1000, f"Δ={delta:+,.0f}", ha="center", color=STYLE["accent"], fontsize=9, fontweight="bold")
    ax.legend(fontsize=10, facecolor=STYLE["card"], edgecolor=STYLE["grid"], labelcolor=STYLE["text"])
    fig.tight_layout()
    cat_chart = fig_to_base64(fig)

    filtered = [r for r in ability_rows if abs(r["pct"]) < 500][:18]
    fig, ax = plt.subplots(figsize=(14, max(6, len(filtered) * 0.4)))
    fig.patch.set_facecolor(STYLE["bg"])
    set_dark_style(ax, "Per-Ability Normalized DPS Delta (Aug − No-Aug)")
    cat_colors = {"pet": "#e74c3c", "direct": "#3498db", "disease": "#2ecc71"}
    names = [r["name"] for r in filtered]
    deltas = [r["delta"] for r in filtered]
    colors = [cat_colors.get(r["cat"], "#aaa") for r in filtered]
    ax.barh(range(len(names)), deltas, color=colors, alpha=0.85)
    ax.set_yticks(range(len(names))); ax.set_yticklabels(names, fontsize=9)
    ax.set_xlabel("DPS Delta", color=STYLE["text"])
    ax.axvline(0, color=STYLE["text"], linewidth=0.5, alpha=0.5)
    ax.invert_yaxis()
    for i, (d, r) in enumerate(zip(deltas, filtered)):
        ax.text(d + (50 if d >= 0 else -50), i, f"{d:+,.0f} ({r['pct']:+.1f}%)",
                va="center", ha="left" if d >= 0 else "right", color=STYLE["text"], fontsize=8)
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color="#e74c3c", label="Pet"), Patch(color="#3498db", label="Direct"),
                       Patch(color="#2ecc71", label="Disease")],
              fontsize=10, facecolor=STYLE["card"], edgecolor=STYLE["grid"],
              labelcolor=STYLE["text"], loc="lower right")
    fig.tight_layout()
    ability_chart = fig_to_base64(fig)

    # Pet sub-category breakdown
    PET_SUBCATS = ["Main Ghoul", "Lesser Ghoul", "Army of the Damned",
                   "Rider's Champion", "Raise Abomination"]
    MAIN_GHOUL_KNOWN = {"Raise Dead", "Infected Claws", "Claw"}
    KNOWN_NON_GHOUL_PET = {
        "Lesser Ghoul", "Raise Abomination", "Rider's Champion", "Army of the Damned",
        "Dark Arbiter", "Blood Draw", "Blinding Sleet", "Death Grip", "Chains of Ice",
        "Brittle", "War", "Death", "Famine", "Bombardments", "Fate Mirror",
        "Breath of Eons", "Inferno's Blessing", "Halazzi's Claws",
        "Prismatic Focusing Iris", "Eternal Voidsong Chain", "Frost Fever",
        "Remorseless Winter", "Icy Death Torrent", "Hyperpyrexia", "Marrowrend",
        "Twilight Barrage", "未知目标",
    }

    pet_subcat_stats = {}
    for label, subset in [("aug", aug), ("noaug", noaug)]:
        subs = defaultdict(float)
        for _, row in subset.iterrows():
            dur = row["total_damage"] / row["dps"]
            bm = compute_buff_multiplier(row["buffs"])
            for a in row["abilities"]:
                if a["name"] in PLAYER_ABILITIES or a["name"] in DISEASE_ABILITIES_SET:
                    continue
                dps = a["total"] / bm / dur
                if a["name"] == "Lesser Ghoul":
                    subs["Lesser Ghoul"] += dps
                elif a["name"] == "Army of the Damned":
                    subs["Army of the Damned"] += dps
                elif a["name"] == "Rider's Champion":
                    subs["Rider's Champion"] += dps
                elif a["name"] == "Raise Abomination":
                    subs["Raise Abomination"] += dps
                elif a["name"] in MAIN_GHOUL_KNOWN or a["name"] not in KNOWN_NON_GHOUL_PET and a["total"] > 100000:
                    subs["Main Ghoul"] += dps
        n = len(subset)
        pet_subcat_stats[label] = {k: subs[k] / n for k in PET_SUBCATS}

    # AoE vs ST pull size analysis
    import statistics
    AOE_ABILITIES = ["Epidemic", "Graveyard"]
    ST_ABILITIES = ["Death Coil", "Necrotic Coil"]

    def get_ability_dps_from_row(row, name):
        dur = row["total_damage"] / row["dps"]
        bm = compute_buff_multiplier(row["buffs"])
        for a in row["abilities"]:
            if a["name"] == name:
                return a["total"] / bm / dur
        return 0

    pullsize_stats = {}
    for label, subset in [("aug", aug), ("noaug", noaug)]:
        ability_avgs = {}
        for ab_name in AOE_ABILITIES + ST_ABILITIES:
            vals = [get_ability_dps_from_row(row, ab_name) for _, row in subset.iterrows()]
            ability_avgs[ab_name] = sum(vals) / len(vals)
        aoe_total = sum(ability_avgs[a] for a in AOE_ABILITIES)
        st_total = sum(ability_avgs[a] for a in ST_ABILITIES)

        ratios = []
        for _, row in subset.iterrows():
            aoe = sum(get_ability_dps_from_row(row, a) for a in AOE_ABILITIES)
            st = sum(get_ability_dps_from_row(row, a) for a in ST_ABILITIES)
            if st > 100:
                ratios.append(aoe / st)

        pullsize_stats[label] = {
            "abilities": ability_avgs,
            "aoe_total": aoe_total,
            "st_total": st_total,
            "ratio_mean": statistics.mean(ratios),
            "ratio_median": statistics.median(ratios),
        }

    # Graveyard by dungeon
    graveyard_by_dungeon = []
    for d in sorted(bdf["dungeon"].unique()):
        aug_d = [get_ability_dps_from_row(row, "Graveyard")
                 for _, row in aug[aug["dungeon"] == d].iterrows()]
        noaug_d = [get_ability_dps_from_row(row, "Graveyard")
                   for _, row in noaug[noaug["dungeon"] == d].iterrows()]
        if aug_d and noaug_d:
            a_avg = sum(aug_d) / len(aug_d)
            n_avg = sum(noaug_d) / len(noaug_d)
            delta = a_avg - n_avg
            pct = delta / n_avg * 100 if n_avg > 0 else 0
            graveyard_by_dungeon.append({
                "dungeon": d, "aug": a_avg, "noaug": n_avg,
                "delta": delta, "pct": pct,
                "n_aug": len(aug_d), "n_noaug": len(noaug_d),
            })

    # AoE/ST chart
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.patch.set_facecolor(STYLE["bg"])
    w = 0.35

    ax = axes[0]
    set_dark_style(ax, "AoE vs Single-Target DPS (Normalized)")
    pair_labels = ["Epidemic\n(AoE)", "Graveyard\n(AoE, Army)", "Death Coil\n(ST)", "Necrotic Coil\n(ST, Army)"]
    all_abs = AOE_ABILITIES + ST_ABILITIES
    aug_vals_ps = [pullsize_stats["aug"]["abilities"][a] for a in all_abs]
    noaug_vals_ps = [pullsize_stats["noaug"]["abilities"][a] for a in all_abs]
    xi = range(len(all_abs))
    ax.bar([i - w/2 for i in xi], aug_vals_ps, w, color=STYLE["aug"], alpha=0.85, label="Aug")
    ax.bar([i + w/2 for i in xi], noaug_vals_ps, w, color=STYLE["noaug"], alpha=0.85, label="No Aug")
    ax.set_xticks(list(xi))
    ax.set_xticklabels(pair_labels, fontsize=8)
    ax.set_ylabel("Normalized DPS", color=STYLE["text"])
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v/1000:.0f}k"))
    for i, (a_v, n_v) in enumerate(zip(aug_vals_ps, noaug_vals_ps)):
        d = a_v - n_v
        pct_v = d / n_v * 100 if n_v > 0 else 0
        ax.text(i, max(a_v, n_v) + 300, f"{pct_v:+.1f}%", ha="center",
                color=STYLE["accent"], fontsize=9, fontweight="bold")
    ax.legend(fontsize=10, facecolor=STYLE["card"], edgecolor=STYLE["grid"], labelcolor=STYLE["text"])

    ax = axes[1]
    set_dark_style(ax, "Paired AoE vs ST Totals")
    pair_names = ["AoE\n(Epi + Grave)", "ST\n(DC + NC)"]
    aug_paired = [pullsize_stats["aug"]["aoe_total"], pullsize_stats["aug"]["st_total"]]
    noaug_paired = [pullsize_stats["noaug"]["aoe_total"], pullsize_stats["noaug"]["st_total"]]
    xi2 = range(2)
    ax.bar([i - w/2 for i in xi2], aug_paired, w, color=STYLE["aug"], alpha=0.85, label="Aug")
    ax.bar([i + w/2 for i in xi2], noaug_paired, w, color=STYLE["noaug"], alpha=0.85, label="No Aug")
    ax.set_xticks(list(xi2))
    ax.set_xticklabels(pair_names)
    ax.set_ylabel("Normalized DPS", color=STYLE["text"])
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v/1000:.0f}k"))
    for i, (a_v, n_v) in enumerate(zip(aug_paired, noaug_paired)):
        d = a_v - n_v
        pct_v = d / n_v * 100 if n_v > 0 else 0
        ax.text(i, max(a_v, n_v) + 500, f"{d:+,.0f} ({pct_v:+.1f}%)", ha="center",
                color=STYLE["accent"], fontsize=10, fontweight="bold")
    ax.legend(fontsize=10, facecolor=STYLE["card"], edgecolor=STYLE["grid"], labelcolor=STYLE["text"])
    fig.tight_layout()
    pullsize_chart = fig_to_base64(fig)

    breakdown_data = {
        "cat_stats": cat_stats, "ability_rows": filtered,
        "n_aug": len(aug), "n_noaug": len(noaug),
        "pet_subcats": pet_subcat_stats,
        "pullsize": pullsize_stats,
        "graveyard_by_dungeon": graveyard_by_dungeon,
    }
    breakdown_charts = {"category": cat_chart, "abilities": ability_chart, "pullsize": pullsize_chart}
    return breakdown_data, breakdown_charts


def main():
    df = load_rankings()
    df = normalize_dps(df)

    print("Generating charts...")
    charts = {
        "distributions": chart_dps_distributions(df),
        "per_dungeon": chart_per_dungeon(df),
        "buff_freq": chart_buff_frequency(df),
        "key_level": chart_key_level(df),
        "comp": chart_comp_comparison(df),
    }

    print("Computing stats...")
    stats = compute_stats(df)

    print("Loading breakdown data...")
    breakdown_data, breakdown_charts = load_breakdowns()
    if breakdown_charts:
        charts.update(breakdown_charts)

    print("Writing HTML report...")
    os.makedirs("results", exist_ok=True)
    html = generate_html(stats, charts, breakdown_data)
    out = os.path.join("results", "report.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\nReport saved to: {os.path.abspath(out)}")
    print(f"\nKey findings:")
    print(f"  Raw DPS delta: {stats['raw_delta']:+,.0f} ({stats['raw_pct']:+.1f}%)")
    print(f"  Buff-normalized delta: {stats['norm_delta']:+,.0f} ({stats['norm_pct']:+.1f}%)")
    print(f"  → Estimated misattribution: ~{abs(stats['norm_delta']):,.0f} DPS ({stats['norm_pct']:+.1f}%)")
    if breakdown_data:
        cs = breakdown_data["cat_stats"]
        print(f"\n  Breakdown of misattribution:")
        for cat in ["pet", "direct", "disease"]:
            print(f"    {cat:<10s}: {cs[cat]['delta']:+,.0f} DPS ({cs[cat]['pct']:+.1f}%)")


if __name__ == "__main__":
    main()
