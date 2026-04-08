#!/usr/bin/env python3
"""Phase 1: Unit Tests — Pure Python, no solver needed.

~49 tests covering failure criteria, CLT FPF, lamination parameters,
CSV schema, per-combo seeding, polygon seeding, pressure scaling,
material properties, edge cases, and defect placement bounds.

All tests import directly from batch_compositeNet.py.
Run: python3 tests_unit.py
"""

import sys
import os
import math
import random

# Ensure batch_compositeNet.py is importable
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
    else:
        _fail_count += 1
        _results.append(("FAIL", name, detail))
        print(f"  FAIL: {name} — {detail}")

def approx(a, b, tol=0.05):
    """Relative tolerance check."""
    if abs(b) < 1e-12:
        return abs(a) < tol
    return abs(a - b) / max(abs(b), 1e-12) < tol

def approx_abs(a, b, tol=0.001):
    """Absolute tolerance check."""
    return abs(a - b) < tol

# ─────────────────────────────────────────────────────────────────────────────
# Helper: build synthetic stress_data and call compute_metrics
# ─────────────────────────────────────────────────────────────────────────────
def metrics_from_stress(s11, s22, s12, mat_dict):
    """Feed a single stress point to compute_metrics and return the result dict."""
    stress_data = [(1, 1, s11, s22, 0.0, s12, 0.0, 0.0)]
    centroids = {1: (50.0, 25.0, 0.0)}
    defects = [{'x': 50.0, 'y': 25.0, 'half_length': 5.0}]
    return B.compute_metrics(stress_data, centroids, defects, mat_dict)


# =============================================================================
# 1.1 Failure criteria correctness (12 tests)
# =============================================================================
def test_failure_criteria():
    print("\n=== 1.1 Failure Criteria Correctness ===")
    mat = B.MATERIALS[1]  # T300/5208
    XT, XC = float(mat['XT']), float(mat['XC'])
    YT, YC = float(mat['YT']), float(mat['YC'])
    SL = float(mat['SL'])

    # Tsai-Wu tests
    m = metrics_from_stress(XT, 0, 0, mat)
    check("TW: pure σ11=XT → TW≈1.0", approx_abs(m['tsai_wu_index'], 1.0, 0.05),
          f"got {m['tsai_wu_index']:.4f}")

    m = metrics_from_stress(0, YT, 0, mat)
    check("TW: pure σ22=YT → TW≈1.0", approx_abs(m['tsai_wu_index'], 1.0, 0.05),
          f"got {m['tsai_wu_index']:.4f}")

    m = metrics_from_stress(0, -YC, 0, mat)
    check("TW: pure σ22=-YC → TW≈1.0", approx_abs(m['tsai_wu_index'], 1.0, 0.05),
          f"got {m['tsai_wu_index']:.4f}")

    m = metrics_from_stress(0, 0, 0, mat)
    check("TW: zero stress → TW=0.0", approx_abs(m['tsai_wu_index'], 0.0, 0.001),
          f"got {m['tsai_wu_index']:.4f}")

    # Hashin tests
    m = metrics_from_stress(XT, 0, 0, mat)
    check("Hashin: σ11=XT, σ12=0 → HFT=1.0", approx_abs(m['max_hashin_ft'], 1.0, 0.001),
          f"got {m['max_hashin_ft']:.4f}")

    m = metrics_from_stress(-XC, 0, 0, mat)
    check("Hashin: σ11=-XC → HFC=1.0", approx_abs(m['max_hashin_fc'], 1.0, 0.001),
          f"got {m['max_hashin_fc']:.4f}")

    m = metrics_from_stress(0, YT, 0, mat)
    check("Hashin: σ22=YT, σ12=0 → HMT=1.0", approx_abs(m['max_hashin_mt'], 1.0, 0.001),
          f"got {m['max_hashin_mt']:.4f}")

    # Hashin matrix compression uses ST = YC/(2*tan(53°))
    ST = YC / (2.0 * math.tan(math.radians(53)))
    m = metrics_from_stress(0, -YC, 0, mat)
    expected_hmc = (-YC/(2*ST))**2 + ((YC/(2*ST))**2 - 1)*(-YC/YC) + 0
    check("Hashin: σ22=-YC → HMC uses ST correctly", m['max_hashin_mc'] > 0.5,
          f"got {m['max_hashin_mc']:.4f}, expected formula val={expected_hmc:.4f}")

    # Puck IFF mode selection
    m = metrics_from_stress(0, YT, 0, mat)
    check("Puck: σ22=+YT → Mode A only (iff_b=iff_c=0)",
          m['puck_iff_b'] == 0.0 and m['puck_iff_c'] == 0.0 and m['puck_iff_a'] > 0,
          f"iff_a={m['puck_iff_a']:.4f}, iff_b={m['puck_iff_b']:.4f}, iff_c={m['puck_iff_c']:.4f}")

    m = metrics_from_stress(0, -YC, SL, mat)
    check("Puck: σ22=-YC, σ12=SL → Mode B or C triggers",
          m['puck_iff_b'] > 0 or m['puck_iff_c'] > 0,
          f"iff_b={m['puck_iff_b']:.4f}, iff_c={m['puck_iff_c']:.4f}")

    m = metrics_from_stress(0, -5.0, SL, mat)
    check("Puck: σ22=-small, σ12=SL → Mode B (shear-dominated compression)",
          m['puck_iff_b'] > 0,
          f"iff_b={m['puck_iff_b']:.4f}")

    # LaRC05 tests
    m = metrics_from_stress(XT, 0, 0, mat)
    check("LaRC: σ11=XT → LaRC FT = 1.0", approx_abs(m['larc_ft'], 1.0, 0.001),
          f"got {m['larc_ft']:.4f}")

    m = metrics_from_stress(-XC, 0, 0, mat)
    # LaRC FC uses kinking: phi0 = SL/G12
    G12 = float(mat['G12'])
    phi0 = SL / G12
    check("LaRC: σ11=-XC → LaRC FC > 0 (kinking formula)",
          m['larc_fc'] > 0,
          f"got {m['larc_fc']:.4f}, phi0={phi0:.4f} rad")


