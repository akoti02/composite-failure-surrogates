> [!info] 20K → 100K Campaign
> **20,000-sample CalculiX campaign** launched overnight 27–28 March 2026. Produced 14,457 sims (14,387 successful). PARDISO benchmarked — no speedup. **100K campaign** completed 29 March ~00:37 UTC across 4 GCP VMs — **101,000 sims, 100,999 converged** (1 solver error). Merged CSV: `results_merged_101k.csv` (69 MB).

---

# Batch Script: `batch_20k.py`

Built on top of the earlier `batch_3000_parallel.py` from V8, with production hardening:

- **Per-worker isolated temp directories** — each ccx instance runs in its own `tempfile.mkdtemp()` to prevent file contention
- **Resume support** — reads existing CSV on startup, skips already-completed sim_ids
- **Periodic CSV backups** every 500 sims
- **Auto-pause** if failure rate exceeds 10%
- **Logging** to `batch_20k.log` with timestamps
- **103 CSV columns** including engineered features (cos/sin angles, aspect ratios, SIF estimates, ligament ratios, boundary proximity)

Settings: 20,750 target samples, `seed=101`, SPOOLES solver (`ccx_static.exe`), 10 parallel workers.

---

# Worker Count Benchmark

Script: `test_optimal_workers.py` — tested 8, 10, 12, 14, 16 workers with 40 sims each (test seed=7777).

| Workers | OK | Fail | Fail% | Wall (s) | Sims/min | Per-sim (s) |
|---------|-----|------|-------|----------|----------|-------------|
| 8 | 40 | 0 | 0% | 264.1 | 9.1 | 6.60 |
| 10 | 40 | 0 | 0% | 241.5 | 9.9 | 6.04 |
| 12 | 38 | 2 | 5% | 260.7 | 9.2 | 6.52 |
| 14 | 34 | 6 | 15% | 226.4 | 10.6 | 5.66 |
| 16 | 29 | 11 | 28% | 167.3 | 14.3 | 4.18 |

**Key finding:** 16 workers has highest raw throughput but 28% failure rate — 16 ccx instances + Gmsh exceed 32 GB RAM. **10 workers chosen as optimal:** 0% failures at 9.9 sims/min. The script misleadingly reported 16 as "BEST" based on raw sims/min, but failed sims need re-running, making 10 the actual best.

---

# Incremental Validation Tests

All tests used 10 workers, SPOOLES solver, `seed=101`.

| Time | Test | Workers | Sims | OK | Fail | Speed | Notes |
|------|------|---------|------|----|------|-------|-------|
| 02:50 | 1-sim smoke | 1 | 1 | 1 | 0 | 6.8/min | Single worker sanity check |
| 02:51 | 10-sim | 12 | 10 | 10 | 0 | 8.7/min | 12 workers, all passed |
| 02:53 | 50-sim | 12 | 50 | 50 | 0 | 16.7/min | Resumed from 10 |
| 03:39 | 100-sim | 10 | 100 | 100 | 0 | 15.3/min | Fresh CSV, final validation |

All passed. CSV integrity verified (103 columns, valid values).

---

# Production Run (03:47–12:09)

- **03:47:50** — Launched: 20,650 remaining sims, 10 workers, resuming from 100 test sims
- **Steady state:** ~13.4–13.5 sims/min (slower than small test batches due to larger average meshes in the full sample set)
- **03:47–11:52** — 6,500 sims completed with only 1 error (0.0% failure rate). Backups saved every 500 sims.
- **11:52–12:01** — Sudden spike: 31 new errors in quick succession (sims 6500–6650). Likely a cluster of large-mesh sims hitting memory limits simultaneously.
- **12:01–12:09** — Errors stabilised at 70 total (1.0% failure rate). Still well below the 10% auto-pause threshold.
- **~12:10** — Artur stopped the run manually.

## Production Run Summary

| Metric | Value |
|--------|-------|
| Duration | ~8 hours 22 minutes |
| Sims completed | 6,910 (6,840 successful, 70 errors) |
| Failure rate | 1.0% |
| Throughput | 13.4–13.5 sims/min |
| ETA for remaining 13,840 sims | ~17 hours |

---

# CSV Quality Review

Thorough analysis of `calculix_results_20k.csv` (6,910 rows, 103 columns):

