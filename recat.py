"""Re-categorize existing breakdown data with corrected ability classification."""
import json, sys
sys.stdout.reconfigure(encoding="utf-8")

PLAYER_ABILITIES = {
    "Putrefy", "Graveyard", "Scourge Strike", "Epidemic",
    "Necrotic Coil", "Death Coil", "Melee", "Soul Reaper",
    "Festering Scythe", "Death and Decay", "Festering Strike",
    "Death Strike", "Anti-Magic Shell",
}
DISEASE_ABILITIES = {
    "Virulent Plague", "Dread Plague", "Pestilence", "Festering Wound",
}

def categorize(name):
    if name in PLAYER_ABILITIES:
        return "direct"
    if name in DISEASE_ABILITIES:
        return "disease"
    return "pet"

with open("data/breakdowns.json", encoding="utf-8") as f:
    data = json.load(f)

for entry in data:
    pet = direct = disease = 0
    for a in entry["abilities"]:
        a["category"] = categorize(a["name"])
        if a["category"] == "pet":
            pet += a["total"]
        elif a["category"] == "disease":
            disease += a["total"]
        else:
            direct += a["total"]
    total = entry["total_damage"]
    entry["pet_damage"] = pet
    entry["direct_damage"] = direct
    entry["disease_damage"] = disease
    entry["pet_pct"] = pet / total * 100 if total else 0
    entry["direct_pct"] = direct / total * 100 if total else 0
    entry["disease_pct"] = disease / total * 100 if total else 0

with open("data/breakdowns.json", "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

# Summary
aug = [e for e in data if e["has_aug"]]
noaug = [e for e in data if not e["has_aug"]]
print(f"Re-categorized {len(data)} entries\n")
print(f"  Aug (n={len(aug)}):")
print(f"    Pet:     {sum(r['pet_pct'] for r in aug)/len(aug):.1f}%")
print(f"    Direct:  {sum(r['direct_pct'] for r in aug)/len(aug):.1f}%")
print(f"    Disease: {sum(r['disease_pct'] for r in aug)/len(aug):.1f}%")
print(f"  No-Aug (n={len(noaug)}):")
print(f"    Pet:     {sum(r['pet_pct'] for r in noaug)/len(noaug):.1f}%")
print(f"    Direct:  {sum(r['direct_pct'] for r in noaug)/len(noaug):.1f}%")
print(f"    Disease: {sum(r['disease_pct'] for r in noaug)/len(noaug):.1f}%")