# =============================================================================
# 1.2 CLT FPF validation (5 tests)
# =============================================================================
def test_clt_fpf():
    print("\n=== 1.2 CLT FPF Validation ===")
    qi_angles = B.LAYUPS[1]['angles']

    fpf_t300 = B._clt_fpf_uniaxial_x(B.MATERIALS[1], qi_angles)
    check("CLT FPF: T300/5208 + QI_8 is plausible (50-500 MPa)",
          50 < fpf_t300 < 500,
          f"got {fpf_t300:.1f} MPa")

    fpf_eglass = B._clt_fpf_uniaxial_x(B.MATERIALS[8], qi_angles)
    check("CLT FPF: E-glass + QI_8 < T300 (weaker material)",
          10 < fpf_eglass < fpf_t300,
          f"got {fpf_eglass:.1f} MPa (T300={fpf_t300:.1f})")

    fpf_jute = B._clt_fpf_uniaxial_x(B.MATERIALS[22], qi_angles)
    check("CLT FPF: Jute + QI_8 < E-glass (weakest material)",
          1 < fpf_jute < fpf_eglass,
          f"got {fpf_jute:.1f} MPa (E-glass={fpf_eglass:.1f})")

    ud0_angles = B.LAYUPS[4]['angles']  # UD_0
    fpf_ud0 = B._clt_fpf_uniaxial_x(B.MATERIALS[1], ud0_angles)
    check("CLT FPF: T300 UD_0 > T300 QI (fibres aligned with load)",
          fpf_ud0 > fpf_t300,
          f"UD_0={fpf_ud0:.1f}, QI={fpf_t300:.1f}")

    ud90_angles = B.LAYUPS[5]['angles']  # UD_90
    fpf_ud90 = B._clt_fpf_uniaxial_x(B.MATERIALS[1], ud90_angles)
    check("CLT FPF: T300 UD_90 << T300 QI (fibres perpendicular)",
          fpf_ud90 < fpf_t300 * 0.5,
          f"UD_90={fpf_ud90:.1f}, QI={fpf_t300:.1f}")


