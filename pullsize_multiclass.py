"""Pull-size decomposition across all three classes (DK, Lock, DH).
Same methodology: comp-controlled (Bear tank), quintile-matched on AoE/ST ratio.
"""
import json
import sys
import statistics
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

import numpy as np

from analyze import compute_buff_multiplier

# DK abilities
DK_AOE = {"Graveyard", "Epidemic", "Death and Decay", "Pestilence", "Raise Abomination"}
DK_ST = {"Scourge Strike", "Death Coil", "Necrotic Coil", "Soul Reaper"}

# Lock abilities
LOCK_AOE = {"Hand of Gul'dan", "Implosion", "Bilescourge Bombers", "Diabolic Ritual",
            "Doom", "Demonbolt"}
LOCK_ST = {"Shadow Bolt", "Demonbolt", "Soul Strike"}
# Lock pets for AoE/ST proxy
LOCK_AOE_PROXY = {"Hand of Gul'dan", "Implosion", "Diabolic Ritual"}
LOCK_ST_PROXY = {"Shadow Bolt", "Demonbolt"}

# DH abilities (Devourer)
DH_AOE = {"Collapsing Star", "Eradicate", "Voidfall Meteor", "Catastrophe"}
DH_ST = {"Devour", "Consume", "Cull", "Reap"}


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


def load_class_data(class_key):
    """Load breakdowns + rankings for a class."""
    paths = {
        "dk": ("data/breakdowns.json", "data/rankings.json"),
        "lock": ("data/lock_breakdowns.json", "data/lock_rankings.json"),
        "dh": ("data/dh_breakdowns.json", "data/dh_rankings.json"),
    }
    breakdown_path, ranking_path = paths[class_key]

    with open(breakdown_path, encoding="utf-8") as f:
        breakdowns = json.load(f)
    with open(ranking_path, encoding="utf-8") as f:
        rankings = json.load(f)

    comp_lookup = {}
    for r in rankings:
        comp_lookup[(r["player"], r["dungeon"])] = r.get("comp", [])

    return breakdowns, comp_lookup


def get_aoe_st(class_key, abilities_dict):
    """Compute AoE and ST totals for a class."""
    if class_key == "dk":
        aoe_names, st_names = DK_AOE, DK_ST
    elif class_key == "lock":
        aoe_names, st_names = LOCK_AOE_PROXY, LOCK_ST_PROXY
    elif class_key == "dh":
        aoe_names, st_names = DH_AOE, DH_ST
    else:
        return 0, 0

    aoe = sum(v for k, v in abilities_dict.items() if k in aoe_names)
    st = sum(v for k, v in abilities_dict.items() if k in st_names)
    return aoe, st


