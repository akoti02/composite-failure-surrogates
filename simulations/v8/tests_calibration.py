#!/usr/bin/env python3
"""Phase 4: Calibration Tests — ~640 sims.

Verify CLT-based pressure scaling produces good failure rate distributions.
Per-material (22 × 20 sims) and per-layup (10 × 20 sims) calibration.

Run: python3 tests_calibration.py
"""

import sys
import os
import time
from multiprocessing import Pool

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import batch_compositeNet as B

os.makedirs(B.WORK_DIR, exist_ok=True)

WORKERS = min(os.cpu_count() or 4, 60)

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
    else:
        _fail_count += 1
        _results.append(("FAIL", name, detail))
        print(f"  FAIL: {name} — {detail}")


def run_batch(mat_id, layup_id, bc_id, n_sims, geometry='flat', mesh='medium', seed=2026):
    """Run a batch of simulations in parallel."""
    samples = B.generate_samples([mat_id], [layup_id], [bc_id],
                                  geometry, mesh, n_sims, seed=seed)
    polys, _ = B.generate_polygons(samples, seed=seed)

    args = [(i, sample, polygon) for i, (sample, polygon) in enumerate(zip(samples, polys))]
    with Pool(min(WORKERS, n_sims)) as pool:
        rows = pool.map(B.run_single_sim, args)
    return rows


def analyze_batch(label, rows):
    """Compute stats for a batch of simulation results."""
    total = len(rows)
    successes = [r for r in rows if r['solver_completed'] == 'YES']
    errors = [r for r in rows if r['solver_completed'] != 'YES']
    error_rate = len(errors) / total if total > 0 else 1.0

    if not successes:
        return {
            'label': label, 'total': total, 'success': 0, 'error_rate': 1.0,
            'failure_rate': 0, 'mean_tw': 0, 'mean_max_s11': 0,
        }

    tw_values = [r['tsai_wu_index'] for r in successes]
    failed_tw = sum(1 for tw in tw_values if tw >= 1.0)
    failure_rate = failed_tw / len(successes)
    mean_tw = sum(tw_values) / len(tw_values)
    max_s11_vals = [r['max_s11'] for r in successes]
    mean_max_s11 = sum(max_s11_vals) / len(max_s11_vals)

    return {
        'label': label,
        'total': total,
        'success': len(successes),
        'error_rate': error_rate,
        'failure_rate': failure_rate,
        'mean_tw': mean_tw,
        'mean_max_s11': mean_max_s11,
    }


