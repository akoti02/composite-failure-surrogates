#!/bin/bash
# Setup script for GCP VM (fea-runner)
# Run this ONCE after SSH-ing into the VM

set -e

echo "=== Step 1: Install system packages ==="
sudo apt update
sudo apt install -y calculix-ccx python3-pip libglu1-mesa libxcursor1 libxinerama1

echo ""
echo "=== Step 2: Install Python packages ==="
pip3 install gmsh

echo ""
echo "=== Step 3: Create working directory ==="
mkdir -p ~/sims

echo ""
echo "=== Step 4: Verify installations ==="
echo -n "ccx: "
which ccx && ccx 2>&1 | head -1 || echo "NOT FOUND"
echo -n "Python: "
python3 --version
echo -n "Gmsh Python: "
python3 -c "import gmsh; print(gmsh.__version__)"

echo ""
echo "=== Step 5: Quick ccx smoke test ==="
cd /tmp
cat > test.inp << 'INPEOF'
*HEADING
Smoke test
*NODE
1, 0.0, 0.0, 0.0
2, 1.0, 0.0, 0.0
3, 0.5, 0.866, 0.0
4, 0.5, 0.0, 0.0
5, 0.75, 0.433, 0.0
6, 0.25, 0.433, 0.0
*ELEMENT, TYPE=S6, ELSET=TEST
1, 1, 2, 3, 4, 5, 6
*MATERIAL, NAME=MAT1
*ELASTIC
210000, 0.3
*SHELL SECTION, ELSET=TEST, MATERIAL=MAT1
0.1
*BOUNDARY
1, 1, 3, 0.0
2, 2, 3, 0.0
*STEP
*STATIC
*CLOAD
3, 2, 100.0
*EL PRINT, ELSET=TEST
S
*END STEP
INPEOF
ccx test 2>&1 | tail -5
if [ -f test.dat ] && [ -s test.dat ]; then
    echo "ccx smoke test: PASSED (produced .dat output)"
else
    echo "ccx smoke test: FAILED (no .dat output)"
fi
rm -f test.*
cd ~

echo ""
echo "=== SETUP COMPLETE ==="
echo "Next: upload batch_20k_cloud.py and calculix_results_20k.csv to ~/sims/"
echo "Then: cd ~/sims && python3 batch_20k_cloud.py --test 5"
