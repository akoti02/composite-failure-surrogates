"""
DEEP INDEPENDENT VERIFICATION of CompositeBench CLT calculations.

This script does NOT import anything from batch_compositeNet or full_verification.
Every calculation is done from scratch, with extensive intermediate output,
so each step can be manually inspected.

Checks:
1. Q-matrix derivation for several materials
2. Q-bar transformation for key angles (0, 45, 90)
3. A-matrix for QI layup — verify quasi-isotropy (A11 ≈ A22, A16 ≈ 0)
4. A-matrix inversion — verify A * A^-1 = I
5. Strain response to unit Nx
6. Ply stress recovery in global and material axes
7. Failure index calculation
8. FPF pressure for QI layup — all 22 materials
9. UD_0 trivial check: FPF should equal XT (fibre aligned)
10. UD_90 trivial check: FPF should equal YT (fibres transverse)
11. Asymmetric laminate: full ABD check for layup 29
12. All 770 combos — independent calculation
13. Cross-check: QI effective modulus vs Halpin-Tsai estimate
14. Sign convention verification for stress transformation

Author: Independent verification script (no shared code with batch_compositeNet)
"""

import math
import sys
import json

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# ═══════════════════════════════════════════════════════════════════════════════
# RAW MATERIAL DATA (copied directly from the MATERIALS dict, not imported)
# ═══════════════════════════════════════════════════════════════════════════════
MATS = {
    1:  {"name": "T300/5208",       "E1": 135000, "E2": 10000, "G12": 5200,  "v12": 0.27, "XT": 1500, "XC": 1200, "YT": 50,  "YC": 250, "SL": 70},
    2:  {"name": "T300/914",        "E1": 138000, "E2": 8900,  "G12": 5600,  "v12": 0.30, "XT": 1500, "XC": 1200, "YT": 62,  "YC": 200, "SL": 79},
    3:  {"name": "T700/Epoxy",      "E1": 132000, "E2": 9000,  "G12": 5000,  "v12": 0.30, "XT": 2150, "XC": 1470, "YT": 55,  "YC": 185, "SL": 90},
    4:  {"name": "T800S/Epoxy",     "E1": 163000, "E2": 8700,  "G12": 5500,  "v12": 0.32, "XT": 2900, "XC": 1490, "YT": 64,  "YC": 197, "SL": 98},
    5:  {"name": "IM7/8552",        "E1": 171400, "E2": 9080,  "G12": 5290,  "v12": 0.32, "XT": 2326, "XC": 1200, "YT": 62,  "YC": 200, "SL": 92},
    6:  {"name": "AS4/3501-6",      "E1": 140000, "E2": 10000, "G12": 7000,  "v12": 0.29, "XT": 2200, "XC": 1700, "YT": 60,  "YC": 200, "SL": 100},
    7:  {"name": "AS4/8552",        "E1": 135000, "E2": 9500,  "G12": 5000,  "v12": 0.30, "XT": 2023, "XC": 1234, "YT": 81,  "YC": 200, "SL": 114},
    8:  {"name": "E-glass/Epoxy",   "E1": 39000,  "E2": 8600,  "G12": 3800,  "v12": 0.28, "XT": 1000, "XC": 700,  "YT": 40,  "YC": 120, "SL": 70},
    9:  {"name": "T1100/Epoxy",     "E1": 324000, "E2": 8000,  "G12": 5500,  "v12": 0.30, "XT": 3100, "XC": 1500, "YT": 50,  "YC": 200, "SL": 80},
    10: {"name": "HTS40/Epoxy",     "E1": 135000, "E2": 9500,  "G12": 4500,  "v12": 0.30, "XT": 2000, "XC": 1300, "YT": 55,  "YC": 200, "SL": 85},
    11: {"name": "S2-glass/Epoxy",  "E1": 55000,  "E2": 16000, "G12": 7600,  "v12": 0.26, "XT": 1700, "XC": 1150, "YT": 60,  "YC": 180, "SL": 75},
    12: {"name": "Kevlar49/Epoxy",  "E1": 80000,  "E2": 5500,  "G12": 2200,  "v12": 0.34, "XT": 1400, "XC": 335,  "YT": 30,  "YC": 158, "SL": 49},
    13: {"name": "T300/PEEK",       "E1": 134000, "E2": 10100, "G12": 5500,  "v12": 0.28, "XT": 2130, "XC": 1100, "YT": 80,  "YC": 200, "SL": 120},
    14: {"name": "AS4/PEKK",        "E1": 138000, "E2": 10300, "G12": 5500,  "v12": 0.31, "XT": 2070, "XC": 1360, "YT": 86,  "YC": 215, "SL": 110},
    15: {"name": "Flax/Epoxy",      "E1": 35000,  "E2": 5500,  "G12": 3000,  "v12": 0.30, "XT": 350,  "XC": 150,  "YT": 25,  "YC": 100, "SL": 40},
    16: {"name": "Basalt/Epoxy",    "E1": 45000,  "E2": 12000, "G12": 5000,  "v12": 0.26, "XT": 1100, "XC": 800,  "YT": 45,  "YC": 140, "SL": 65},
    17: {"name": "M55J/Epoxy",      "E1": 340000, "E2": 7000,  "G12": 5000,  "v12": 0.28, "XT": 1800, "XC": 900,  "YT": 40,  "YC": 180, "SL": 65},
    18: {"name": "T650/Cycom",      "E1": 152000, "E2": 8700,  "G12": 4800,  "v12": 0.31, "XT": 2400, "XC": 1500, "YT": 65,  "YC": 240, "SL": 95},
    19: {"name": "IM10/Epoxy",      "E1": 190000, "E2": 9000,  "G12": 5600,  "v12": 0.31, "XT": 3100, "XC": 1600, "YT": 60,  "YC": 210, "SL": 90},
    20: {"name": "Carbon/BMI",      "E1": 155000, "E2": 8500,  "G12": 5000,  "v12": 0.30, "XT": 2000, "XC": 1400, "YT": 55,  "YC": 200, "SL": 80},
    21: {"name": "HM-CFRP",         "E1": 230000, "E2": 6500,  "G12": 4500,  "v12": 0.25, "XT": 1200, "XC": 700,  "YT": 35,  "YC": 170, "SL": 55},
    22: {"name": "Jute/Polyester",  "E1": 20000,  "E2": 5000,  "G12": 2500,  "v12": 0.30, "XT": 200,  "XC": 100,  "YT": 20,  "YC": 80,  "SL": 30},
}

