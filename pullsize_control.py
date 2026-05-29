"""Control for pull size using AoE/ST ratio as proxy."""
import json
import os
import sys
import statistics
import bisect

sys.stdout.reconfigure(encoding="utf-8")

from analyze import compute_buff_multiplier


def get_dps(entry, name):
    dur = entry["total_damage"] / entry["dps"]
    bm = compute_buff_multiplier(entry["buffs"])
    for a in entry["abilities"]:
        if a["name"] == name:
            return a["total"] / bm / dur
    return 0


def run_pullsize_analysis():
    """Run the pull size decomposition analysis. Returns a dict of results."""
    path = os.path.join("data", "breakdowns.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    entries = []
    for e in data:
        bm = compute_buff_multiplier(e["buffs"])
        norm_dps = e["dps"] / bm
        aoe = get_dps(e, "Epidemic") + get_dps(e, "Graveyard")
        st = get_dps(e, "Death Coil") + get_dps(e, "Necrotic Coil")
        if st < 100:
            continue
        entries.append({
            "has_aug": e["has_aug"],
            "norm_dps": norm_dps,
            "aoe_st_ratio": aoe / st,
            "key_level": e["key_level"],
        })

    # Quintile buckets
    ratios = sorted(e["aoe_st_ratio"] for e in entries)
    n = len(ratios)
    quintile_bounds = [ratios[min(int(n * q), n - 1)] for q in [0, 0.2, 0.4, 0.6, 0.8, 1.0]]

    buckets = []
    for i in range(5):
        lo = quintile_bounds[i]
        hi = quintile_bounds[i + 1] + (0.001 if i == 4 else 0)
        bucket_aug = [e for e in entries if e["has_aug"] and lo <= e["aoe_st_ratio"] < hi]
        bucket_noaug = [e for e in entries if not e["has_aug"] and lo <= e["aoe_st_ratio"] < hi]
        if not bucket_aug or not bucket_noaug:
            continue
        aug_avg = statistics.mean(e["norm_dps"] for e in bucket_aug)
        noaug_avg = statistics.mean(e["norm_dps"] for e in bucket_noaug)
        delta = aug_avg - noaug_avg
        pct = delta / noaug_avg * 100
        buckets.append({
            "label": f"{lo:.1f} – {hi:.1f}",
            "aug_dps": aug_avg, "noaug_dps": noaug_avg,
            "delta": delta, "pct": pct,
            "n_aug": len(bucket_aug), "n_noaug": len(bucket_noaug),
        })

    # Regression
    import numpy as np

    X_aug = np.array([1.0 if e["has_aug"] else 0.0 for e in entries])
    X_ratio = np.array([e["aoe_st_ratio"] for e in entries])
    X_key = np.array([float(e["key_level"]) for e in entries])
    y = np.array([e["norm_dps"] for e in entries])
    noaug_mean = float(np.mean(y[X_aug == 0]))

    # Full model: has_aug + ratio + key_level
    X_full = np.column_stack([np.ones(len(entries)), X_aug, X_ratio, X_key])
    beta_full = np.linalg.lstsq(X_full, y, rcond=None)[0]

    # Ratio only: has_aug + ratio
    X_ratio_only = np.column_stack([np.ones(len(entries)), X_aug, X_ratio])
    beta_ratio = np.linalg.lstsq(X_ratio_only, y, rcond=None)[0]

    # Uncontrolled: has_aug only
    X_uncont = np.column_stack([np.ones(len(entries)), X_aug])
    beta_uncont = np.linalg.lstsq(X_uncont, y, rcond=None)[0]

    # Compute contributions
    uncontrolled_dps = float(beta_uncont[1])
    ratio_only_dps = float(beta_ratio[1])
    regression_aug_dps = float(beta_full[1])

    pullsize_contribution_dps = uncontrolled_dps - ratio_only_dps
    keylevel_contribution_dps = ratio_only_dps - regression_aug_dps

    return {
        "uncontrolled_dps": uncontrolled_dps,
        "uncontrolled_pct": uncontrolled_dps / noaug_mean * 100,
        "ratio_only_dps": ratio_only_dps,
        "ratio_only_pct": ratio_only_dps / noaug_mean * 100,
        "regression_aug_dps": regression_aug_dps,
        "regression_aug_pct": regression_aug_dps / noaug_mean * 100,
        "pullsize_contribution_dps": pullsize_contribution_dps,
        "pullsize_contribution_pct": pullsize_contribution_dps / noaug_mean * 100,
        "keylevel_contribution_dps": keylevel_contribution_dps,
        "keylevel_contribution_pct": keylevel_contribution_dps / noaug_mean * 100,
        "buckets": buckets,
    }


if __name__ == "__main__":
    results = run_pullsize_analysis()
    print(f"Uncontrolled: {results['uncontrolled_dps']:+,.0f} ({results['uncontrolled_pct']:+.1f}%)")
    print(f"+ Pull size:  {results['ratio_only_dps']:+,.0f} ({results['ratio_only_pct']:+.1f}%)")
    print(f"+ Key level:  {results['regression_aug_dps']:+,.0f} ({results['regression_aug_pct']:+.1f}%)")
    print(f"\nPull size accounts for: {results['pullsize_contribution_pct']:.1f}%")
    print(f"Key level accounts for: {results['keylevel_contribution_pct']:.1f}%")
    print(f"Residual: {results['regression_aug_pct']:+.1f}%")
