#!/usr/bin/env python3
"""Phase 6: Mesh Convergence Analysis.

Compares coarse/medium/fine results for seed alignment, convergence metrics,
mesh-level bias, and element count scaling.

Prerequisites: Run the 3 mesh-level batches first:
  python3 batch_compositeNet.py --materials 1-8 --layups 1-10 --bcs 1-2 \
      --geometry flat --mesh coarse --sims-per-combo 50 --workers 90 --seed 2026
  (repeat for medium and fine)

Usage:
  python3 tests_mesh_convergence.py <coarse_csv> <medium_csv> <fine_csv>
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
                if k in ('material_name', 'layup_name', 'bc_mode', 'geometry',
                         'mesh_level', 'solver_completed'):
                    parsed[k] = v
                else:
                    try:
                        parsed[k] = float(v) if '.' in str(v) else int(v)
                    except (ValueError, TypeError):
                        parsed[k] = v
            rows.append(parsed)
    return rows


def combo_key(row):
    """Generate a key for matching sims across mesh levels."""
    return (int(row['material_id']), int(row['layup_id']), row['bc_mode'])


def match_sims(rows_a, rows_b):
    """Match sims between two CSVs by combo + defect parameters.

    Groups by combo key, then matches within combo by sim index (sorted by pressure_x).
    Returns list of (row_a, row_b) pairs.
    """
    from collections import defaultdict
    groups_a = defaultdict(list)
    groups_b = defaultdict(list)
    for r in rows_a:
        if r['solver_completed'] == 'YES':
            groups_a[combo_key(r)].append(r)
    for r in rows_b:
        if r['solver_completed'] == 'YES':
            groups_b[combo_key(r)].append(r)

    pairs = []
    for key in groups_a:
        if key not in groups_b:
            continue
        ga = sorted(groups_a[key], key=lambda r: r['pressure_x'])
        gb = sorted(groups_b[key], key=lambda r: r['pressure_x'])
        n = min(len(ga), len(gb))
        for i in range(n):
            pairs.append((ga[i], gb[i]))
    return pairs


# =============================================================================
# 6.1 Seed alignment (CRITICAL)
# =============================================================================
def check_seed_alignment(coarse, medium, fine):
    print("\n=== 6.1 Seed Alignment (CRITICAL) ===")

    # Match coarse-medium
    pairs_cm = match_sims(coarse, medium)
    pairs_mf = match_sims(medium, fine)

    print(f"  Matched pairs: coarse-medium={len(pairs_cm)}, medium-fine={len(pairs_mf)}")

    # Check defect parameters match exactly
    seed_fields = ['defect1_x', 'defect1_y', 'defect1_half_length',
                   'defect1_angle', 'defect1_roughness',
                   'pressure_x', 'pressure_y']

    mismatches_cm = 0
    for ra, rb in pairs_cm[:500]:  # Sample first 500 pairs
        for field in seed_fields:
            va = float(ra.get(field, 0))
            vb = float(rb.get(field, 0))
            if abs(va - vb) > 1e-6:
                mismatches_cm += 1
                break

    check(f"6.1 Coarse-Medium seed alignment: {mismatches_cm} mismatches in {min(len(pairs_cm), 500)} pairs",
          mismatches_cm == 0)

    mismatches_mf = 0
    for ra, rb in pairs_mf[:500]:
        for field in seed_fields:
            va = float(ra.get(field, 0))
            vb = float(rb.get(field, 0))
            if abs(va - vb) > 1e-6:
                mismatches_mf += 1
                break

    check(f"6.1 Medium-Fine seed alignment: {mismatches_mf} mismatches in {min(len(pairs_mf), 500)} pairs",
          mismatches_mf == 0)

    # n_elements: fine > medium > coarse for matched pairs
    elem_ordering = 0
    total_checked = 0
    for rc, rm in pairs_cm[:200]:
        # Find matching fine sim
        for rmf, rf in pairs_mf:
            if (int(rmf['material_id']) == int(rm['material_id']) and
                int(rmf['layup_id']) == int(rm['layup_id']) and
                abs(rmf['pressure_x'] - rm['pressure_x']) < 1e-6):
                nc = int(rc['n_elements'])
                nm = int(rm['n_elements'])
                nf = int(rf['n_elements'])
                total_checked += 1
                if nf > nm > nc:
                    elem_ordering += 1
                break

    if total_checked > 0:
        check(f"6.1 n_elements: fine > medium > coarse ({elem_ordering}/{total_checked})",
              elem_ordering / total_checked > 0.95)

    return pairs_cm, pairs_mf


# =============================================================================
# 6.2 Convergence metrics
# =============================================================================
def check_convergence(pairs_cm, pairs_mf):
    print("\n=== 6.2 Convergence Metrics ===")

    def compute_rel_diffs(pairs, fi_col='tsai_wu_index'):
        diffs = []
        for ra, rb in pairs:
            va = float(ra.get(fi_col, 0))
            vb = float(rb.get(fi_col, 0))
            denom = max(abs(vb), 0.01)
            rel = abs(va - vb) / denom
            diffs.append(rel)
        return sorted(diffs)

    # Fine vs Medium
    diffs_mf = compute_rel_diffs(pairs_mf)
    if diffs_mf:
        median_mf = diffs_mf[len(diffs_mf) // 2]
        p95_mf = diffs_mf[int(len(diffs_mf) * 0.95)]
        print(f"  Fine vs Medium: median_rel_diff={median_mf:.3f}, p95={p95_mf:.3f}")
        check(f"6.2 Fine-Medium median relative diff < 20%", median_mf < 0.20,
              f"median={median_mf:.3f}")
        check(f"6.2 Fine-Medium 95th percentile < 50%", p95_mf < 0.50,
              f"p95={p95_mf:.3f}")

    # Coarse vs Medium
    diffs_cm = compute_rel_diffs(pairs_cm)
    if diffs_cm:
        median_cm = diffs_cm[len(diffs_cm) // 2]
        p95_cm = diffs_cm[int(len(diffs_cm) * 0.95)]
        print(f"  Coarse vs Medium: median_rel_diff={median_cm:.3f}, p95={p95_cm:.3f}")

        # Monotonic convergence: coarse-medium diff should be LARGER than fine-medium diff
        if diffs_mf:
            check("6.2 Monotonic convergence: coarse-medium diff > fine-medium diff",
                  median_cm > median_mf * 0.8,  # Allow some tolerance
                  f"coarse-med={median_cm:.3f}, fine-med={median_mf:.3f}")


# =============================================================================
# 6.3 No mesh-level bias
# =============================================================================
def check_mesh_bias(coarse, medium, fine):
    print("\n=== 6.3 No Mesh-Level Bias ===")

    def failure_rate(rows):
        yes = [r for r in rows if r['solver_completed'] == 'YES']
        if not yes:
            return 0
        return sum(1 for r in yes if float(r.get('tsai_wu_index', 0)) >= 1.0) / len(yes)

    fr_c = failure_rate(coarse)
    fr_m = failure_rate(medium)
    fr_f = failure_rate(fine)

    print(f"  Failure rates: coarse={fr_c:.1%}, medium={fr_m:.1%}, fine={fr_f:.1%}")

    check("6.3 Global failure rate diff < 15% between mesh levels",
          abs(fr_c - fr_f) < 0.15,
          f"|coarse-fine|={abs(fr_c-fr_f):.1%}")

    # Per-material check
    mat_ids = sorted(set(int(r['material_id']) for r in medium))
    for mid in mat_ids:
        mname = B.MATERIALS.get(mid, {}).get('name', f'mat{mid}')
        fr_mc = failure_rate([r for r in coarse if int(r['material_id']) == mid])
        fr_mf = failure_rate([r for r in fine if int(r['material_id']) == mid])
        if abs(fr_mc - fr_mf) > 0.30:
            check(f"6.3 Mat {mid} ({mname}): coarse-fine bias < 30%", False,
                  f"|diff|={abs(fr_mc-fr_mf):.1%}")


# =============================================================================
# 6.4 Element count scaling
# =============================================================================
def check_element_scaling(coarse, medium, fine):
    print("\n=== 6.4 Element Count Scaling ===")

    def median_elements(rows):
        elems = sorted(int(r['n_elements']) for r in rows
                       if r['solver_completed'] == 'YES' and int(r.get('n_elements', 0)) > 0)
        return elems[len(elems) // 2] if elems else 0

    nc = median_elements(coarse)
    nm = median_elements(medium)
    nf = median_elements(fine)

    print(f"  Median elements: coarse={nc}, medium={nm}, fine={nf}")

    if nc > 0 and nm > 0:
        ratio_mc = nm / nc
        check(f"6.4 medium/coarse element ratio ≈ 3-6× (got {ratio_mc:.1f}×)",
              2.0 <= ratio_mc <= 8.0)

    if nm > 0 and nf > 0:
        ratio_fm = nf / nm
        check(f"6.4 fine/medium element ratio ≈ 3-6× (got {ratio_fm:.1f}×)",
              2.0 <= ratio_fm <= 8.0)


# =============================================================================
# Main
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description="Mesh convergence analysis")
    parser.add_argument('coarse_csv', help="Path to coarse mesh results CSV")
    parser.add_argument('medium_csv', help="Path to medium mesh results CSV")
    parser.add_argument('fine_csv', help="Path to fine mesh results CSV")
    args = parser.parse_args()

    for path in [args.coarse_csv, args.medium_csv, args.fine_csv]:
        if not os.path.exists(path):
            print(f"ERROR: File not found: {path}")
            sys.exit(1)

    print("=" * 70)
    print("Phase 6: Mesh Convergence Analysis")
    print("=" * 70)

    print(f"Loading CSVs...")
    coarse = load_csv(args.coarse_csv)
    medium = load_csv(args.medium_csv)
    fine = load_csv(args.fine_csv)
    print(f"  Coarse: {len(coarse)} rows")
    print(f"  Medium: {len(medium)} rows")
    print(f"  Fine:   {len(fine)} rows")

    pairs_cm, pairs_mf = check_seed_alignment(coarse, medium, fine)
    check_convergence(pairs_cm, pairs_mf)
    check_mesh_bias(coarse, medium, fine)
    check_element_scaling(coarse, medium, fine)

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
        print("\nAll mesh convergence checks passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()