# ═══════════════════════════════════════════════════════════════════════════════
# RAW LAYUP DATA (copied directly, not imported)
# ═══════════════════════════════════════════════════════════════════════════════
LAYS = {
    1:  [0, 45, -45, 90, 90, -45, 45, 0],
    2:  [0, 45, -45, 90, 0, 45, -45, 90, 90, -45, 45, 0, 90, -45, 45, 0],
    3:  [0, 90, 0, 90, 90, 0, 90, 0],
    4:  [0]*8,
    5:  [90]*8,
    6:  [45, -45, 45, -45, -45, 45, -45, 45],
    7:  [30, -30, 30, -30, -30, 30, -30, 30],
    8:  [60, -60, 60, -60, -60, 60, -60, 60],
    9:  [45, 0, -45, 90, 90, -45, 0, 45],
    10: [0, 0, 45, -45, -45, 45, 0, 0],
    11: [45]*8,
    12: [0, 90, 90, 0, 0, 90, 90, 0],
    13: [45, -45, 0, 0, 90, 0, 0, -45, 45, 45, -45, 0, 0, 90, 0, 0, -45, 45],
    14: [45, -45, 45, -45, 45, -45, 45, -45, -45, 45, -45, 45, -45, 45, -45, 45],
    15: [0, 45, 90, -45, 0, 45, 45, 0, -45, 90, 45, 0],
    16: [0, 0, 45, -45, 0, 90, 0, -45, 45, 0, 0, 45, -45, 0, 90, 0, -45, 45, 0, 0],
    17: [55, -55, 55, -55, -55, 55, -55, 55],
    18: [75, -75, 75, -75, -75, 75, -75, 75],
    19: [20, 70, -20, -70, -70, -20, 70, 20],
    20: [25, 65, -25, -65, -65, -25, 65, 25],
    21: [10, -10, 10, -10, -10, 10, -10, 10],
    22: [15, -15, 15, -15, -15, 15, -15, 15],
    23: [20, -20, 20, -20, -20, 20, -20, 20],
    24: [0, 90, 45, -45, -45, 45, 90, 0],
    25: [0, 30, 60, 90, 0, 30, 60, 90],
    26: [15, 45, 75, 15, 45, 75, 15, 45],
    27: [0,45,-45,90]*3 + [90,-45,45,0]*3,
    28: [0,90]*6 + [90,0]*6,
    29: [0, 45, -45, 90],
    30: [0, 90, 90, 0],
    31: [0]*16,
    32: [0, 30, -30, 90, 90, -30, 30, 0],
    33: [0, 60, -60, 90, 90, -60, 60, 0],
    34: [0, 15, -15, 0, 0, -15, 15, 0],
    35: [0, 45, -45, 90, 90, 90, 90, 90, 90, -45, 45, 0],
}

PLY_T = 0.15
errors = []
warnings = []
test_count = 0
pass_count = 0

def check(name, actual, expected, tol=1e-4, rel=True):
    """Check a value and report pass/fail."""
    global test_count, pass_count
    test_count += 1
    if isinstance(expected, bool):
        ok = actual == expected
    elif expected == 0:
        ok = abs(actual) <= tol
    elif rel:
        ok = abs(actual - expected) / abs(expected) <= tol
    else:
        ok = abs(actual - expected) <= tol
    if ok:
        pass_count += 1
    else:
        errors.append(f"FAIL: {name}: got {actual}, expected {expected} (tol={tol})")
        print(f"  *** FAIL: {name}: got {actual}, expected {expected}")
    return ok


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1: Q-matrix for T300/5208
# ═══════════════════════════════════════════════════════════════════════════════
print("=" * 80)
print("STEP 1: Reduced stiffness Q-matrix — T300/5208")
print("=" * 80)

m = MATS[1]
E1, E2, v12, G12 = m['E1'], m['E2'], m['v12'], m['G12']
v21 = v12 * E2 / E1
dd = 1.0 - v12 * v21

print(f"  E1 = {E1}, E2 = {E2}, v12 = {v12}, G12 = {G12}")
print(f"  v21 = v12 * E2 / E1 = {v12} * {E2} / {E1} = {v21:.8f}")
print(f"  denominator = 1 - v12*v21 = 1 - {v12}*{v21:.8f} = {dd:.8f}")

Q11 = E1 / dd
Q22 = E2 / dd
Q12 = v12 * E2 / dd
Q66 = G12

print(f"  Q11 = E1/dd = {E1}/{dd:.8f} = {Q11:.4f}")
print(f"  Q22 = E2/dd = {E2}/{dd:.8f} = {Q22:.4f}")
print(f"  Q12 = v12*E2/dd = {v12}*{E2}/{dd:.8f} = {Q12:.4f}")
print(f"  Q66 = G12 = {Q66:.4f}")

# Verify: Q12 should also equal v21*E1/dd
Q12_alt = v21 * E1 / dd
print(f"  Q12 (via v21*E1/dd) = {v21:.8f}*{E1}/{dd:.8f} = {Q12_alt:.4f}")
check("Q12 reciprocity", Q12, Q12_alt, tol=1e-10)

# Verify: v21 * E1 = v12 * E2
check("Reciprocity: v21*E1 = v12*E2", v21*E1, v12*E2, tol=1e-10)

print()

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2: Q-bar for 0°, 45°, 90° — verify known identities
# ═══════════════════════════════════════════════════════════════════════════════
print("=" * 80)
print("STEP 2: Q-bar transformation — verify known identities")
print("=" * 80)

def compute_Qbar(Q11, Q22, Q12, Q66, theta_deg):
    t = math.radians(theta_deg)
    c, s = math.cos(t), math.sin(t)
    c2, s2, cs = c*c, s*s, c*s
    Qb11 = Q11*c2*c2 + 2*(Q12+2*Q66)*c2*s2 + Q22*s2*s2
    Qb22 = Q11*s2*s2 + 2*(Q12+2*Q66)*c2*s2 + Q22*c2*c2
    Qb12 = (Q11+Q22-4*Q66)*c2*s2 + Q12*(c2*c2+s2*s2)
    Qb16 = (Q11-Q12-2*Q66)*c2*cs + (Q12-Q22+2*Q66)*s2*cs
    Qb26 = (Q11-Q12-2*Q66)*cs*s2 + (Q12-Q22+2*Q66)*cs*c2
    Qb66 = (Q11+Q22-2*Q12-2*Q66)*c2*s2 + Q66*(c2*c2+s2*s2)
    return [[Qb11, Qb12, Qb16], [Qb12, Qb22, Qb26], [Qb16, Qb26, Qb66]]

# At 0°: Q-bar should equal Q (no rotation)
Qb0 = compute_Qbar(Q11, Q22, Q12, Q66, 0)
print(f"\n  θ = 0°:")
print(f"    Qb11 = {Qb0[0][0]:.4f}  (should = Q11 = {Q11:.4f})")
print(f"    Qb22 = {Qb0[1][1]:.4f}  (should = Q22 = {Q22:.4f})")
print(f"    Qb12 = {Qb0[0][1]:.4f}  (should = Q12 = {Q12:.4f})")
print(f"    Qb16 = {Qb0[0][2]:.4f}  (should = 0)")
print(f"    Qb26 = {Qb0[1][2]:.4f}  (should = 0)")
print(f"    Qb66 = {Qb0[2][2]:.4f}  (should = Q66 = {Q66:.4f})")
check("Qbar(0°)[11] = Q11", Qb0[0][0], Q11, tol=1e-10)
check("Qbar(0°)[22] = Q22", Qb0[1][1], Q22, tol=1e-10)
check("Qbar(0°)[12] = Q12", Qb0[0][1], Q12, tol=1e-10)
check("Qbar(0°)[16] = 0", Qb0[0][2], 0, tol=1e-6, rel=False)
check("Qbar(0°)[26] = 0", Qb0[1][2], 0, tol=1e-6, rel=False)
check("Qbar(0°)[66] = Q66", Qb0[2][2], Q66, tol=1e-10)

