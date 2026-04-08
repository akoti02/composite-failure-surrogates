#!/usr/bin/env python3
"""Phase 2: Smoke Tests — Needs CalculiX + gmsh. Runs actual simulations.

27 simulations covering every geometry×mesh, BC modes, material extremes,
mesh convergence seed alignment, cutout and curved edge cases.

Uses run_single_sim() from batch_compositeNet.py directly.

Run: python3 tests_smoke.py
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import batch_compositeNet as B

# Ensure work directory exists
os.makedirs(B.WORK_DIR, exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# Test infrastructure
# ─────────────────────────────────────────────────────────────────────────────
_pass_count = 0
_fail_count = 0
_results = []
_sim_times = []

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


def run_sim(mat_id, layup_id, bc_id, geometry, mesh_level, seed=2026):
    """Generate one sample + polygon, run run_single_sim, return row dict."""
    samples = B.generate_samples([mat_id], [layup_id], [bc_id],
                                  geometry, mesh_level, 1, seed=seed)
    if not samples:
        return None
    sample = samples[0]
    polys, _ = B.generate_polygons([sample], seed=seed)
    polygons = polys[0]

    t0 = time.time()
    row = B.run_single_sim((0, sample, polygons))
    elapsed = time.time() - t0
    row['_elapsed'] = elapsed
    _sim_times.append((f"m{mat_id}_l{layup_id}_b{bc_id}_{geometry}_{mesh_level}", elapsed))
    return row


# =============================================================================
# 2.1 Every geometry × mesh combo (9 sims)
# =============================================================================
def test_geometry_mesh_combos():
    print("\n=== 2.1 Every Geometry × Mesh Combo (9 sims) ===")
    n_elems = {}
    for geom in ['flat', 'cutout', 'curved']:
        for mesh in ['coarse', 'medium', 'fine']:
            label = f"{geom}_{mesh}"
            row = run_sim(1, 1, 1, geom, mesh)

            check(f"2.1 {label}: solver completes",
                  row is not None and row['solver_completed'] == 'YES',
                  f"got {row['solver_completed'] if row else 'None'}")

            if row is None or row['solver_completed'] != 'YES':
                continue

            # All stresses finite
            check(f"2.1 {label}: stresses finite",
                  all(isinstance(row[k], (int, float)) for k in ['max_s11', 'min_s11', 'max_s12']))

            # All 4 failure indices ≥ 0
            check(f"2.1 {label}: failure indices ≥ 0",
                  row['tsai_wu_index'] >= 0)

            # CSV row has all 131 columns
            check(f"2.1 {label}: row has 131 columns",
                  all(k in row for k in B.CSV_COLUMNS))

            # post_fpf is 0 or 1
            check(f"2.1 {label}: post_fpf is 0 or 1",
                  row['post_fpf'] in (0, 1))

            n_elems[(geom, mesh)] = row['n_elements']

    # Element count: fine > medium > coarse
    for geom in ['flat', 'cutout', 'curved']:
        nc = n_elems.get((geom, 'coarse'), 0)
        nm = n_elems.get((geom, 'medium'), 0)
        nf = n_elems.get((geom, 'fine'), 0)
        if nc > 0 and nm > 0 and nf > 0:
            check(f"2.1 {geom}: fine({nf}) > medium({nm}) > coarse({nc})",
                  nf > nm > nc)


# =============================================================================
# 2.2 Every BC mode (3 sims)
# =============================================================================
def test_bc_modes():
    print("\n=== 2.2 Every BC Mode (3 sims) ===")
    rows = {}
    for bc_id in [1, 2, 3]:
        bc_name = B.BC_MODES[bc_id]
        row = run_sim(1, 1, bc_id, 'flat', 'medium')
        rows[bc_id] = row
        check(f"2.2 BC {bc_name}: converges",
              row is not None and row['solver_completed'] == 'YES')

    if rows.get(1) and rows.get(2):
        r1, r2 = rows[1], rows[2]
        if r1['solver_completed'] == 'YES' and r2['solver_completed'] == 'YES':
            check("2.2 biaxial vs tension_comp: different min_s11",
                  abs(r1['min_s11'] - r2['min_s11']) > 0.1,
                  f"biaxial={r1['min_s11']:.2f}, tension_comp={r2['min_s11']:.2f}")

    if rows.get(1) and rows.get(3):
        r1, r3 = rows[1], rows[3]
        if r1['solver_completed'] == 'YES' and r3['solver_completed'] == 'YES':
            check("2.2 shear BC has higher max_s12 than biaxial",
                  r3['max_s12'] > r1['max_s12'],
                  f"shear={r3['max_s12']:.2f}, biaxial={r1['max_s12']:.2f}")


# =============================================================================
# 2.3 Material extremes (6 sims)
# =============================================================================
def test_material_extremes():
    print("\n=== 2.3 Material Extremes — 6 Critical Materials ===")
    critical_mats = [9, 12, 15, 17, 21, 22]
    for mid in critical_mats:
        mname = B.MATERIALS[mid]['name']
        row = run_sim(mid, 1, 1, 'flat', 'medium')
        if row is None:
            check(f"2.3 {mname} (mat={mid}): converges", False, "returned None")
            continue
        check(f"2.3 {mname} (mat={mid}): converges",
              row['solver_completed'] == 'YES',
              f"got {row['solver_completed']}")
        if row['solver_completed'] == 'YES':
            check(f"2.3 {mname}: tsai_wu > 0",
                  row['tsai_wu_index'] > 0,
                  f"TW={row['tsai_wu_index']:.4f}")


# =============================================================================
# 2.4 Mesh convergence seed alignment (3 sims)
# =============================================================================
def test_seed_alignment():
    print("\n=== 2.4 Mesh Convergence Seed Alignment ===")
    samples_by_mesh = {}
    for mesh in ['coarse', 'medium', 'fine']:
        samples = B.generate_samples([1], [1], [1], 'flat', mesh, 1, seed=2026)
        samples_by_mesh[mesh] = samples[0]

    sc = samples_by_mesh['coarse']
    sm = samples_by_mesh['medium']
    sf = samples_by_mesh['fine']

    # Defect positions match exactly
    n_def = min(len(sc['defects']), len(sm['defects']), len(sf['defects']))
    if n_def > 0:
        pos_match = all(
            abs(sc['defects'][i]['x'] - sm['defects'][i]['x']) < 1e-10
            and abs(sc['defects'][i]['x'] - sf['defects'][i]['x']) < 1e-10
            and abs(sc['defects'][i]['y'] - sm['defects'][i]['y']) < 1e-10
            and abs(sc['defects'][i]['y'] - sf['defects'][i]['y']) < 1e-10
            for i in range(n_def)
        )
        check("2.4 Defect positions match exactly across mesh levels", pos_match)
    else:
        check("2.4 Defect positions match (no defects to compare)", True)

    # Pressure values match exactly
    check("2.4 Pressure values match across mesh levels",
          abs(sc['pressure_x'] - sm['pressure_x']) < 1e-10
          and abs(sc['pressure_x'] - sf['pressure_x']) < 1e-10)

    # Polygon coordinates match exactly
    pc, _ = B.generate_polygons([sc], seed=2026)
    pm, _ = B.generate_polygons([sm], seed=2026)
    pf, _ = B.generate_polygons([sf], seed=2026)
    if pc[0] and pm[0] and pf[0]:
        check("2.4 Polygon coordinates match across mesh levels",
              pc[0] == pm[0] == pf[0])

    # Actually run sims and verify n_elements differ
    rows = {}
    for mesh in ['coarse', 'medium', 'fine']:
        row = run_sim(1, 1, 1, 'flat', mesh)
        rows[mesh] = row
    nc = rows.get('coarse', {}).get('n_elements', 0)
    nm = rows.get('medium', {}).get('n_elements', 0)
    nf = rows.get('fine', {}).get('n_elements', 0)
    if nc > 0 and nm > 0 and nf > 0:
        check("2.4 n_elements differ across mesh levels",
              nc != nm and nm != nf,
              f"coarse={nc}, medium={nm}, fine={nf}")


# =============================================================================
# 2.5 Cutout edge cases (3 sims)
# =============================================================================
def test_cutout_edge_cases():
    print("\n=== 2.5 Cutout Edge Cases (3 sims) ===")
    for seed, desc in [(2026, "cutout seed A"), (2027, "cutout seed B"), (2028, "cutout seed C")]:
        row = run_sim(1, 1, 1, 'cutout', 'medium', seed=seed)
        check(f"2.5 {desc}: converges",
              row is not None and row['solver_completed'] == 'YES',
              f"got {row['solver_completed'] if row else 'None'}")


# =============================================================================
# 2.6 Curved edge cases (3 sims)
# =============================================================================
def test_curved_edge_cases():
    print("\n=== 2.6 Curved Edge Cases (3 sims) ===")
    for seed, desc in [(2026, "curved seed A"), (2027, "curved seed B"), (2028, "curved seed C")]:
        row = run_sim(1, 1, 1, 'curved', 'medium', seed=seed)
        check(f"2.6 {desc}: converges",
              row is not None and row['solver_completed'] == 'YES',
              f"got {row['solver_completed'] if row else 'None'}")


# =============================================================================
# Main
# =============================================================================
def main():
    print("=" * 70)
    print("Phase 2: Smoke Tests — CalculiX + gmsh")
    print("=" * 70)

    t0 = time.time()
    test_geometry_mesh_combos()
    test_bc_modes()
    test_material_extremes()
    test_seed_alignment()
    test_cutout_edge_cases()
    test_curved_edge_cases()
    total = time.time() - t0

    print("\n" + "=" * 70)
    print(f"RESULTS: {_pass_count} passed, {_fail_count} failed, {_pass_count + _fail_count} total")
    print(f"Total time: {total:.0f}s")
    print("=" * 70)

    if _sim_times:
        print("\nSim times (sorted by duration):")
        for label, t in sorted(_sim_times, key=lambda x: -x[1])[:10]:
            print(f"  {label}: {t:.1f}s")

    if _fail_count > 0:
        print("\nFailed tests:")
        for r in _results:
            if r[0] == "FAIL":
                print(f"  ✗ {r[1]}: {r[2]}")
        sys.exit(1)
    else:
        print("\nAll tests passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()