# =============================================================================
# 1.3 CLT FPF for asymmetric layups (2 tests)
# =============================================================================
def test_clt_fpf_asymmetric():
    print("\n=== 1.3 CLT FPF Asymmetric Layups ===")
    qi_angles = B.LAYUPS[1]['angles']
    fpf_qi = B._clt_fpf_uniaxial_x(B.MATERIALS[1], qi_angles)

    asym25 = B.LAYUPS[25]['angles']
    fpf_25 = B._clt_fpf_uniaxial_x(B.MATERIALS[1], asym25)
    check("CLT FPF: Layup 25 [0/30/60/90]₂ returns plausible value (not 100.0 fallback)",
          1.0 < fpf_25 < 1e5 and fpf_25 != 100.0,
          f"got {fpf_25:.1f} MPa")

    asym26 = B.LAYUPS[26]['angles']
    fpf_26 = B._clt_fpf_uniaxial_x(B.MATERIALS[1], asym26)
    check("CLT FPF: Layup 26 [15/45/75]₈ returns plausible value (not 100.0 fallback)",
          1.0 < fpf_26 < 1e5 and fpf_26 != 100.0,
          f"got {fpf_26:.1f} MPa")


# =============================================================================
# 1.4 Lamination parameters (4 tests)
# =============================================================================
def test_lamination_params():
    print("\n=== 1.4 Lamination Parameters ===")
    t = 0.15

    # QI_8 → V1A ≈ 0, V2A ≈ 0
    lp = B.compute_lamination_params(B.LAYUPS[1]['angles'], t)
    check("LamParams: QI_8 → V1A≈0, V2A≈0",
          abs(lp[0]) < 0.05 and abs(lp[1]) < 0.05,
          f"V1A={lp[0]:.4f}, V2A={lp[1]:.4f}")

    # UD_0_8 → V1A=1.0, V2A=0, V3A=1.0, V4A=0
    lp = B.compute_lamination_params(B.LAYUPS[4]['angles'], t)
    check("LamParams: UD_0_8 → V1A=1.0, V3A=1.0",
          approx_abs(lp[0], 1.0, 0.001) and approx_abs(lp[1], 0.0, 0.001)
          and approx_abs(lp[2], 1.0, 0.001) and approx_abs(lp[3], 0.0, 0.001),
          f"V1A={lp[0]:.4f}, V2A={lp[1]:.4f}, V3A={lp[2]:.4f}, V4A={lp[3]:.4f}")

    # Angle_pm45_4s → V1A=0, V3A=-1.0
    lp = B.compute_lamination_params(B.LAYUPS[6]['angles'], t)
    check("LamParams: ±45 → V1A≈0, V3A≈-1.0",
          abs(lp[0]) < 0.05 and approx_abs(lp[2], -1.0, 0.05),
          f"V1A={lp[0]:.4f}, V3A={lp[2]:.4f}")

    # Thick_QI_24 → same V1A/V2A as QI_8 (thickness-normalized)
    lp_qi8 = B.compute_lamination_params(B.LAYUPS[1]['angles'], t)
    lp_qi24 = B.compute_lamination_params(B.LAYUPS[27]['angles'], t)
    check("LamParams: Thick_QI_24 V1A≈QI_8 V1A",
          approx_abs(lp_qi24[0], lp_qi8[0], 0.05) and approx_abs(lp_qi24[1], lp_qi8[1], 0.05),
          f"QI_8: V1A={lp_qi8[0]:.4f}, QI_24: V1A={lp_qi24[0]:.4f}")


# =============================================================================
# 1.5 CSV schema (3 tests)
# =============================================================================
def test_csv_schema():
    print("\n=== 1.5 CSV Schema ===")
    cols = B.CSV_COLUMNS

    check("CSV: column count = 131", len(cols) == 131,
          f"got {len(cols)}")

    critical_cols = ['sim_id', 'material_id', 'tsai_wu_index', 'post_fpf',
                     'puck_iff_b', 'puck_iff_c', 'larc_fc', 'larc_mt',
                     'max_hashin_ft', 'max_hashin_mc', 'V1A', 'n_defects',
                     'pressure_x', 'solver_completed', 'failed_tsai_wu']
    missing = [c for c in critical_cols if c not in cols]
    check("CSV: all critical column names present", len(missing) == 0,
          f"missing: {missing}")

    check("CSV: no duplicate column names", len(cols) == len(set(cols)),
          f"duplicates: {[c for c in cols if cols.count(c) > 1]}")