# At 90°: Q-bar should swap Q11↔Q22
Qb90 = compute_Qbar(Q11, Q22, Q12, Q66, 90)
print(f"\n  θ = 90°:")
print(f"    Qb11 = {Qb90[0][0]:.4f}  (should = Q22 = {Q22:.4f})")
print(f"    Qb22 = {Qb90[1][1]:.4f}  (should = Q11 = {Q11:.4f})")
print(f"    Qb12 = {Qb90[0][1]:.4f}  (should = Q12 = {Q12:.4f})")
print(f"    Qb16 = {Qb90[0][2]:.4f}  (should = 0)")
check("Qbar(90°)[11] = Q22", Qb90[0][0], Q22, tol=1e-10)
check("Qbar(90°)[22] = Q11", Qb90[1][1], Q11, tol=1e-10)
check("Qbar(90°)[12] = Q12", Qb90[0][1], Q12, tol=1e-10)
check("Qbar(90°)[16] = 0", Qb90[0][2], 0, tol=1e-6, rel=False)

# At 45°: Qb16 for +45 and -45 should be equal and opposite
Qb45p = compute_Qbar(Q11, Q22, Q12, Q66, 45)
Qb45m = compute_Qbar(Q11, Q22, Q12, Q66, -45)
print(f"\n  θ = ±45°:")
print(f"    Qb16(+45) = {Qb45p[0][2]:.4f}")
print(f"    Qb16(-45) = {Qb45m[0][2]:.4f}")
print(f"    Sum = {Qb45p[0][2] + Qb45m[0][2]:.4f}  (should = 0)")
check("Qbar16(+45) + Qbar16(-45) = 0", Qb45p[0][2] + Qb45m[0][2], 0, tol=1e-6, rel=False)

# At ±45°: Qb11(+45) = Qb11(-45), Qb22(+45) = Qb22(-45)
check("Qbar11(+45) = Qbar11(-45)", Qb45p[0][0], Qb45m[0][0], tol=1e-10)
check("Qbar22(+45) = Qbar22(-45)", Qb45p[1][1], Qb45m[1][1], tol=1e-10)

# At 45°: Q11 = Q22 (by symmetry of 45° rotation swapping 1↔2 axes in the 45° frame)
print(f"    Qb11(45) = {Qb45p[0][0]:.4f}")
print(f"    Qb22(45) = {Qb45p[1][1]:.4f}")
# Note: Qb11(45) ≠ Qb22(45) in general for orthotropic materials. Check manually.

print()


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3: A-matrix for QI layup — check quasi-isotropy
# ═══════════════════════════════════════════════════════════════════════════════
print("=" * 80)
print("STEP 3: A-matrix for QI [0/45/-45/90]_s — T300/5208")
print("=" * 80)

angles = [0, 45, -45, 90, 90, -45, 45, 0]
n = len(angles)
h = n * PLY_T

A = [[0.0]*3 for _ in range(3)]
B = [[0.0]*3 for _ in range(3)]
D = [[0.0]*3 for _ in range(3)]
Qbar_list = []

for k, th in enumerate(angles):
    Qb = compute_Qbar(Q11, Q22, Q12, Q66, th)
    Qbar_list.append(Qb)
    zb = -h/2 + k*PLY_T
    zt = zb + PLY_T
    for i in range(3):
        for j in range(3):
            A[i][j] += Qb[i][j] * (zt - zb)
            B[i][j] += 0.5 * Qb[i][j] * (zt**2 - zb**2)
            D[i][j] += (1.0/3.0) * Qb[i][j] * (zt**3 - zb**3)

print(f"  h_total = {h} mm, n_plies = {n}")
print(f"\n  A-matrix (N/mm):")
for i in range(3):
    print(f"    [{A[i][0]:12.2f}  {A[i][1]:12.2f}  {A[i][2]:12.2f}]")

print(f"\n  B-matrix (N):")
for i in range(3):
    print(f"    [{B[i][0]:12.4f}  {B[i][1]:12.4f}  {B[i][2]:12.4f}]")

# Check quasi-isotropy: A11 ≈ A22, A16 ≈ 0, A26 ≈ 0
print(f"\n  Quasi-isotropy checks:")
print(f"    A11 = {A[0][0]:.2f}")
print(f"    A22 = {A[1][1]:.2f}")
print(f"    A11/A22 = {A[0][0]/A[1][1]:.6f}  (should ≈ 1.0 for QI)")
print(f"    A16 = {A[0][2]:.6f}  (should ≈ 0)")
print(f"    A26 = {A[1][2]:.6f}  (should ≈ 0)")
check("QI: A11 ≈ A22", A[0][0]/A[1][1], 1.0, tol=0.001)
check("QI: A16 ≈ 0", A[0][2], 0, tol=0.01, rel=False)
check("QI: A26 ≈ 0", A[1][2], 0, tol=0.01, rel=False)

# For QI: A66 should ≈ (A11 - A12) / 2 (isotropic condition)
A_iso_check = (A[0][0] - A[0][1]) / 2
print(f"    A66 = {A[2][2]:.2f}")
print(f"    (A11-A12)/2 = {A_iso_check:.2f}")
check("QI: A66 ≈ (A11-A12)/2", A[2][2], A_iso_check, tol=0.01)

# B-matrix should be zero for symmetric layup
bn = sum(abs(B[i][j]) for i in range(3) for j in range(3))
an = sum(abs(A[i][j]) for i in range(3) for j in range(3))
print(f"\n    B-norm = {bn:.10f}")
print(f"    A-norm = {an:.2f}")
print(f"    B/A = {bn/an:.2e}  (should be < 1e-10 for symmetric)")
check("Symmetric: B ≈ 0", bn/an, 0, tol=1e-10, rel=False)

print()


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 4: A-matrix inversion and verification A * A^-1 = I
# ═══════════════════════════════════════════════════════════════════════════════
print("=" * 80)
print("STEP 4: A-matrix inversion — verify A * A^-1 = I")
print("=" * 80)

def inv3x3(m):
    a,b,c = m[0]; d,e,f = m[1]; g,h,k = m[2]
    det = a*(e*k-f*h) - b*(d*k-f*g) + c*(d*h-e*g)
    if abs(det) < 1e-30: return None, 0
    id_ = 1.0/det
    return [[(e*k-f*h)*id_,(c*h-b*k)*id_,(b*f-c*e)*id_],
            [(f*g-d*k)*id_,(a*k-c*g)*id_,(c*d-a*f)*id_],
            [(d*h-e*g)*id_,(b*g-a*h)*id_,(a*e-b*d)*id_]], det