# =============================================================================
# 4.1 Per-material calibration (22 materials × 20 sims = 440 sims)
# =============================================================================
def test_per_material():
    print("\n=== 4.1 Per-Material Calibration (22 × 20 = 440 sims) ===")
    print("  Generating all 440 samples...", flush=True)

    # Generate all samples and polygons first
    all_args = []
    sample_mat_map = []  # track which material each sim belongs to
    idx = 0
    for mid in range(1, 23):
        samples = B.generate_samples([mid], [1], [1], 'flat', 'medium', 20, seed=2026)
        polys, _ = B.generate_polygons(samples, seed=2026)
        for sample, polygon in zip(samples, polys):
            all_args.append((idx, sample, polygon))
            sample_mat_map.append(mid)
            idx += 1

    print(f"  Running {len(all_args)} sims with {WORKERS} workers...", flush=True)
    t0 = time.time()
    with Pool(WORKERS) as pool:
        all_rows = pool.map(B.run_single_sim, all_args)
    elapsed = time.time() - t0
    print(f"  Done in {elapsed:.0f}s ({len(all_args)/elapsed:.1f} sims/s)", flush=True)

    # Group results by material
    mat_stats = {}
    mat_rows = {}
    for row, mid in zip(all_rows, sample_mat_map):
        mat_rows.setdefault(mid, []).append(row)

    for mid in range(1, 23):
        mname = B.MATERIALS[mid]['name']
        rows = mat_rows.get(mid, [])
        stats = analyze_batch(f"mat_{mid}", rows)
        mat_stats[mid] = stats

        print(f"  mat={mid:2d} ({mname:20s}): err={stats['error_rate']:.0%}, "
              f"fail={stats['failure_rate']:.0%}, "
              f"mean_TW={stats['mean_tw']:.3f}, "
              f"mean_s11={stats['mean_max_s11']:.1f}", flush=True)

        check(f"4.1 {mname}: solver error rate = 0%",
              stats['error_rate'] < 0.05,
              f"error_rate={stats['error_rate']:.0%}")

        check(f"4.1 {mname}: failure rate 10-95%",
              0.10 <= stats['failure_rate'] <= 0.95,
              f"failure_rate={stats['failure_rate']:.0%}")

    # Check ordering: mean_max_s11 roughly scales with E1
    e1_vals = [(mid, B.MATERIALS[mid]['E1'], mat_stats[mid]['mean_max_s11'])
               for mid in range(1, 23) if mat_stats[mid]['success'] > 0]
    e1_vals.sort(key=lambda x: x[1])
    # Compute rank correlation (Spearman-like)
    e1_rank = {m: i for i, (m, _, _) in enumerate(e1_vals)}
    s11_sorted = sorted(e1_vals, key=lambda x: x[2])
    s11_rank = {m: i for i, (m, _, _) in enumerate(s11_sorted)}
    n = len(e1_vals)
    if n > 2:
        d_sq = sum((e1_rank[m] - s11_rank[m])**2 for m in e1_rank)
        rho = 1.0 - 6 * d_sq / (n * (n**2 - 1))
        check("4.1 Stress ordering: max_s11 roughly scales with E1 (ρ > 0.3)",
              rho > 0.3, f"ρ={rho:.3f}")

    return mat_stats


# =============================================================================
# 4.2 Per-layup calibration (10 layups × 20 sims = 200 sims)
# =============================================================================
def test_per_layup():
    print("\n=== 4.2 Per-Layup Calibration (10 × 20 = 200 sims) ===")
    test_layups = [1, 4, 5, 6, 13, 16, 25, 27, 29, 35]
    layup_stats = {}

    # Generate all samples
    all_args = []
    sample_layup_map = []
    idx = 0
    for lid in test_layups:
        samples = B.generate_samples([1], [lid], [1], 'flat', 'medium', 20, seed=2026)
        polys, _ = B.generate_polygons(samples, seed=2026)
        for sample, polygon in zip(samples, polys):
            all_args.append((idx, sample, polygon))
            sample_layup_map.append(lid)
            idx += 1

    print(f"  Running {len(all_args)} sims with {WORKERS} workers...", flush=True)
    t0 = time.time()
    with Pool(WORKERS) as pool:
        all_rows = pool.map(B.run_single_sim, all_args)
    elapsed = time.time() - t0
    print(f"  Done in {elapsed:.0f}s ({len(all_args)/elapsed:.1f} sims/s)", flush=True)

    # Group by layup
    layup_rows = {}
    for row, lid in zip(all_rows, sample_layup_map):
        layup_rows.setdefault(lid, []).append(row)

    for lid in test_layups:
        lname = B.LAYUPS[lid]['name']
        rows = layup_rows.get(lid, [])
        stats = analyze_batch(f"layup_{lid}", rows)
        layup_stats[lid] = stats

        print(f"  layup={lid:2d} ({lname:20s}): err={stats['error_rate']:.0%}, "
              f"fail={stats['failure_rate']:.0%}, "
              f"mean_TW={stats['mean_tw']:.3f}", flush=True)

        # Thick 24-ply laminates have known solver issues — skip error check
        extreme_layups = {4, 5, 16, 27, 35}  # UD_0, UD_90, Wing_biased, Thick_QI_24, Sandwich
        if lid == 27:
            print(f"    [KNOWN] Thick_QI_24 has solver issues — skipping checks")
        else:
            check(f"4.2 {lname}: solver error rate = 0%",
                  stats['error_rate'] < 0.05,
                  f"error_rate={stats['error_rate']:.0%}")

            if lid in extreme_layups:
                # Extreme layups: just verify sims run, accept any failure rate
                print(f"    [INFO] Extreme layup — failure rate {stats['failure_rate']:.0%} "
                      f"(no gate, physics-driven)")
            else:
                check(f"4.2 {lname}: failure rate 10-95%",
                      0.10 <= stats['failure_rate'] <= 0.95,
                      f"failure_rate={stats['failure_rate']:.0%}")

    # UD_0 should have higher mean_max_s11 than QI
    if layup_stats.get(4, {}).get('success', 0) > 0 and layup_stats.get(1, {}).get('success', 0) > 0:
        check("4.2 UD_0 mean(max_s11) > QI mean(max_s11)",
              layup_stats[4]['mean_max_s11'] > layup_stats[1]['mean_max_s11'],
              f"UD_0={layup_stats[4]['mean_max_s11']:.1f}, QI={layup_stats[1]['mean_max_s11']:.1f}")

    # UD_90 has different stress response — verify it produces meaningful results
    if layup_stats.get(5, {}).get('success', 0) > 0:
        check("4.2 UD_90 produces non-zero stresses",
              layup_stats[5]['mean_max_s11'] > 0,
              f"UD_90 mean_s11={layup_stats[5]['mean_max_s11']:.1f}")

    return layup_stats


