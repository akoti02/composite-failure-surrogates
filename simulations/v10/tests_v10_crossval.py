#!/usr/bin/env python3
"""Phase 8: V10 Cross-Validation.

Compare V11 results against V10 reference for T300/5208 + QI.
Distributions should be statistically compatible (not identical — different seeds).

Usage:
  python3 tests_v10_crossval.py <v11_csv> <v10_csv>
"""

import sys
import os
import csv
import math
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import batch_compositeNet as B

# ─────────────────────────────────────────────────────────────────────────────
# Test infrastructure
# ─────────────────────────────────────────────────────────────────────────────
_pass_count = 0
_fail_count = 0
_results = []

def check(name, condition, detail=""):
    global _pass_count, _fail_count
    if condition:
        _pass_count += 1
        _results.append(("PASS", name))
        print(f"  PASS: {name}")
    else:
        _fail_count += 1
        _results.append(("FAIL", name, detail))
        print(f"  FAIL: {name} — {detail}")


def load_csv(csv_path):
    rows = []
    with open(csv_path, 'r', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            parsed = {}
            for k, v in row.items():
                try:
                    parsed[k] = float(v) if '.' in str(v) else int(v)
                except (ValueError, TypeError):
                    parsed[k] = v
            rows.append(parsed)
    return rows


def stats(values):
    """Compute mean and std of a list of values."""
    if not values:
        return 0, 0
    mean = sum(values) / len(values)
    var = sum((v - mean)**2 for v in values) / len(values)
    return mean, math.sqrt(var)


# =============================================================================
# Distribution comparison
# =============================================================================
def check_distributions(v11_rows, v10_rows):
    print("\n=== Distribution Comparison ===")

    # Filter V11 to T300/5208 (mat=1) + QI (layup=1) + biaxial only
    # V10 only has this single material/layup combo
    v11 = [r for r in v11_rows
           if r.get('solver_completed') == 'YES'
           and str(r.get('material_id', '')) == '1'
           and str(r.get('layup_id', '')) == '1'
           and r.get('bc_mode', '') == 'biaxial']
    v10 = [r for r in v10_rows if r.get('solver_completed', 'YES') == 'YES']

    print(f"  V11 (mat=1, layup=1, biaxial): {len(v11)} successful sims")
    print(f"  V10: {len(v10)} successful sims")

    # max_s11 distribution
    v11_s11 = [float(r['max_s11']) for r in v11 if 'max_s11' in r]
    v10_s11 = [float(r['max_s11']) for r in v10 if 'max_s11' in r]

    if v11_s11 and v10_s11:
        m11, s11 = stats(v11_s11)
        m10, s10 = stats(v10_s11)
        print(f"  max_s11: V11 mean={m11:.1f} std={s11:.1f}, V10 mean={m10:.1f} std={s10:.1f}")

        mean_diff = abs(m11 - m10) / max(abs(m10), 1) if m10 != 0 else 0
        check("max_s11 means within 20%",
              mean_diff < 0.20,
              f"V11={m11:.1f}, V10={m10:.1f}, diff={mean_diff:.1%}")

        if s10 > 0:
            std_diff = abs(s11 - s10) / s10
            check("max_s11 stds within 30%",
                  std_diff < 0.30,
                  f"V11={s11:.1f}, V10={s10:.1f}, diff={std_diff:.1%}")

    # tsai_wu_index distribution
    v11_tw = [float(r['tsai_wu_index']) for r in v11 if 'tsai_wu_index' in r]
    v10_tw = [float(r['tsai_wu_index']) for r in v10 if 'tsai_wu_index' in r]

    if v11_tw and v10_tw:
        m11, s11 = stats(v11_tw)
        m10, s10 = stats(v10_tw)
        print(f"  tsai_wu: V11 mean={m11:.3f} std={s11:.3f}, V10 mean={m10:.3f} std={s10:.3f}")

        mean_diff = abs(m11 - m10) / max(abs(m10), 0.01)
        check("tsai_wu means within 20%",
              mean_diff < 0.20,
              f"V11={m11:.3f}, V10={m10:.3f}, diff={mean_diff:.1%}")

    # Failure rate comparison
    v11_fr = sum(1 for tw in v11_tw if tw >= 1.0) / len(v11_tw) if v11_tw else 0
    v10_fr = sum(1 for tw in v10_tw if tw >= 1.0) / len(v10_tw) if v10_tw else 0
    print(f"  Failure rate: V11={v11_fr:.1%}, V10={v10_fr:.1%}")
    check("Failure rates within 15%",
          abs(v11_fr - v10_fr) < 0.15,
          f"V11={v11_fr:.1%}, V10={v10_fr:.1%}, diff={abs(v11_fr-v10_fr):.1%}")

    # n_elements comparison
    v11_ne = [int(r['n_elements']) for r in v11 if 'n_elements' in r and int(r.get('n_elements', 0)) > 0]
    v10_ne = [int(r['n_elements']) for r in v10 if 'n_elements' in r and int(r.get('n_elements', 0)) > 0]

    if v11_ne and v10_ne:
        m11, _ = stats(v11_ne)
        m10, _ = stats(v10_ne)
        mean_diff = abs(m11 - m10) / max(m10, 1)
        print(f"  n_elements: V11 mean={m11:.0f}, V10 mean={m10:.0f}")
        check("n_elements means similar",
              mean_diff < 0.50,  # Allow larger tolerance — mesh randomness
              f"V11={m11:.0f}, V10={m10:.0f}, diff={mean_diff:.1%}")


# =============================================================================
# V11-specific columns
# =============================================================================
def check_new_columns(v11_rows):
    print("\n=== V11-Specific Columns ===")
    # Use all successful V11 rows (not just mat=1) for column checks
    v11 = [r for r in v11_rows if r.get('solver_completed') == 'YES']
    print(f"  Checking {len(v11)} successful V11 rows")

    new_cols = ['puck_iff_b', 'puck_iff_c', 'larc_ft', 'larc_fc', 'larc_mt', 'post_fpf']
    for col in new_cols:
        populated = sum(1 for r in v11 if col in r)
        non_zero = sum(1 for r in v11 if col in r and float(r.get(col, 0)) != 0)
        check(f"V11 column '{col}' populated in all rows",
              populated == len(v11),
              f"{populated}/{len(v11)} rows have {col}")
        if col != 'post_fpf':  # post_fpf is binary, may have many zeros
            print(f"    {col}: {non_zero}/{len(v11)} non-zero ({non_zero/len(v11):.0%})")


# =============================================================================
# Main
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description="V10 vs V11 cross-validation")
    parser.add_argument('v11_csv', help="Path to V11 results CSV")
    parser.add_argument('v10_csv', help="Path to V10 reference CSV")
    args = parser.parse_args()

    for path in [args.v11_csv, args.v10_csv]:
        if not os.path.exists(path):
            print(f"ERROR: File not found: {path}")
            sys.exit(1)

    print("=" * 70)
    print("Phase 8: V10 Cross-Validation")
    print("=" * 70)

    v11_rows = load_csv(args.v11_csv)
    v10_rows = load_csv(args.v10_csv)
    print(f"V11: {len(v11_rows)} rows")
    print(f"V10: {len(v10_rows)} rows")

    check_distributions(v11_rows, v10_rows)
    check_new_columns(v11_rows)

    print("\n" + "=" * 70)
    print(f"RESULTS: {_pass_count} passed, {_fail_count} failed")
    print("=" * 70)

    if _fail_count > 0:
        print("\nFailed checks:")
        for r in _results:
            if r[0] == "FAIL":
                print(f"  ✗ {r[1]}: {r[2]}")
        sys.exit(1)
    else:
        print("\nV10 cross-validation passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()
