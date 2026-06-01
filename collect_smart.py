"""Smart data collector with proper rate limit handling.

Usage:
  python collect_smart.py breakdowns dh        # DH ability breakdowns
  python collect_smart.py breakdowns lock      # Lock ability breakdowns
  python collect_smart.py aug lock             # Aug perspective from Lock reports
  python collect_smart.py aug lock 21          # Aug perspective from Lock reports, key 21 only
  python collect_smart.py aug dk              # Aug perspective from DK reports
"""
import json
import os
import sys
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

from wcl_api import query as wcl_query, get_rate_info

WORKERS = 3  # Concurrent request threads (rate limiter in wcl_api serializes timing)

BATCH_SIZE = 10  # Sweet spot: enough to be efficient, not so many that one failure loses a lot

CLASS_MAP = {
    "lock": ("Warlock", "lock_rankings.json", "lock_breakdowns.json"),
    "dh": ("DemonHunter", "dh_rankings.json", "dh_breakdowns.json"),
    "dk": ("DeathKnight", "rankings.json", "breakdowns.json"),
}


def build_breakdown_query(entries, source_class):
    """Batch query for DPS class ability breakdowns."""
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


def build_aug_query(entries):
    """Batch query for Aug Evoker ability breakdowns."""
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





def save_json(path, data):
    """Atomic-ish save: write to tmp then rename."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def collect_breakdowns(class_key, max_new=None):
    """Collect DPS class ability breakdowns with smart rate limiting."""
    wcl_class, rankings_file, out_file = CLASS_MAP[class_key]
    rankings_path = os.path.join("data", rankings_file)
    out_path = os.path.join("data", out_file)

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

    if max_new:
        sample = sample[:max_new]

    total_batches = (len(sample) + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"Collecting {len(sample)} breakdowns in {total_batches} batches of {BATCH_SIZE}")

    results = list(existing_results)
    errors = 0
    start_time = time.time()
    results_lock = __import__('threading').Lock()

    def process_batch(batch_info):
        batch, batch_num = batch_info
        q = build_breakdown_query(batch, wcl_class)
        batch_results = []
        batch_errors = 0
        try:
            data = wcl_query(q, {})
            report_data = data.get("reportData", {})
            for i, entry in enumerate(batch):
                report = report_data.get(f"r{i}")
                if not report or not report.get("table"):
                    batch_errors += 1
                    continue
                raw = report["table"].get("data", {}).get("entries", [])
                abilities = []
                total = 0
                for e in raw:
                    total += e.get("total", 0)
                    abilities.append({"name": e.get("name", "Unknown"), "total": e.get("total", 0)})
                batch_results.append({
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
            batch_errors = len(batch)
            print(f"  Batch {batch_num} error: {ex}")
        return batch_results, batch_errors

    batches = []
    for batch_start in range(0, len(sample), BATCH_SIZE):
        batch = sample[batch_start:batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1
        batches.append((batch, batch_num))

    completed = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(process_batch, b): b[1] for b in batches}
        for future in as_completed(futures):
            batch_results, batch_errors = future.result()
            with results_lock:
                results.extend(batch_results)
                errors += batch_errors
                completed += 1

            if completed % 5 == 0 or completed == total_batches:
                new_collected = len(results) - len(existing_results)
                elapsed = time.time() - start_time
                rate = new_collected / elapsed * 3600 if elapsed > 10 else 0
                info = get_rate_info()
                print(f"  [{completed}/{total_batches}] +{new_collected} new, {errors} err | "
                      f"budget: {info['remaining']}/{info['limit']} | "
                      f"~{rate:.0f}/hr")

            if completed % 10 == 0:
                save_json(out_path, results)

    save_json(out_path, results)
    aug_r = sum(1 for r in results if r["has_aug"])
    elapsed = time.time() - start_time
    print(f"\nDone: {len(results)} breakdowns ({aug_r} aug / {len(results)-aug_r} no-aug), "
          f"{errors} errors, {elapsed/60:.1f} min")


def collect_aug_perspective(class_key, key_filter=None, max_new=500):
    """Collect Aug Evoker damage from reports where class_key was the DPS."""
    _, rankings_file, _ = CLASS_MAP[class_key]
    rankings_path = os.path.join("data", rankings_file)
    out_path = os.path.join("data", f"aug_with_{class_key}.json")

    with open(rankings_path, encoding="utf-8") as f:
        rankings = json.load(f)

    aug_reports = [r for r in rankings if r["has_aug"]]
    if key_filter:
        aug_reports = [r for r in aug_reports if r["key_level"] == key_filter]
    print(f"Source: {len(aug_reports)} aug-{class_key} reports" +
          (f" (key {key_filter} only)" if key_filter else ""))

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
    sample = sample[:max_new]

    total_batches = (len(sample) + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"Collecting {len(sample)} Aug breakdowns in {total_batches} batches")

    results = list(existing)
    errors = 0
    start_time = time.time()
    results_lock = __import__('threading').Lock()

    def process_batch(batch_info):
        batch, batch_num = batch_info
        q = build_aug_query(batch)
        batch_results = []
        batch_errors = 0
        try:
            data = wcl_query(q, {})
            report_data = data.get("reportData", {})
            for i, entry in enumerate(batch):
                report = report_data.get(f"r{i}")
                if not report or not report.get("table"):
                    batch_errors += 1
                    continue
                raw = report["table"].get("data", {}).get("entries", [])
                abilities = []
                total = 0
                for e in raw:
                    total += e.get("total", 0)
                    abilities.append({"name": e.get("name", "Unknown"), "total": e.get("total", 0)})
                duration_s = entry.get("duration_s") or (entry.get("duration_ms", 0) / 1000)
                aug_dps = total / duration_s if duration_s > 0 else 0
                batch_results.append({
                    "report_code": entry["report_code"],
                    "fight_id": entry["fight_id"],
                    "dungeon": entry["dungeon"],
                    "key_level": entry["key_level"],
                    "paired_with": class_key,
                    "paired_dps": entry["dps"],
                    "aug_total_damage": total,
                    "aug_dps": aug_dps,
                    "duration_s": duration_s,
                    "abilities": abilities,
                    "comp": entry.get("comp", []),
                })
        except Exception as ex:
            batch_errors = len(batch)
            print(f"  Batch {batch_num} error: {ex}")
        return batch_results, batch_errors

    batches = []
    for batch_start in range(0, len(sample), BATCH_SIZE):
        batch = sample[batch_start:batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1
        batches.append((batch, batch_num))

    completed = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(process_batch, b): b[1] for b in batches}
        for future in as_completed(futures):
            batch_results, batch_errors = future.result()
            with results_lock:
                results.extend(batch_results)
                errors += batch_errors
                completed += 1

            if completed % 5 == 0 or completed == total_batches:
                new_collected = len(results) - len(existing)
                elapsed = time.time() - start_time
                rate = new_collected / elapsed * 3600 if elapsed > 10 else 0
                info = get_rate_info()
                print(f"  [{completed}/{total_batches}] +{new_collected} new, {errors} err | "
                      f"budget: {info['remaining']}/{info['limit']} | "
                      f"~{rate:.0f}/hr")

            if completed % 10 == 0:
                save_json(out_path, results)

    save_json(out_path, results)
    elapsed = time.time() - start_time
    print(f"\nDone: {len(results)} Aug breakdowns (paired with {class_key}), "
          f"{errors} errors, {elapsed/60:.1f} min")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage:")
        print("  python collect_smart.py breakdowns [lock|dh|dk] [max_new]")
        print("  python collect_smart.py aug [lock|dh|dk] [key_level] [max_new]")
        sys.exit(1)

    mode = sys.argv[1]
    class_key = sys.argv[2]

    if class_key not in CLASS_MAP:
        print(f"Unknown class: {class_key}. Use: {', '.join(CLASS_MAP.keys())}")
        sys.exit(1)

    if mode == "breakdowns":
        max_new = int(sys.argv[3]) if len(sys.argv) > 3 else None
        collect_breakdowns(class_key, max_new=max_new)
    elif mode == "aug":
        key_filter = None
        max_new = 500
        for arg in sys.argv[3:]:
            if arg.isdigit():
                val = int(arg)
                if val < 100:
                    key_filter = val
                else:
                    max_new = val
        collect_aug_perspective(class_key, key_filter=key_filter, max_new=max_new)
    else:
        print(f"Unknown mode: {mode}. Use: breakdowns, aug")
        sys.exit(1)
