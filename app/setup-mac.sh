#!/bin/bash
# RP3 App — Mac Setup Script
# Run this once to set up the development environment on macOS

set -e

echo "=== RP3 App — Mac Setup ==="
echo ""

# Check Xcode Command Line Tools
if ! xcode-select -p &>/dev/null; then
    echo "Xcode Command Line Tools required. Installing..."
    xcode-select --install
    echo "Please re-run this script after Xcode tools finish installing."
    exit 1
fi
echo "[ok] Xcode Command Line Tools"

# Check Node.js
if ! command -v node &>/dev/null; then
    echo "Node.js required. Install via: brew install node"
    exit 1
fi
echo "[ok] Node.js $(node --version)"

# Check Rust
if ! command -v cargo &>/dev/null; then
    echo "Rust required. Installing via rustup..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    source "$HOME/.cargo/env"
fi
echo "[ok] Rust $(cargo --version)"

# Check Python 3
if ! command -v python3 &>/dev/null; then
    echo "Python 3 required. Install via: brew install python3"
    exit 1
fi
echo "[ok] Python $(python3 --version)"

# Install Node dependencies
echo ""
echo "Installing Node dependencies..."
npm install

# Install Python ML dependencies + PyInstaller for sidecar
echo ""
echo "Installing Python ML dependencies..."
pip3 install numpy xgboost scikit-learn pyinstaller

# Build sidecar binary for macOS (needed for release builds)
echo ""
echo "Building macOS sidecar binary..."
cd sidecar
if [ ! -f _models_data.py ]; then
    echo "ERROR: _models_data.py not found in sidecar/. Cannot build without model data."
    exit 1
fi
pyinstaller --onefile --name rp3-sidecar server.py \
  --hidden-import inference --hidden-import _models_data \
  --add-data "_models_data.py:."
echo "[ok] Sidecar built at sidecar/dist/rp3-sidecar"
cd ..

echo ""
echo "=== Setup complete ==="
echo ""
echo "To run in dev mode:  npx tauri dev"
echo "To build release:    npx tauri build"
echo ""
echo "Note: First launch will compile the Rust backend (~2 min)."
echo "Subsequent launches are instant."
