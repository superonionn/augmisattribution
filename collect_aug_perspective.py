"""Collect Aug Evoker damage breakdowns from reports where we have Lock/DK data.

Queries the same report+fight with sourceClass=Evoker to see how much damage
WCL credits to the Aug when paired with different classes.
"""
import json
import os
import sys
import time
import random

sys.stdout.reconfigure(encoding="utf-8")

from wcl_api import query as wcl_query

BATCH_SIZE = 12


def build_batch_query(entries):
    """Build a single GraphQL query that fetches Aug damage from multiple reports."""
    parts = []
    for i, entry in enumerate(entries):
        parts.append(f"""
        r{i}: report(code: "{entry['report_code']}") {{
            table(
                dataType: DamageDone,
                fightIDs: [{entry['fight_id']}],
                sourceClass: "Evoker",
                viewBy: Ability
            )
        }}""")

    return "query { reportData {" + "".join(parts) + " } }"


def collect(source_class):
    """Collect Aug damage from reports where source_class was the DPS."""
    class_to_rankings = {
        "lock": "lock_rankings.json",
        "dk": "rankings.json",
        "dh": "dh_rankings.json",
    }
    if source_class not in class_to_rankings:
        print(f"Unknown class: {source_class}")
        sys.exit(1)
    rankings_path = os.path.join("data", class_to_rankings[source_class])

    out_path = os.path.join("data", f"aug_with_{source_class}.json")

    with open(rankings_path, encoding="utf-8") as f:
        rankings = json.load(f)

    aug_reports = [r for r in rankings if r["has_aug"]]
    print(f"Source: {len(aug_reports)} aug-{source_class} reports available")

    existing = []
    existing_keys = set()
    if os.path.exists(out_path):
        with open(out_path, encoding="utf-8") as f:
            existing = json.load(f)
        for e in existing:
            existing_keys.add((e["report_code"], e["fight_id"]))
        print(f"Loaded {len(existing)} existing Aug breakdowns")

    sample = [r for r in aug_reports if (r["report_code"], r["fight_id"]) not in existing_keys]
    random.shuffle(sample)
    sample = sample[:500]  # cap at 500 new entries per run

    print(f"Collecting {len(sample)} Aug breakdowns in batches of {BATCH_SIZE} (~{len(sample)//BATCH_SIZE} requests)")

    results = list(existing)
    errors = 0
    consecutive_429 = 0

    for batch_start in range(0, len(sample), BATCH_SIZE):
        batch = sample[batch_start:batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1
        total_batches = (len(sample) + BATCH_SIZE - 1) // BATCH_SIZE

        if batch_start % (BATCH_SIZE * 10) == 0:
            print(f"  Batch {batch_num}/{total_batches} — {len(results)} collected, {errors} errors")

        q = build_batch_query(batch)
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

                duration_s = entry.get("duration_s") or (entry.get("duration_ms", 0) / 1000)
                aug_dps = total / duration_s if duration_s > 0 else 0

                results.append({
                    "report_code": entry["report_code"],
                    "fight_id": entry["fight_id"],
                    "dungeon": entry["dungeon"],
                    "key_level": entry["key_level"],
                    "paired_with": source_class,
                    "paired_dps": entry["dps"],
                    "aug_total_damage": total,
                    "aug_dps": aug_dps,
                    "duration_s": duration_s,
                    "abilities": abilities,
                    "comp": entry.get("comp", []),
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

    print(f"\nDone: {len(results)} Aug breakdowns (paired with {source_class}), {errors} errors")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("lock", "dk", "dh"):
        print(f"Usage: python collect_aug_perspective.py [lock|dk|dh]")
        sys.exit(1)
    collect(sys.argv[1])