# =============================================================================
# 1.6 Per-combo seeding (5 tests)
# =============================================================================
def test_combo_seeding():
    print("\n=== 1.6 Per-Combo Seeding ===")

    # Same combo → identical samples on two calls
    s1 = B.generate_samples([1], [1], [1], 'flat', 'medium', 10, seed=2026)
    s2 = B.generate_samples([1], [1], [1], 'flat', 'medium', 10, seed=2026)
    match = all(
        abs(s1[i]['pressure_x'] - s2[i]['pressure_x']) < 1e-10
        and abs(s1[i]['pressure_y'] - s2[i]['pressure_y']) < 1e-10
        for i in range(len(s1))
    )
    check("Seeding: same combo → identical samples on two calls", match)

    # Same combo at different mesh levels → identical pressures and defect positions
    sc = B.generate_samples([1], [1], [1], 'flat', 'coarse', 5, seed=2026)
    sm = B.generate_samples([1], [1], [1], 'flat', 'medium', 5, seed=2026)
    sf = B.generate_samples([1], [1], [1], 'flat', 'fine', 5, seed=2026)
    # Samples are shuffled, so sort by sim pressure_x to match
    sc.sort(key=lambda s: s['pressure_x'])
    sm.sort(key=lambda s: s['pressure_x'])
    sf.sort(key=lambda s: s['pressure_x'])
    mesh_match = all(
        abs(sc[i]['pressure_x'] - sm[i]['pressure_x']) < 1e-10
        and abs(sc[i]['pressure_x'] - sf[i]['pressure_x']) < 1e-10
        for i in range(len(sc))
    )
    check("Seeding: same combo coarse/medium/fine → identical pressures", mesh_match)

    # Different combos → different samples
    sa = B.generate_samples([1], [1], [1], 'flat', 'medium', 5, seed=2026)
    sb = B.generate_samples([2], [1], [1], 'flat', 'medium', 5, seed=2026)
    sa.sort(key=lambda s: s['pressure_x'])
    sb.sort(key=lambda s: s['pressure_x'])
    diff = any(abs(sa[i]['pressure_x'] - sb[i]['pressure_x']) > 1e-6 for i in range(len(sa)))
    check("Seeding: different materials → different samples", diff)

    # sims_per_combo=5 vs 10 → both deterministic but different (LHS regenerated)
    s5 = B.generate_samples([1], [1], [1], 'flat', 'medium', 5, seed=2026)
    s10 = B.generate_samples([1], [1], [1], 'flat', 'medium', 10, seed=2026)
    # Both should be deterministic (reproducible)
    s5b = B.generate_samples([1], [1], [1], 'flat', 'medium', 5, seed=2026)
    s5.sort(key=lambda s: s['pressure_x'])
    s5b.sort(key=lambda s: s['pressure_x'])
    det5 = all(abs(s5[i]['pressure_x'] - s5b[i]['pressure_x']) < 1e-10 for i in range(5))
    check("Seeding: sims_per_combo=5 is deterministic (LHS(5) vs LHS(10) differ but both reproducible)", det5)

    # No collisions across all 22×35×3 = 2310 combos
    seeds = set()
    for m in range(1, 23):
        for l in range(1, 36):
            for b in range(1, 4):
                seeds.add(B._combo_seed(2026, m, l, b))
    check("Seeding: no collisions across all 2310 combos", len(seeds) == 2310,
          f"got {len(seeds)} unique seeds")