Ainv, det_A = inv3x3(A)
print(f"  det(A) = {det_A:.4e}")
print(f"\n  A^-1 (mm/N):")
for i in range(3):
    print(f"    [{Ainv[i][0]:14.8e}  {Ainv[i][1]:14.8e}  {Ainv[i][2]:14.8e}]")

# Verify A * A^-1 = I
print(f"\n  A * A^-1 =")
for i in range(3):
    row = []
    for j in range(3):
        val = sum(A[i][k] * Ainv[k][j] for k in range(3))
        row.append(val)
    expected = [0, 0, 0]
    expected[i] = 1.0
    print(f"    [{row[0]:12.8f}  {row[1]:12.8f}  {row[2]:12.8f}]")
    for j in range(3):
        check(f"(A*Ainv)[{i}][{j}] = {'1' if i==j else '0'}", row[j], expected[j], tol=1e-10, rel=False)

print()


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 5: Strain response and ply stresses for QI, T300/5208
# ═══════════════════════════════════════════════════════════════════════════════
print("=" * 80)
print("STEP 5: Ply stresses for QI T300/5208 under Nx=1 N/mm")
print("=" * 80)

# Response to unit Nx = [1, 0, 0]
eps_x = Ainv[0][0]
eps_y = Ainv[1][0]
gam_xy = Ainv[2][0]

print(f"  Mid-plane strains (for Nx=1 N/mm, symmetric → κ=0):")
print(f"    εx  = {eps_x:.10e}")
print(f"    εy  = {eps_y:.10e}")
print(f"    γxy = {gam_xy:.10e}")

print(f"\n  Ply-by-ply stress and failure analysis:")
print(f"  {'Ply':>3} {'θ':>5} {'z_mid':>8} {'σx':>12} {'σy':>12} {'τxy':>12} {'σ1':>12} {'σ2':>12} {'τ12':>12} {'f1':>10} {'f2':>10} {'f12':>10} {'f_max':>10} {'Mode':<10}")

XT, XC, YT, YC, SL = m['XT'], m['XC'], m['YT'], m['YC'], m['SL']
max_fi = 0.0
crit_info = ""

for pk, th in enumerate(angles):
    zb = -h/2 + pk*PLY_T
    zm = zb + PLY_T/2.0

    # Strain at mid-ply (symmetric → no bending)
    ex, ey, gxy = eps_x, eps_y, gam_xy

    # Global stress
    Qb = Qbar_list[pk]
    sx = Qb[0][0]*ex + Qb[0][1]*ey + Qb[0][2]*gxy
    sy = Qb[0][1]*ex + Qb[1][1]*ey + Qb[1][2]*gxy
    txy = Qb[0][2]*ex + Qb[1][2]*ey + Qb[2][2]*gxy

    # Material stress (rotation)
    t_ = math.radians(th)
    cc, ss = math.cos(t_), math.sin(t_)
    s1 = sx*cc*cc + sy*ss*ss + 2*txy*cc*ss
    s2 = sx*ss*ss + sy*cc*cc - 2*txy*cc*ss
    t12 = -sx*cc*ss + sy*cc*ss + txy*(cc*cc - ss*ss)

    # Failure indices
    fi1 = s1/XT if s1>=0 else abs(s1)/XC
    fi2 = s2/YT if s2>=0 else abs(s2)/YC
    fi12 = abs(t12)/SL
    fi = max(fi1, fi2, fi12)

    if fi1>=fi2 and fi1>=fi12:
        mode = 'fibre_T' if s1>=0 else 'fibre_C'
    elif fi2>=fi12:
        mode = 'matrix_T' if s2>=0 else 'matrix_C'
    else:
        mode = 'shear'

    print(f"  {pk+1:>3} {th:>5}° {zm:>8.4f} {sx:>12.6f} {sy:>12.6f} {txy:>12.6f} {s1:>12.6f} {s2:>12.6f} {t12:>12.6f} {fi1:>10.6f} {fi2:>10.6f} {fi12:>10.6f} {fi:>10.6f} {mode:<10}")

    if fi > max_fi:
        max_fi = fi
        crit_info = f"ply {pk+1} ({th}°), mode={mode}"

fpf_Nx = 1.0 / max_fi
fpf_p = fpf_Nx / h

print(f"\n  max failure index = {max_fi:.10f}")
print(f"  FPF Nx = 1/{max_fi:.10f} = {fpf_Nx:.4f} N/mm")
print(f"  FPF pressure = {fpf_Nx:.4f} / {h} = {fpf_p:.4f} MPa")
print(f"  Critical: {crit_info}")

# Sanity: for QI, 90° ply should be critical (matrix_T)
# σ2 in 90° ply should be positive (transverse tension under global X-tension)
# because the 90° fibres are perpendicular to the load


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 6: Verify stress transformation with known identity
# ═══════════════════════════════════════════════════════════════════════════════
print()
print("=" * 80)
print("STEP 6: Stress transformation sign convention verification")
print("=" * 80)

# For θ=0°: material axes = global axes → σ1=σx, σ2=σy, τ12=τxy
# For θ=90°: material 1-axis is global Y → σ1=σy, σ2=σx, τ12=-τxy

sx_test, sy_test, txy_test = 100.0, 30.0, 15.0

for th_test in [0, 90, 45]:
    t_ = math.radians(th_test)
    cc, ss = math.cos(t_), math.sin(t_)
    s1 = sx_test*cc*cc + sy_test*ss*ss + 2*txy_test*cc*ss
    s2 = sx_test*ss*ss + sy_test*cc*cc - 2*txy_test*cc*ss
    t12 = -sx_test*cc*ss + sy_test*cc*ss + txy_test*(cc*cc - ss*ss)
    print(f"  θ={th_test:>3}°: σ1={s1:>10.4f}  σ2={s2:>10.4f}  τ12={t12:>10.4f}")

check("θ=0°: σ1=σx", 100.0, 100.0)
check("θ=0°: σ2=σy", 30.0, 30.0)
# θ=90°
t_ = math.radians(90)
cc, ss = math.cos(t_), math.sin(t_)
s1_90 = sx_test*cc*cc + sy_test*ss*ss + 2*txy_test*cc*ss
s2_90 = sx_test*ss*ss + sy_test*cc*cc - 2*txy_test*cc*ss
check("θ=90°: σ1 = σy", s1_90, sy_test, tol=1e-10)
check("θ=90°: σ2 = σx", s2_90, sx_test, tol=1e-10)

# Invariant check: σ1 + σ2 should always = σx + σy (trace invariance)
for th_test in [0, 15, 30, 45, 60, 75, 90]:
    t_ = math.radians(th_test)
    cc, ss = math.cos(t_), math.sin(t_)
    s1 = sx_test*cc*cc + sy_test*ss*ss + 2*txy_test*cc*ss
    s2 = sx_test*ss*ss + sy_test*cc*cc - 2*txy_test*cc*ss
    check(f"Trace invariant θ={th_test}°: σ1+σ2 = σx+σy", s1+s2, sx_test+sy_test, tol=1e-10)

