# RP3 — Composite Failure Surrogate

A desktop application for predicting stress distributions and failure in composite laminates with manufacturing defects (wrinkles, voids, delaminations). Combines analytical solutions (Lekhnitskii anisotropic elasticity) with ML surrogate models trained on FEA data.

## Features

- **Analysis Tab** — Configure defect geometry, loading, and material; run ML surrogate predictions (ensemble of neural networks, XGBoost, PINN) for 11 failure outputs
- **Stress Field Tab** — Interactive 2D stress field visualization with ply-resolved views, failure index mapping (Tsai-Wu, Hashin, Max Stress), worst-ply envelope, ML-calibrated scaling, and contour overlays
- **Laminate Tab** — Classical Lamination Theory engine: ABD matrices, ply stress/strain analysis, progressive failure simulation, thermal effects
- **Explorer Tab** — Parameter sweeps, sensitivity analysis, and Monte Carlo simulation across defect/load space
- **Project Tab** — Save/load analysis sessions, compare results, export data

## Tech Stack

- **Frontend**: React + TypeScript + Tailwind CSS
- **Desktop**: Tauri (Rust)
- **ML Backend**: Python sidecar (PyTorch, XGBoost, scikit-learn)
- **Physics**: Lekhnitskii complex variable solution, CLT, Tsai-Wu/Hashin failure criteria

## Quick Start

### Prerequisites
- Node.js 18+
- Rust toolchain (for Tauri)
- Python 3.10+ with dependencies: `pip install torch xgboost scikit-learn numpy`

### Development
```bash
npm install
npm run dev        # Vite dev server (frontend only)
npx tauri dev      # Full app with Rust + Python sidecar
```

### Build Release
```bash
npx tauri build
```

Output: `src-tauri/target/release/rp3.exe` (standalone) or NSIS installer in `src-tauri/target/release/bundle/nsis/`

### Sidecar Setup
The ML sidecar must be built separately before `tauri build`:
```bash
cd sidecar
pip install pyinstaller
pyinstaller rp3-sidecar.spec
```
This produces `sidecar/dist/rp3-sidecar.exe` which Tauri bundles into the release.

## Project Structure

```
src/
  components/       # React UI components
  lib/
    stress-field.ts # Lekhnitskii analytical solver
    clt.ts          # Classical Lamination Theory
    ply-stress-field.ts  # Ply-resolved stress + failure analysis
    materials.ts    # Composite material database
    types.ts        # Shared type definitions
sidecar/
  server.py         # Python ML inference server
  inference.py      # Model loading and prediction
src-tauri/
  src/              # Rust backend (Tauri commands, sidecar management)
```

## Download

Pre-built **Windows x64** installer: see [Releases](https://github.com/akoti02/composite-failure-surrogates/releases) page.

**macOS / Linux:** No pre-built binaries yet. Build from source:
```bash
# macOS — run the setup script, then build
./setup-mac.sh
npx tauri build

# Linux — install deps manually, then build
npm install
pip3 install numpy xgboost scikit-learn pyinstaller
cd sidecar && pyinstaller --onefile --name rp3-sidecar server.py \
  --hidden-import inference --hidden-import _models_data \
  --add-data "_models_data.py:." && cd ..
npx tauri build
```
