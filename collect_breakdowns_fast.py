"""Fast breakdown collection using batched GraphQL queries (aliases)."""
import json
import os
import sys
import time
import random

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

from wcl_api import query as wcl_query

BATCH_SIZE = 12

CLASS_MAP = {
    "lock": "Warlock",
    "dh": "DemonHunter",
}


def build_batch_query(entries, source_class):
    """Build a single GraphQL query that fetches multiple reports via aliases."""
    parts = []
    for i, entry in enumerate(entries):
        parts.append(f"""
        r{i}: report(code: "{entry['report_code']}") {{
            table(
                dataType: DamageDone,
                fightIDs: [{entry['fight_id']}],
                sourceClass: "{source_class}",
                viewBy: Ability
            )
        }}""")

    return "query { reportData {" + "".join(parts) + " } }"


def collect(key):
    wcl_class = CLASS_MAP[key]
    rankings_path = os.path.join("data", f"{key}_rankings.json")
    out_path = os.path.join("data", f"{key}_breakdowns.json")

    with open(rankings_path, encoding="utf-8") as f:
        rankings = json.load(f)

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
    sample = [s for s in sample if (s["player"], s["dungeon"]) not in existing]

    print(f"Need {len(sample)} breakdowns in batches of {BATCH_SIZE} (~{len(sample)//BATCH_SIZE} requests)")

    results = list(existing_results)
    errors = 0
    consecutive_429 = 0

    for batch_start in range(0, len(sample), BATCH_SIZE):
        batch = sample[batch_start:batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1
        total_batches = (len(sample) + BATCH_SIZE - 1) // BATCH_SIZE

        if batch_start % (BATCH_SIZE * 10) == 0:
            print(f"  Batch {batch_num}/{total_batches} — {len(results)} collected, {errors} errors")

        q = build_batch_query(batch, wcl_class)
        try:
            data = wcl_query(q, {})
            report_data = data.get("reportData", {})
            consecutive_429 = 0

            for i, entry in enumerate(batch):
                report = report_data.get(f"r{i}")
                if not report or not report.get("table"):
                    errors += 1
                    continue
                raw = report["table"].get("data", {}).get("entries", [])
                abilities = []
                total = 0
                for e in raw:
                    total += e.get("total", 0)
                    abilities.append({"name": e.get("name", "Unknown"), "total": e.get("total", 0)})

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

        except Exception as ex:
            errors += len(batch)
            if "429" in str(ex):
                consecutive_429 += 1
                if consecutive_429 >= 3:
                    print(f"  Rate limited, backing off 60s...")
                    time.sleep(60)
                    consecutive_429 = 0

        time.sleep(1.5)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    aug_r = sum(1 for r in results if r["has_aug"])
    print(f"\nDone: {len(results)} breakdowns ({aug_r} aug / {len(results)-aug_r} no-aug), {errors} errors")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in CLASS_MAP:
        print(f"Usage: python collect_breakdowns_fast.py [{'/'.join(CLASS_MAP.keys())}]")
        sys.exit(1)
    collect(sys.argv[1])