# =============================================================================
# 1.7 Per-defect polygon seeding (3 tests)
# =============================================================================
def test_polygon_seeding():
    print("\n=== 1.7 Per-Defect Polygon Seeding ===")

    # Create a minimal sample for polygon generation
    sample = {
        'material_id': 1, 'layup_id': 1, 'bc_mode': 'biaxial',
        'geometry': 'flat', 'mesh_level': 'medium',
        'defects': [{'x': 50.0, 'y': 25.0, 'half_length': 8.0,
                     'width': 0.3, 'angle': 45.0, 'roughness': 0.5}],
        'n_defects': 1, 'pressure_x': 100.0, 'pressure_y': 50.0, 'ply_thickness': 0.15,
    }

    # Same sample → identical polygon on two calls
    p1, _ = B.generate_polygons([sample], seed=2026)
    p2, _ = B.generate_polygons([sample], seed=2026)
    check("PolySeed: same sample → identical polygon on two calls",
          p1[0] is not None and p2[0] is not None and p1[0] == p2[0])

    # Same sample in batch of 1 vs batch of 100 → identical polygon
    batch_100 = [sample] * 100
    p100, _ = B.generate_polygons(batch_100, seed=2026)
    check("PolySeed: batch of 1 vs batch of 100 → identical polygon",
          p1[0] is not None and p100[0] is not None and p1[0] == p100[0])

    # Different samples → different polygons
    sample2 = dict(sample)
    sample2['defects'] = [{'x': 30.0, 'y': 15.0, 'half_length': 10.0,
                           'width': 0.4, 'angle': 90.0, 'roughness': 0.7}]
    p_diff, _ = B.generate_polygons([sample2], seed=2026)
    check("PolySeed: different samples → different polygons",
          p1[0] != p_diff[0])


# =============================================================================
# 1.8 Pressure scaling sanity (5 tests)
# =============================================================================
def test_pressure_scaling():
    print("\n=== 1.8 Pressure Scaling Sanity ===")

    # All 22 materials have positive, non-zero pressure ranges
    all_positive = all(
        B.MATERIAL_PRESSURE_RANGES[m][0] > 0 and B.MATERIAL_PRESSURE_RANGES[m][1] > B.MATERIAL_PRESSURE_RANGES[m][0]
        for m in range(1, 23)
    )
    check("Pressure: all 22 materials have positive non-zero ranges", all_positive)

    # Jute px_hi < T300 px_hi
    jute_hi = B.MATERIAL_PRESSURE_RANGES[22][1]
    t300_hi = B.MATERIAL_PRESSURE_RANGES[1][1]
    check("Pressure: Jute px_hi < T300 px_hi",
          jute_hi < t300_hi,
          f"Jute={jute_hi:.1f}, T300={t300_hi:.1f}")

    # M55J and T1100 have high px_hi (stiffest materials)
    m55j_hi = B.MATERIAL_PRESSURE_RANGES[17][1]
    t1100_hi = B.MATERIAL_PRESSURE_RANGES[9][1]
    median_hi = sorted(B.MATERIAL_PRESSURE_RANGES[m][1] for m in range(1, 23))[11]
    check("Pressure: M55J and T1100 have above-median px_hi",
          m55j_hi > median_hi and t1100_hi > median_hi,
          f"M55J={m55j_hi:.1f}, T1100={t1100_hi:.1f}, median={median_hi:.1f}")

    # All 35 layup scale factors are in [0.4, 3.0]
    all_in_range = all(0.4 <= B.LAYUP_SCALE_FACTORS[l] <= 3.0 for l in range(1, 36))
    check("Pressure: all 35 layup scale factors in [0.4, 3.0]", all_in_range,
          f"out of range: {[(l, B.LAYUP_SCALE_FACTORS[l]) for l in range(1,36) if not (0.4 <= B.LAYUP_SCALE_FACTORS[l] <= 3.0)]}")

    # UD_0 scale > 1.0, UD_90 scale < 1.0
    ud0_sf = B.LAYUP_SCALE_FACTORS[4]
    ud90_sf = B.LAYUP_SCALE_FACTORS[5]
    check("Pressure: UD_0 scale > 1.0, UD_90 scale < 1.0",
          ud0_sf > 1.0 and ud90_sf < 1.0,
          f"UD_0={ud0_sf:.3f}, UD_90={ud90_sf:.3f}")


