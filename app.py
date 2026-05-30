"""Flask web app serving the aug misattribution analysis."""
import os
import sys
sys.stdout.reconfigure(encoding="utf-8")

from flask import Flask, render_template_string
from analyze import (
    load_rankings, normalize_dps, compute_stats, compute_buff_multiplier,
    chart_dps_distributions, chart_per_dungeon, chart_buff_frequency,
    chart_key_level, chart_comp_comparison, load_breakdowns,
    BUFF_MULTIPLIERS, STYLE,
)
from pullsize_control import run_pullsize_analysis
from analyze_lock import (
    load_lock_rankings, normalize_lock_dps, compute_lock_stats,
    chart_lock_distributions, chart_lock_per_dungeon, chart_lock_key_level,
    load_lock_breakdowns,
)

app = Flask(__name__)

# Cache generated content
_cache = {}


def get_dk_data():
    if "dk" in _cache:
        return _cache["dk"]

    df = load_rankings()
    df = normalize_dps(df)
    charts = {
        "distributions": chart_dps_distributions(df),
        "per_dungeon": chart_per_dungeon(df),
        "buff_freq": chart_buff_frequency(df),
        "key_level": chart_key_level(df),
        "comp": chart_comp_comparison(df),
    }
    stats = compute_stats(df)
    breakdown_data, breakdown_charts = load_breakdowns()
    if breakdown_charts:
        charts.update(breakdown_charts)

    pullsize = run_pullsize_analysis()

    result = {"stats": stats, "charts": charts, "breakdown": breakdown_data, "pullsize": pullsize}
    _cache["dk"] = result
    return result


def get_lock_data():
    if "lock" in _cache:
        return _cache["lock"]

    df = load_lock_rankings()
    df = normalize_lock_dps(df)
    charts = {
        "distributions": chart_lock_distributions(df),
        "per_dungeon": chart_lock_per_dungeon(df),
        "key_level": chart_lock_key_level(df),
    }
    stats = compute_lock_stats(df)
    breakdown_data, breakdown_charts = load_lock_breakdowns()
    if breakdown_charts:
        charts.update(breakdown_charts)

    result = {"stats": stats, "charts": charts, "breakdown": breakdown_data}
    _cache["lock"] = result
    return result


