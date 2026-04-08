"""
CompositeBench — Post-tier analysis script.
Checks convergence, pressure ranges, failure indices, physics sanity.

Usage:
  python analyze_test.py <csv_file> [--geometry flat|cutout|curved]
"""

import csv
import sys
import math
import os

# Import material/layup data from the batch script
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from batch_compositeNet import (
    MATERIALS, LAYUPS, MATERIAL_PRESSURE_RANGES,
    LAYUP_SCALE_FACTORS, CUTOUT_PRESSURE_FACTOR,
    _clt_fpf_uniaxial_x,
)


def load_csv(path):
    with open(path, 'r', newline='') as f:
        reader = csv.DictReader(f)
        return list(reader)


def analyze(rows, geometry="flat"):
    n = len(rows)
    print(f"\n{'='*70}")
    print(f"  ANALYSIS: {n} rows, geometry={geometry}")
    print(f"{'='*70}")

    # ── 1. Convergence rate ──
    ok = sum(1 for r in rows if r.get('solver_completed') == 'YES')
    fail = n - ok
    pct = 100 * ok / n if n else 0
    status = "PASS" if pct >= 90 else "WARN" if pct >= 70 else "FAIL"
    print(f"\n[{status}] Convergence: {ok}/{n} ({pct:.1f}%)")
    if fail > 0:
        # Break down failures by material/layup
        fail_by_mat = {}
        for r in rows:
            if r.get('solver_completed') != 'YES':
                mid = r.get('material_id', '?')
                fail_by_mat[mid] = fail_by_mat.get(mid, 0) + 1
        print(f"  Failures by material: {fail_by_mat}")

    # Filter to successful sims for remaining checks
    good = [r for r in rows if r.get('solver_completed') == 'YES']
    if not good:
        print("\n  No successful sims to analyze!")
        return False

    # ── 2. Pressure range validation ──
    print(f"\n── Pressure Range Check ──")
    px_issues = 0
    for r in good:
        mid = int(r['material_id'])
        lid = int(r['layup_id'])
        px = float(r['pressure_x'])

        px_lo, px_hi = MATERIAL_PRESSURE_RANGES[mid]
        ls = LAYUP_SCALE_FACTORS[lid]
        px_lo_s = px_lo * ls
        px_hi_s = px_hi * ls
        if geometry == "cutout":
            px_lo_s *= CUTOUT_PRESSURE_FACTOR
            px_hi_s *= CUTOUT_PRESSURE_FACTOR

        # Allow 1% tolerance for floating point
        tol = 0.01 * (px_hi_s - px_lo_s) if px_hi_s > px_lo_s else 0.1
        if px < px_lo_s - tol or px > px_hi_s + tol:
            if px_issues < 5:
                print(f"  OUT OF RANGE: sim {r['sim_id']} mat={mid} layup={lid} "
                      f"px={px:.2f} expected [{px_lo_s:.2f}, {px_hi_s:.2f}]")
            px_issues += 1
    if px_issues == 0:
        print(f"  [PASS] All {len(good)} sims have pressure_x in expected range")
    else:
        print(f"  [FAIL] {px_issues}/{len(good)} sims with pressure_x out of range")

    # ── 3. Failure index distribution ──
    print(f"\n── Failure Index Distribution ──")
    for idx_name in ['tsai_wu_index', 'max_hashin_ft', 'puck_ff', 'larc_ft']:
        vals = []
        for r in good:
            try:
                v = float(r.get(idx_name, 0))
                if not math.isnan(v):
                    vals.append(v)
            except (ValueError, TypeError):
                pass
        if not vals:
            print(f"  {idx_name}: ALL NaN/missing")
            continue
        n_zero = sum(1 for v in vals if abs(v) < 1e-12)
        vals_sorted = sorted(vals)
        p25 = vals_sorted[len(vals_sorted)//4]
        p50 = vals_sorted[len(vals_sorted)//2]
        p75 = vals_sorted[3*len(vals_sorted)//4]
        n_gt1 = sum(1 for v in vals if v > 1.0)
        print(f"  {idx_name}: n={len(vals)}, zeros={n_zero}, "
              f"p25={p25:.4f}, p50={p50:.4f}, p75={p75:.4f}, max={max(vals):.4f}, "
              f"n>1={n_gt1} ({100*n_gt1/len(vals):.0f}%)")

    # ── 4. NaN/zero column check ──
    print(f"\n── NaN/Zero Column Check ──")
    stress_cols = ['max_mises', 'max_s11', 'min_s11', 'max_s12']
    for col in stress_cols:
        vals = []
        n_nan = 0
        n_zero = 0
        for r in good:
            try:
                v = float(r.get(col, 0))
                if math.isnan(v):
                    n_nan += 1
                elif abs(v) < 1e-12:
                    n_zero += 1
                else:
                    vals.append(v)
            except (ValueError, TypeError):
                n_nan += 1
        if vals:
            print(f"  {col}: valid={len(vals)}, nan={n_nan}, zero={n_zero}, "
                  f"range=[{min(vals):.2f}, {max(vals):.2f}]")
            if max(vals) > 1e12:
                print(f"    [WARN] Suspiciously large stress: {max(vals):.2e}")
        else:
            print(f"  {col}: ALL nan/zero — [FAIL]")

    # ── 5. Failure flag correlation ──
    print(f"\n── Failure Flag Correlation ──")
    for criterion, idx_col, flag_col in [
        ('Tsai-Wu', 'tsai_wu_index', 'failed_tsai_wu'),
        ('Hashin', 'max_hashin_ft', 'failed_hashin'),
        ('Puck', 'puck_ff', 'failed_puck'),
        ('LaRC', 'larc_ft', 'failed_larc'),
    ]:
        n_flag = sum(1 for r in good if str(r.get(flag_col, '0')) == '1')
        # Check: if index > 1, flag should be 1
        mismatches = 0
        for r in good:
            try:
                idx_val = float(r.get(idx_col, 0))
                flag_val = str(r.get(flag_col, '0'))
                if idx_val > 1.0 and flag_val != '1':
                    mismatches += 1
            except (ValueError, TypeError):
                pass
        print(f"  {criterion}: {n_flag}/{len(good)} flagged failed, {mismatches} mismatches (idx>1 but flag=0)")

    # ── 6. Physics cross-checks ──
    print(f"\n── Physics Cross-Checks ──")

    # Group by material
    by_mat = {}
    for r in good:
        mid = int(r['material_id'])
        by_mat.setdefault(mid, []).append(r)

    for mid, mat_rows in sorted(by_mat.items()):
        mat_name = MATERIALS[mid]['name']
        tw_vals = []
        px_vals = []
        for r in mat_rows:
            try:
                tw = float(r.get('tsai_wu_index', 0))
                px = float(r.get('pressure_x', 0))
                if not math.isnan(tw):
                    tw_vals.append(tw)
                    px_vals.append(px)
            except (ValueError, TypeError):
                pass
        if tw_vals:
            avg_tw = sum(tw_vals) / len(tw_vals)
            max_tw = max(tw_vals)
            avg_px = sum(px_vals) / len(px_vals)
            n_failed = sum(1 for v in tw_vals if v > 1.0)
            print(f"  Mat {mid:2d} ({mat_name:18s}): n={len(tw_vals):3d}, "
                  f"avg_px={avg_px:8.2f} MPa, avg_TW={avg_tw:.3f}, max_TW={max_tw:.3f}, "
                  f"n_failed={n_failed}")

    # Geometry-specific checks
    if geometry == "cutout":
        print(f"\n── Cutout-Specific Checks ──")
        for r in good:
            hd = float(r.get('hole_diameter', 0))
            hx = float(r.get('hole_x', 0))
            hy = float(r.get('hole_y', 0))
            if hd < 4.9 or hd > 20.1:
                print(f"  [WARN] sim {r['sim_id']}: hole_diameter={hd:.1f} outside [5,20]")
            if hx < 0 or hx > 100 or hy < 0 or hy > 50:
                print(f"  [WARN] sim {r['sim_id']}: hole position ({hx:.1f},{hy:.1f}) outside plate")
        print(f"  Checked {len(good)} cutout sims for hole bounds")

    elif geometry == "curved":
        print(f"\n── Curved-Specific Checks ──")
        for r in good:
            rad = float(r.get('panel_radius', 0))
            if rad < 99 or rad > 501:
                print(f"  [WARN] sim {r['sim_id']}: panel_radius={rad:.1f} outside [100,500]")
        print(f"  Checked {len(good)} curved sims for radius bounds")

    print(f"\n{'='*70}")
    all_ok = px_issues == 0 and pct >= 90
    if all_ok:
        print("  OVERALL: PASS")
    else:
        print("  OVERALL: ISSUES FOUND — review above")
    print(f"{'='*70}\n")
    return all_ok


def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_test.py <csv_file> [--geometry flat|cutout|curved]")
        sys.exit(1)

    csv_path = sys.argv[1]
    geometry = "flat"
    if '--geometry' in sys.argv:
        idx = sys.argv.index('--geometry')
        if idx + 1 < len(sys.argv):
            geometry = sys.argv[idx + 1]

    rows = load_csv(csv_path)
    if not rows:
        print(f"No data in {csv_path}")
        sys.exit(1)

    analyze(rows, geometry)


if __name__ == "__main__":
    main()
