> [!info] Document Metadata
> **Script:** `run_batch_simulations_v6.py`
> **Output:** `simulation_results_v6.csv` (2,574 rows — UNUSABLE)
> **Last Updated:** Thursday, 26 March 2026
> **Related:** [[V5 — Jagged Crack Geometry & 5000 Samples]], [[V7 — Progressive Damage Fix & Script Restructure]]

---

## Overview

V6 introduced **Hashin progressive damage** with energy-based damage evolution to the composite plate model. The intent was to capture post-initiation stiffness degradation (SDEG) and produce realistic failure predictions rather than initiation-only criteria.

## What Went Wrong

The `softening=LINEAR` parameter was missing from the `DamageEvolution()` API call. Abaqus silently rejected the call (caught by a broad `except` block), so all 2,574 simulations ran with **initiation-only Hashin** — no stiffness degradation occurred.

**Symptoms:**
- `max_sdeg = 0` across all samples
- Only 0.3% failure rate (should have been ~15-30%)
- Results looked superficially plausible but damage model was never active

## Data Status

> [!warning] Do Not Use
> The V6 CSV (`simulation_results_v6.csv`, 1.6 MB) is kept for reference only. The damage evolution columns are meaningless. **Do not train ML models on this data.**

## Resolution

See [[V7 — Progressive Damage Fix & Script Restructure]] for the corrected implementation, including the root cause analysis, the 3-script restructure, and the fix.
