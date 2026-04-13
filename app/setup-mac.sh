#!/bin/bash
# RP3 App — Mac Setup Script
# Run this once to set up the development environment on macOS

set -e

echo "=== RP3 App — Mac Setup ==="

# Check prerequisites
command -v node >/dev/null 2>&1 || { echo "Node.js required. Install via: brew install node"; exit 1; }
command -v cargo >/dev/null 2>&1 || { echo "Rust required. Install via: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "Python 3 required. Install via: brew install python3"; exit 1; }

# Install Node dependencies
echo "Installing Node dependencies..."
npm install

# Install Python ML dependencies for sidecar
echo "Installing Python ML dependencies..."
pip3 install numpy xgboost scikit-learn

# Install Tauri CLI
echo "Installing Tauri CLI..."
npm install -g @tauri-apps/cli

echo ""
echo "=== Setup complete ==="
echo ""
echo "To run in dev mode:  npx tauri dev"
echo "To build release:    npx tauri build"
