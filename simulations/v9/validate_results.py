#!/usr/bin/env python3
"""Phase 5+: Reusable CSV Validator for CompositeBench results.

Validates completeness, per-material/layup/BC plausibility, defect sanity,
cross-column consistency, and geometry-specific checks.

Usage:
  python3 validate_results.py <csv_path> [--expected-rows N] [--geometry flat|cutout|curved]
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
_warn_count = 0
_results = []

def check(name, condition, detail=""):
    global _pass_count, _fail_count
    if condition:
        _pass_count += 1
        _results.append(("PASS", name))
    else:
        _fail_count += 1
        _results.append(("FAIL", name, detail))
        print(f"  FAIL: {name} — {detail}")

def warn(name, detail=""):
    global _warn_count
    _warn_count += 1
    _results.append(("WARN", name, detail))
    print(f"  WARN: {name} — {detail}")


def load_csv(csv_path):
    """Load CSV into list of dicts, converting numeric fields."""
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


# =============================================================================
# 5.1 Completeness
# =============================================================================
def check_completeness(rows, expected_rows=None, csv_path=""):
    print("\n=== 5.1 Completeness ===")

    if expected_rows:
        actual = len(rows)
        pct = abs(actual - expected_rows) / expected_rows if expected_rows > 0 else 0
        check(f"Row count matches expected (±1%): {actual} vs {expected_rows}",
              pct < 0.01, f"diff={pct:.1%}")

    # solver_completed = 'YES' for ≥93% (thick 24-ply laminates have known solver issues
    # contributing ~5.7% error rate; remaining 1.3% margin for occasional errors)
    yes_count = sum(1 for r in rows if r.get('solver_completed') == 'YES')
    yes_pct = yes_count / len(rows) if rows else 0
    check(f"solver_completed=YES for ≥93%: {yes_pct:.1%}",
          yes_pct >= 0.93, f"YES={yes_count}/{len(rows)} ({yes_pct:.1%})")

    # No NaN or Inf in numeric columns
    numeric_cols = [c for c in B.CSV_COLUMNS
                    if c not in ('material_name', 'layup_name', 'bc_mode', 'geometry',
                                 'mesh_level', 'solver_completed')]
    nan_inf_count = 0
    for r in rows:
        for col in numeric_cols:
            val = r.get(col)
            if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                nan_inf_count += 1
    check(f"No NaN/Inf in numeric columns", nan_inf_count == 0,
          f"found {nan_inf_count} NaN/Inf values")

    # All 131 columns populated
    if rows:
        cols_present = set(rows[0].keys())
        expected_cols = set(B.CSV_COLUMNS)
        missing = expected_cols - cols_present
        check(f"All 131 columns present", len(missing) == 0,
              f"missing: {missing}")


# =============================================================================
# 5.2 Per-material plausibility
# =============================================================================
def check_per_material(rows):
    print("\n=== 5.2 Per-Material Plausibility ===")
    mat_ids = sorted(set(int(r['material_id']) for r in rows))

    for mid in mat_ids:
        mname = B.MATERIALS.get(mid, {}).get('name', f'mat{mid}')
        mat_rows = [r for r in rows if int(r['material_id']) == mid
                    and r['solver_completed'] == 'YES']
        if not mat_rows:
            warn(f"Mat {mid} ({mname}): no successful sims")
            continue

        max_s11_vals = [r['max_s11'] for r in mat_rows]
        min_s11_vals = [r['min_s11'] for r in mat_rows]
        tw_vals = [r['tsai_wu_index'] for r in mat_rows]

        check(f"Mat {mid} ({mname}): max_s11 > 0 exists",
              any(v > 0 for v in max_s11_vals))

        check(f"Mat {mid} ({mname}): min_s11 < 0 exists",
              any(v < 0 for v in min_s11_vals))

        # TW can be slightly negative for low-stress states (Tsai-Wu formula allows this)
        check(f"Mat {mid} ({mname}): all tsai_wu_index > -0.1",
              all(v > -0.1 for v in tw_vals),
              f"min_tw={min(tw_vals):.4f}")

        # Failure rate between 10-95% (some materials have extreme SCF sensitivity)
        failed = sum(1 for tw in tw_vals if tw >= 1.0)
        fr = failed / len(tw_vals)
        check(f"Mat {mid} ({mname}): failure rate 10-95% ({fr:.0%})",
              0.10 <= fr <= 0.95,
              f"failure_rate={fr:.0%} ({failed}/{len(tw_vals)})")

    # max_s11 roughly orders with E1 (correlation > 0.5)
    mat_mean_s11 = {}
    for mid in mat_ids:
        mat_rows = [r for r in rows if int(r['material_id']) == mid
                    and r['solver_completed'] == 'YES']
        if mat_rows:
            mat_mean_s11[mid] = sum(r['max_s11'] for r in mat_rows) / len(mat_rows)

    if len(mat_mean_s11) > 5:
        items = sorted(mat_mean_s11.items(), key=lambda x: B.MATERIALS[x[0]]['E1'])
        e1_rank = {m: i for i, (m, _) in enumerate(items)}
        items_s11 = sorted(mat_mean_s11.items(), key=lambda x: x[1])
        s11_rank = {m: i for i, (m, _) in enumerate(items_s11)}
        n = len(items)
        d_sq = sum((e1_rank[m] - s11_rank[m])**2 for m in e1_rank)
        rho = 1.0 - 6 * d_sq / (n * (n**2 - 1))
        check(f"max_s11 correlates with E1 (ρ={rho:.2f} > 0.5)", rho > 0.5)


# =============================================================================
# 5.3 Per-layup plausibility
# =============================================================================
def check_per_layup(rows):
    print("\n=== 5.3 Per-Layup Plausibility ===")
    layup_ids = sorted(set(int(r['layup_id']) for r in rows))

    for lid in layup_ids:
        lname = B.LAYUPS.get(lid, {}).get('name', f'layup{lid}')
        layup_rows = [r for r in rows if int(r['layup_id']) == lid
                      and r['solver_completed'] == 'YES']
        if not layup_rows:
            warn(f"Layup {lid} ({lname}): no successful sims")
            continue

        # Check lamination parameters match compute_lamination_params
        angles = B.LAYUPS[lid]['angles']
        expected_lp = B.compute_lamination_params(angles, 0.15)
        sample_row = layup_rows[0]
        lp_match = all(
            abs(sample_row.get(f'V{i}A', 0) - expected_lp[i-1]) < 0.01
            for i in [1, 2, 3, 4]
        )
        # V1A is index 0 in tuple, column name V1A
        check(f"Layup {lid} ({lname}): lamination params match",
              lp_match,
              f"expected V1A={expected_lp[0]:.4f}, got {sample_row.get('V1A', 'N/A')}")


# =============================================================================
# 5.4 Per-BC plausibility
# =============================================================================
def check_per_bc(rows):
    print("\n=== 5.4 Per-BC Plausibility ===")
    bc_modes = sorted(set(r['bc_mode'] for r in rows))

    bc_stats = {}
    for bc in bc_modes:
        bc_rows = [r for r in rows if r['bc_mode'] == bc and r['solver_completed'] == 'YES']
        if bc_rows:
            mean_s12 = sum(r['max_s12'] for r in bc_rows) / len(bc_rows)
            mean_min_s11 = sum(r['min_s11'] for r in bc_rows) / len(bc_rows)
            bc_stats[bc] = {'mean_s12': mean_s12, 'mean_min_s11': mean_min_s11}

    if 'uniaxial_shear' in bc_stats and 'biaxial' in bc_stats:
        check("BC: shear has higher mean(max_s12) than biaxial",
              bc_stats['uniaxial_shear']['mean_s12'] > bc_stats['biaxial']['mean_s12'],
              f"shear={bc_stats['uniaxial_shear']['mean_s12']:.2f}, "
              f"biaxial={bc_stats['biaxial']['mean_s12']:.2f}")

    if 'tension_comp' in bc_stats and 'biaxial' in bc_stats:
        check("BC: tension_comp has more negative min_s11",
              bc_stats['tension_comp']['mean_min_s11'] < bc_stats['biaxial']['mean_min_s11'],
              f"tc={bc_stats['tension_comp']['mean_min_s11']:.2f}, "
              f"biaxial={bc_stats['biaxial']['mean_min_s11']:.2f}")


# =============================================================================
# 5.5 Defect sanity
# =============================================================================
def check_defect_sanity(rows):
    print("\n=== 5.5 Defect Sanity ===")
    yes_rows = [r for r in rows if r['solver_completed'] == 'YES']

    # n_defects in [0, 5]
    bad_ndef = [r for r in rows if not (0 <= int(r.get('n_defects', 0)) <= 5)]
    check("n_defects ∈ [0, 5] for every sim", len(bad_ndef) == 0,
          f"{len(bad_ndef)} violations")

    # % with n_defects=0 < 5%
    zero_def = sum(1 for r in rows if int(r.get('n_defects', 0)) == 0)
    zero_pct = zero_def / len(rows) if rows else 0
    check(f"% sims with n_defects=0 < 5%: {zero_pct:.1%}",
          zero_pct < 0.05, f"{zero_def}/{len(rows)}")

    # Defect positions within valid range
    out_of_bounds = 0
    for r in yes_rows:
        for di in range(1, 6):
            px = f"defect{di}_x"
            py = f"defect{di}_y"
            if r.get(px, 0) > 0:  # defect exists
                x = float(r[px])
                y = float(r[py])
                if not (10 <= x <= 90 and 5 <= y <= 45):
                    out_of_bounds += 1
    check("Defect positions within expected bounds", out_of_bounds == 0,
          f"{out_of_bounds} out of bounds")

    # Per-defect max_tsai_wu_defect{i} ≥ 0
    neg_tw = 0
    for r in yes_rows:
        for di in range(1, 6):
            col = f"max_tsai_wu_defect{di}"
            val = float(r.get(col, 0))
            if val < 0:
                neg_tw += 1
    check("Per-defect max_tsai_wu_defect ≥ 0", neg_tw == 0, f"{neg_tw} negative")


# =============================================================================
# 5.6 Cross-column consistency
# =============================================================================
def check_cross_column(rows):
    print("\n=== 5.6 Cross-Column Consistency ===")
    yes_rows = [r for r in rows if r['solver_completed'] == 'YES']

    # post_fpf = 1 ↔ at least one of failed_* = 1
    pf_mismatch = 0
    for r in yes_rows:
        pf = int(r.get('post_fpf', 0))
        any_failed = (int(r.get('failed_tsai_wu', 0)) or int(r.get('failed_hashin', 0))
                      or int(r.get('failed_puck', 0)) or int(r.get('failed_larc', 0)))
        if pf != (1 if any_failed else 0):
            pf_mismatch += 1
    check("post_fpf consistent with failed_* flags", pf_mismatch == 0,
          f"{pf_mismatch} mismatches")

    # failed_tsai_wu = 1 → tsai_wu_index ≥ 1.0
    tw_mismatch = 0
    for r in yes_rows:
        if int(r.get('failed_tsai_wu', 0)) == 1:
            if float(r.get('tsai_wu_index', 0)) < 1.0:
                tw_mismatch += 1
    check("failed_tsai_wu=1 → tsai_wu_index ≥ 1.0", tw_mismatch == 0,
          f"{tw_mismatch} mismatches")

    # failed_hashin = 1 → at least one hashin index ≥ 1.0
    h_mismatch = 0
    for r in yes_rows:
        if int(r.get('failed_hashin', 0)) == 1:
            h_max = max(float(r.get('max_hashin_ft', 0)), float(r.get('max_hashin_fc', 0)),
                        float(r.get('max_hashin_mt', 0)), float(r.get('max_hashin_mc', 0)))
            if h_max < 1.0:
                h_mismatch += 1
    check("failed_hashin=1 → hashin index ≥ 1.0", h_mismatch == 0,
          f"{h_mismatch} mismatches")

    # solver_completed = 'ERROR' → all indices = 0
    err_rows = [r for r in rows if r['solver_completed'] == 'ERROR']
    err_nonzero = 0
    for r in err_rows:
        if float(r.get('tsai_wu_index', 0)) != 0:
            err_nonzero += 1
    check("solver_completed=ERROR → indices=0", err_nonzero == 0,
          f"{err_nonzero} errors with non-zero indices")


# =============================================================================
# 5.7 Cutout-specific
# =============================================================================
def check_cutout(rows):
    print("\n=== 5.7 Cutout-Specific ===")
    cutout_rows = [r for r in rows if r.get('geometry') == 'cutout']
    if not cutout_rows:
        print("  [SKIP] No cutout rows found")
        return

    # hole_diameter in [5, 20]
    bad_hole = [r for r in cutout_rows
                if not (5.0 <= float(r.get('hole_diameter', 0)) <= 20.0)
                and float(r.get('hole_diameter', 0)) > 0]
    check("Cutout: hole_diameter ∈ [5, 20]", len(bad_hole) == 0,
          f"{len(bad_hole)} out of range")

    # hole_x, hole_y within plate bounds
    bad_pos = 0
    for r in cutout_rows:
        hx = float(r.get('hole_x', 0))
        hy = float(r.get('hole_y', 0))
        if hx > 0 and (hx < 0 or hx > B.PLATE_L or hy < 0 or hy > B.PLATE_W):
            bad_pos += 1
    check("Cutout: hole position within plate", bad_pos == 0)


# =============================================================================
# 5.8 Curved-specific
# =============================================================================
def check_curved(rows):
    print("\n=== 5.8 Curved-Specific ===")
    curved_rows = [r for r in rows if r.get('geometry') == 'curved']
    if not curved_rows:
        print("  [SKIP] No curved rows found")
        return

    # panel_radius in [200, 500]
    bad_radius = [r for r in curved_rows
                  if not (200 <= float(r.get('panel_radius', 0)) <= 500)
                  and float(r.get('panel_radius', 0)) > 0]
    check("Curved: panel_radius ∈ [200, 500]", len(bad_radius) == 0,
          f"{len(bad_radius)} out of range")


# =============================================================================
# Main
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description="Validate CompositeBench CSV results")
    parser.add_argument('csv_path', help="Path to results CSV file")
    parser.add_argument('--expected-rows', type=int, default=None,
                        help="Expected number of rows (±1%%)")
    parser.add_argument('--geometry', type=str, default=None,
                        choices=['flat', 'cutout', 'curved'],
                        help="Expected geometry type")
    args = parser.parse_args()

    if not os.path.exists(args.csv_path):
        print(f"ERROR: CSV file not found: {args.csv_path}")
        sys.exit(1)

    print("=" * 70)
    print(f"Validating: {args.csv_path}")
    print("=" * 70)

    rows = load_csv(args.csv_path)
    print(f"Loaded {len(rows)} rows")

    check_completeness(rows, args.expected_rows, args.csv_path)
    check_per_material(rows)
    check_per_layup(rows)
    check_per_bc(rows)
    check_defect_sanity(rows)
    check_cross_column(rows)
    check_cutout(rows)
    check_curved(rows)

    print("\n" + "=" * 70)
    print(f"RESULTS: {_pass_count} passed, {_fail_count} failed, {_warn_count} warnings")
    print("=" * 70)

    if _fail_count > 0:
        print("\nFailed checks:")
        for r in _results:
            if r[0] == "FAIL":
                print(f"  ✗ {r[1]}: {r[2]}")
        sys.exit(1)
    else:
        print("\nAll validation checks passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()
