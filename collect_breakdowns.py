"""
Collect per-ability damage breakdowns for a sample of rankings.

For each sampled ranking, queries the WCL report for the DK's damage table
broken down by ability. This lets us compare which parts of the DK's damage
(pet vs direct vs diseases) change with aug.

Samples all no-aug entries + equal number of random aug entries.
Outputs: data/breakdowns.json
"""

import json
import os
import random
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

from wcl_api import query

BREAKDOWN_QUERY = """
query($code: String!, $fid: [Int]) {
    reportData {
        report(code: $code) {
            table(
                dataType: DamageDone,
                fightIDs: $fid,
                sourceClass: "DeathKnight",
                viewBy: Ability
            )
        }
    }
}
"""

# Whitelist of known DK PLAYER abilities — everything else is pet damage
# (ghoul/abomination get random names like "Spinechomp", "Gravecruncher", etc.)
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


def categorize_ability(name: str) -> str:
    """Categorize an ability. Player abilities are whitelisted;
    everything else (random ghoul names, army, riders, etc.) is pet."""
    if name in PLAYER_ABILITIES:
        return "direct"
    if name in DISEASE_ABILITIES:
        return "disease"
    return "pet"


def fetch_breakdown(report_code: str, fight_id: int) -> dict | None:
    """Fetch ability breakdown for a DK in a specific fight."""
    try:
        data = query(BREAKDOWN_QUERY, {"code": report_code, "fid": [fight_id]})
        table = data["reportData"]["report"]["table"]["data"]
        entries = table.get("entries", [])

        abilities = []
        total = 0
        for e in entries:
            total += e.get("total", 0)
            abilities.append({
                "name": e.get("name", "Unknown"),
                "total": e.get("total", 0),
                "type": e.get("type", 0),
            })

        return {"total": total, "abilities": abilities}
    except Exception as ex:
        print(f"  Error fetching {report_code}/{fight_id}: {ex}", file=sys.stderr)
        return None


def collect_breakdowns():
    os.makedirs("data", exist_ok=True)

    with open(os.path.join("data", "rankings.json"), encoding="utf-8") as f:
        rankings = json.load(f)

    aug_entries = [r for r in rankings if r["has_aug"]]
    noaug_entries = [r for r in rankings if not r["has_aug"]]

    print(f"Total rankings: {len(rankings)}")
    print(f"Aug: {len(aug_entries)}, No-Aug: {len(noaug_entries)}")

    # Sample: all no-aug + equal number of random aug
    sample_size = len(noaug_entries)
    aug_sample = random.sample(aug_entries, min(sample_size, len(aug_entries)))
    sample = noaug_entries + aug_sample
    random.shuffle(sample)

    print(f"Sampling {len(sample)} entries ({len(noaug_entries)} no-aug + {len(aug_sample)} aug)")

    results = []
    errors = 0
    for i, entry in enumerate(sample):
        if i % 50 == 0:
            print(f"  Progress: {i}/{len(sample)} ({errors} errors)")

        breakdown = fetch_breakdown(entry["report_code"], entry["fight_id"])
        if breakdown is None:
            errors += 1
            continue

        # Categorize abilities
        pet_total = 0
        direct_total = 0
        disease_total = 0
        ability_details = []

        for a in breakdown["abilities"]:
            cat = categorize_ability(a["name"])
            if cat == "pet":
                pet_total += a["total"]
            elif cat == "disease":
                disease_total += a["total"]
            else:
                direct_total += a["total"]

            ability_details.append({
                "name": a["name"],
                "total": a["total"],
                "category": cat,
            })

        total = breakdown["total"]
        results.append({
            "player": entry["player"],
            "dungeon": entry["dungeon"],
            "dps": entry["dps"],
            "key_level": entry["key_level"],
            "has_aug": entry["has_aug"],
            "buffs": entry["buffs"],
            "total_damage": total,
            "pet_damage": pet_total,
            "direct_damage": direct_total,
            "disease_damage": disease_total,
            "pet_pct": pet_total / total * 100 if total else 0,
            "direct_pct": direct_total / total * 100 if total else 0,
            "disease_pct": disease_total / total * 100 if total else 0,
            "abilities": ability_details,
        })

        time.sleep(0.3)

    out_path = os.path.join("data", "breakdowns.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(results)} breakdowns to {out_path} ({errors} errors)")

    # Quick summary
    aug_r = [r for r in results if r["has_aug"]]
    noaug_r = [r for r in results if not r["has_aug"]]
    if aug_r and noaug_r:
        print(f"\nQuick breakdown comparison:")
        print(f"  Aug (n={len(aug_r)}):")
        print(f"    Pet:     {sum(r['pet_pct'] for r in aug_r)/len(aug_r):.1f}%")
        print(f"    Direct:  {sum(r['direct_pct'] for r in aug_r)/len(aug_r):.1f}%")
        print(f"    Disease: {sum(r['disease_pct'] for r in aug_r)/len(aug_r):.1f}%")
        print(f"  No-Aug (n={len(noaug_r)}):")
        print(f"    Pet:     {sum(r['pet_pct'] for r in noaug_r)/len(noaug_r):.1f}%")
        print(f"    Direct:  {sum(r['direct_pct'] for r in noaug_r)/len(noaug_r):.1f}%")
        print(f"    Disease: {sum(r['disease_pct'] for r in noaug_r)/len(noaug_r):.1f}%")


if __name__ == "__main__":
    collect_breakdowns()
