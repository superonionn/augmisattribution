"""
Generic ranking + breakdown collection for any DPS class/spec.

Usage:
  python collect_class.py lock    # collect Demo Lock rankings + breakdowns
  python collect_class.py dh      # collect Devourer DH rankings + breakdowns
"""

import json
import os
import sys
import time
import random

sys.stdout.reconfigure(encoding="utf-8")

from wcl_api import query

DUNGEONS = {
    112526: "Algeth'ar Academy",
    12811: "Magisters' Terrace",
    12874: "Maisara Caverns",
    12915: "Nexus-Point Xenas",
    10658: "Pit of Saron",
    361753: "Seat of the Triumvirate",
    61209: "Skyreach",
    12805: "Windrunner Spire",
}

CLASS_CONFIGS = {
    "lock": {
        "wcl_class": "Warlock",
        "wcl_spec": "Demonology",
        "label": "Demo Lock",
        "data_prefix": "lock",
    },
    "dh": {
        "wcl_class": "DemonHunter",
        "wcl_spec": "Devourer",
        "label": "Devourer DH",
        "data_prefix": "dh",
    },
}

RANKINGS_QUERY = """
query($encounterID: Int!, $page: Int!, $className: String!, $specName: String!) {
    worldData {
        encounter(id: $encounterID) {
            name
            characterRankings(
                className: $className
                specName: $specName
                metric: dps
                page: $page
                includeCombatantInfo: true
                includeOtherPlayers: true
            )
        }
    }
}
"""

BREAKDOWN_QUERY = """
query($code: String!, $fid: [Int], $sourceClass: String!) {
    reportData {
        report(code: $code) {
            table(
                dataType: DamageDone,
                fightIDs: $fid,
                sourceClass: $sourceClass,
                viewBy: Ability
            )
        }
    }
}
"""

TARGET_PER_DUNGEON = 400


def extract_comp(all_characters):
    return [
        {"name": c["name"], "class": c["class"], "spec": c["spec"]}
        for c in all_characters
    ]


def has_aug(comp):
    return any(c["class"] == "Evoker" and c["spec"] == "Augmentation" for c in comp)


def has_priest(comp):
    return any(c["class"] == "Priest" for c in comp)


def infer_buffs(comp):
    classes = {c["class"] for c in comp}
    return {
        "mark_of_the_wild": "Druid" in classes,
        "mystic_touch": "Monk" in classes,
        "chaos_brand": "DemonHunter" in classes,
        "battle_shout": "Warrior" in classes,
        "skyfury": "Shaman" in classes,
        "augmentation": has_aug(comp),
    }


def collect_rankings(config):
    os.makedirs("data", exist_ok=True)
    all_rankings = []
    label = config["label"]

    for enc_id, dungeon_name in DUNGEONS.items():
        print(f"\n{'='*60}")
        print(f"  {dungeon_name} — {label}")
        print(f"{'='*60}")

        dungeon_rankings = []
        page = 1

        while len(dungeon_rankings) < TARGET_PER_DUNGEON:
            print(f"  Fetching page {page}...")
            data = query(RANKINGS_QUERY, {
                "encounterID": enc_id, "page": page,
                "className": config["wcl_class"], "specName": config["wcl_spec"],
            })
            cr = data["worldData"]["encounter"]["characterRankings"]
            batch = cr.get("rankings", [])

            if not batch:
                print(f"  No more data at page {page}")
                break

            for r in batch:
                if len(dungeon_rankings) >= TARGET_PER_DUNGEON:
                    break

                comp = extract_comp(r.get("allCharacters", []))
                if has_priest(comp):
                    continue

                buffs = infer_buffs(comp)
                entry = {
                    "dungeon": dungeon_name,
                    "encounter_id": enc_id,
                    "player": r["name"],
                    "dps": r["amount"],
                    "key_level": r.get("hardModeLevel", 0),
                    "duration_ms": r["duration"],
                    "duration_s": r["duration"] / 1000,
                    "report_code": r["report"]["code"],
                    "fight_id": r["report"]["fightID"],
                    "server": r.get("server", {}).get("name", ""),
                    "region": r.get("server", {}).get("region", ""),
                    "comp": comp,
                    "buffs": buffs,
                    "has_aug": buffs["augmentation"],
                }
                dungeon_rankings.append(entry)

            if not cr.get("hasMorePages", False):
                break
            page += 1
            time.sleep(0.5)

        aug_count = sum(1 for r in dungeon_rankings if r["has_aug"])
        print(f"  Collected {len(dungeon_rankings)} — Aug: {aug_count} | No-Aug: {len(dungeon_rankings) - aug_count}")
        all_rankings.extend(dungeon_rankings)

    out_path = os.path.join("data", f"{config['data_prefix']}_rankings.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_rankings, f, indent=2, ensure_ascii=False)

    total_aug = sum(1 for r in all_rankings if r["has_aug"])
    print(f"\nSaved {len(all_rankings)} {label} rankings ({total_aug} aug / {len(all_rankings) - total_aug} no-aug)")
    return all_rankings


def collect_breakdowns(config, rankings):
    aug_entries = [r for r in rankings if r["has_aug"]]
    noaug_entries = [r for r in rankings if not r["has_aug"]]

    sample_size = len(noaug_entries)
    aug_sample = random.sample(aug_entries, min(sample_size, len(aug_entries)))
    sample = noaug_entries + aug_sample
    random.shuffle(sample)

    print(f"\nCollecting breakdowns: {len(sample)} entries ({len(noaug_entries)} no-aug + {len(aug_sample)} aug)")

    results = []
    errors = 0
    for i, entry in enumerate(sample):
        if i % 50 == 0:
            print(f"  Progress: {i}/{len(sample)} ({errors} errors)")

        try:
            data = query(BREAKDOWN_QUERY, {
                "code": entry["report_code"],
                "fid": [entry["fight_id"]],
                "sourceClass": config["wcl_class"],
            })
            table = data["reportData"]["report"]["table"]["data"]
            raw_abilities = table.get("entries", [])
        except Exception as ex:
            print(f"  Error: {ex}", file=sys.stderr)
            errors += 1
            continue

        abilities = []
        total = 0
        for e in raw_abilities:
            total += e.get("total", 0)
            abilities.append({
                "name": e.get("name", "Unknown"),
                "total": e.get("total", 0),
            })

        results.append({
            "player": entry["player"],
            "dungeon": entry["dungeon"],
            "dps": entry["dps"],
            "key_level": entry["key_level"],
            "has_aug": entry["has_aug"],
            "buffs": entry["buffs"],
            "total_damage": total,
            "abilities": abilities,
        })

        time.sleep(0.3)

    out_path = os.path.join("data", f"{config['data_prefix']}_breakdowns.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(results)} breakdowns to {out_path} ({errors} errors)")
    return results


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in CLASS_CONFIGS:
        print(f"Usage: python collect_class.py [{'/'.join(CLASS_CONFIGS.keys())}]")
        sys.exit(1)

    key = sys.argv[1]
    config = CLASS_CONFIGS[key]
    print(f"Collecting {config['label']} data...")

    rankings = collect_rankings(config)
    print(f"\nNow collecting per-ability breakdowns...")
    collect_breakdowns(config, rankings)
