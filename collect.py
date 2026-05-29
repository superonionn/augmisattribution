"""
Collect top Unholy DK rankings from all Midnight S1 dungeons.

For each ranking, captures:
- DK DPS, key level, duration, report code, fight ID
- Full 5-man comp (class/spec for each player)
- Inferred raid buffs from comp

Outputs: data/rankings.json
"""

import json
import os
import sys
import time

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

RANKINGS_QUERY = """
query($encounterID: Int!, $page: Int!) {
    worldData {
        encounter(id: $encounterID) {
            name
            characterRankings(
                className: "DeathKnight"
                specName: "Unholy"
                metric: dps
                page: $page
                includeCombatantInfo: true
                includeOtherPlayers: true
            )
        }
    }
}
"""

TARGET_PER_DUNGEON = 400


def extract_comp(all_characters: list[dict]) -> list[dict]:
    """Extract simplified comp from allCharacters."""
    return [
        {"name": c["name"], "class": c["class"], "spec": c["spec"]}
        for c in all_characters
    ]


def has_aug(comp: list[dict]) -> bool:
    return any(c["class"] == "Evoker" and c["spec"] == "Augmentation" for c in comp)


def has_priest(comp: list[dict]) -> bool:
    return any(c["class"] == "Priest" for c in comp)


def infer_buffs(comp: list[dict]) -> dict[str, bool]:
    """Infer which raid buffs are available from the comp."""
    classes = {c["class"] for c in comp}
    return {
        "mark_of_the_wild": "Druid" in classes,
        "mystic_touch": "Monk" in classes,
        "chaos_brand": "DemonHunter" in classes,
        "battle_shout": "Warrior" in classes,
        "skyfury": "Shaman" in classes,
        "augmentation": has_aug(comp),
    }


def collect_rankings():
    os.makedirs("data", exist_ok=True)
    all_rankings = []

    for enc_id, dungeon_name in DUNGEONS.items():
        print(f"\n{'='*60}")
        print(f"  {dungeon_name} (encounter {enc_id})")
        print(f"{'='*60}")

        dungeon_rankings = []
        page = 1

        while len(dungeon_rankings) < TARGET_PER_DUNGEON:
            print(f"  Fetching page {page}...")
            data = query(RANKINGS_QUERY, {"encounterID": enc_id, "page": page})
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
                    "score": r.get("score", 0),
                    "medal": r.get("medal", ""),
                    "comp": comp,
                    "buffs": buffs,
                    "has_aug": buffs["augmentation"],
                }
                dungeon_rankings.append(entry)

            has_more = cr.get("hasMorePages", False)
            if not has_more:
                print(f"  No more pages after page {page}")
                break
            page += 1
            time.sleep(0.5)

        aug_count = sum(1 for r in dungeon_rankings if r["has_aug"])
        no_aug_count = len(dungeon_rankings) - aug_count
        key_levels = [r["key_level"] for r in dungeon_rankings]
        min_key = min(key_levels) if key_levels else 0
        max_key = max(key_levels) if key_levels else 0

        print(f"  Collected {len(dungeon_rankings)} rankings")
        print(f"  Key range: +{min_key} to +{max_key}")
        print(f"  With Aug: {aug_count} | Without Aug: {no_aug_count}")

        all_rankings.extend(dungeon_rankings)

    out_path = os.path.join("data", "rankings.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_rankings, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"  TOTAL: {len(all_rankings)} rankings saved to {out_path}")
    print(f"  Aug: {sum(1 for r in all_rankings if r['has_aug'])}")
    print(f"  No Aug: {sum(1 for r in all_rankings if not r['has_aug'])}")
    print(f"{'='*60}")


if __name__ == "__main__":
    collect_rankings()