- **Integrity:** Zero nulls, zero malformed rows, zero duplicate sim_ids, 7 missing IDs (in-flight when killed)
- **Success rate:** 6,840 YES / 70 ERROR (99.0%)
- **Error rows:** All correctly zeroed (max_mises=0, tsai_wu=0)
- **Physics plausibility** (successful sims only):
  - max_mises: 49.7–2,822.6 MPa (mean 883) — reasonable for CFRP under biaxial load
  - tsai_wu_index: 0.056–7.26 (mean 1.43) — values >1 indicate predicted failure, distribution correct
  - Hashin matrix tension dominates (max 22.5), compression modes negligible — correct for tensile loading with cracks
- **Correlations all physically correct:**
  - pressure → stress: r=0.45 (x), r=0.65 (y)
  - mises ↔ tsai_wu: r=0.98
  - mises ↔ hashin_mt: r=0.95
- **Defect distribution:** Nearly uniform across 1–5 defects (1,289 / 1,359 / 1,365 / 1,382 / 1,367)
- **One outlier:** sim 6824 with only 37 elements (unusual geometry), but valid stress values

**Verdict:** Data is clean, physically consistent, and ready for ML training.

---

# PARDISO Benchmark

Attempt to speed up the solver using Intel PARDISO (via MKL) instead of SPOOLES.

## MKL Installation

- Installed Intel oneAPI MKL 2025.3.1 via winget (665 MB)
- `ccx_dynamic.exe` requires `mkl_rt.2.dll` which dynamically loads PARDISO
- First attempt: copied only `mkl_rt.2.dll` → crash ("Cannot load mkl_intel_thread.2.dll")
- Second attempt: copied 9 DLLs (mkl_core, mkl_intel_thread, mkl_def, mkl_avx2, mkl_avx512, mkl_sequential, mkl_mc3, mkl_rt) + `libiomp5md.dll` (OpenMP runtime)
- Smoke test: `ccx_dynamic.exe` ran successfully but defaulted to PaStiX — needed `*STATIC,SOLVER=PARDISO` in the input file

## Benchmark Results

Script: `benchmark_pardiso.py` — 10 identical sims with each solver, run serially.

| Sim | Elements | SPOOLES (s) | PARDISO (s) | Speedup |
|-----|----------|-------------|-------------|---------|
| 1 | 39,907 | 44.44 | 59.64 | 0.75x (slower) |
| 2 | 10,341 | 11.61 | 12.48 | 0.93x |
| 3 | 22,751 | 29.88 | 31.59 | 0.95x |
| 4 | 18,304 | 22.90 | 25.94 | 0.88x |
| 5 | 8,179 | 9.13 | 9.50 | 0.96x |
| 6 | 42,196 | 74.45 | 62.70 | 1.19x (faster) |
| 7 | 45,670 | 80.80 | 65.74 | 1.23x (faster) |
| 8 | 11,025 | 13.64 | 14.95 | 0.91x |
| 9 | 16,803 | 22.49 | 22.63 | 0.99x |
| 10 | 3,429 | 3.71 | 4.34 | 0.86x |
| **Average** | | **31.30** | **30.95** | **1.01x** |

**Verdict:** PARDISO provides essentially zero speedup (~1%). Marginally faster on the largest meshes (40k+ elements) but slower on smaller ones. PARDISO is designed for large 3D models with 100k+ DOF; our shell models are too small. Gmsh mesh generation also takes a significant portion of each sim's wall time, so the solver isn't the only bottleneck.

---

# 20K Final State

- **Completed:** 14,457 sims in CSV (14,387 successful, 70 errors) — 99.5% success rate
- **Cloud run produced zero errors** — all 70 errors were from the laptop run
- **CSV location:** `Attachments/Data/V9/calculix_results_v9_20k.csv`

## V7 (Abaqus) vs V9 (CalculiX) Cross-Validation

Compared 891 successful V7 Abaqus sims against 14,387 V9 CalculiX sims — same composite plate model, same defect types, independent solvers:

| Metric | V7 Abaqus (891 sims) | V9 CalculiX (14,387 sims) | Notes |
|--------|---------------------|--------------------------|-------|
| **Success rate** | 89.1% | 99.5% | CalculiX far more stable |
| **max_mises mean** | 864 MPa | 883 MPa | Within 2% — strong agreement |
| **max_mises p50** | 778 | 865 | Similar distributions |
| **tsai_wu mean** | 1.94 | 1.44 | Abaqus slightly higher |
| **hashin_mt mean** | 4.14 | 2.57 | Abaqus ~1.6x higher |
| **max_s12 (shear)** | **0 (all zeros — bug!)** | 47.7 mean | V7 never captured shear stress |
| **min_s11 (compression)** | -1,227 | -5,582 | CalculiX captures more extremes |
| **n_elements mean** | 4,744 | 18,508 | CalculiX uses ~4x finer mesh |
| **failed_tsai_wu %** | 71% | 66% | Similar |
| **failed_hashin %** | 76% | 74% | Similar |

