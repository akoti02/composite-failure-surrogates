# 100K CalculiX Simulation Run — Setup Instructions

## Overview
Run 101,000 FEA simulations across 4 GCP VMs in parallel. Each VM runs an independent slice of the work. Results are 4 separate CSVs that get merged afterwards.

## VM Configuration

| VM Name | Machine Type | vCPUs | RAM | Workers | Sim Range | Zone |
|---------|-------------|-------|-----|---------|-----------|------|
| fea-100k-vm1 | c2d-standard-112 | 112 | 448 GB | 100 | 1–25,250 | us-central1-a |
| fea-100k-vm2 | c2d-standard-112 | 112 | 448 GB | 100 | 25,251–50,500 | us-central1-a |
| fea-100k-vm3 | c2d-standard-112 | 112 | 448 GB | 100 | 50,501–75,750 | us-central1-a |
| fea-100k-vm4 | c2d-standard-60 | 60 | 240 GB | 55 | 75,751–101,000 | us-central1-a |

Total: 396 vCPUs (within 400 C2D quota).
All VMs: Ubuntu 22.04 LTS, 50 GB disk, **Standard provisioning** (NOT Spot — we got preempted last time).

## Files to Upload to Each VM

Only 2 files needed per VM:
1. `setup_100k.sh` — one-time setup script
2. `batch_100k.py` — the simulation runner

## Per-VM Setup (do this on EACH VM)

```bash
# 1. Upload files via SSH UPLOAD button
# 2. Run setup
chmod +x ~/setup_100k.sh && ~/setup_100k.sh
# 3. Move script
mv ~/batch_100k.py ~/sims/
```

## Smoke Test (do on ONE VM first)

```bash
cd ~/sims && python3 batch_100k.py --vm 1 --workers 5 --test 5
```
Should complete in ~2 minutes with 5/5 OK, 0 errors.

## Launch Production Run

On each VM, run the appropriate command:

**VM1:**
```bash
cd ~/sims && nohup python3 batch_100k.py --vm 1 --workers 100 > run.log 2>&1 &
```

**VM2:**
```bash
cd ~/sims && nohup python3 batch_100k.py --vm 2 --workers 100 > run.log 2>&1 &
```

**VM3:**
```bash
cd ~/sims && nohup python3 batch_100k.py --vm 3 --workers 100 > run.log 2>&1 &
```

**VM4 (smaller VM):**
```bash
cd ~/sims && nohup python3 batch_100k.py --vm 4 --workers 55 > run.log 2>&1 &
```

## Monitor

On each VM:
```bash
tail -f ~/sims/batch_100k_vm<N>.log
```

## Download Results

Each VM produces its own CSV:
- VM1: `~/sims/results_vm1.csv`
- VM2: `~/sims/results_vm2.csv`
- VM3: `~/sims/results_vm3.csv`
- VM4: `~/sims/results_vm4.csv`

Download all 4 CSVs, then merge locally.

## DELETE ALL VMs IMMEDIATELY AFTER DOWNLOADING

Total cost at ~$2.55/hr per c2d-112 and ~$1.27/hr for c2d-60:
- 3 × $2.55 + $1.27 = ~$8.92/hr
- For ~5 hours: ~$45

## Expected Timeline

- Setup per VM: ~5 minutes
- Sample generation: ~3 minutes (each VM generates all 101k samples, runs only its slice)
- Simulation run: ~4-5 hours
- Total wall time: ~5.5 hours
