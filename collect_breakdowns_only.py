"""Re-collect breakdowns for a class using existing rankings data, with rate limit handling."""
import json
import os
import sys
import time
import random

sys.stdout.reconfigure(encoding="utf-8")

from wcl_api import query

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

CLASS_MAP = {
    "lock": "Warlock",
    "dh": "DemonHunter",
}


def collect(key):
    wcl_class = CLASS_MAP[key]
    rankings_path = os.path.join("data", f"{key}_rankings.json")
    out_path = os.path.join("data", f"{key}_breakdowns.json")

    with open(rankings_path, encoding="utf-8") as f:
        rankings = json.load(f)

    # Load existing breakdowns to skip already-collected entries
    existing = set()
    existing_results = []
    if os.path.exists(out_path):
        with open(out_path, encoding="utf-8") as f:
            existing_results = json.load(f)
        for e in existing_results:
            existing.add((e["player"], e["dungeon"]))
        print(f"Loaded {len(existing_results)} existing breakdowns")

    aug_entries = [r for r in rankings if r["has_aug"]]
    noaug_entries = [r for r in rankings if not r["has_aug"]]

    sample_size = len(noaug_entries)
    aug_sample = random.sample(aug_entries, min(sample_size, len(aug_entries)))
    sample = noaug_entries + aug_sample
    random.shuffle(sample)

    # Skip already collected
    sample = [s for s in sample if (s["player"], s["dungeon"]) not in existing]
    print(f"Need to collect {len(sample)} breakdowns (skipping {len(existing)} already done)")

    results = list(existing_results)
    errors = 0
    consecutive_429 = 0

    for i, entry in enumerate(sample):
        if i % 50 == 0:
            print(f"  Progress: {i}/{len(sample)} ({errors} errors, {len(results)} total)")

        try:
            data = query(BREAKDOWN_QUERY, {
                "code": entry["report_code"],
                "fid": [entry["fight_id"]],
                "sourceClass": wcl_class,
            })
            table = data["reportData"]["report"]["table"]["data"]
            raw_abilities = table.get("entries", [])
            consecutive_429 = 0
        except Exception as ex:
            errors += 1
            if "429" in str(ex):
                consecutive_429 += 1
                if consecutive_429 >= 5:
                    print(f"  Rate limited, backing off 60s...")
                    time.sleep(60)
                    consecutive_429 = 0
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

        time.sleep(0.5)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    aug_r = sum(1 for r in results if r["has_aug"])
    print(f"\nSaved {len(results)} breakdowns ({aug_r} aug / {len(results)-aug_r} no-aug), {errors} errors")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in CLASS_MAP:
        print(f"Usage: python collect_breakdowns_only.py [{'/'.join(CLASS_MAP.keys())}]")
        sys.exit(1)
    collect(sys.argv[1])