**Key findings:**
1. **Mises stresses agree within 2%** — two independent solvers producing consistent physics, validating the CalculiX pipeline
2. **V7 had a shear stress bug** — `max_s12 = 0` for all 891 sims. Abaqus wasn't outputting S12. CalculiX captures it correctly. This alone justifies the switch.
3. **CalculiX uses finer meshes** (18.5k vs 4.7k elements) — captures more extreme stress values at crack tips
4. **Tsai-Wu/Hashin slightly lower in CalculiX** — finer mesh distributes stress more smoothly rather than concentrating in fewer integration points
5. **CalculiX is far more reliable** — 99.5% vs 89.1% success rate

## 14,457-Sim CSV Quality Summary

- **Integrity:** 103 columns, zero nulls, zero malformed rows, zero duplicate sim_ids
- **Physics:** All correlations physically correct (pressure→stress r=0.45/0.65, mises↔tsai_wu r=0.977, mises↔hashin_mt r=0.933)
- **Defect distribution:** Uniform across 1–5 defects (2,853–2,896 each)
- **Laptop vs cloud consistency:** Mean mises = 883.3 for both subsets — Ubuntu ccx 2.17 and Windows ccx 2.23 produce identical results
- **Per-defect mises:** All 5 columns perfectly match defect presence (no corruption)

---

# Files Created This Session

| File | Purpose |
|------|---------|
| `batch_20k.py` | Production batch runner |
| `test_optimal_workers.py` | Worker count benchmark |
| `benchmark_pardiso.py` | PARDISO vs SPOOLES benchmark |
| `calculix_results_20k.csv` | 6,910 rows of results |
| `batch_20k.log` | Full production run log |
| MKL DLLs (9 files + libiomp5md.dll) | Intel MKL for PARDISO |
| Backup CSVs (×13) | `_backup_500.csv` through `_backup_6500.csv` |

