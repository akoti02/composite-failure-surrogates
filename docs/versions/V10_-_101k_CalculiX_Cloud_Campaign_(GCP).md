> [!success] 101K Campaign Complete
> **101,000 simulations completed** in ~4 hours 18 minutes across 4 Google Cloud VMs. 100,999 converged (1 solver error). Merged CSV: `results_merged_101k.csv` (69 MB, 103 columns). Independent dataset from V9 (seed=2026 vs seed=101).

---

# Overview

The V10 campaign is a 101,000-simulation production run using CalculiX, executed on Google Cloud Platform infrastructure. It represents a 113x increase over the V7 Abaqus dataset (891 sims) and a 7x increase over V9 (14,457 sims). The dataset uses the same 103-column schema as V9 but is generated from an independent random seed (2026), making it a fully independent dataset suitable for ML training at scale.

---

# Script: `batch_100k.py`

Evolution of V9's `batch_20k.py` with multi-VM support:

- **101,000 target sims** (fresh sample pool, `seed=2026`)
- **VM-aware**: `--vm N` flag selects sim ID range from `VM_RANGES` dict
- **Same production hardening** as V9: resume support, periodic backups, auto-pause at 10% failure rate, isolated temp dirs per worker
- **103 CSV columns** — identical schema to V9

Additionally, `batch_100k_helper.py` was created during the run to redistribute VM4's remaining work to the faster VMs, using `--start`, `--end`, and `--tag` arguments.

---

# Infrastructure

## GCP Project

- **Project:** `fluted-visitor-491612-p5`
- **Zone:** `us-central1-f`
- **Quota:** 500 C2D CPUs in `us-central1` (approved via quota increase request)
- **Cost:** ~$17/hr total across all 4 VMs, ~$73 total (covered by GCP free trial credits)

## VM Configuration

| VM | Instance Type | vCPUs | RAM | Workers | Sim Range | Sims |
|----|--------------|-------|-----|---------|-----------|------|
| fea-runner-1 | c2d-standard-112 | 112 | 448 GB | 100 | 1–25,250 | 25,250 |
| fea-runner-2 | c2d-standard-112 | 112 | 448 GB | 100 | 25,251–50,500 | 25,250 |
| fea-runner-3 | c2d-standard-112 | 112 | 448 GB | 100 | 50,501–75,750 | 25,250 |
| fea-runner-4 | c2d-standard-56 | 56 | 224 GB | 50 | 75,751–101,000 | 25,250 |

- **Provisioning:** On-demand (Spot was tried during V9 — got preempted)
- **OS:** Debian 12, CalculiX 2.21, Python 3.11, Gmsh 4.15

## Software Stack

Each VM was set up using `setup_100k.sh`:
- `calculix-ccx` (apt package, v2.21)
- `python3-pip` + `gmsh` (pip, v4.15)
- `libgl1-mesa-glx` (Gmsh dependency)

---

# Execution Log

## Setup & Launch (28 March 2026, ~20:00 UTC)

1. `gcloud` CLI on Windows used to provision all 4 VMs
2. `setup_100k.sh` uploaded and executed on each VM
3. `batch_100k.py` uploaded to `~/sims/` on all 4 VMs
4. Smoke test: 5 sims per VM, all passed
5. Production launch: `nohup python3 batch_100k.py --vm N --workers W > /dev/null 2>&1 &`

## Disk Crisis & Fix

VMs were initially created with **10 GB disks** instead of 50 GB. All 4 hit "No space left on device" after ~100 sims. Fixed without data loss:

1. `gcloud compute disks resize` to 50 GB (online, no reboot)
2. `apt-get clean` to free space
3. `growpart /dev/sda 1` + `resize2fs /dev/sda1` to expand filesystem

## Monitoring

The monitoring script checked all 4 VMs every 5 minutes via `check_vms.ps1`. Each check: SSH into each VM, read last log line, CSV row count, disk %, RAM available, process count. If a VM finished: download CSV, stop VM.

## Production Run (20:19–00:37 UTC)

| VM | Steady-State Speed | Error Rate | Finished |
|----|-------------------|------------|----------|
| fea-runner-1 | ~122 sims/min | 0.004% (1 error) | ~23:42 UTC |
| fea-runner-2 | ~119 sims/min | 0% | ~23:40 UTC |
| fea-runner-3 | ~121 sims/min | 0% | ~23:44 UTC |
| fea-runner-4 | ~61 sims/min | 0% | Partial, redistributed |
| **Combined** | **~423 sims/min** | | |

## Work Redistribution (~23:50–00:37 UTC)

VM4 (c2d-56, 50 workers) ran at half the speed. Remaining ~9,152 sims redistributed to VM1-3 using `batch_100k_helper.py`:

