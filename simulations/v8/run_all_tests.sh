#!/bin/bash
# CompositeBench pre-campaign testing pipeline — Phases 1-5
# Stops at first failing phase (except Phase 3 which produces a report).
#
# Run: bash run_all_tests.sh
# Budget: ~6-8 hours on EPYC 9654 (~£9-12)

set -e
cd "$(dirname "$0")"

WORKERS=90
SEED=2026
SIMS_DIR=~/sims

echo "=================================================================="
echo "CompositeBench Pre-Campaign Testing Pipeline"
echo "Started: $(date)"
echo "=================================================================="

# ── Phase 1: Unit Tests (~1 min) ──────────────────────────────────────
echo ""
echo "=== PHASE 1: Unit Tests ==="
python3 tests_unit.py || { echo "PHASE 1 FAILED — stopping."; exit 1; }

# ── Phase 2: Smoke Tests (~15 min) ───────────────────────────────────
echo ""
echo "=== PHASE 2: Smoke Tests ==="
python3 tests_smoke.py || { echo "PHASE 2 FAILED — stopping."; exit 1; }

# ── Phase 3: Pathological Combos (~30 min) ────────────────────────────
echo ""
echo "=== PHASE 3: Pathological Combos ==="
# Phase 3 produces a report — does not hard-fail on critical material issues
# but DOES fail if normal materials have errors or sims hit timeout
python3 tests_pathological.py
P3_EXIT=$?
if [ $P3_EXIT -ne 0 ]; then
    echo "PHASE 3: Unexpected failures detected — review pathological_report.json"
    echo "Continuing to Phase 4 (Phase 3 is advisory)..."
fi

# ── Phase 4: Calibration (~45 min) ───────────────────────────────────
echo ""
echo "=== PHASE 4: Calibration ==="
python3 tests_calibration.py || { echo "PHASE 4 FAILED — stopping."; exit 1; }

# ── Phase 5: All-Combo Sweep (~2-2.5 hrs) ────────────────────────────
echo ""
echo "=== PHASE 5: All-Combo Sweep ==="

echo "--- 5a: Flat sweep (22×35×3×5 = 11,550 sims) ---"
python3 batch_compositeNet.py \
    --materials 1-22 --layups 1-35 --bcs 1-3 \
    --geometry flat --mesh medium \
    --sims-per-combo 5 --workers $WORKERS --seed $SEED

FLAT_CSV=$(ls -t $SIMS_DIR/results_vm1_flat_medium*.csv 2>/dev/null | head -1)
if [ -z "$FLAT_CSV" ]; then
    echo "ERROR: Flat sweep CSV not found in $SIMS_DIR"
    exit 1
fi
python3 validate_results.py "$FLAT_CSV" --expected-rows 11550 || { echo "PHASE 5a FAILED"; exit 1; }

echo ""
echo "--- 5b: Cutout sweep (22×15×2×3 = 1,980 sims) ---"
python3 batch_compositeNet.py \
    --materials 1-22 --layups 1-15 --bcs 1-2 \
    --geometry cutout --mesh medium \
    --sims-per-combo 3 --workers $WORKERS --seed $SEED

CUTOUT_CSV=$(ls -t $SIMS_DIR/results_vm1_cutout_medium*.csv 2>/dev/null | head -1)
if [ -n "$CUTOUT_CSV" ]; then
    python3 validate_results.py "$CUTOUT_CSV" --expected-rows 1980 || { echo "PHASE 5b FAILED"; exit 1; }
fi

echo ""
echo "--- 5c: Curved sweep (10×10×2×3 = 600 sims) ---"
python3 batch_compositeNet.py \
    --materials 1-10 --layups 1-10 --bcs 1-2 \
    --geometry curved --mesh medium \
    --sims-per-combo 3 --workers $WORKERS --seed $SEED

CURVED_CSV=$(ls -t $SIMS_DIR/results_vm1_curved_medium*.csv 2>/dev/null | head -1)
if [ -n "$CURVED_CSV" ]; then
    python3 validate_results.py "$CURVED_CSV" --expected-rows 600 || { echo "PHASE 5c FAILED"; exit 1; }
fi

echo ""
echo "=================================================================="
echo "PHASES 1-5 COMPLETE"
echo "Finished: $(date)"
echo "=================================================================="
echo ""
echo "Next steps:"
echo "  Phase 6 (mesh convergence): run 3 batches at coarse/medium/fine, then:"
echo "    python3 tests_mesh_convergence.py <coarse.csv> <medium.csv> <fine.csv>"
echo ""
echo "  Phase 7 (scale test): run full batch, then validate:"
echo "    python3 batch_compositeNet.py --materials 1-22 --layups 1-35 --bcs 1-3 \\"
echo "        --geometry flat --mesh medium --sims-per-combo 50 --workers $WORKERS --seed $SEED"
echo "    python3 validate_results.py <output.csv> --expected-rows 115500"
echo ""
echo "  Phase 8 (V10 cross-validation):"
echo "    python3 batch_compositeNet.py --materials 1 --layups 1 --bcs 1 \\"
echo "        --geometry flat --mesh medium --sims-per-combo 200 --seed $SEED"
echo "    python3 tests_v10_crossval.py <v11.csv> results_merged_101k_sample.csv"
