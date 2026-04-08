#!/bin/bash
# Cloud-init userdata for Cherry Servers VM — CompositeBench testing
set -e

echo "=== Installing dependencies ==="
apt-get update -qq
apt-get install -y -qq calculix-ccx python3-pip libglu1-mesa libxcursor1 libxinerama1
pip3 install gmsh scipy --break-system-packages 2>/dev/null || pip3 install gmsh scipy

echo "=== Creating work directory ==="
mkdir -p /root/sims

echo "=== Verifying installations ==="
echo -n "ccx: "; which ccx
echo -n "Python: "; python3 --version
echo -n "Gmsh: "; python3 -c "import gmsh; print(gmsh.__version__)"
echo -n "Scipy: "; python3 -c "import scipy; print(scipy.__version__)"

echo "=== SETUP COMPLETE ===" > /root/setup_done.flag
