# RP3 — Composite Failure Surrogate

A desktop application for predicting stress distributions and failure in composite laminates with manufacturing defects (wrinkles, voids, delaminations). Combines analytical solutions (Lekhnitskii anisotropic elasticity) with ML surrogate models trained on FEA data.

## Features

- **Analysis Tab** — Configure defect geometry, loading, and material; run ML surrogate predictions (ensemble of neural networks, XGBoost, PINN) for 11 failure outputs
- **Stress Field Tab** — Interactive 2D stress field visualization with ply-resolved views, failure index mapping (Tsai-Wu, Hashin, Max Stress), worst-ply envelope, ML-calibrated scaling, and contour overlays
- **Laminate Tab** — Classical Lamination Theory engine: ABD matrices, ply stress/strain analysis, progressive failure simulation, thermal effects
- **Explorer Tab** — Parameter sweeps, sensitivity analysis, and Monte Carlo simulation across defect/load space
- **Project Tab** — Save/load analysis sessions, compare results, export data
- **Live auto-update, bilingual UI (EN / RU), signed release binaries**

## Install (recommended)

Pre-built binaries are published to [GitHub Releases](https://github.com/akoti02/composite-failure-surrogates/releases).

### Windows (x64)
1. Download `RP3_*_x64-setup.exe` from the latest release
2. Run it — the NSIS installer is per-user, no admin rights needed
3. Launch RP3 from Start menu

### macOS (Apple Silicon)
1. Download `RP3_*_aarch64.dmg` from the latest release
2. Open the disk image, drag **RP3** to Applications
3. **First launch:** right-click (or Ctrl-click) the app in Applications → **Open** → **Open** in the confirmation dialog.
   This is needed once because the build isn't Apple-notarized (we don't pay for an Apple Developer account); Gatekeeper will stop warning after this. Every update from here on installs without the prompt.

### Auto-update
From v0.3.0 onwards, installed copies check GitHub Releases on launch. When a new version is out you'll see a violet banner — one click → signed binary downloads → installer runs silently (Windows: passive NSIS; macOS: in-place replace) → app relaunches on the new version. No reinstall wizard.

## Tech Stack

- **Frontend**: React + TypeScript + Tailwind CSS
- **Desktop**: Tauri 2 (Rust)
- **ML Backend**: Python sidecar (XGBoost, scikit-learn, NumPy)
- **Physics**: Lekhnitskii complex variable solution, CLT, Tsai-Wu/Hashin failure criteria

## Build from source

Only needed if you want to modify the app. The [CI workflow](../.github/workflows/release.yml) is the canonical build recipe — if a local build disagrees with it, CI is right.

### Prerequisites
- **Node.js 20 LTS** (`nvm install 20` / `fnm use 20`). Node 21+ is not tested against our Tauri version.
- Rust stable toolchain (install via rustup)
- Python 3.12 with sidecar deps: `pip install -r sidecar/requirements.txt`
- macOS only: `brew install libomp` (xgboost runtime dep)

### Development

```bash
cd app
npm install
npm run dev          # Vite dev server (frontend only)
npx tauri dev        # Full app with Rust + Python sidecar (spawns server.py directly)
```

### Build a signed release locally

```bash
# 1. Build the Python sidecar
cd app/sidecar
pyinstaller --clean rp3-sidecar.spec

# 2. Build the Tauri bundle (set signing key env vars first)
cd ..
export TAURI_SIGNING_PRIVATE_KEY="<path to ~/.tauri/rp3.key>"
export TAURI_SIGNING_PRIVATE_KEY_PASSWORD=""
npx tauri build
```

Output:
- **Windows**: `src-tauri/target/release/bundle/nsis/RP3_*-setup.exe` (+ `.sig`)
- **macOS**: `src-tauri/target/release/bundle/dmg/RP3_*.dmg` (+ `.app.tar.gz` for updater, + `.sig`)

## Project Structure

```
src/
  components/       React UI components
  lib/
    i18n.ts          Bilingual dictionary + <LangProvider>
    stress-field.ts  Lekhnitskii analytical solver
    clt.ts           Classical Lamination Theory
    materials.ts     Composite material database (5 materials)
    presets.ts       Predefined analysis scenarios
    types.ts         Shared type definitions
sidecar/
  server.py          Python ML inference server (stdin/stdout JSON-RPC)
  inference.py       Model loading and prediction
  _models_data.py    Embedded XGBoost model blobs (base64)
  rp3-sidecar.spec   PyInstaller build spec (cross-platform)
  requirements.txt   Pinned Python deps
src-tauri/
  src/               Rust backend (Tauri commands, sidecar management)
  tauri.conf.json    App config (incl. updater endpoint + pubkey)
```

## Troubleshooting

**App starts but status says "No models loaded / Error: Sidecar not found"** → the Python sidecar crashed or isn't bundled. Check logs at `~/.rp3/sidecar.log` and `~/.rp3/sidecar_stderr.log`.

**macOS: "RP3 is damaged and can't be opened"** → you double-clicked without right-click. Right-click → Open. If that still fails, `xattr -rd com.apple.quarantine /Applications/RP3.app` in Terminal.

**Update banner never appears** → check that you're online; the app queries `https://github.com/akoti02/composite-failure-surrogates/releases/latest/download/latest.json` once on launch.