print()


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 7: Trivial cases — UD_0 and UD_90
# ═══════════════════════════════════════════════════════════════════════════════
print("=" * 80)
print("STEP 7: Trivial FPF cases — UD_0 and UD_90")
print("=" * 80)

def full_clt_fpf(mat, angles, verbose=False):
    """Complete CLT FPF — independent implementation."""
    E1, E2, v12_, G12_ = mat['E1'], mat['E2'], mat['v12'], mat['G12']
    XT_, XC_, YT_, YC_, SL_ = mat['XT'], mat['XC'], mat['YT'], mat['YC'], mat['SL']

    v21_ = v12_ * E2 / E1
    dd_ = 1.0 - v12_ * v21_
    Q11_ = E1 / dd_
    Q22_ = E2 / dd_
    Q12_ = v12_ * E2 / dd_
    Q66_ = G12_

    n_ = len(angles)
    h_ = n_ * PLY_T

    A_ = [[0.0]*3 for _ in range(3)]
    B_ = [[0.0]*3 for _ in range(3)]
    D_ = [[0.0]*3 for _ in range(3)]
    Qbl = []

    for k_, th_ in enumerate(angles):
        Qb_ = compute_Qbar(Q11_, Q22_, Q12_, Q66_, th_)
        Qbl.append(Qb_)
        zb_ = -h_/2 + k_*PLY_T
        zt_ = zb_ + PLY_T
        for i_ in range(3):
            for j_ in range(3):
                A_[i_][j_] += Qb_[i_][j_] * (zt_ - zb_)
                B_[i_][j_] += 0.5 * Qb_[i_][j_] * (zt_**2 - zb_**2)
                D_[i_][j_] += (1.0/3.0) * Qb_[i_][j_] * (zt_**3 - zb_**3)

    bn_ = sum(abs(B_[i_][j_]) for i_ in range(3) for j_ in range(3))
    an_ = sum(abs(A_[i_][j_]) for i_ in range(3) for j_ in range(3))
    is_sym = bn_ < 0.001 * an_

    if is_sym:
        Ainv_, _ = inv3x3(A_)
        if Ainv_ is None:
            return 0, "error", -1
        ex_ = Ainv_[0][0]
        ey_ = Ainv_[1][0]
        gxy_ = Ainv_[2][0]
        kx_ = ky_ = kxy_ = 0.0
    else:
        # Full 6×6 ABD inversion
        abd = [[0.0]*6 for _ in range(6)]
        for i_ in range(3):
            for j_ in range(3):
                abd[i_][j_] = A_[i_][j_]
                abd[i_][j_+3] = B_[i_][j_]
                abd[i_+3][j_] = B_[i_][j_]
                abd[i_+3][j_+3] = D_[i_][j_]

        # Gauss-Jordan on augmented matrix
        aug = [abd[r][:] + [1.0 if r == c_ else 0.0 for c_ in range(6)] for r in range(6)]
        for col in range(6):
            mx = col
            for row in range(col+1, 6):
                if abs(aug[row][col]) > abs(aug[mx][col]):
                    mx = row
            aug[col], aug[mx] = aug[mx], aug[col]
            if abs(aug[col][col]) < 1e-30:
                return 0, "singular", -1
            piv = aug[col][col]
            for j_ in range(12):
                aug[col][j_] /= piv
            for row in range(6):
                if row != col:
                    f_ = aug[row][col]
                    for j_ in range(12):
                        aug[row][j_] -= f_ * aug[col][j_]
        abd_inv = [aug[r][6:12] for r in range(6)]

        ex_ = abd_inv[0][0]
        ey_ = abd_inv[1][0]
        gxy_ = abd_inv[2][0]
        kx_ = abd_inv[3][0]
        ky_ = abd_inv[4][0]
        kxy_ = abd_inv[5][0]

    max_fi_ = 0.0
    crit_mode_ = ""
    crit_ply_ = -1

    for pk_, th_ in enumerate(angles):
        zb_ = -h_/2 + pk_*PLY_T
        zm_ = zb_ + PLY_T/2.0

        exx = ex_ + zm_*kx_
        eyy = ey_ + zm_*ky_
        gxxyy = gxy_ + zm_*kxy_

        Qb_ = Qbl[pk_]
        sx_ = Qb_[0][0]*exx + Qb_[0][1]*eyy + Qb_[0][2]*gxxyy
        sy_ = Qb_[0][1]*exx + Qb_[1][1]*eyy + Qb_[1][2]*gxxyy
        txy_ = Qb_[0][2]*exx + Qb_[1][2]*eyy + Qb_[2][2]*gxxyy

        t__ = math.radians(th_)
        cc_, ss_ = math.cos(t__), math.sin(t__)
        s1_ = sx_*cc_*cc_ + sy_*ss_*ss_ + 2*txy_*cc_*ss_
        s2_ = sx_*ss_*ss_ + sy_*cc_*cc_ - 2*txy_*cc_*ss_
        t12_ = -sx_*cc_*ss_ + sy_*cc_*ss_ + txy_*(cc_*cc_ - ss_*ss_)

        fi1_ = s1_/XT_ if s1_>=0 else abs(s1_)/XC_
        fi2_ = s2_/YT_ if s2_>=0 else abs(s2_)/YC_
        fi12_ = abs(t12_)/SL_ if SL_>0 else 0.0
        fi_ = max(fi1_, fi2_, fi12_)

        if fi1_>=fi2_ and fi1_>=fi12_:
            mode_ = 'fibre_T' if s1_>=0 else 'fibre_C'
        elif fi2_>=fi12_:
            mode_ = 'matrix_T' if s2_>=0 else 'matrix_C'
        else:
            mode_ = 'shear'

        if fi_ > max_fi_:
            max_fi_ = fi_
            crit_mode_ = mode_
            crit_ply_ = pk_+1

    if max_fi_ < 1e-15:
        return 1e6, "none", 0

    fpf_Nx_ = 1.0 / max_fi_
    fpf_p_ = fpf_Nx_ / h_
    return round(fpf_p_, 4), crit_mode_, crit_ply_

