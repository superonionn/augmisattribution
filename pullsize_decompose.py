"""Decompose the aug vs no-aug DPS delta into pull-size effect vs stripping effect.

Logic: If aug groups pull bigger (MW > RSham healing), AoE abilities will be higher
regardless of stripping. By matching on AoE/ST ratio (pull-size proxy), we can isolate
the pure stripping effect from the pull-size effect.
"""
import json
import sys
import statistics
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

import numpy as np

from analyze import compute_buff_multiplier

DK_AOE = {"Graveyard", "Epidemic", "Death and Decay", "Pestilence", "Raise Abomination"}
DK_ST = {"Scourge Strike", "Death Coil", "Necrotic Coil", "Soul Reaper"}
DK_PET = {"Raise Dead", "未知目标", "Sweeping Claws", "Infected Claws", "Lesser Ghoul",
           "Claw", "Halazzi's Claws"}
# Merge these pet names into a single "Ghoul" category
PET_MERGE = {"Raise Dead": "Ghoul", "未知目标": "Ghoul", "Sweeping Claws": "Ghoul",
             "Infected Claws": "Ghoul", "Claw": "Ghoul", "Halazzi's Claws": "Ghoul"}


def classify_comp(comp):
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


def load_data():
    with open("data/breakdowns.json", encoding="utf-8") as f:
        dk_data = json.load(f)
    with open("data/rankings.json", encoding="utf-8") as f:
        dk_rankings = json.load(f)

    comp_lookup = {}
    for r in dk_rankings:
        comp_lookup[(r["player"], r["dungeon"])] = r.get("comp", [])

    entries = []
    for e in dk_data:
        comp = comp_lookup.get((e["player"], e["dungeon"]), [])
        tank, healer_spec, dps_partners = classify_comp(comp)
        if tank != "Druid":
            continue
        if e["has_aug"] and healer_spec != "Mistweaver":
            continue
        if not e["has_aug"] and healer_spec != "Restoration":
            continue
        if not e["has_aug"]:
            if "DemonHunter" not in dps_partners and "Warlock" not in dps_partners:
                continue

        bm = compute_buff_multiplier(e["buffs"])
        dur = e["total_damage"] / e["dps"] if e["dps"] > 0 else 0
        if dur <= 0:
            continue

        # Compute per-ability DPS (normalized)
        abilities = {}
        aoe_total = st_total = 0
        for a in e["abilities"]:
            name = PET_MERGE.get(a["name"], a["name"])
            dps_val = a["total"] / bm / dur
            abilities[name] = abilities.get(name, 0) + dps_val
            if a["name"] in DK_AOE:
                aoe_total += dps_val
            elif a["name"] in DK_ST:
                st_total += dps_val

        if st_total < 100:
            continue

        ratio = aoe_total / st_total
        entries.append({
            "has_aug": e["has_aug"],
            "key_level": e["key_level"],
            "norm_dps": e["dps"] / bm,
            "aoe_st_ratio": ratio,
            "aoe_dps": aoe_total,
            "st_dps": st_total,
            "abilities": abilities,
        })

    return entries


