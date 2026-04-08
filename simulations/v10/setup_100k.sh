#!/bin/bash
# Setup script for 100K run — run this on EACH VM after creation
set -e

echo "=== Installing dependencies ==="
sudo apt-get update -qq
sudo apt-get install -y -qq calculix-ccx python3-pip libglu1-mesa libxcursor1 libxinerama1
pip3 install gmsh scipy

echo ""
echo "=== Creating work directory ==="
mkdir -p ~/sims

echo ""
echo "=== Verifying installations ==="
echo -n "ccx: "; which ccx
echo -n "Python: "; python3 --version
echo -n "Gmsh: "; python3 -c "import gmsh; print(gmsh.__version__)"
echo -n "Scipy: "; python3 -c "import scipy; print(scipy.__version__)"

echo ""
echo "=== Quick ccx smoke test ==="
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
ccx test 2>&1 | tail -3
if [ -f test.dat ] && [ -s test.dat ]; then
    echo "ccx smoke test: PASSED"
else
    echo "ccx smoke test: FAILED"
    exit 1
fi
rm -f test.*
cd ~

echo ""
echo "=== SETUP COMPLETE ==="
echo "Next: upload batch_100k.py to ~/sims/"
echo "Then: cd ~/sims && python3 batch_100k.py --vm <N> --workers <W> --test 5"