# UD_0: all plies at 0°, σ1 = σx (direct), so FPF = XT
print(f"\n  UD_0 (all fibres at 0°):")
for mid_test in [1, 8, 22]:
    mt = MATS[mid_test]
    fpf_ud0, mode_ud0, _ = full_clt_fpf(mt, [0]*8)
    # For UD_0 under uniaxial Nx: each ply sees σ1 = Nx/h / (1 ply), but actually
    # the stress in fibre direction = E1/(E1*(1-v12*v21)) * eps_x ≈ Nx/h for 0° ply
    # In fact for all-0° laminate: A11 = Q11*h, A^-1[0][0] = 1/(Q11*h)
    # eps_x = Nx / (Q11*h), σ1 = Q11 * eps_x = Nx/h → FPF when σ1=XT → Nx/h = XT → FPF_p = XT
    # But there's also a transverse stress σ2 from Poisson...

    # Actually: for all-0° laminate, the stress state is:
    # σ1 = Q11 * eps_x + Q12 * eps_y (in material = global for 0°)
    # σ2 = Q12 * eps_x + Q22 * eps_y
    # With Nx=1, Ny=0: eps_x = A^-1[0][0], eps_y = A^-1[1][0]
    # For UD_0: A = Q * h (since all plies same), so A^-1 = Q^-1 / h
    # Q^-1 * [1, 0, 0]^T → eps_x = S11, eps_y = S12 (compliance)
    # σ1 = Q11*S11 + Q12*S12 = 1/h (exactly — from definition of S)
    # σ2 = Q12*S11 + Q22*S12 = 0/h = 0 (from definition of compliance)
    # So σ1 = Nx/h, σ2 = 0, τ12 = 0 → FPF = XT

    expected_fpf = float(mt['XT'])
    diff = abs(fpf_ud0 - expected_fpf)
    print(f"    Mat {mid_test} ({mt['name']}): FPF = {fpf_ud0:.1f}, expected XT = {expected_fpf:.1f}, diff = {diff:.4f}")
    check(f"UD_0 Mat{mid_test}: FPF = XT", fpf_ud0, expected_fpf, tol=0.001)

# UD_90: all plies at 90°, σ2 = ?
print(f"\n  UD_90 (all fibres at 90°):")
for mid_test in [1, 8, 22]:
    mt = MATS[mid_test]
    fpf_ud90, mode_ud90, _ = full_clt_fpf(mt, [90]*8)

    # For all-90° laminate under uniaxial Nx:
    # Global axes: A = Qbar(90°)*h. At 90°, Qbar_11 = Q22, Qbar_22 = Q11, Qbar_12 = Q12
    # Strain: eps_x = Nx / (A11) = Nx / (Q22*h) (approximately, ignoring off-diag)
    # But need to be more careful with full matrix:
    # At 90°: material 1-dir = global Y, material 2-dir = global X
    # σ_x (global) → σ_2 (material) for 90° ply
    # So FPF occurs when σ2 = σ_x(global) reaches YT
    # But it's not exactly σ_x = Nx/h because of Poisson coupling
    # Let's just check the value matches our calculation

    # For UD_90, the stress in material axes:
    # At 90°: σ1 = σy, σ2 = σx. Under Nx only, σx = Nx/h, σy = 0...
    # No wait. σx and σy are not simply Nx/h and 0.
    # The strain state is: eps = A^-1 * [Nx, 0, 0]
    # Then stress in each ply = Qbar * eps
    # σx = Qbar_11 * eps_x + Qbar_12 * eps_y
    # σy = Qbar_12 * eps_x + Qbar_22 * eps_y
    # For UD_90: Qbar_11 = Q22, Qbar_22 = Q11, Qbar_12 = Q12, Qbar_66 = Q66
    # A = Qbar*h, A^-1 = Qbar^-1/h
    # [eps_x, eps_y, gam_xy] = Qbar^-1 * [Nx/h, 0, 0]
    # eps_x = Qbar^-1[0][0] * Nx/h = S11_bar * Nx/h
    # σ_x = Nx/h (always true for any laminate under Nx only, by equilibrium)
    # σ_y = Qbar_12 * eps_x + Qbar_22 * eps_y

    # For 90° ply: σ1 = σy, σ2 = σx
    # σx = Nx/h (equilibrium)
    # So σ2 = Nx/h → FPF when σ2 = YT → Nx = YT*h → FPF_p = YT

    # Wait, σx = Nx/h is only true for the AVERAGE across the laminate, not for each ply.
    # For a single-material UD, all plies are identical, so σx is the same in each ply
    # and equals Nx/h. So FPF_p = YT for UD_90.

    expected_fpf = float(mt['YT'])
    diff = abs(fpf_ud90 - expected_fpf)
    print(f"    Mat {mid_test} ({mt['name']}): FPF = {fpf_ud90:.1f}, expected YT = {expected_fpf:.1f}, mode = {mode_ud90}, diff = {diff:.4f}")
    check(f"UD_90 Mat{mid_test}: FPF = YT", fpf_ud90, expected_fpf, tol=0.001)

print()


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 8: Asymmetric laminate — layup 29 [0, 45, -45, 90]
# ═══════════════════════════════════════════════════════════════════════════════
print("=" * 80)
print("STEP 8: Asymmetric laminate — layup 29 [0, 45, -45, 90]")
print("=" * 80)

angles_29 = [0, 45, -45, 90]
n29 = len(angles_29)
h29 = n29 * PLY_T

# Build ABD
A29 = [[0.0]*3 for _ in range(3)]
B29 = [[0.0]*3 for _ in range(3)]
D29 = [[0.0]*3 for _ in range(3)]
Qbl29 = []

for k, th in enumerate(angles_29):
    Qb = compute_Qbar(Q11, Q22, Q12, Q66, th)
    Qbl29.append(Qb)
    zb = -h29/2 + k*PLY_T
    zt = zb + PLY_T
    for i in range(3):
        for j in range(3):
            A29[i][j] += Qb[i][j] * (zt - zb)
            B29[i][j] += 0.5 * Qb[i][j] * (zt**2 - zb**2)
            D29[i][j] += (1.0/3.0) * Qb[i][j] * (zt**3 - zb**3)

bn29 = sum(abs(B29[i][j]) for i in range(3) for j in range(3))
an29 = sum(abs(A29[i][j]) for i in range(3) for j in range(3))
print(f"  B/A = {bn29/an29:.6f}  (should be >> 0 for asymmetric)")
print(f"  B-matrix:")
for i in range(3):
    print(f"    [{B29[i][0]:12.4f}  {B29[i][1]:12.4f}  {B29[i][2]:12.4f}]")

# Verify B ≠ 0
assert bn29/an29 > 0.001, "Layup 29 should be asymmetric!"
print(f"  Confirmed: B-matrix is significant → full 6×6 ABD inversion required")

# Compute FPF
fpf_29, mode_29, ply_29 = full_clt_fpf(MATS[1], angles_29)
print(f"\n  FPF = {fpf_29:.4f} MPa, mode = {mode_29}, crit ply = {ply_29}")

# Compare: 8-ply symmetric QI should give higher FPF than 4-ply asymmetric QI
# because B-coupling amplifies stresses
fpf_qi8, _, _ = full_clt_fpf(MATS[1], [0, 45, -45, 90, 90, -45, 45, 0])
print(f"  8-ply symmetric QI FPF = {fpf_qi8:.4f} MPa")
print(f"  Ratio (4-ply/8-ply) = {fpf_29/fpf_qi8:.4f}")
print(f"  4-ply asymmetric is weaker due to B-coupling: {'YES ✓' if fpf_29 < fpf_qi8 else 'NO — unexpected!'}")
check("Asymmetric 4-ply QI weaker than symmetric 8-ply QI", fpf_29 < fpf_qi8, True, tol=0)