def quintile_matched_analysis(entries):
    """Match aug and no-aug runs by AoE/ST quintile, then compare per-ability."""
    aug = [e for e in entries if e["has_aug"]]
    noaug = [e for e in entries if not e["has_aug"]]

    print(f"Comp-controlled entries: {len(aug)} aug (Bear+MW), {len(noaug)} no-aug (Bear+RSham+meta)")

    # Compute quintile bounds from combined data
    all_ratios = sorted(e["aoe_st_ratio"] for e in entries)
    n = len(all_ratios)
    bounds = [all_ratios[int(n * q)] for q in [0, 0.2, 0.4, 0.6, 0.8]] + [all_ratios[-1] + 0.01]

    print(f"\nQuintile bounds: {[f'{b:.2f}' for b in bounds]}")
    print(f"\n{'Quintile':<12} {'AoE/ST':>8} {'Aug n':>6} {'NoAug n':>8} {'Aug DPS':>10} {'NoAug DPS':>10} {'Delta':>8} {'%':>7}")
    print("-" * 75)

    matched_aug = []
    matched_noaug = []

    for qi in range(5):
        lo, hi = bounds[qi], bounds[qi + 1]
        q_aug = [e for e in aug if lo <= e["aoe_st_ratio"] < hi]
        q_noaug = [e for e in noaug if lo <= e["aoe_st_ratio"] < hi]
        if not q_aug or not q_noaug:
            print(f"  Q{qi+1} ({lo:.1f}-{hi:.1f}): skipped (aug={len(q_aug)}, noaug={len(q_noaug)})")
            continue

        aug_dps = statistics.mean(e["norm_dps"] for e in q_aug)
        noaug_dps = statistics.mean(e["norm_dps"] for e in q_noaug)
        delta = aug_dps - noaug_dps
        pct = delta / noaug_dps * 100

        mid = (lo + hi) / 2
        print(f"  Q{qi+1} ({lo:.1f}-{hi:.1f}) {mid:>6.2f}   {len(q_aug):>5}   {len(q_noaug):>7}   "
              f"{aug_dps:>9,.0f}   {noaug_dps:>9,.0f}  {delta:>+7,.0f} {pct:>+6.1f}%")

        matched_aug.extend(q_aug)
        matched_noaug.extend(q_noaug)

    return matched_aug, matched_noaug


def per_ability_pullsize_controlled(aug_entries, noaug_entries):
    """Compare per-ability DPS after matching on pull size quintile."""
    # Just use all matched entries and compare ability means
    def ability_means(entries):
        totals = defaultdict(list)
        for row in entries:
            for name, dps in row["abilities"].items():
                totals[name].append(dps)
        return {n: statistics.mean(v) for n, v in totals.items() if len(v) >= 8}

    aug_ab = ability_means(aug_entries)
    noaug_ab = ability_means(noaug_entries)

    print(f"\nPer-ability delta (pull-size matched via quintile overlap):")
    print(f"  {'Ability':<25} {'Cat':<6} {'Aug':>8} {'NoAug':>8} {'Delta':>8} {'%':>7}")
    print("  " + "-" * 62)

    rows = []
    for name in set(aug_ab) | set(noaug_ab):
        a = aug_ab.get(name, 0)
        n = noaug_ab.get(name, 0)
        if a + n < 300:
            continue
        diff = a - n
        pct = diff / n * 100 if n > 0 else 0
        cat = "aoe" if name in DK_AOE else "st" if name in DK_ST else "pet" if name in DK_PET or name == "Ghoul" else "other"
        if name == "Melee":
            cat = "wf"
        rows.append((name, cat, a, n, diff, pct))

    rows.sort(key=lambda x: -abs(x[4]))
    for name, cat, a, n, diff, pct in rows[:18]:
        print(f"  {name:<25} {cat:<6} {a:>8,.0f} {n:>8,.0f} {diff:>+8,.0f} {pct:>+6.1f}%")

    # Category totals
    cat_aug = defaultdict(float)
    cat_noaug = defaultdict(float)
    for name, cat, a, n, diff, pct in rows:
        cat_aug[cat] += a
        cat_noaug[cat] += n

    print(f"\n  Category totals (pull-size controlled):")
    for cat in ["aoe", "st", "pet", "other", "wf"]:
        a = cat_aug[cat]
        n = cat_noaug[cat]
        if a + n < 100:
            continue
        pct = (a - n) / n * 100 if n else 0
        label = {"aoe": "AoE", "st": "ST", "pet": "Pet/Ghoul", "other": "Other", "wf": "Melee(WF)"}[cat]
        print(f"    {label:<12}: Aug={a:>8,.0f}  NoAug={n:>8,.0f}  Delta={a-n:>+7,.0f} ({pct:>+5.1f}%)")