def run_class_analysis(class_key):
    """Full pull-size decomposition for one class."""
    breakdowns, comp_lookup = load_class_data(class_key)

    # Build entries with comp info
    aug_mw = []       # Aug + Bear + MW
    aug_rsham = []    # Aug + Bear + RSham
    noaug_rsham = []  # NoAug + Bear + RSham + meta DPS

    for e in breakdowns:
        comp = comp_lookup.get((e["player"], e["dungeon"]), [])
        tank, healer_spec, dps_partners = classify_comp(comp)

        # Only Bear tank for controlled comparison
        if tank != "Druid":
            continue

        bm = compute_buff_multiplier(e["buffs"])
        dur = e["total_damage"] / e["dps"] if e["dps"] > 0 else 0
        if dur <= 0:
            continue

        abilities = {}
        for a in e["abilities"]:
            abilities[a["name"]] = a["total"] / bm / dur

        aoe, st = get_aoe_st(class_key, abilities)
        if st < 50:
            continue

        entry = {
            "has_aug": e["has_aug"],
            "key_level": e["key_level"],
            "norm_dps": e["dps"] / bm,
            "aoe_st_ratio": aoe / st if st > 0 else 0,
            "aoe_dps": aoe,
            "st_dps": st,
            "abilities": abilities,
            "healer": healer_spec,
        }

        if e["has_aug"]:
            if healer_spec == "Mistweaver":
                aug_mw.append(entry)
            elif healer_spec == "Restoration":
                aug_rsham.append(entry)
        else:
            if healer_spec == "Restoration":
                # Check for meta DPS partners
                has_meta = ("DemonHunter" in dps_partners or "Warlock" in dps_partners
                            or "DeathKnight" in dps_partners)
                if has_meta:
                    noaug_rsham.append(entry)

    label = {"dk": "Unholy DK", "lock": "Demo Lock", "dh": "Devourer DH"}[class_key]
    print(f"\n{'='*70}")
    print(f"  {label} — Comp-Controlled Pull-Size Decomposition")
    print(f"{'='*70}")
    print(f"  Aug + Bear + MW:    {len(aug_mw)} runs")
    print(f"  Aug + Bear + RSham: {len(aug_rsham)} runs")
    print(f"  NoAug + Bear + RSham (meta DPS): {len(noaug_rsham)} runs")

    # Main comparison: Aug(Bear+MW) vs NoAug(Bear+RSham)
    results = {}
    for comparison_label, aug_group, noaug_group in [
        ("Aug(MW) vs NoAug(RSham)", aug_mw, noaug_rsham),
        ("Aug(RSham) vs NoAug(RSham) [same healer]", aug_rsham, noaug_rsham),
    ]:
        if len(aug_group) < 8 or len(noaug_group) < 8:
            print(f"\n  {comparison_label}: insufficient data (aug={len(aug_group)}, noaug={len(noaug_group)})")
            continue

        all_entries = aug_group + noaug_group

        aug_ratio = statistics.mean(e["aoe_st_ratio"] for e in aug_group)
        noaug_ratio = statistics.mean(e["aoe_st_ratio"] for e in noaug_group)
        aug_dps = statistics.mean(e["norm_dps"] for e in aug_group)
        noaug_dps = statistics.mean(e["norm_dps"] for e in noaug_group)
        aug_key = statistics.mean(e["key_level"] for e in aug_group)
        noaug_key = statistics.mean(e["key_level"] for e in noaug_group)

        print(f"\n  --- {comparison_label} ---")
        print(f"  Raw: Aug={aug_dps:,.0f} vs NoAug={noaug_dps:,.0f} ({aug_dps-noaug_dps:+,.0f}, {(aug_dps-noaug_dps)/noaug_dps*100:+.1f}%)")
        print(f"  Pull size: Aug ratio={aug_ratio:.2f} vs NoAug={noaug_ratio:.2f} (delta={aug_ratio-noaug_ratio:+.2f})")
        print(f"  Key level: Aug={aug_key:.1f} vs NoAug={noaug_key:.1f}")

        # OLS decomposition
        X_aug = np.array([1.0 if e["has_aug"] else 0.0 for e in all_entries])
        X_ratio = np.array([e["aoe_st_ratio"] for e in all_entries])
        X_key = np.array([float(e["key_level"]) for e in all_entries])
        y = np.array([e["norm_dps"] for e in all_entries])
        noaug_mean = float(np.mean(y[X_aug == 0]))

        X1 = np.column_stack([np.ones(len(all_entries)), X_aug])
        b1 = np.linalg.lstsq(X1, y, rcond=None)[0]
        X3 = np.column_stack([np.ones(len(all_entries)), X_aug, X_ratio, X_key])
        b3 = np.linalg.lstsq(X3, y, rcond=None)[0]

        raw = float(b1[1])
        controlled = float(b3[1])
        pullsize_effect = raw - controlled

        print(f"  OLS: Raw={raw:+,.0f} ({raw/noaug_mean*100:+.1f}%) -> Controlled={controlled:+,.0f} ({controlled/noaug_mean*100:+.1f}%)")
        print(f"  Pull size + key explains: {pullsize_effect:+,.0f} ({pullsize_effect/noaug_mean*100:+.1f}%)")

        # AoE vs ST separately
        y_aoe = np.array([e["aoe_dps"] for e in all_entries])
        y_st = np.array([e["st_dps"] for e in all_entries])
        b_aoe = np.linalg.lstsq(X3, y_aoe, rcond=None)[0]
        b_st = np.linalg.lstsq(X3, y_st, rcond=None)[0]
        noaug_aoe = float(np.mean(y_aoe[X_aug == 0]))
        noaug_st = float(np.mean(y_st[X_aug == 0]))

        print(f"  AoE coeff (controlled): {float(b_aoe[1]):+,.0f} ({float(b_aoe[1])/noaug_aoe*100:+.1f}% of noaug AoE)")
        print(f"  ST coeff (controlled):  {float(b_st[1]):+,.0f} ({float(b_st[1])/noaug_st*100:+.1f}% of noaug ST)")

        results[comparison_label] = {
            "raw": raw, "controlled": controlled,
            "pullsize_effect": pullsize_effect,
            "aoe_coeff": float(b_aoe[1]), "st_coeff": float(b_st[1]),
        }

    return results


def run_multiclass_summary():
    """Return structured data for the website."""
    all_results = {}
    for cls in ["dk", "lock", "dh"]:
        all_results[cls] = run_class_analysis(cls)

    summary = []
    for cls in ["dk", "lock", "dh"]:
        label = {"dk": "Unholy DK", "lock": "Demo Lock", "dh": "Devourer DH"}[cls]
        r = all_results[cls]
        if not r:
            continue
        # Primary comparison: Aug(MW) vs NoAug(RSham)
        primary = r.get("Aug(MW) vs NoAug(RSham)")
        same_healer = r.get("Aug(RSham) vs NoAug(RSham) [same healer]")
        if primary:
            summary.append({
                "class": cls,
                "label": label,
                "raw": primary["raw"],
                "controlled": primary["controlled"],
                "pullsize_effect": primary["pullsize_effect"],
                "aoe_coeff": primary["aoe_coeff"],
                "st_coeff": primary["st_coeff"],
                "same_healer_raw": same_healer["raw"] if same_healer else None,
                "same_healer_controlled": same_healer["controlled"] if same_healer else None,
            })
    return summary


if __name__ == "__main__":
    all_results = {}
    for cls in ["dk", "lock", "dh"]:
        all_results[cls] = run_class_analysis(cls)

    print(f"\n\n{'='*70}")
    print(f"  CROSS-CLASS SUMMARY")
    print(f"{'='*70}")
    print(f"\n  {'Class':<10} {'Raw':>8} {'Controlled':>12} {'Pull explains':>14} {'AoE coeff':>11} {'ST coeff':>10}")
    print(f"  {'-'*65}")
    for cls in ["dk", "lock", "dh"]:
        label = {"dk": "DK", "lock": "Lock", "dh": "DH"}[cls]
        r = all_results[cls]
        if not r:
            print(f"  {label:<10} insufficient data")
            continue
        # Use the MW vs RSham comparison (main one)
        key = "Aug(MW) vs NoAug(RSham)"
        if key not in r:
            print(f"  {label:<10} insufficient data for primary comparison")
            continue
        d = r[key]
        print(f"  {label:<10} {d['raw']:>+7,.0f} {d['controlled']:>+11,.0f} {d['pullsize_effect']:>+13,.0f} "
              f"{d['aoe_coeff']:>+10,.0f} {d['st_coeff']:>+9,.0f}")