BASE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Aug Evoker Misattribution Analysis</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: %(bg)s; color: %(text)s; font-family: 'Segoe UI', system-ui, sans-serif; padding: 0; }
  .nav { background: %(card)s; padding: 12px 40px; border-bottom: 1px solid %(grid)s; display: flex; align-items: center; gap: 30px; position: sticky; top: 0; z-index: 100; }
  .nav h1 { color: %(accent)s; font-size: 18px; margin-right: 20px; }
  .nav a { color: %(text)s; text-decoration: none; padding: 8px 16px; border-radius: 6px; font-size: 14px; transition: background 0.2s; }
  .nav a:hover { background: %(bg)s; }
  .nav a.active { background: %(accent)s; color: %(bg)s; font-weight: bold; }
  .content { padding: 30px 40px; max-width: 1400px; margin: 0 auto; }
  h2 { color: %(accent)s; font-size: 20px; margin: 30px 0 15px; border-bottom: 1px solid %(grid)s; padding-bottom: 6px; }
  h3 { color: %(accent)s; font-size: 16px; margin: 20px 0 10px; }
  .subtitle { color: #888; font-size: 14px; margin-bottom: 30px; }
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 15px; margin-bottom: 25px; }
  .card { background: %(card)s; border-radius: 10px; padding: 18px; }
  .card .label { color: #888; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; }
  .card .value { font-size: 28px; font-weight: bold; margin-top: 5px; }
  .card .sub { color: #888; font-size: 13px; margin-top: 3px; }
  .aug { color: %(aug)s; }
  .noaug { color: %(noaug)s; }
  .accent { color: %(accent)s; }
  .chart { background: %(card)s; border-radius: 10px; padding: 15px; margin: 15px 0; text-align: center; }
  .chart img { max-width: 100%%; border-radius: 6px; }
  table { width: 100%%; border-collapse: collapse; margin: 10px 0; }
  th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid %(grid)s; }
  th { color: %(accent)s; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; }
  td { font-size: 14px; }
  .conclusion { background: linear-gradient(135deg, #16213e, #1a1a40); border: 1px solid %(accent)s40; border-radius: 12px; padding: 25px; margin: 30px 0; }
  .conclusion h2 { border: none; margin-top: 0; }
  .methodology { background: %(card)s; border-radius: 10px; padding: 20px; margin: 20px 0; font-size: 13px; color: #aaa; }
  .methodology h3 { color: %(accent)s; font-size: 15px; margin-bottom: 10px; }
  .tip { position: relative; cursor: help; border-bottom: 1px dotted #888; }
  .tip .tiptext { visibility: hidden; background: #0d1117; color: #e0e0e0; border: 1px solid %(accent)s; border-radius: 6px; padding: 8px 12px; font-size: 12px; line-height: 1.5; position: absolute; z-index: 10; bottom: 125%%; left: 50%%; transform: translateX(-50%%); width: 280px; text-align: left; box-shadow: 0 4px 12px rgba(0,0,0,0.4); pointer-events: none; }
  .tip:hover .tiptext { visibility: visible; }
  .methodology ul { margin-left: 20px; }
  .methodology li { margin: 5px 0; }
  .coming-soon { text-align: center; padding: 100px 40px; }
  .coming-soon h2 { border: none; font-size: 32px; }
  .coming-soon p { color: #888; font-size: 16px; margin-top: 15px; }
</style>
</head>
<body>

<div class="nav">
  <h1>Aug Misattribution</h1>
  <a href="/" class="{{ 'active' if active == 'dk' else '' }}">Unholy DK</a>
  <a href="/dh" class="{{ 'active' if active == 'dh' else '' }}">Devourer DH</a>
  <a href="/lock" class="{{ 'active' if active == 'lock' else '' }}">Demo Lock</a>
  <a href="/aug" class="{{ 'active' if active == 'aug' else '' }}">Aug Evoker</a>
</div>

<div class="content">
{{ content | safe }}
</div>

</body>
</html>""" % STYLE


@app.route("/")
def dk_page():
    data = get_dk_data()
    stats = data["stats"]
    charts = data["charts"]
    bd = data["breakdown"]
    ps = data["pullsize"]

    content = _render_dk(stats, charts, bd, ps)
    return render_template_string(BASE_TEMPLATE, content=content, active="dk")


@app.route("/dh")
def dh_page():
    content = """
    <div class="coming-soon">
      <h2>Devourer DH Analysis</h2>
      <p>Coming soon. Will analyze DH damage patterns with and without Aug to compare against DK findings.</p>
      <p style="margin-top:10px; color:#666;">DH is more skill/routing-dependent, so controlling for player quality will be important.</p>
    </div>"""
    return render_template_string(BASE_TEMPLATE, content=content, active="dh")


@app.route("/lock")
def lock_page():
    data = get_lock_data()
    stats = data["stats"]
    charts = data["charts"]
    bd = data["breakdown"]

    content = _render_lock(stats, charts, bd)
    return render_template_string(BASE_TEMPLATE, content=content, active="lock")


@app.route("/aug")
def aug_page():
    content = """
    <div class="coming-soon">
      <h2>Aug Evoker Perspective</h2>
      <p>Coming soon. This analysis keeps Aug constant and compares how the Aug's own logged damage
         changes based on DPS partners (DK vs DH vs Lock).</p>
      <p style="margin-top:10px; color:#666;">If WCL misattributes more from certain classes,
         the Aug's logged damage should be lower when paired with those classes.</p>
    </div>"""
    return render_template_string(BASE_TEMPLATE, content=content, active="aug")


def _render_dk(stats, charts, bd, ps):
    """Render the full DK analysis page content."""
    from analyze import generate_breakdown_html, _generate_pullsize_html, _conclusion_breakdown

    # Summary cards
    html = f"""
<h2 style="border:none; margin-top:0;">Unholy DK — Midnight Season 1</h2>
<p class="subtitle">Top 400 rankings per dungeon across all regions</p>

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
    <div class="label">After Pull Size + Key Control</div>
    <div class="value accent">{ps['regression_aug_dps']:+,.0f}</div>
    <div class="sub">{ps['regression_aug_pct']:+.1f}% (residual misattribution)</div>
  </div>
</div>
"""

    # DPS distributions
    html += f"""
<h2>DPS Distributions</h2>
<div class="chart"><img src="data:image/png;base64,{charts['distributions']}"></div>
"""

    # Buff frequency
    nice_names = {
        "mark_of_the_wild": "Mark of the Wild",
        "mystic_touch": "Mystic Touch",
        "chaos_brand": "Chaos Brand",
        "battle_shout": "Battle Shout",
        "skyfury": "Skyfury (incl. Windfury)",
    }
    buff_rows = ""
    for bn, freq in stats["buff_freq"].items():
        mult = BUFF_MULTIPLIERS[bn]
        buff_rows += f"""<tr><td>{nice_names.get(bn, bn)}</td><td>{freq['aug']:.1f}%</td><td>{freq['noaug']:.1f}%</td><td>+{(mult-1)*100:.1f}%</td></tr>"""

    html += f"""
<h2>Buff Frequency</h2>
<p style="color:#888; font-size:13px; margin-bottom:10px;">
  Aug comps typically bring MotW + Mystic Touch + Chaos Brand.
  Non-aug comps typically bring Battle Shout + Skyfury (± Mystic Touch).
</p>
<div class="chart"><img src="data:image/png;base64,{charts['buff_freq']}"></div>
<table>
  <thead><tr><th>Buff</th><th>Aug comps</th><th>No-Aug comps</th><th>DPS effect</th></tr></thead>
  <tbody>{buff_rows}</tbody>
</table>
<p style="color:#888; font-size:12px; margin-top:5px;">
  Average buff multiplier — Aug: {stats['aug_buff_mult']:.4f}x | No-Aug: {stats['noaug_buff_mult']:.4f}x
</p>
"""

    # Per dungeon
    dungeon_rows = ""
    for d in stats["dungeon_stats"]:
        color = "#6C5CE7" if d["delta"] > 0 else "#E17055"
        dungeon_rows += f"""<tr><td>{d['dungeon']}</td><td style="color:{color}">{d['delta']:+,.0f}</td><td style="color:{color}">{d['pct']:+.1f}%</td><td>{d['n_aug']}</td><td>{d['n_noaug']}</td></tr>"""

    html += f"""
<h2>Per-Dungeon Breakdown</h2>
<div class="chart"><img src="data:image/png;base64,{charts['per_dungeon']}"></div>
<table>
  <thead><tr><th>Dungeon</th><th>DPS Delta</th><th>%</th><th>n (aug)</th><th>n (no-aug)</th></tr></thead>
  <tbody>{dungeon_rows}</tbody>
</table>
"""

    # Key level
    kl_rows = ""
    for kl in stats["kl_stats"]:
        color = "#6C5CE7" if kl["delta"] > 0 else "#E17055"
        kl_rows += f"""<tr><td>+{kl['key']}</td><td style="color:{color}">{kl['delta']:+,.0f}</td><td style="color:{color}">{kl['pct']:+.1f}%</td><td>{kl['n_aug']}</td><td>{kl['n_noaug']}</td></tr>"""

    html += f"""
<h2>Key Level Matched</h2>
<div class="chart"><img src="data:image/png;base64,{charts['key_level']}"></div>
<table>
  <thead><tr><th>Key Level</th><th>DPS Delta</th><th>%</th><th>n (aug)</th><th>n (no-aug)</th></tr></thead>
  <tbody>{kl_rows}</tbody>
</table>
"""

    # Comp comparison
    html += f"""
<h2>Comp Archetype Comparison</h2>
<div class="chart"><img src="data:image/png;base64,{charts['comp']}"></div>
"""

    # Breakdown sections
    if bd:
        html += generate_breakdown_html(charts, bd)

    # Pull size decomposition
    html += _render_pullsize_decomposition(ps)

    # Conclusion
    html += f"""
<div class="conclusion">
  <h2>Summary</h2>
  <p style="font-size:16px; line-height:1.7;">
    After normalizing for raid buffs, Unholy DKs with Aug show
    <strong style="color:{STYLE['accent']}">{stats['norm_delta']:+,.0f} DPS ({stats['norm_pct']:+.1f}%)</strong>
    higher personal DPS than DKs without Aug.
  </p>
  <p style="font-size:14px; line-height:1.7; margin-top:10px; color:#aaa;">
    After additionally controlling for pull size (AoE/ST ratio) and key level,
    the residual is <strong>{ps['regression_aug_dps']:+,.0f} DPS ({ps['regression_aug_pct']:+.1f}%)</strong>.
    This represents an upper bound on actual misattribution — player skill bias
    and other unmeasured factors may still contribute.
  </p>
  {_conclusion_breakdown(bd) if bd else ''}
</div>

<div class="methodology">
  <h3>Methodology</h3>
  <ul>
    <li>Data: Top 400 Unholy DK rankings per dungeon from WarcraftLogs API (characterRankings), across all regions.</li>
    <li>Buff normalization: Each DK's logged DPS is divided by the multiplicative product of all raid buffs present.
        MotW=+3%, Mystic Touch=+2.85%, Chaos Brand=+1.3%, Battle Shout=+5%, Skyfury=+3%.</li>
    <li>Pull size control: AoE/ST ratio (Epidemic+Graveyard)/(Death Coil+Necrotic Coil) used as proxy for pull size.</li>
    <li>Regression: normalized_dps ~ has_aug + aoe_st_ratio + key_level (OLS).</li>
    <li>Caveats: Buff multipliers are estimates. Player skill selection bias exists. Pull size proxy is imperfect.</li>
  </ul>
</div>
"""
    return html


def _render_lock(stats, charts, bd):
    """Render the full Demo Lock analysis page content."""
    html = f"""
<h2 style="border:none; margin-top:0;">Demo Lock — Midnight Season 1</h2>
<p class="subtitle">Top 400 rankings per dungeon across all regions (Demonology spec)</p>

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
    <div class="sub">~{abs(stats['norm_delta']):,.0f} DPS upper bound</div>
  </div>
</div>
"""

    # DPS distributions
    html += f"""
<h2>DPS Distributions</h2>
<div class="chart"><img src="data:image/png;base64,{charts['distributions']}"></div>
"""

    # Per dungeon
    dungeon_rows = ""
    for d in stats["dungeon_stats"]:
        color = "#6C5CE7" if d["delta"] > 0 else "#E17055"
        dungeon_rows += f"""<tr><td>{d['dungeon']}</td><td style="color:{color}">{d['delta']:+,.0f}</td><td style="color:{color}">{d['pct']:+.1f}%</td><td>{d['n_aug']}</td><td>{d['n_noaug']}</td></tr>"""

    html += f"""
<h2>Per-Dungeon Breakdown</h2>
<div class="chart"><img src="data:image/png;base64,{charts['per_dungeon']}"></div>
<table>
  <thead><tr><th>Dungeon</th><th>DPS Delta</th><th>%</th><th>n (aug)</th><th>n (no-aug)</th></tr></thead>
  <tbody>{dungeon_rows}</tbody>
</table>
"""

    # Key level
    kl_rows = ""
    for kl in stats["kl_stats"]:
        color = "#6C5CE7" if kl["delta"] > 0 else "#E17055"
        kl_rows += f"""<tr><td>+{kl['key']}</td><td style="color:{color}">{kl['delta']:+,.0f}</td><td style="color:{color}">{kl['pct']:+.1f}%</td><td>{kl['n_aug']}</td><td>{kl['n_noaug']}</td></tr>"""

    html += f"""
<h2>Key Level Matched</h2>
<div class="chart"><img src="data:image/png;base64,{charts['key_level']}"></div>
<table>
  <thead><tr><th>Key Level</th><th>DPS Delta</th><th>%</th><th>n (aug)</th><th>n (no-aug)</th></tr></thead>
  <tbody>{kl_rows}</tbody>
</table>
"""

    # Breakdown sections
    if bd:
        html += _render_lock_breakdown(charts, bd)

    # Conclusion
    html += _render_lock_conclusion(stats, bd)

    return html


def _render_lock_breakdown(charts, bd):
    """Render the Lock damage breakdown section."""
    cs = bd["cat_stats"]
    n_aug = bd["n_aug"]
    n_noaug = bd["n_noaug"]

    total_delta = cs["pet"]["delta"] + cs["player"]["delta"]

    cat_table_rows = ""
    for cat in ["pet", "player"]:
        s = cs[cat]
        share = s["delta"] / total_delta * 100 if total_delta else 0
        color = "#6C5CE7" if s["delta"] > 0 else "#E17055"
        label = "Pet (Demons)" if cat == "pet" else "Player (Direct)"
        cat_table_rows += f"""
        <tr>
            <td>{label}</td>
            <td>{s['aug_pct']:.1f}%</td>
            <td>{s['noaug_pct']:.1f}%</td>
            <td>{s['aug_dps']:,.0f}</td>
            <td>{s['noaug_dps']:,.0f}</td>
            <td style="color:{color}">{s['delta']:+,.0f}</td>
            <td style="color:{color}">{s['pct']:+.1f}%</td>
            <td>{share:.0f}%</td>
        </tr>"""

    html = f"""
<h2>Damage Breakdown Analysis</h2>
<p style="color:#888; font-size:13px; margin-bottom:10px;">
  Analyzing {n_aug + n_noaug} per-fight ability breakdowns ({n_aug} aug, {n_noaug} no-aug).
  Demo Lock damage is ~80% pet/demon damage, making pet misattribution the primary concern.
  All DPS values are buff-normalized.
</p>

<div class="chart"><img src="data:image/png;base64,{charts.get('lock_category', '')}"></div>

<table>
  <thead><tr>
    <th>Category</th><th>Aug %</th><th>No-Aug %</th>
    <th>Aug DPS</th><th>No-Aug DPS</th><th>Δ DPS</th><th>Δ%</th><th>Share of Δ</th>
  </tr></thead>
  <tbody>{cat_table_rows}</tbody>
</table>
"""

    # Pet sub-categories
    pet_subs = bd.get("pet_subcats")
    if pet_subs:
        from analyze_lock import PET_SUBCATS, SUBCAT_ORDER
        pet_sub_rows = ""
        total_pet_delta = 0
        subcat_names = SUBCAT_ORDER
        for name in subcat_names:
            a = pet_subs["aug"].get(name, 0)
            n = pet_subs["noaug"].get(name, 0)
            delta = a - n
            pct = delta / n * 100 if n > 0 else 0
            total_pet_delta += delta
            color = "#6C5CE7" if delta > 0 else "#E17055"
            pet_sub_rows += f"""
            <tr>
                <td>{name}</td>
                <td>{a:,.0f}</td>
                <td>{n:,.0f}</td>
                <td style="color:{color}">{delta:+,.0f}</td>
                <td style="color:{color}">{pct:+.1f}%</td>
            </tr>"""
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

        html += f"""
<h2>Pet Damage Sub-Categories</h2>
<p style="color:#888; font-size:13px; margin-bottom:10px;">
  Breaking down pet damage by demon type. Felguard (Main Pet) includes the permanent Felguard
  with its randomly generated name (like DK's main ghoul). Diabolic Ritual damage is consolidated
  by WCL — individual ritual demons (Pit Lord, Mother of Chaos, etc.) are not broken out separately.
  Dominion of Argus sub-types (Antoran Jailer, Inquisitor, Alythess, Sacrolash) log 0 damage — their
  effects are rolled into the main Dominion of Argus entry.
</p>

<div class="chart"><img src="data:image/png;base64,{charts.get('lock_subcats', '')}"></div>

<table>
  <thead><tr>
    <th>Demon Source</th><th>Aug DPS</th><th>No-Aug DPS</th><th>Δ DPS</th><th>Δ%</th>
  </tr></thead>
  <tbody>{pet_sub_rows}</tbody>
</table>
"""

    # Per-ability chart and table
    ABILITY_TOOLTIPS = {
        "Diabolic Ritual": "Diabolist hero talent. Summons a Pit Lord, Mother of Chaos, or Overlord on a cycle. All do uncapped AoE. WCL consolidates all sub-demons into this one entry.",
        "Dominion of Argus": "Diabolist hero talent. Summons Legion generals (Antoran Jailer, Inquisitor, Alythess, Sacrolash). Uncapped AoE. Sub-types log 0 damage separately — all rolled into this entry.",
        "Summon Demonic Tyrant": "Major cooldown. Extends active demons and does uncapped AoE via Burning Cleave talent. Damage scales with number of active demons.",
        "Call Dreadstalkers": "Summons 2 Dreadstalkers that cleave nearby targets. Target-capped cleave.",
        "Wild Imp (Hand of Gul'dan)": "Imps summoned by Hand of Gul'dan. Cleave via To Hell and Back talent (target-capped). Can be consumed by Implosion for AoE burst.",
        "Wild Imp (Inner Demons/To Hell and Back)": "Imps passively summoned by Inner Demons talent + To Hell and Back cleave. Target-capped. Can be consumed by Implosion.",
        "Implosion": "Consumes all active Wild Imps, dealing AoE damage per imp consumed. Target-capped. Higher Implosion DPS means fewer imps alive to do passive damage.",
        "Hand of Gul'dan": "Core ability. Impact damage is uncapped AoE, also summons Wild Imps.",
        "Summon Charhound": "Summoned demon that does target-capped cleave damage.",
        "Shadow Bolt": "Single-target filler spell. Cast when no other priority abilities are available.",
        "Demonbolt": "Single-target filler spell (empowered). Cast during Demonic Core procs.",
        "Grimoire: Imp Lord": "Grimoire talent summon. Stronger imp that does additional damage.",
    }

    ability_rows = bd.get("ability_rows", [])
    ability_table_rows = ""
    for r in ability_rows[:15]:
        color = "#6C5CE7" if r["delta"] > 0 else "#E17055"
        cat_color = {"pet": "#e74c3c", "player": "#3498db"}.get(r["cat"], "#aaa")
        pct_str = f"{r['pct']:+.1f}%" if abs(r["pct"]) < 500 else "new"
        tip = ABILITY_TOOLTIPS.get(r["name"], "")
        name_html = f"""<span class="tip">{r['name']}<span class="tiptext">{tip}</span></span>""" if tip else r["name"]
        ability_table_rows += f"""
        <tr>
            <td>{name_html}</td>
            <td><span style="color:{cat_color}">{r['cat']}</span></td>
            <td>{r['aug']:,.0f} <span style="color:#666;font-size:11px">(n={r.get('aug_n','-')})</span></td>
            <td>{r['noaug']:,.0f} <span style="color:#666;font-size:11px">(n={r.get('noaug_n','-')})</span></td>
            <td style="color:{color}">{r['delta']:+,.0f}</td>
            <td style="color:{color}">{pct_str}</td>
        </tr>"""

    html += f"""
<h2>Per-Ability DPS Delta</h2>
<p style="color:#888; font-size:13px; margin-bottom:10px;">
  Individual ability comparison (buff-normalized DPS). Hover ability names for descriptions.
  <span style="color:#e74c3c">Red = Pet/Demon</span>,
  <span style="color:#3498db">Blue = Player/Direct</span>.
</p>

<div class="chart"><img src="data:image/png;base64,{charts.get('lock_abilities', '')}"></div>

<table>
  <thead><tr>
    <th>Ability</th><th>Type</th><th>Aug DPS (n)</th><th>No-Aug DPS (n)</th><th>Δ DPS</th><th>Δ%</th>
  </tr></thead>
  <tbody>{ability_table_rows}</tbody>
</table>
"""

    # Uncapped vs Capped AoE analysis
    aoe = bd.get("aoe_analysis")
    if aoe:
        html += _render_lock_aoe_analysis(charts, bd)

    # Wild Imp deep dive
    imp = bd.get("imp_analysis")
    if imp:
        html += _render_lock_imp_analysis(bd)

    return html



def _render_lock_aoe_analysis(charts, bd):
    """Render uncapped vs capped AoE comparison."""
    aoe = bd["aoe_analysis"]
    uncapped_abs = bd["uncapped_abilities"]
    capped_abs = bd["capped_abilities"]
    st_abs = bd["st_abilities"]

    NICE_NAMES = {
        "Summon Demonic Tyrant": "Demonic Tyrant",
        "Diabolic Ritual": "Diabolic Ritual",
        "Dominion of Argus": "Dominion of Argus",
        "Hand of Gul'dan": "Hand of Gul'dan",
        "Wild Imp (Hand of Gul'dan)": "Wild Imp (HoG)",
        "Wild Imp (Inner Demons/To Hell and Back)": "Wild Imp (ID/THB)",
        "Call Dreadstalkers": "Dreadstalkers",
        "Implosion": "Implosion",
        "Summon Charhound": "Charhound",
        "Shadow Bolt": "Shadow Bolt",
        "Demonbolt": "Demonbolt",
    }

    def make_rows(abilities, category):
        rows = ""
        for ab in abilities:
            a = aoe[category][ab]["aug"]
            n = aoe[category][ab]["noaug"]
            delta = a - n
            pct = delta / n * 100 if n > 0 else 0
            color = "#6C5CE7" if delta > 0 else "#E17055"
            rows += f"""<tr><td>{NICE_NAMES.get(ab, ab)}</td><td>{a:,.0f}</td><td>{n:,.0f}</td><td style="color:{color}">{delta:+,.0f}</td><td style="color:{color}">{pct:+.1f}%</td></tr>"""
        return rows

    uc_a = aoe["uncapped"]["_total_aug"]
    uc_n = aoe["uncapped"]["_total_noaug"]
    cc_a = aoe["capped"]["_total_aug"]
    cc_n = aoe["capped"]["_total_noaug"]
    st_a = aoe["st"]["_total_aug"]
    st_n = aoe["st"]["_total_noaug"]

    return f"""
<h2>Uncapped vs Capped AoE Analysis</h2>
<p style="color:#888; font-size:13px; margin-bottom:10px;">
  If misattribution were a flat multiplier, all ability types should be inflated equally.
  Splitting abilities by their AoE target cap reveals whether the delta comes from
  gameplay/routing differences (bigger pulls) or actual misattribution.
</p>

<div class="chart"><img src="data:image/png;base64,{charts.get('lock_aoe', '')}"></div>

<div class="cards">
  <div class="card">
    <div class="label">Uncapped AoE</div>
    <div class="value" style="color:#6C5CE7">{(uc_a - uc_n) / uc_n * 100:+.1f}%</div>
    <div class="sub">Tyrant, Diabolic Ritual, Dominion, HoG impact</div>
  </div>
  <div class="card">
    <div class="label">Capped/Cleave</div>
    <div class="value" style="color:#E17055">{(cc_a - cc_n) / cc_n * 100:+.1f}%</div>
    <div class="sub">Wild Imps, Dreadstalkers, Implosion, Charhound</div>
  </div>
  <div class="card">
    <div class="label">ST Filler</div>
    <div class="value accent">{(st_a - st_n) / st_n * 100:+.1f}%</div>
    <div class="sub">Shadow Bolt + Demonbolt</div>
  </div>
</div>

<h3>Uncapped AoE (scales infinitely with pull size)</h3>
<table>
  <thead><tr><th>Ability</th><th>Aug DPS</th><th>No-Aug DPS</th><th>Δ DPS</th><th>Δ%</th></tr></thead>
  <tbody>{make_rows(uncapped_abs, "uncapped")}
    <tr style="border-top:2px solid {STYLE['grid']};font-weight:bold"><td>Total</td><td>{uc_a:,.0f}</td><td>{uc_n:,.0f}</td><td style="color:#6C5CE7">{uc_a-uc_n:+,.0f}</td><td style="color:#6C5CE7">{(uc_a-uc_n)/uc_n*100:+.1f}%</td></tr>
  </tbody>
</table>

<h3>Capped/Cleave (target-capped, doesn't scale with pull size)</h3>
<table>
  <thead><tr><th>Ability</th><th>Aug DPS</th><th>No-Aug DPS</th><th>Δ DPS</th><th>Δ%</th></tr></thead>
  <tbody>{make_rows(capped_abs, "capped")}
    <tr style="border-top:2px solid {STYLE['grid']};font-weight:bold"><td>Total</td><td>{cc_a:,.0f}</td><td>{cc_n:,.0f}</td><td style="color:#E17055">{cc_a-cc_n:+,.0f}</td><td style="color:#E17055">{(cc_a-cc_n)/cc_n*100:+.1f}%</td></tr>
  </tbody>
</table>
"""


def _render_lock_imp_analysis(bd):
    """Render Wild Imp deep dive section."""
    imp = bd["imp_analysis"]
    imp_by_dungeon = bd.get("imp_by_dungeon", [])

    aug_imp = imp["aug"]["imp_dps"]
    noaug_imp = imp["noaug"]["imp_dps"]
    imp_delta = aug_imp - noaug_imp
    imp_pct = imp_delta / noaug_imp * 100


    dungeon_rows = ""
    for g in imp_by_dungeon:
        color = "#6C5CE7" if g["delta"] > 0 else "#E17055"
        dungeon_rows += f"""<tr><td>{g['dungeon']}</td><td>{g['aug']:,.0f}</td><td>{g['noaug']:,.0f}</td><td style="color:{color}">{g['delta']:+,.0f}</td><td style="color:{color}">{g['pct']:+.1f}%</td><td>{g['n_aug']}</td><td>{g['n_noaug']}</td></tr>"""

    return f"""
<h2>Wild Imp Deep Dive</h2>
<p style="color:#888; font-size:13px; margin-bottom:10px;">
  Wild Imps cleave via To Hell and Back, so they should do <em>more</em> damage in bigger pulls — yet
  they show a large <em>negative</em> delta. This section investigates why.
</p>

<div class="cards">
  <div class="card">
    <div class="label">Wild Imp DPS (Aug)</div>
    <div class="value accent">{aug_imp:,.0f}</div>
    <div class="sub">{imp['aug']['imp_pct']:.1f}% of total damage</div>
  </div>
  <div class="card">
    <div class="label">Wild Imp DPS (No-Aug)</div>
    <div class="value accent">{noaug_imp:,.0f}</div>
    <div class="sub">{imp['noaug']['imp_pct']:.1f}% of total damage</div>
  </div>
  <div class="card">
    <div class="label">Imp Delta</div>
    <div class="value" style="color:#E17055">{imp_delta:+,.0f}</div>
    <div class="sub">{imp_pct:+.1f}% — less damage in aug groups</div>
  </div>
  <div class="card">
    <div class="label">Other Lock Pets</div>
    <div class="value" style="color:#6C5CE7">+2-5%</div>
    <div class="sub">Tyrant, Dreadstalkers, Ritual all positive</div>
  </div>
</div>

<p style="color:#ccc; font-size:14px; line-height:1.7; margin:15px 0;">
  <strong style="color:{STYLE['accent']}">Key mystery — why only Wild Imps?</strong>
  The -10 to -12% imp delta is NOT explained by Ebon Might reattribution. If WCL were stripping
  Ebon Might from pets, <em>all</em> pets would show -8 to -10% — but Tyrant (+4.9%), Dreadstalkers (+3.6%),
  and Diabolic Ritual (+3.8%) are all positive. Unholy DK pets (Army +0.6%, Ghoul +3.5%) are also flat/positive.
</p>
<p style="color:#999; font-size:13px; line-height:1.6; margin:10px 0;">
  Something specific to Wild Imps is causing this deficit. Imps are unique in that they spawn in large batches
  (6 per Hand of Gul'dan, passive spawns from Inner Demons), are short-lived (~15-20s), and many instances exist
  simultaneously. This may cause a WCL attribution anomaly where imp damage is being over-credited to the Aug Evoker.
</p>
<p style="color:#999; font-size:13px; line-height:1.6; margin:10px 0;">
  <strong>Investigation ongoing:</strong> We're collecting Aug Evoker damage data from these same reports to see
  if the Aug is credited more damage when paired with Lock (imp-heavy) vs DK. If so, it would confirm
  over-attribution from imps specifically.
</p>

<h3>Wild Imp DPS by Dungeon</h3>
<p style="color:#888; font-size:13px; margin-bottom:10px;">
  The negative imp delta is consistent across all dungeons, not concentrated in specific ones.
</p>
<table>
  <thead><tr><th>Dungeon</th><th>Aug DPS</th><th>No-Aug DPS</th><th>Δ DPS</th><th>Δ%</th><th>n aug</th><th>n no-aug</th></tr></thead>
  <tbody>{dungeon_rows}</tbody>
</table>
"""


def _render_lock_conclusion(stats, bd):
    """Render the Lock conclusion section."""
    html = f"""
<div class="conclusion">
  <h2>Summary</h2>
  <p style="font-size:16px; line-height:1.7;">
    After normalizing for raid buffs, Demo Locks with Aug show
    <strong style="color:{STYLE['accent']}">{stats['norm_delta']:+,.0f} DPS ({stats['norm_pct']:+.1f}%)</strong>
    higher personal DPS than Locks without Aug.
  </p>"""

    if bd:
        cs = bd["cat_stats"]
        aoe = bd.get("aoe_analysis")
        imp = bd.get("imp_analysis")
        uc_pct = ""
        cc_pct = ""
        if aoe:
            uc_a = aoe["uncapped"]["_total_aug"]
            uc_n = aoe["uncapped"]["_total_noaug"]
            cc_a = aoe["capped"]["_total_aug"]
            cc_n = aoe["capped"]["_total_noaug"]
            uc_pct = f"{(uc_a - uc_n) / uc_n * 100:+.1f}%"
            cc_pct = f"{(cc_a - cc_n) / cc_n * 100:+.1f}%"
        html += f"""
  <p style="font-size:14px; line-height:1.7; margin-top:15px; color:#ccc;">
    <strong style="color:{STYLE['accent']}">Key finding — uncapped vs capped AoE split:</strong><br>
    Uncapped AoE (Tyrant, Diabolic Ritual, Dominion, HoG impact): <strong>{uc_pct}</strong><br>
    Capped/cleave (Wild Imps, Dreadstalkers, Implosion, Charhound): <strong>{cc_pct}</strong>
  </p>
  <p style="font-size:13px; line-height:1.6; margin-top:10px; color:#999;">
    Wild Imps show -10 to -12% in aug groups — but this is <strong>NOT</strong> explained by
    Ebon Might reattribution. If it were, all pets would show similar negatives. Instead, Tyrant (+4.9%),
    Dreadstalkers (+3.6%), Diabolic Ritual (+3.8%), and all DK pets (Army +0.6%, Ghoul +3.5%)
    are flat or positive.
  </p>
  <p style="font-size:13px; line-height:1.6; margin-top:10px; color:#999;">
    Something specific to Wild Imps — likely related to their high-quantity, short-lived,
    simultaneous-instance nature — is causing WCL to over-credit imp damage to the Aug Evoker.
    We're collecting Aug perspective data to confirm whether Aug gets credited more damage
    when paired with Lock vs DK.
  </p>
  <p style="font-size:13px; line-height:1.6; margin-top:10px; color:#999;">
    The positive uncapped AoE delta (+6%) and flat ST filler (+0.6-1.8%) suggest aug groups may
    pull slightly bigger, but the magnitude is modest — not the 15-20% that would be needed
    to explain the full pattern through pull size alone.
  </p>"""

    html += """
</div>

<div class="methodology">
  <h3>Methodology</h3>
  <ul>
    <li>Data: Top 400 Demo Lock rankings per dungeon from WarcraftLogs API (characterRankings), across all regions.</li>
    <li>Buff normalization: Same approach as DK — each Lock's logged DPS is divided by the multiplicative product of all raid buffs present.</li>
    <li>Damage categorization: Pet abilities include all demon summons (Tyrant, Dreadstalkers, Wild Imps, Charhound, Diabolic Ritual, Dominion of Argus, Grimoire demons). Player abilities include Hand of Gul'dan, Shadow Bolt, Demonbolt, Implosion.</li>
    <li>Caveats: Smaller breakdown sample than DK. Buff multipliers are estimates using DK values (Lock has similar phys/magic split). No clean AoE/ST proxy exists for Demo Lock unlike DK.</li>
  </ul>
</div>
"""
    return html


def _render_pullsize_decomposition(ps):
    """Render the pull size decomposition section."""
    html = f"""
<h2>Decomposing the 3.9% Delta</h2>
<p style="color:#888; font-size:13px; margin-bottom:15px;">
  Using AoE/ST ratio as a proxy for pull size and OLS regression to separate the contributions.
</p>

<div class="cards">
  <div class="card">
    <div class="label">Pull Size Effect</div>
    <div class="value" style="color:#E17055">{ps['pullsize_contribution_pct']:.1f}%</div>
    <div class="sub">~{ps['pullsize_contribution_dps']:,.0f} DPS from bigger pulls</div>
  </div>
  <div class="card">
    <div class="label">Key Level Effect</div>
    <div class="value" style="color:#E17055">{ps['keylevel_contribution_pct']:.1f}%</div>
    <div class="sub">~{ps['keylevel_contribution_dps']:,.0f} DPS from higher keys</div>
  </div>
  <div class="card">
    <div class="label">Residual (Misattribution + Skill)</div>
    <div class="value" style="color:{STYLE['accent']}">{ps['regression_aug_pct']:+.1f}%</div>
    <div class="sub">~{ps['regression_aug_dps']:,.0f} DPS unexplained</div>
  </div>
</div>

<table>
  <thead><tr><th>Control Method</th><th>Aug Effect (DPS)</th><th>Aug Effect (%)</th></tr></thead>
  <tbody>
    <tr><td>Uncontrolled (buff-normalized only)</td><td>{ps['uncontrolled_dps']:+,.0f}</td><td>{ps['uncontrolled_pct']:+.1f}%</td></tr>
    <tr><td>+ Pull size control (AoE/ST ratio)</td><td>{ps['ratio_only_dps']:+,.0f}</td><td>{ps['ratio_only_pct']:+.1f}%</td></tr>
    <tr><td>+ Pull size + Key level control</td><td>{ps['regression_aug_dps']:+,.0f}</td><td>{ps['regression_aug_pct']:+.1f}%</td></tr>
  </tbody>
</table>

<h3>Pull Size Buckets (AoE/ST Ratio Quintiles)</h3>
<p style="color:#888; font-size:13px; margin-bottom:10px;">
  Entries bucketed by their AoE/ST ratio. Within each bucket, comparing aug vs no-aug DPS.
</p>
<table>
  <thead><tr><th>AoE/ST Range</th><th>Aug DPS</th><th>No-Aug DPS</th><th>Δ DPS</th><th>Δ%</th><th>n aug</th><th>n no-aug</th></tr></thead>
  <tbody>"""

    for b in ps["buckets"]:
        color = "#6C5CE7" if b["delta"] > 0 else "#E17055"
        html += f"""<tr><td>{b['label']}</td><td>{b['aug_dps']:,.0f}</td><td>{b['noaug_dps']:,.0f}</td><td style="color:{color}">{b['delta']:+,.0f}</td><td style="color:{color}">{b['pct']:+.1f}%</td><td>{b['n_aug']}</td><td>{b['n_noaug']}</td></tr>"""

    html += """</tbody></table>"""
    return html


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
