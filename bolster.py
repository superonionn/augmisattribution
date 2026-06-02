"""Run a sequence of collections, checking budget between each step."""
import sys
import time
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

from wcl_api import query, get_rate_info
from collect_smart import collect_breakdowns, collect_aug_perspective

BUDGET_FLOOR = 50  # stop if remaining drops below this


def check_budget():
    """Make a lightweight query to get live budget from headers."""
    data = query("{ rateLimitData { pointsSpentThisHour pointsResetIn limitPerHour } }", {})
    rld = data.get("rateLimitData", {})
    spent = rld.get("pointsSpentThisHour", 0)
    limit = rld.get("limitPerHour", 800)
    reset_in = rld.get("pointsResetIn", 0)
    remaining = limit - spent
    print(f"Budget: {remaining}/{limit} (resets in {reset_in // 60}m{reset_in % 60}s)")
    return remaining, reset_in


def wait_for_budget(min_needed=100):
    """Wait until we have enough budget to proceed."""
    remaining, reset_in = check_budget()
    if remaining >= min_needed:
        return remaining
    wait = reset_in + 10
    print(f"Need {min_needed} points, have {remaining}. Waiting {wait}s ({wait // 60}m)...")
    time.sleep(wait)
    remaining, _ = check_budget()
    return remaining


def main():
    steps = [
        ("DH breakdowns (312 → 1500)", lambda: collect_breakdowns("dh", max_new=1188)),
        ("DK breakdowns (1059 → 1500)", lambda: collect_breakdowns("dk", max_new=441)),
        ("Aug+DH perspective (0 → 500)", lambda: collect_aug_perspective("dh", max_new=500)),
    ]

    for i, (label, fn) in enumerate(steps):
        print(f"\n{'=' * 60}")
        print(f"  Step {i + 1}/{len(steps)}: {label}")
        print(f"{'=' * 60}")

        remaining = wait_for_budget(min_needed=50)
        if remaining < BUDGET_FLOOR:
            print(f"Budget too low ({remaining}), stopping.")
            break

        fn()

        info = get_rate_info()
        print(f"Post-step budget: {info['remaining']}/{info['limit']}")

    print("\nAll done!")


if __name__ == "__main__":
    main()