def regression_decomposition(entries):
    """OLS decomposition: DPS = b0 + b1*has_aug + b2*aoe_st_ratio + b3*key_level."""
    X_aug = np.array([1.0 if e["has_aug"] else 0.0 for e in entries])
    X_ratio = np.array([e["aoe_st_ratio"] for e in entries])
    X_key = np.array([float(e["key_level"]) for e in entries])
    y = np.array([e["norm_dps"] for e in entries])

    noaug_mean = float(np.mean(y[X_aug == 0]))

    # Uncontrolled
    X1 = np.column_stack([np.ones(len(entries)), X_aug])
    b1 = np.linalg.lstsq(X1, y, rcond=None)[0]

    # + pull size
    X2 = np.column_stack([np.ones(len(entries)), X_aug, X_ratio])
    b2 = np.linalg.lstsq(X2, y, rcond=None)[0]

    # + key level
    X3 = np.column_stack([np.ones(len(entries)), X_aug, X_ratio, X_key])
    b3 = np.linalg.lstsq(X3, y, rcond=None)[0]

    raw = float(b1[1])
    after_pull = float(b2[1])
    after_both = float(b3[1])

    print(f"\n{'='*60}")
    print(f"  OLS Decomposition (comp-controlled subset)")
    print(f"{'='*60}")
    print(f"  Raw aug coefficient:          {raw:>+8,.0f} DPS ({raw/noaug_mean*100:>+5.1f}%)")
    print(f"  After controlling pull size:  {after_pull:>+8,.0f} DPS ({after_pull/noaug_mean*100:>+5.1f}%)")
    print(f"  After controlling pull+key:   {after_both:>+8,.0f} DPS ({after_both/noaug_mean*100:>+5.1f}%)")
    print(f"\n  Breakdown:")
    print(f"    Pull size explains:  {raw - after_pull:>+8,.0f} DPS ({(raw-after_pull)/noaug_mean*100:>+5.1f}%)")
    print(f"    Key level explains:  {after_pull - after_both:>+8,.0f} DPS ({(after_pull-after_both)/noaug_mean*100:>+5.1f}%)")
    print(f"    Residual (stripping):{after_both:>+8,.0f} DPS ({after_both/noaug_mean*100:>+5.1f}%)")
    print(f"\n  Interpretation:")
    print(f"    - Pull size: Aug groups (MW healer) can survive bigger pulls")
    print(f"    - Key level: Aug groups tend to push higher keys in this sample")
    print(f"    - Residual: The remaining delta after controlling for both —")
    print(f"      this is the pure under-stripping effect on AoE abilities")

    # Also compute AoE-only regression
    y_aoe = np.array([e["aoe_dps"] for e in entries])
    y_st = np.array([e["st_dps"] for e in entries])

    X_full = np.column_stack([np.ones(len(entries)), X_aug, X_ratio, X_key])
    b_aoe = np.linalg.lstsq(X_full, y_aoe, rcond=None)[0]
    b_st = np.linalg.lstsq(X_full, y_st, rcond=None)[0]

    noaug_aoe_mean = float(np.mean(y_aoe[X_aug == 0]))
    noaug_st_mean = float(np.mean(y_st[X_aug == 0]))

    print(f"\n  AoE vs ST decomposition (fully controlled):")
    print(f"    AoE aug coeff: {float(b_aoe[1]):>+7,.0f} DPS ({float(b_aoe[1])/noaug_aoe_mean*100:>+5.1f}% of noaug AoE)")
    print(f"    ST aug coeff:  {float(b_st[1]):>+7,.0f} DPS ({float(b_st[1])/noaug_st_mean*100:>+5.1f}% of noaug ST)")
    print(f"\n    AoE positive = under-stripping (aug contribution leaking through)")
    print(f"    ST negative = over-stripping (too much taken from DPS, given to Aug)")


if __name__ == "__main__":
    entries = load_data()
    matched_aug, matched_noaug = quintile_matched_analysis(entries)
    per_ability_pullsize_controlled(matched_aug, matched_noaug)
    regression_decomposition(entries)