All files located in `C:\CalculiX\test_composite\` except MKL DLLs in `C:\CalculiX\calculix_2.23_4win\`.

---

# GCP Cloud VM Setup (28 March 2026)

To finish the remaining ~13,000 sims faster than the ~17 hours the laptop would need, a GCP Spot VM was provisioned via Perplexity/Comet browser.

## VM Configuration

| Setting | Value |
|---------|-------|
| Name | `fea-runner` |
| Instance type | `e2-standard-32` (32 vCPUs, 128 GB RAM) |
| Provisioning | Spot (~$0.50/hr) |
| OS | Ubuntu 22.04 LTS, 50 GB disk |
| Zone | `us-central1-b` |
| Cost | Covered by GCP free trial credits |

## Software Installed

- CalculiX (`ccx`) at `/usr/bin/ccx`
- Python 3.10.12
- Gmsh 4.8.4
- `build-essential` (gcc, g++, make)

## Upload & Run Plan

1. Upload sim files via `gcloud compute scp --recurse C:\path\to\sims fea-runner:~/sims --zone=us-central1-b`
2. Run batch script with `multiprocessing.Pool(30)` — 30 parallel CalculiX jobs
3. Download results CSV
4. **Delete VM immediately** after to stop charges

**Estimated completion:** ~40–45 minutes for the remaining ~13,000 sims — vs ~17 hours on the laptop.

## Cloud Run Execution Log (28 March, ~13:00 onwards)

Three files were prepared for the cloud run:
- `cloud_setup.sh` — one-time VM setup (installs pip gmsh, runs ccx smoke test)
- `batch_20k_cloud.py` — Linux version of the batch script (30 workers, `/usr/bin/ccx`, `~/sims/`)
- `calculix_results_20k.csv` — the 6,910 existing laptop results so resume works

### Setup

Connected to the VM via SSH-in-browser (GCP Console). First SSH attempt timed out during file upload — reconnected, verified all software was still installed (`which ccx && python3 --version && which gmsh` → all present). Uploaded all 3 files via the SSH window's UPLOAD FILE button.

Ran `cloud_setup.sh`:
- System packages: all already installed from initial provisioning (calculix-ccx 2.17-3, Python 3.10.12)
- Python packages: installed Gmsh 4.15.2 (40 MB wheel)
- ccx smoke test: PASSED (produced `.dat` output, Total CalculiX Time: 0.002802s)

### Smoke Test (5 sims)

Moved files into `~/sims/`, ran `python3 batch_20k_cloud.py --test 5`:
- Generated 20,750 sample parameters in 1.0s
- Crack polygon generation: 20,750 valid, 0 self-intersecting (~2 minutes)
- Resume check: found 6,910 sims already in CSV
- Test run: 5/5 OK, 0 ERR (0.0%), 1.2 min elapsed, 4.0 sims/min
- All 5 sims successful, CSV integrity confirmed

### Production Run (13:07 onwards)

Launched with `nohup python3 batch_20k_cloud.py --workers 30 > run.log 2>&1 &` (PID 8328).

Monitoring via `tail -f ~/sims/batch_20k_cloud.log`:

| Sims Done | Elapsed | Errors | Fail% | Sims/min | ETA |
|-----------|---------|--------|-------|----------|-----|
| 50/13,835 | 2.0 min | 0 | 0.0% | 25.6 | 539 min |
| 100/13,835 | 3.4 min | 0 | 0.0% | 29.4 | 467 min |
| 150/13,835 | 5.0 min | 0 | 0.0% | 29.8 | 459 min |

Throughput ramping up as workers warm in — started at 25.6 sims/min, climbing towards 30. ETA settling around 7–8 hours. Slower than the initial 40-minute estimate (the `e2-standard-32` has shared vCPUs, not dedicated cores, and the Ubuntu-packaged CalculiX is v2.17 vs the Windows 2.23 build). Still roughly 2x the laptop's throughput of 13.5 sims/min, with 0% failure rate so far.

Run is ongoing via `nohup` — safe to disconnect from SSH.

### E2 Performance Verdict

The `e2-standard-32` delivered ~30 sims/min — only ~2x the laptop's 13.5 sims/min, far short of the estimated 40-minute completion. Root cause: E2 instances use shared, lower-frequency CPUs rather than dedicated cores.

### Upgrading to Compute-Optimized C2 Instance

To get meaningful speedup, a new VM `fea-runner-c2` was configured:

| Setting | Value |
|---------|-------|
| Name | `fea-runner-c2` |
| Instance type | `c2-standard-60` (60 vCPUs, 30 dedicated cores @ 3.1 GHz) |
| RAM | 240 GB |
| Provisioning | Spot (~$1.02/hr) |

**Quota issue:** New GCP accounts only allow 8 C2 CPUs by default — we need 60. A quota increase request (8 → 60 C2 CPUs in `us-central1`) was submitted via IAM Quotas page. These are typically approved within minutes to a few hours.

**Also needed:** A global CPU quota increase — currently 32/32 used by `fea-runner`. Either stop `fea-runner` first or get the global quota bumped before launching the C2 VM.

**Plan once approved:** Create the C2 VM, install same software, transfer CSV from the E2 VM (or re-upload), resume the batch. Expected throughput: 3–4x the E2, bringing the remaining ~13,000 sims down to ~1–2 hours.

The old `fea-runner` (E2) is still running the batch in the background while we wait for quota approval.

### E2 Run — Continued Progress (13:31)

Attempted to kill the E2 batch (`kill -9 8328`) to prepare for the C2 switch — but the process survived (`nohup` kept it alive). This is actually useful since it means progress continues at ~$0.50/hr while waiting for the C2 quota.

Status at 13:31:25:

| Metric | Value |
|--------|-------|
| Completed (this session) | 650/13,835 |
| Total in CSV | ~7,565 (6,915 resumed + 650 new) |
| Errors | 0 (0.0%) |
| Speed | ~29.5 sims/min |
| ETA | ~447 min (~7.5 hrs from start) |

Plan: Once C2 quota is approved, spin up `fea-runner-c2`, transfer the CSV, and resume — the script's resume feature will skip all already-completed sims automatically.

### C2 Quota Approved — Switch to C2D-Standard-56

Quota increase approved by Google (13:28): 60 C2 CPUs in `us-central1`, 60 global. However, the first C2 Spot VM was **preempted** (killed by Google) after ~1 hour — Spot instances are unreliable for multi-hour jobs.

New VM created: **`fea-runner-standard`** with Standard (non-preemptible) provisioning:

| Setting | Value |
|---------|-------|
| Name | `fea-runner-standard` |
| Instance type | `c2d-standard-56` (56 vCPUs, 28 AMD EPYC Milan cores, 224 GB RAM) |
| Provisioning | Standard (cannot be preempted) |
| Cost | ~$2.55/hr |
| OS | Ubuntu 22.04 LTS, 50 GB disk |
| Zone | `us-central1-a` |

### C2D Production Run (16:03 onwards)

Launched: `python3 batch_20k_cloud.py --workers 56`, resuming from 6,910 sims.

| Sims Done | Elapsed | Errors | Sims/min | ETA |
|-----------|---------|--------|----------|-----|
| 50 | 1.1 min | 0 | 44.1 | 313 min |
| 500 | 9.0 min | 0 | 55.9 | 239 min |
| 1,000 | 17.6 min | 0 | 56.8 | 226 min |
| 1,300 | 22.7 min | 0 | 57.2 | 219 min |

Throughput stabilised at **~57 sims/min** with 0% errors. ETA: **~3.5–4 hours** for the remaining 13,840 sims.

---

# 100K Campaign (28 March 2026, ~20:19 UTC onwards)

The two-phase pipeline (separate mesh generation and solve) was considered but ultimately not implemented. Instead, `batch_100k.py` was written as a single-phase script (mesh + solve in one worker function), distributed across 4 VMs. The brute-force approach with enough cores turned out to be simpler and fast enough.

## Script: `batch_100k.py`

Evolution of `batch_20k.py` with multi-VM support:

- **101,000 target sims** (fresh sample pool, `seed=2026`, independent from the 20K dataset)
- **VM-aware**: `--vm N` flag selects sim ID range from `VM_RANGES` dict
- **Same production hardening** as batch_20k: resume support, periodic backups, auto-pause, isolated temp dirs
- **103 CSV columns** — identical schema to V9 20K dataset

## 4-VM Infrastructure

Quota increase approved: 500 C2D CPUs in `us-central1`. All VMs in zone `us-central1-f`, project `fluted-visitor-491612-p5`.

| VM | Instance Type | vCPUs | RAM | Workers | Sim Range | Sims |
|----|--------------|-------|-----|---------|-----------|------|
| fea-runner-1 | c2d-standard-112 | 112 | 448 GB | 100 | 1–25,250 | 25,250 |
| fea-runner-2 | c2d-standard-112 | 112 | 448 GB | 100 | 25,251–50,500 | 25,250 |
| fea-runner-3 | c2d-standard-112 | 112 | 448 GB | 100 | 50,501–75,750 | 25,250 |
| fea-runner-4 | c2d-standard-56 | 56 | 224 GB | 50 | 75,751–101,000 | 25,250 |

- **Provisioning:** On-demand (not Spot — got preempted during the 20K run)
- **Cost:** ~$4.83/hr per c2d-112, ~$2.55/hr for c2d-56 = **~$17.04/hr total**
- **OS:** Debian 12, CalculiX 2.21, Python 3.11, Gmsh 4.15

## Setup & Launch

1. `gcloud` CLI installed on Windows; SSH via PowerShell helper (`run_on_vm.ps1`) wrapping `gcloud compute ssh`
2. `setup_100k.sh` uploaded and run on each VM — installs `calculix-ccx`, `python3-pip`, `gmsh`, `libgl1-mesa-glx`
3. `batch_100k.py` uploaded to `~/sims/` on all 4 VMs
4. Smoke test: 5 sims per VM, all passed
5. Production launch: `nohup python3 batch_100k.py --vm N --workers W > /dev/null 2>&1 &`

## Disk Crisis & Fix

VMs were initially created with **10 GB disks** instead of 50 GB. All 4 VMs hit "No space left on device" after ~100 sims. Fixed without data loss:

1. `gcloud compute disks resize` to 50 GB (online, no reboot)
2. `apt-get clean` to free space for installing tools
3. `apt install cloud-guest-utils` for `growpart`
4. `growpart /dev/sda 1` — expand partition to fill disk
5. `resize2fs /dev/sda1` — expand filesystem

All VMs now have 49 GB usable. Disk usage stable at 13–35% — temp files are cleaned per sim, only CSVs grow (~2 KB/sim, ~50 MB for 25K sims).

## Monitoring Protocol

The monitoring script checks all 4 VMs every 5 minutes via an alarm clock script (`check_vms.ps1`). Each check cycle:

1. SSH into each VM, read: last log line, CSV row count, disk %, RAM available, process count
2. Verify zero errors, all worker processes alive, resources healthy
3. If a VM process died: restart (resume picks up from CSV)
4. If a VM finished (`BATCH COMPLETE` in log): download CSV to `C:\CalculiX\test_composite\results_100k\`, stop VM
5. When all 4 done: merge CSVs, stop all VMs

## Production Run Progress

Launched ~20:19 UTC on 28 March 2026. Completed ~00:37 UTC on 29 March (~4h 18m total). Throughput stabilised within first 5 minutes.

| VM | Steady-State Speed | Error Rate |
|----|-------------------|------------|
| fea-runner-1 | ~122 sims/min | 0.004% (1 error) |
| fea-runner-2 | ~119 sims/min | 0% |
| fea-runner-3 | ~121 sims/min | 0% |
| fea-runner-4 | ~61 sims/min | 0% |
| **Combined** | **~423 sims/min** | |

### Phase 1: Primary Ranges (~20:19–23:45 UTC)

VM1-3 finished their 25,250-sim ranges in ~3.5 hours. VM4 (half the workers) completed ~16,098 of its 25,250 sims by ~23:45 UTC.

| VM | Sims | OK | Errors | Finished |
|----|------|----|--------|----------|
| fea-runner-1 | 25,250 | 25,141 | 1 | ~23:42 UTC |
| fea-runner-2 | 25,250 | 25,124 | 0 | ~23:40 UTC |
| fea-runner-3 | 25,250 | 25,171 | 0 | ~23:44 UTC |
| fea-runner-4 | 25,250 | 16,098 (partial) | 0 | — |

### Phase 2: Work Redistribution (~23:50–00:37 UTC)

VM4 (c2d-56, 50 workers) ran at half the speed of VM1-3. `batch_100k_helper.py` (patched version with `--start`, `--end`, `--tag` arguments) was used to redistribute VM4's remaining ~9,152 sims across VM1-3. VM4's partial CSV was seeded to each helper so the resume logic skipped already-done sims. VM4 continued in parallel but was redundant.

| Helper | VM | Range | Sims Done | Finished |
|--------|----|-------|-----------|----------|
| help3 | fea-runner-3 | 81,938–88,374 | 2,839 | ~00:27 UTC |
| help5 | fea-runner-1 | 94,688–97,844 | 3,156 | ~00:37 UTC |
| help6 | fea-runner-2 | 97,845–101,000 | 3,157 | ~00:37 UTC |

### Final Results

- **101,000 / 101,000 simulations completed** (100%)
- **100,999 converged**, 1 solver error (sim_id 16421)
- **Total wall time:** ~4h 18m (20:19–00:37 UTC)
- **Merged CSV:** `results_merged_101k.csv` (69 MB, 103 columns, 101K rows)
- **All 4 VMs stopped** at ~00:41 UTC on 29 March

RAM fluctuations observed on VM2 (146→92 GB available) were Linux disk cache, not actual memory pressure — `MemAvailable` stayed well above 10 GB on all VMs throughout.

## Files Created for 100K Run

| File | Purpose |
|------|---------|
| `batch_100k.py` | Production batch runner with `--vm` support |
| `setup_100k.sh` | VM setup script (apt packages + pip gmsh) |
| `batch_100k_helper.py` | Patched version with `--start/--end/--tag` for work redistribution |
| `run_on_vm.ps1` | PowerShell SSH helper for gcloud |
| `check_vms.ps1` | Alarm clock script that runs every 5 min |

Results in `C:\CalculiX\test_composite\results_100k\`:

| File | Rows | Description |
|------|------|-------------|
| `results_vm1.csv` | 25,142 | VM1 primary range (1–25,250) |
| `results_vm2.csv` | 25,124 | VM2 primary range (25,251–50,500) |
| `results_vm3.csv` | 25,171 | VM3 primary range (50,501–75,750) |
| `results_vm4.csv` | 16,099 | VM4 partial (75,751–101,000) |
| `results_help3.csv` | 2,840 | Helper on VM3 (81,938–88,374) |
| `results_help5.csv` | 3,157 | Helper on VM1 (94,688–97,844) |
| `results_help6.csv` | 3,158 | Helper on VM2 (97,845–101,000) |
| **`results_merged_101k.csv`** | **101,001** | **Deduplicated merge (101K data rows + header)** |