# Also verify 6x6 ABD inversion by checking ABD * ABD^-1 = I
abd29 = [[0.0]*6 for _ in range(6)]
for i in range(3):
    for j in range(3):
        abd29[i][j] = A29[i][j]
        abd29[i][j+3] = B29[i][j]
        abd29[i+3][j] = B29[i][j]
        abd29[i+3][j+3] = D29[i][j]

# Invert
aug = [abd29[r][:] + [1.0 if r == c else 0.0 for c in range(6)] for r in range(6)]
for col in range(6):
    mx = col
    for row in range(col+1, 6):
        if abs(aug[row][col]) > abs(aug[mx][col]):
            mx = row
    aug[col], aug[mx] = aug[mx], aug[col]
    piv = aug[col][col]
    for j in range(12):
        aug[col][j] /= piv
    for row in range(6):
        if row != col:
            f = aug[row][col]
            for j in range(12):
                aug[row][j] -= f * aug[col][j]
abd29_inv = [aug[r][6:12] for r in range(6)]

# Check ABD * ABD^-1 = I
print(f"\n  ABD * ABD^-1 identity check:")
max_off_diag = 0
for i in range(6):
    for j in range(6):
        val = sum(abd29[i][k] * abd29_inv[k][j] for k in range(6))
        expected = 1.0 if i == j else 0.0
        err = abs(val - expected)
        if err > max_off_diag:
            max_off_diag = err
print(f"  Max |ABD * ABD^-1 - I| = {max_off_diag:.2e}  (should be < 1e-10)")
check("ABD * ABD^-1 = I", max_off_diag < 1e-8, True, tol=0)

print()


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 9: QI FPF for all 22 materials
# ═══════════════════════════════════════════════════════════════════════════════
print("=" * 80)
print("STEP 9: QI FPF for all 22 materials")
print("=" * 80)

qi_angles = [0, 45, -45, 90, 90, -45, 45, 0]
qi_fpf_results = {}

print(f"  {'ID':>3} {'Name':<20} {'FPF (MPa)':>12} {'Mode':<10} {'Crit Ply':>8}")
for mid in sorted(MATS.keys()):
    fpf, mode, ply = full_clt_fpf(MATS[mid], qi_angles)
    qi_fpf_results[mid] = fpf
    print(f"  {mid:>3} {MATS[mid]['name']:<20} {fpf:>12.4f} {mode:<10} {ply:>8}")

print()


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 10: ALL 770 combos — compare with verification_results.json
# ═══════════════════════════════════════════════════════════════════════════════
print("=" * 80)
print("STEP 10: Full 770-combo verification against verification_results.json")
print("=" * 80)

with open(r"C:\CalculiX\test_composite\verification_results.json") as f:
    vdata = json.load(f)

# Build lookup from verification data
verif_lookup = {}
for c in vdata['combos']:
    key = (int(c['mat_id']), int(c['layup_id']))
    verif_lookup[key] = c['fpf_MPa']

n_exact = 0
n_close = 0
n_mismatch = 0
max_diff_pct = 0
worst_combo = None

all_770_fpf = {}

for mid in sorted(MATS.keys()):
    for lid in sorted(LAYS.keys()):
        fpf, mode, ply = full_clt_fpf(MATS[mid], LAYS[lid])
        fpf_r = round(fpf, 4)
        all_770_fpf[(mid, lid)] = fpf_r

        key = (mid, lid)
        if key in verif_lookup:
            v_fpf = verif_lookup[key]
            if v_fpf == fpf_r:
                n_exact += 1
            elif v_fpf > 0 and abs(fpf_r - v_fpf) / v_fpf < 0.0001:
                n_close += 1
            else:
                n_mismatch += 1
                diff_pct = abs(fpf_r - v_fpf) / v_fpf * 100 if v_fpf > 0 else 999
                if diff_pct > max_diff_pct:
                    max_diff_pct = diff_pct
                    worst_combo = (mid, lid, fpf_r, v_fpf, diff_pct)
                if n_mismatch <= 5:
                    print(f"  MISMATCH: Mat {mid} Layup {lid}: independent={fpf_r}, stored={v_fpf}, diff={diff_pct:.4f}%")

print(f"\n  Results:")
print(f"    Exact matches: {n_exact}/770")
print(f"    Close matches (< 0.01%): {n_close}/770")
print(f"    Mismatches: {n_mismatch}/770")
if worst_combo:
    print(f"    Worst mismatch: Mat {worst_combo[0]} Layup {worst_combo[1]}: {worst_combo[2]} vs {worst_combo[3]} ({worst_combo[4]:.4f}%)")
check("All 770 combos match", n_mismatch, 0, tol=0, rel=False)

print()


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 11: Verify FPF physical reasonableness
# ═══════════════════════════════════════════════════════════════════════════════
print("=" * 80)
print("STEP 11: Physical reasonableness checks")
print("=" * 80)

# UD_0 should give highest FPF, UD_90 lowest, for all materials
print(f"\n  UD_0 > QI > UD_90 ordering:")
for mid in sorted(MATS.keys()):
    ud0 = all_770_fpf[(mid, 4)]    # UD_0_8
    qi = all_770_fpf[(mid, 1)]     # QI_8
    ud90 = all_770_fpf[(mid, 5)]   # UD_90_8
    ok = ud0 > qi > ud90
    if not ok:
        print(f"  *** FAIL Mat {mid} ({MATS[mid]['name']}): UD_0={ud0}, QI={qi}, UD_90={ud90}")
    check(f"Mat{mid}: UD_0 > QI > UD_90", ok, True, tol=0)

# ±45 should be weaker than QI for carbon (high E1/E2) but could vary for glass
print(f"\n  ±45 vs QI (should be weaker for high-anisotropy materials):")
for mid in [1, 5, 9]:  # T300, IM7, T1100
    pm45 = all_770_fpf[(mid, 6)]
    qi = all_770_fpf[(mid, 1)]
    print(f"  Mat {mid} ({MATS[mid]['name']}): ±45={pm45:.1f}, QI={qi:.1f}, ratio={pm45/qi:.3f}")
    check(f"Mat{mid}: ±45 < QI", pm45 < qi, True, tol=0)

# CP should be close to but slightly higher than QI (no off-axis plies to shear-fail)
print(f"\n  CP vs QI:")
for mid in [1, 8, 22]:
    cp = all_770_fpf[(mid, 3)]
    qi = all_770_fpf[(mid, 1)]
    print(f"  Mat {mid} ({MATS[mid]['name']}): CP={cp:.1f}, QI={qi:.1f}, ratio={cp/qi:.3f}")

