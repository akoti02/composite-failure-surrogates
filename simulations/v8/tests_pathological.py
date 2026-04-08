#!/usr/bin/env python3
"""Phase 3: Pathological Combo Tests — ~110 sims across 5 tiers.

Tests dangerous (material, layup, BC) triples identified by deep analysis.
Does NOT hard-fail — produces a structured report documenting which combos
work, which are problematic, and recommended actions.

Run: python3 tests_pathological.py
"""

import sys
import os
import time
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import batch_compositeNet as B

os.makedirs(B.WORK_DIR, exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# Test infrastructure
# ─────────────────────────────────────────────────────────────────────────────
_report = []

def run_combo(mat_id, layup_id, bc_id, n_sims=5, mesh='medium', seed_base=2026):
    """Run n_sims for a specific combo. Returns list of row dicts."""
    results = []
    for i in range(n_sims):
        seed = seed_base + i * 7
        samples = B.generate_samples([mat_id], [layup_id], [bc_id],
                                      'flat', mesh, 1, seed=seed)
        if not samples:
            results.append(None)
            continue
        sample = samples[0]
        polys, _ = B.generate_polygons([sample], seed=seed)
        polygons = polys[0]

        t0 = time.time()
        row = B.run_single_sim((0, sample, polygons))
        elapsed = time.time() - t0
        row['_elapsed'] = elapsed
        results.append(row)
    return results


def analyze_combo(label, why, mat_id, layup_id, bc_id, results):
    """Analyze results for a combo and add to report."""
    total = len(results)
    successes = [r for r in results if r and r['solver_completed'] == 'YES']
    errors = [r for r in results if r is None or r['solver_completed'] != 'YES']
    error_rate = len(errors) / total if total > 0 else 1.0

    times = [r['_elapsed'] for r in results if r and '_elapsed' in r]
    max_time = max(times) if times else 0
    mean_time = sum(times) / len(times) if times else 0

    tw_values = [r['tsai_wu_index'] for r in successes]
    mean_tw = sum(tw_values) / len(tw_values) if tw_values else 0
    max_s11_vals = [r['max_s11'] for r in successes]

    entry = {
        'label': label,
        'why': why,
        'mat_id': mat_id,
        'mat_name': B.MATERIALS[mat_id]['name'],
        'layup_id': layup_id,
        'layup_name': B.LAYUPS[layup_id]['name'],
        'bc_id': bc_id,
        'bc_name': B.BC_MODES[bc_id],
        'total': total,
        'success': len(successes),
        'errors': len(errors),
        'error_rate': error_rate,
        'mean_time': mean_time,
        'max_time': max_time,
        'mean_tw': mean_tw,
        'max_s11_values': max_s11_vals,
        'status': 'OK' if error_rate == 0 else ('WARN' if error_rate < 0.5 else 'CRITICAL'),
    }
    _report.append(entry)

    status_str = f"{'OK' if error_rate == 0 else 'WARN' if error_rate < 0.5 else 'CRITICAL'}"
    print(f"  [{status_str}] {label}: {len(successes)}/{total} OK, "
          f"err={error_rate:.0%}, mean_t={mean_time:.1f}s, mean_TW={mean_tw:.3f}")
    if max_time > 60:
        print(f"    ⚠ SLOW: max solve time = {max_time:.1f}s")
    return entry


# =============================================================================
# TIER 1: Solver divergence risk (5 triples × 5 sims = 25 sims)
# =============================================================================
def test_tier1():
    print("\n=== TIER 1: Solver Divergence Risk (25 sims) ===")
    combos = [
        ("T1-M55J+UD90+biax",      "E1/E2=48.6 all-transverse load", 17, 5, 1),
        ("T1-T1100+UD90+biax",     "E1/E2=40.5 all-transverse load", 9, 5, 1),
        ("T1-HMCFRP+UD90+biax",    "E1/E2=35.4 weakest YT=35", 21, 5, 1),
        ("T1-HMCFRP+Thick24+tc",   "Very stiff + thick + compression", 21, 27, 2),
        ("T1-T1100+Thick24+biax",  "Extreme stiffness thick laminate", 9, 27, 1),
    ]
    for label, why, mid, lid, bid in combos:
        results = run_combo(mid, lid, bid)
        analyze_combo(label, why, mid, lid, bid, results)


# =============================================================================
# TIER 2: Numerical precision risk (5 triples × 5 sims = 25 sims)
# =============================================================================
def test_tier2():
    print("\n=== TIER 2: Numerical Precision Risk (25 sims) ===")
    combos = [
        ("T2-Jute+Thin4+shear",    "Weakest mat + thinnest + shear", 22, 29, 3),
        ("T2-Flax+Thin4+shear",    "Very weak + thin + shear", 15, 29, 3),
        ("T2-Kevlar+ThinCP+shear", "Low SL=49 + thin + shear", 12, 30, 3),
        ("T2-Jute+UD90+biax",      "Lowest everything transverse", 22, 5, 1),
        ("T2-HMCFRP+UD90+tc",      "Weakest YT under compression", 21, 5, 2),
    ]
    for label, why, mid, lid, bid in combos:
        results = run_combo(mid, lid, bid)
        analyze_combo(label, why, mid, lid, bid, results)


# =============================================================================
# TIER 3: Asymmetric layup B-matrix path (4 triples × 5 sims = 20 sims)
# =============================================================================
def test_tier3():
    print("\n=== TIER 3: Asymmetric Layup B-Matrix Path (20 sims) ===")
    combos = [
        ("T3-Kevlar+Asym25+tc",  "Asymmetric + weak XC + compression", 12, 25, 2),
        ("T3-Flax+Asym26+tc",    "Asymmetric + low stiffness + comp", 15, 26, 2),
        ("T3-T300+Asym25+biax",  "Asymmetric baseline material", 1, 25, 1),
        ("T3-T300+Asym26+biax",  "Asymmetric baseline material", 1, 26, 1),
    ]
    for label, why, mid, lid, bid in combos:
        results = run_combo(mid, lid, bid)
        entry = analyze_combo(label, why, mid, lid, bid, results)
        # Check: do asymmetric layups produce higher failure indices?
        if entry['mean_tw'] > 0:
            print(f"    Asymmetric mean_TW={entry['mean_tw']:.3f}")


# =============================================================================
# TIER 4: Defect stress tests (5 scenarios × 5 sims = 25 sims)
# =============================================================================
def test_tier4():
    print("\n=== TIER 4: Defect Stress Tests (25 sims) ===")
    # These use different seeds to get varying defect configurations
    scenarios = [
        ("T4-MaxDefects",     "Max defects (5) large half_lengths", 2026),
        ("T4-SingleTiny",     "Single tiny defect", 3001),
        ("T4-NearBoundary",   "Defects near plate boundary", 4001),
        ("T4-HighRoughness",  "Very rough cracks (roughness≈0.9)", 5001),
        ("T4-CutoutDefects",  "Cutout + defects near hole", 6001),
    ]
    for label, why, seed in scenarios:
        if "Cutout" in label:
            # Use cutout geometry for this scenario
            results = []
            for i in range(5):
                s = seed + i * 7
                samples = B.generate_samples([1], [1], [1], 'cutout', 'medium', 1, seed=s)
                if not samples:
                    results.append(None)
                    continue
                sample = samples[0]
                polys, _ = B.generate_polygons([sample], seed=s)
                t0 = time.time()
                row = B.run_single_sim((0, sample, polys[0]))
                row['_elapsed'] = time.time() - t0
                results.append(row)
        else:
            results = run_combo(1, 1, 1, n_sims=5, seed_base=seed)
        analyze_combo(label, why, 1, 1, 1, results)


# =============================================================================
# TIER 5: Solve time monitoring (5 triples × 3 sims = 15 sims)
# =============================================================================
def test_tier5():
    print("\n=== TIER 5: Solve Time Monitoring (15 sims) ===")
    combos = [
        ("T5-T1100+Thick24+biax+fine",  "Large stiff system", 9, 27, 1),
        ("T5-M55J+ThickCP+tc+fine",     "Very stiff thick compression", 17, 28, 2),
        ("T5-HMCFRP+QI16+biax+fine",    "Stiff 16-ply fine mesh", 21, 2, 1),
        ("T5-Eglass+Wing+biax+fine",    "20-ply industry layup fine", 8, 16, 1),
        ("T5-S2glass+Thick24+shear+fine","Thick + fine + shear", 11, 27, 3),
    ]
    for label, why, mid, lid, bid in combos:
        results = run_combo(mid, lid, bid, n_sims=3, mesh='fine')
        entry = analyze_combo(label, why, mid, lid, bid, results)
        if entry['max_time'] > 60:
            print(f"    ⚠ SLOW: {entry['max_time']:.0f}s > 60s threshold")
        if entry['max_time'] > 300:
            print(f"    ✗ TIMEOUT RISK: {entry['max_time']:.0f}s approaches 300s limit")


# =============================================================================
# Report generation
# =============================================================================
def generate_report():
    print("\n" + "=" * 70)
    print("PATHOLOGICAL COMBO REPORT")
    print("=" * 70)

    ok = [e for e in _report if e['status'] == 'OK']
    warn = [e for e in _report if e['status'] == 'WARN']
    crit = [e for e in _report if e['status'] == 'CRITICAL']

    print(f"\nSummary: {len(ok)} OK, {len(warn)} WARN, {len(crit)} CRITICAL")

    if crit:
        print("\n--- CRITICAL (>50% failure) ---")
        for e in crit:
            print(f"  {e['label']}: {e['mat_name']} + {e['layup_name']} + {e['bc_name']}")
            print(f"    Error rate: {e['error_rate']:.0%} ({e['errors']}/{e['total']})")
            print(f"    Why: {e['why']}")
            print(f"    Action: EXCLUDE from campaign or adjust pressure range")

    if warn:
        print("\n--- WARN (1-50% failure) ---")
        for e in warn:
            print(f"  {e['label']}: {e['mat_name']} + {e['layup_name']} + {e['bc_name']}")
            print(f"    Error rate: {e['error_rate']:.0%} ({e['errors']}/{e['total']})")
            print(f"    Why: {e['why']}")

    slow = [e for e in _report if e['max_time'] > 60]
    if slow:
        print("\n--- SLOW SIMS (>60s) ---")
        for e in slow:
            print(f"  {e['label']}: max={e['max_time']:.0f}s, mean={e['mean_time']:.0f}s")

    # Check normal materials have 0% error (exclude T5 fine-mesh stress tests —
    # those are intentionally extreme combos regardless of material)
    normal_mats = set(range(1, 23)) - {9, 12, 15, 17, 21, 22}
    normal_errors = [e for e in _report
                     if e['mat_id'] in normal_mats and e['errors'] > 0
                     and not e['label'].startswith('T5-')]
    if normal_errors:
        print("\n--- UNEXPECTED: Normal materials with errors ---")
        for e in normal_errors:
            print(f"  {e['label']}: {e['mat_name']} had {e['errors']} errors!")

    # Save JSON report
    report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "pathological_report.json")
    with open(report_path, 'w') as f:
        json.dump(_report, f, indent=2, default=str)
    print(f"\nFull report saved to: {report_path}")


# =============================================================================
# Main
# =============================================================================
def main():
    print("=" * 70)
    print("Phase 3: Pathological Combo Tests")
    print("=" * 70)

    t0 = time.time()
    test_tier1()
    test_tier2()
    test_tier3()
    test_tier4()
    test_tier5()
    total = time.time() - t0

    generate_report()

    print(f"\nTotal time: {total:.0f}s ({total/60:.1f} min)")

    # Phase 3 does NOT hard-fail — it produces a report
    # But flag if normal materials have unexpected errors
    normal_mats = set(range(1, 23)) - {9, 12, 15, 17, 21, 22}
    normal_errors = [e for e in _report
                     if e['mat_id'] in normal_mats and e['errors'] > 0
                     and not e['label'].startswith('T5-')]
    if normal_errors:
        print("\n✗ FAIL: Normal materials have unexpected solver errors!")
        sys.exit(1)

    # Flag if any sim took >300s (timeout)
    timeout_risk = [e for e in _report if e['max_time'] > 300]
    if timeout_risk:
        print("\n✗ FAIL: Sims approaching timeout limit!")
        sys.exit(1)

    print("\nPhase 3 complete — review report for decision points.")
    sys.exit(0)


if __name__ == "__main__":
    main()
