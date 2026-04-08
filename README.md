# Machine Learning Surrogates for Parametric Composite Failure Prediction

**AENG30017 Research Project — University of Bristol, 2025–26**

Artur Akoev · Student Number 2111017 · Department of Aerospace Engineering

---

## Overview

This repository contains the complete codebase for a progressive FEA–ML surrogate pipeline spanning ten configurations, from isotropic steel plates with a single circular hole (V1, 100 simulations) to composite laminates with jagged random-walk cracks under Hashin progressive damage (V10, 101,000 simulations at $73 cloud cost).

**Key results:**
- PINN achieves R² = 0.904 for peak von Mises stress (V10)
- XGBoost yields Tsai–Wu F₁ = 0.948 and Hashin F₁ = 0.962
- Experimental verification of the Grinsztajn et al. (2022) NN–tree crossover at ~50k samples
- Hashin compression modes recover from R² = 0.051 (V4) to 0.670 (V10)
## Repository Structure

```
├── simulations/            # FEA pipeline scripts (parametric geometry → solver → CSV)
│   ├── v4/                 # Abaqus composite multi-defect (20 script revisions)
│   ├── v7/                 # Abaqus jagged cracks + Hashin (3-stage architecture)
│   ├── v8/                 # CalculiX validation + test suite
│   ├── v9/                 # 20k cloud campaign (laptop–cloud consistency)
│   ├── v10/                # 101k production campaign (GCP, $73)
│   └── v11/                # CompositeNet 1.155M planning (future work)
│
├── ml/                     # Machine learning training and inference
│   ├── v1/                 # Isotropic baseline (Ridge, RF, GB, XGB, NN)
│   ├── v2/                 # Elliptical defects (7 features, 300 samples)
│   ├── v7/                 # Jagged cracks (68 features, 891 samples)
│   └── v10/                # 101k-scale pipeline
│       ├── training/       # Main ML pipeline + model export
│       ├── experiments/    # Ablation, class weights, mesh convergence
│       └── app/            # Streamlit surrogate prediction app
│
├── infrastructure/         # Cloud deployment scripts
│   └── gcp/                # GCP VM orchestration (PowerShell + bash)
│
└── docs/                   # Version documentation
    └── versions/           # Per-version design notes (V1–V11)
```
## Version Timeline

| Version | Material | Solver | Samples | Features | Key Contribution |
|---------|----------|--------|---------|----------|-----------------|
| V1 | Steel | Abaqus | 100 | 3 | Pipeline automation, Kirsch validation |
| V2 | Steel | Abaqus | 300 | 7 | Elliptical defects, LHS sampling |
| V3 | Steel | Abaqus | 500 | 13 | Two-hole interaction (scoping) |
| V4 | CFRP | Abaqus | 500 | 32 | Composite multi-defect, 20-bug campaign |
| V5 | CFRP | Abaqus | — | 40 | Jagged crack geometry (scoping) |
| V6 | CFRP | Abaqus | 2,574 | 42 | `softening=LINEAR` bug (all SDEG = 0) |
| V7 | CFRP | Abaqus | 891 | 68 | Bug fix, 3-stage validation architecture |
| V8 | CFRP | CalculiX | 1,200 | 45 | Open-source pivot, Abaqus validation |
| V9 | CFRP | CalculiX | 14,387 | 103 | Cloud consistency verification |
| V10 | CFRP | CalculiX | 100,999 | 98 | **101k campaign, $73, Grinsztajn crossover** |

## Dependencies

**FEA:** Abaqus 2022 (V1–V7), CalculiX 2.21+ (V8–V10), Gmsh 4.x

**Python 3.10+:**
```
scikit-learn>=1.3  xgboost>=2.0  catboost>=1.2  pytorch>=2.0
mapie>=0.8  shap>=0.43  optuna>=3.4
matplotlib>=3.8  seaborn>=0.13  pandas  numpy  scipy
```
## Reproducing the V10 Campaign

1. Set up a GCP VM with CalculiX and Gmsh installed (see `simulations/v10/setup_100k.sh`)
2. Run `python simulations/v10/batch_100k.py --start 0 --end 25000 --workers 100`
3. Merge CSVs and run `python ml/v10/training/v10_ml_pipeline.py`

Full instructions: [`simulations/v10/INSTRUCTIONS_100K.md`](simulations/v10/INSTRUCTIONS_100K.md)

## Licence

This code is released for academic and research purposes. If you use this work, please cite the accompanying report.