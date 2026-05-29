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
    content = """
    <div class="coming-soon">
      <h2>Demo Lock Analysis</h2>
      <p>Coming soon. Demo Lock's uncapped AoE pets (Tyrant via Burning Cleave, Inquisitor via Mind Sear)
         are strong candidates for misattribution.</p>
      <p style="margin-top:10px; color:#666;">Expected key level skew will need careful control.</p>
    </div>"""
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
