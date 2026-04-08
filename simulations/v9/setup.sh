#!/bin/bash
# CompositeBench server setup script
# Run on Cherry Servers EPYC instance (Ubuntu/Debian)

set -e

echo "=== CompositeBench Server Setup ==="

# System packages
echo "Installing system packages..."
apt-get update -q
apt-get install -y -q python3 python3-pip gmsh calculix-ccx

# Python packages
echo "Installing Python packages..."
pip3 install scipy

# Verify installations
echo ""
echo "=== Verification ==="
echo -n "Python3: "; python3 --version
echo -n "gmsh: "; gmsh --version 2>&1 || echo "gmsh not found!"
echo -n "ccx: "; which ccx && echo "OK" || echo "ccx not found!"
echo -n "scipy: "; python3 -c "import scipy; print(scipy.__version__)" 2>/dev/null || echo "scipy not found!"

# Create work directories
mkdir -p ~/sims
mkdir -p ~/compositeNet

echo ""
echo "=== Setup Complete ==="
echo "Deploy files to ~/compositeNet/ and run: bash run_all_tests.sh"