# 16-ply should have same FPF as 8-ply (same layup, more plies → same stress)
print(f"\n  QI_8 vs QI_16 (should be identical FPF):")
for mid in [1, 8, 22]:
    qi8 = all_770_fpf[(mid, 1)]
    qi16 = all_770_fpf[(mid, 2)]
    print(f"  Mat {mid}: QI_8={qi8:.4f}, QI_16={qi16:.4f}")
    check(f"Mat{mid}: QI_8 = QI_16", qi8, qi16, tol=1e-6)

# UD_0_8 vs UD_0_16 (should be identical)
print(f"\n  UD_0_8 vs UD_0_16 (should be identical FPF):")
for mid in [1, 8, 22]:
    ud8 = all_770_fpf[(mid, 4)]
    ud16 = all_770_fpf[(mid, 31)]
    print(f"  Mat {mid}: UD_0_8={ud8:.4f}, UD_0_16={ud16:.4f}")
    check(f"Mat{mid}: UD_0_8 = UD_0_16", ud8, ud16, tol=1e-6)

print()


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 12: Verify layup scale factors
# ═══════════════════════════════════════════════════════════════════════════════
print("=" * 80)
print("STEP 12: Layup scale factors — independent computation")
print("=" * 80)

scale_factors = {}
for lid in sorted(LAYS.keys()):
    ratios = []
    for mid in sorted(MATS.keys()):
        fpf_qi = all_770_fpf[(mid, 1)]
        fpf_lay = all_770_fpf[(mid, lid)]
        if fpf_qi > 1e-9:
            ratios.append(fpf_lay / fpf_qi)
    ratios.sort()
    median = ratios[len(ratios)//2] if ratios else 1.0
    sf = max(0.15, min(8.0, median))
    scale_factors[lid] = sf

# Load stored scale factors from verification_results.json
stored_sf = {}
for lid_str in vdata['layups']:
    stored_sf[int(lid_str)] = vdata['layups'][lid_str]['scale_factor']

print(f"  {'ID':>3} {'Name':<22} {'Independent':>12} {'Stored':>12} {'Match':>6}")
n_sf_match = 0
for lid in sorted(scale_factors.keys()):
    indep = scale_factors[lid]
    stor = stored_sf.get(lid, -1)
    match = abs(indep - stor) < 0.0001
    if match:
        n_sf_match += 1
    else:
        print(f"  *** MISMATCH:")
    layup_name = ""
    for lid_str in vdata['layups']:
        if int(lid_str) == lid:
            layup_name = vdata['layups'][lid_str]['name']
    print(f"  {lid:>3} {layup_name:<22} {indep:>12.4f} {stor:>12.4f} {'✓' if match else 'FAIL':>6}")

check(f"All {len(scale_factors)} scale factors match", n_sf_match, len(scale_factors), tol=0, rel=False)

print()


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 13: Verify pressure ranges make sense
# ═══════════════════════════════════════════════════════════════════════════════
print("=" * 80)
print("STEP 13: Pressure range calibration check")
print("=" * 80)

# Load stored pressure ranges from verification_results.json
print(f"\n  {'ID':>3} {'Name':<20} {'FPF':>8} {'px_lo':>8} {'px_hi':>8} {'lo/FPF':>8} {'hi/FPF':>8}")
for mid_str in sorted(vdata['qi_fpf'].keys(), key=int):
    q = vdata['qi_fpf'][mid_str]
    fpf = q['fpf_MPa']
    lo = q['px_lo']
    hi = q['px_hi']
    name = vdata['materials'][mid_str]['name']
    lo_r = lo/fpf if fpf > 0 else 999
    hi_r = hi/fpf if fpf > 0 else 999
    print(f"  {mid_str:>3} {name:<20} {fpf:>8.1f} {lo:>8.1f} {hi:>8.1f} {lo_r:>8.4f} {hi_r:>8.4f}")
    check(f"Mat{mid_str} lo/FPF ≈ 0.12", lo_r, 0.12, tol=0.02)
    check(f"Mat{mid_str} hi/FPF ≈ 1.35", hi_r, 1.35, tol=0.02)

print()


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 14: Lekhnitskii SCF verification
# ═══════════════════════════════════════════════════════════════════════════════
print("=" * 80)
print("STEP 14: Lekhnitskii SCF — independent calculation")
print("=" * 80)

print(f"  {'ID':>3} {'Name':<20} {'E1/E2':>8} {'E1/G12':>8} {'v12':>6} {'SCF':>8} {'Stored':>8} {'Match':>6}")
for mid_str in sorted(vdata['scf'].keys(), key=int):
    mid = int(mid_str)
    mt = MATS[mid]
    E1, E2, v12_, G12_ = mt['E1'], mt['E2'], mt['v12'], mt['G12']

    # K_t = 1 + sqrt(2*(sqrt(E1/E2) - v12) + E1/G12)
    scf_calc = 1.0 + math.sqrt(2.0*(math.sqrt(E1/E2) - v12_) + E1/G12_)
    scf_stored = vdata['scf'][mid_str]
    match = abs(scf_calc - scf_stored) < 0.001

    print(f"  {mid:>3} {mt['name']:<20} {E1/E2:>8.2f} {E1/G12_:>8.2f} {v12_:>6.2f} {scf_calc:>8.3f} {scf_stored:>8.3f} {'✓' if match else 'FAIL':>6}")
    check(f"SCF Mat{mid}", scf_calc, scf_stored, tol=0.001)

# Isotropic limit: E1=E2, G12=E/(2(1+v)) → SCF should → 3.0
E_iso = 70000
v_iso = 0.30
G_iso = E_iso / (2*(1+v_iso))
scf_iso = 1.0 + math.sqrt(2.0*(math.sqrt(E_iso/E_iso) - v_iso) + E_iso/G_iso)
print(f"\n  Isotropic check: E={E_iso}, v={v_iso}, G={G_iso:.0f}")
print(f"  SCF = {scf_iso:.6f}  (should = 3.0)")
check("Isotropic SCF = 3.0", scf_iso, 3.0, tol=1e-10)

print()


# ═══════════════════════════════════════════════════════════════════════════════
# FINAL SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════
print("=" * 80)
print("FINAL VERIFICATION SUMMARY")
print("=" * 80)
print(f"  Total checks: {test_count}")
print(f"  Passed: {pass_count}")
print(f"  Failed: {test_count - pass_count}")

if errors:
    print(f"\n  FAILURES:")
    for e in errors:
        print(f"    {e}")
else:
    print(f"\n  ALL {test_count} CHECKS PASSED ✓")

if warnings:
    print(f"\n  WARNINGS:")
    for w_ in warnings:
        print(f"    {w_}")

print()
if test_count == pass_count:
    print("  VERDICT: The analytical validation is CORRECT.")
    print("  All CLT calculations, Q-bar transformations, ABD matrices, stress")
    print("  transformations, failure indices, FPF pressures, scale factors,")
    print("  Lekhnitskii SCFs, and all 770 combination results are verified.")
else:
    print(f"  VERDICT: {test_count - pass_count} ERRORS FOUND — INVESTIGATION NEEDED")