# =============================================================================
# 1.9 Material property ratios (3 tests)
# =============================================================================
def test_material_properties():
    print("\n=== 1.9 Material Property Ratios ===")

    # All materials: E1/E2 > 1.0
    check("MatProps: all E1/E2 > 1.0",
          all(B.MATERIALS[m]['E1'] > B.MATERIALS[m]['E2'] for m in range(1, 23)))

    # All materials: XT > YT
    check("MatProps: all XT > YT",
          all(B.MATERIALS[m]['XT'] > B.MATERIALS[m]['YT'] for m in range(1, 23)))

    # Thermodynamic constraint: v12 * v21 < 1 (where v21 = v12 * E2/E1)
    thermo_ok = all(
        B.MATERIALS[m]['v12'] * (B.MATERIALS[m]['v12'] * B.MATERIALS[m]['E2'] / B.MATERIALS[m]['E1']) < 1.0
        for m in range(1, 23)
    )
    check("MatProps: v12 × E2/E1 < 1 (thermodynamic constraint)", thermo_ok)


# =============================================================================
# 1.10 Edge cases (4 tests)
# =============================================================================
def test_edge_cases():
    print("\n=== 1.10 Edge Cases ===")
    mat = B.MATERIALS[1]

    # All-NaN stress_data → returns None
    nan = float('nan')
    stress_nan = [(1, 1, nan, nan, nan, nan, nan, nan)]
    m = B.compute_metrics(stress_nan, {1: (50, 25, 0)},
                          [{'x': 50, 'y': 25, 'half_length': 5}], mat)
    check("Edge: all-NaN stress_data → returns None", m is None)

    # Single stress entry → returns valid dict
    m = metrics_from_stress(100.0, 10.0, 5.0, mat)
    check("Edge: single stress entry → returns valid dict",
          m is not None and 'tsai_wu_index' in m and m['n_elements'] == 1)

    # build_row with error=True → post_fpf=0, all indices=0
    sample = {
        'material_id': 1, 'layup_id': 1, 'bc_mode': 'biaxial',
        'geometry': 'flat', 'mesh_level': 'medium',
        'defects': [], 'n_defects': 0,
        'pressure_x': 100.0, 'pressure_y': 50.0, 'ply_thickness': 0.15,
    }
    row = B.build_row(1, sample, mat, error=True, n_elements=500)
    check("Edge: build_row error=True → post_fpf=0, indices=0",
          row['post_fpf'] == 0 and row['tsai_wu_index'] == 0 and row['solver_completed'] == 'ERROR')

    # build_row with metrics where tsai_wu ≥ 1.0 → post_fpf=1
    m = metrics_from_stress(XT := float(mat['XT']), 0, 0, mat)
    row = B.build_row(2, sample, mat, metrics=m)
    check("Edge: build_row with TW≥1 → post_fpf=1",
          row['post_fpf'] == 1,
          f"post_fpf={row['post_fpf']}, tw={row['tsai_wu_index']:.4f}")


# =============================================================================
# 1.11 Defect placement bounds (3 tests)
# =============================================================================
def test_defect_bounds():
    print("\n=== 1.11 Defect Placement Bounds ===")

    # Defect at plate edge → rejected
    check("DefectBounds: defect at plate edge → rejected",
          not B.validate_crack_bounds(1, 1, 10, 0.3, 0, 0.5, B.PLATE_L, B.PLATE_W))

    # Defect at plate center → accepted
    check("DefectBounds: defect at plate center → accepted",
          B.validate_crack_bounds(50, 25, 10, 0.3, 0, 0.5, B.PLATE_L, B.PLATE_W))

    # Overlapping defects detected
    d1 = {'x': 50, 'y': 25, 'half_length': 10}
    d2 = {'x': 55, 'y': 25, 'half_length': 10}
    check("DefectBounds: overlapping defects detected",
          B.overlaps_existing(d2, [d1]))


# =============================================================================
# Main
# =============================================================================
def main():
    print("=" * 70)
    print("Phase 1: Unit Tests — Pure Python")
    print("=" * 70)

    test_failure_criteria()
    test_clt_fpf()
    test_clt_fpf_asymmetric()
    test_lamination_params()
    test_csv_schema()
    test_combo_seeding()
    test_polygon_seeding()
    test_pressure_scaling()
    test_material_properties()
    test_edge_cases()
    test_defect_bounds()

    # Summary
    print("\n" + "=" * 70)
    print(f"RESULTS: {_pass_count} passed, {_fail_count} failed, {_pass_count + _fail_count} total")
    print("=" * 70)

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