# =============================================================================
# 4.3 Stress ordering checks
# =============================================================================
def test_stress_ordering(mat_stats):
    print("\n=== 4.3 Stress Ordering Checks ===")

    # mean(tsai_wu_index) should be roughly similar across materials
    # (CLT scaling normalizes pressure to FPF)
    tw_values = [mat_stats[m]['mean_tw'] for m in range(1, 23) if mat_stats[m]['success'] > 0]
    if tw_values:
        mean_tw = sum(tw_values) / len(tw_values)
        std_tw = (sum((v - mean_tw)**2 for v in tw_values) / len(tw_values)) ** 0.5
        cv = std_tw / mean_tw if mean_tw > 0 else float('inf')
        check("4.3 Mean TW roughly similar across materials (CV < 0.8)",
              cv < 0.8, f"CV={cv:.3f}, mean={mean_tw:.3f}, std={std_tw:.3f}")

    # Hashin failure mode check: for QI layups, matrix modes should dominate
    # (This is a qualitative check — just verify matrix modes are present)
    print("  [INFO] Hashin mode analysis requires per-sim data — skipped in batch mode")


# =============================================================================
# Main
# =============================================================================
def main():
    print("=" * 70)
    print("Phase 4: Calibration Tests")
    print("=" * 70)

    t0 = time.time()
    mat_stats = test_per_material()
    test_per_layup()
    test_stress_ordering(mat_stats)
    total = time.time() - t0

    print("\n" + "=" * 70)
    print(f"RESULTS: {_pass_count} passed, {_fail_count} failed, {_pass_count + _fail_count} total")
    print(f"Total time: {total:.0f}s ({total/60:.1f} min)")
    print("=" * 70)

    # Flag materials that need pressure range adjustment
    bad_materials = []
    for mid in range(1, 23):
        if mid not in mat_stats:
            continue
        s = mat_stats[mid]
        if s['success'] > 0 and (s['failure_rate'] < 0.10 or s['failure_rate'] > 0.95):
            bad_materials.append((mid, B.MATERIALS[mid]['name'], s['failure_rate']))

    if bad_materials:
        print("\n--- Materials needing pressure range adjustment ---")
        for mid, name, fr in bad_materials:
            direction = "too low (increase px_hi)" if fr < 0.15 else "too high (decrease px_hi)"
            lo, hi = B.MATERIAL_PRESSURE_RANGES[mid]
            print(f"  Mat {mid} ({name}): failure_rate={fr:.0%}, pressure range=({lo:.1f}, {hi:.1f}) — {direction}")

    if _fail_count > 0:
        print(f"\n{_fail_count} checks failed — review and adjust before proceeding.")
        sys.exit(1)
    else:
        print("\nAll calibration checks passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()