| Helper | VM | Range | Sims Done | Finished |
|--------|----|-------|-----------|----------|
| help3 | fea-runner-3 | 81,938–88,374 | 2,839 | ~00:27 UTC |
| help5 | fea-runner-1 | 94,688–97,844 | 3,156 | ~00:37 UTC |
| help6 | fea-runner-2 | 97,845–101,000 | 3,157 | ~00:37 UTC |

All 4 VMs stopped at ~00:41 UTC on 29 March.

---

# Data Quality Verification (29 March 2026)

Verified programmatically on the merged CSV:

| Metric | Value |
|--------|-------|
| **Total rows** | 101,000 |
| **Solver converged** | 100,999 (99.999%) |
| **Solver errors** | 1 (sim_id 16421) |
| **Columns** | 103 |
| **Duplicate sim_ids** | 0 |
| **Zero mises in OK sims** | 0 |
| **Null values** | 0 |

## Key Statistics (100,999 successful sims)

| Metric | Mean | Min | Max |
|--------|------|-----|-----|
| max_mises (MPa) | 883 | 22 | 4,251 |
| tsai_wu_index | 1.44 | — | — |
| max_s12 (MPa) | 47.7 | — | 261 |
| n_elements | — | — | — |

## Failure Rates

- **Tsai-Wu failed:** 66,054 / 100,999 (65.4%)
- **Hashin failed:** 74,803 / 100,999 (74.1%)
- Both classes well-populated for classification training

## Defect Distribution

| n_defects | Count |
|-----------|-------|
| 1 | 20,200 |
| 2 | 20,200 |
| 3 | 20,200 |
| 4 | 20,200 |
| 5 | 20,199 |

Perfectly uniform.

## Physics Consistency

- Mises mean (883 MPa) matches V9 20k (883 MPa) and V7 Abaqus (864 MPa) — three independent runs agree
- Mises ↔ Tsai-Wu correlation: r ≈ 0.98
- S12 shear stress captured correctly (V7 Abaqus had S12=0 bug)
- Pressure range: 5–100 MPa biaxial (same as V7/V9)

---

# Files

## Scripts (in `C:\CalculiX\test_composite\`)

| File | Purpose |
|------|---------|
| `batch_100k.py` | Production batch runner with `--vm` support |
| `batch_100k_helper.py` | Helper for work redistribution (`--start/--end/--tag`) |
| `setup_100k.sh` | VM setup script |
| `run_on_vm.ps1` | PowerShell SSH wrapper for gcloud |
| `check_vms.ps1` | Monitoring alarm clock (5 min intervals) |

## Results (in `C:\CalculiX\test_composite\results_100k\`)

| File | Rows | Description |
|------|------|-------------|
| `results_vm1.csv` | 25,142 | VM1 primary range (1–25,250) |
| `results_vm2.csv` | 25,124 | VM2 primary range (25,251–50,500) |
| `results_vm3.csv` | 25,171 | VM3 primary range (50,501–75,750) |
| `results_vm4.csv` | 16,099 | VM4 partial (75,751–101,000) |
| `results_help3.csv` | 2,840 | Helper on VM3 |
| `results_help5.csv` | 3,157 | Helper on VM1 |
| `results_help6.csv` | 3,158 | Helper on VM2 |
| **`results_merged_101k.csv`** | **101,001** | **Deduplicated merge (header + 101k data rows)** |

---

# Comparison with Previous Versions

| Property | V7 (Abaqus) | V9 (CalculiX 20k) | V10 (CalculiX 101k) |
|----------|-------------|-------------------|---------------------|
| Samples | 891 | 14,387 | 100,999 |
| Solver | Abaqus 2023 | CalculiX 2.17/2.23 | CalculiX 2.21 |
| Infrastructure | University machine | Laptop + 1 GCP VM | 4 GCP VMs |
| Wall time | ~days | ~8 hrs laptop + ~4 hrs cloud | ~4 hrs 18 min |
| Success rate | 89.1% | 99.5% | 99.999% |
| Mises mean | 864 MPa | 883 MPa | 883 MPa |
| S12 bug | Yes (all zeros) | No | No |
| Columns | 61 | 103 | 103 |
| Seed | — | 101 | 2026 |
| Cost | University license | ~$2.55/hr | ~$73 total |

---

# Significance for ML Training

- **113x more data than V7** — transforms the ML problem from data-starved to data-rich
- **GPR (O(n³)) will not scale** — need sparse GP or skip entirely
- **Tree models (XGBoost, CatBoost, RF) should scale well** and benefit from denser coverage of the parameter space
- **Neural networks / PINN** should see the largest relative improvement — deep models need large datasets to outperform trees (McElfresh et al., 2023; Vurtur Badarinath et al., 2021)
- **Simple 80/20 split** gives ~20k test samples — more than the entire V7+V9 combined
- **Defect interaction learning** now feasible — with 20k samples per defect count, the model can learn genuine multi-crack interaction effects rather than just rough trends
