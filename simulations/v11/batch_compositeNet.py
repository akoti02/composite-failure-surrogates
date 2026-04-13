"""
CompositeBench — 10M+ Open Composite Damage FEA Dataset Generator
Extends batch_100k.py to 22 materials, 35 layups, 4 BCs, 3 geometries.

Usage:
  python batch_compositeNet.py --materials 1-22 --layups 1-35 --bcs 1-4 \
      --geometry flat --mesh medium --sims-per-combo 1000 --workers 100 \
      --vm-id 1 --vm-total 20

  python batch_compositeNet.py --test 10  # local smoke test (10 sims)
"""

import subprocess
import os
import sys
import math
import random
import re
import csv
import time
import shutil
import argparse
import tempfile
import itertools
from multiprocessing import Pool, Lock

# File locking: fcntl on Linux (campaign target), msvcrt on Windows (local testing)
try:
    import fcntl
    def _lock_file(f):
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
    def _unlock_file(f):
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
except ImportError:
    import msvcrt
    def _lock_file(f):
        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
    def _unlock_file(f):
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)

# Fail fast if scipy is missing (used for LHS sampling)
try:
    from scipy.stats.qmc import LatinHypercube  # noqa: F401
except ImportError:
    print("ERROR: scipy is required. Install with: pip install scipy", file=sys.stderr)
    sys.exit(1)

# Optional: h5py for full-field per-element output
try:
    import h5py
    import numpy as np
    HAS_HDF5 = True
except ImportError:
    HAS_HDF5 = False

# Force UTF-8 on Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# =============================================================================
# Constants
# =============================================================================
PLATE_L = 100.0
PLATE_W = 50.0
MAX_DEFECTS = 5
MAX_PLACEMENT_ATTEMPTS = 200
MIN_CRACK_WIDTH = 0.15

CRACK_SEG_LEN_MIN = 0.2
CRACK_SEG_LEN_MAX = 0.8
MAX_ANGLE_DEV_DEG = 45.0
MIN_POLYGON_SEGMENTS = 12

# Auto-detect platform
if sys.platform == 'win32':
    CCX_EXE = r"C:\CalculiX\calculix_2.23_4win\ccx_static.exe"
    CCX_UMAT_EXE = r"C:\CalculiX\calculix_2.21_umat\ccx_2.21.exe"
    WORK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "compositeNet_sims")
else:
    CCX_EXE = "/usr/bin/ccx"
    CCX_UMAT_EXE = os.path.expanduser("~/ccx_umat/CalculiX/ccx_2.21/src/ccx_2.21")
    WORK_DIR = os.path.expanduser("~/sims")

# -----------------------------------------------------------------------------
# 2.5 Solver dispatch
# -----------------------------------------------------------------------------
# Task #18 (dispatch infrastructure): every sample carries a ``solver`` string
# that routes it to one of three backends. In this first revision of the
# dispatcher only solvers 1 (stock CCX, static linear) and 2 (CCX + Hashin
# fatigue UMAT, static nonlinear with damage softening) are fully wired. The
# OR and Code_Aster paths return an explicit NOT_IMPLEMENTED error row so the
# CSV still has a valid failure mark and the failure-rate watchdog treats
# them correctly; they are kept as extension points for follow-up work.
#
# NOTE: Plate-with-cracks in Code_Aster makes little physical sense for a
# mid-plane-damage study — Aster's role in the V11 suite is delamination
# coupons (DCB/ENF/MMB), which run through ``phaseB_dcb_aster.py`` outside
# this batch. The Aster entry here exists purely so --solvers=3 is a valid
# CLI value and the CSV can record "solver_aster" rows as rejected.
SOLVERS = {
    1: "ccx_stock",
    2: "ccx_umat",
    3: "or",
    4: "aster",
}
DEFAULT_SOLVER_ID = 1

SOLVER_TIMEOUT = 300          # stock CCX (linear static) — fast path
UMAT_SOLVER_TIMEOUT = 1800    # CCX+UMAT nonlinear with damage softening — slow
SAVE_HDF5 = False  # Set via --hdf5 flag; requires h5py + numpy
HDF5_PATH = None   # Path to the shared HDF5 file
CRACK_SEARCH_BUFFER = 5.0
NUM_WORKERS = 100
BACKUP_INTERVAL = 500
MAX_FAIL_RATE = 0.20
MIN_SIMS_FOR_FAIL_CHECK = 200

# =============================================================================
# 2.1 Material Library — 22 systems
# Properties: E1, E2 (MPa), G12 (MPa), v12, XT, XC, YT, YC, SL (MPa)
# =============================================================================
MATERIALS = {
    # v23: transverse Poisson's ratio. For CFRP ~0.40-0.50; glass ~0.35-0.40; natural ~0.35; aramid ~0.40
    1:  {"name": "T300/5208",       "E1": 135000, "E2": 10000, "G12": 5200,  "v12": 0.27, "v23": 0.43, "XT": 1500, "XC": 1200, "YT": 50,  "YC": 250, "SL": 70,  "source": "MIL-HDBK-17"},
    2:  {"name": "T300/914",        "E1": 138000, "E2": 8900,  "G12": 5600,  "v12": 0.30, "v23": 0.43, "XT": 1500, "XC": 1200, "YT": 62,  "YC": 200, "SL": 79,  "source": "Soden 1998"},
    3:  {"name": "T700/Epoxy",      "E1": 132000, "E2": 9000,  "G12": 5000,  "v12": 0.30, "v23": 0.45, "XT": 2150, "XC": 1470, "YT": 55,  "YC": 185, "SL": 90,  "source": "Toray"},
    4:  {"name": "T800S/Epoxy",     "E1": 163000, "E2": 8700,  "G12": 5500,  "v12": 0.32, "v23": 0.45, "XT": 2900, "XC": 1490, "YT": 64,  "YC": 197, "SL": 98,  "source": "Toray"},
    5:  {"name": "IM7/8552",        "E1": 171400, "E2": 9080,  "G12": 5290,  "v12": 0.32, "v23": 0.45, "XT": 2326, "XC": 1200, "YT": 62,  "YC": 200, "SL": 92,  "source": "Hexcel/Camanho2006"},
    6:  {"name": "AS4/3501-6",      "E1": 140000, "E2": 10000, "G12": 7000,  "v12": 0.29, "v23": 0.42, "XT": 2200, "XC": 1700, "YT": 60,  "YC": 200, "SL": 100, "source": "MIL-HDBK-17"},
    7:  {"name": "AS4/8552",        "E1": 135000, "E2": 9500,  "G12": 5000,  "v12": 0.30, "v23": 0.44, "XT": 2023, "XC": 1234, "YT": 81,  "YC": 200, "SL": 114, "source": "Hexcel"},
    8:  {"name": "E-glass/Epoxy",   "E1": 39000,  "E2": 8600,  "G12": 3800,  "v12": 0.28, "v23": 0.37, "XT": 1000, "XC": 700,  "YT": 40,  "YC": 120, "SL": 70,  "source": "Daniel&Ishai"},
    9:  {"name": "T1100/Epoxy",     "E1": 324000, "E2": 8000,  "G12": 5500,  "v12": 0.30, "v23": 0.46, "XT": 3100, "XC": 1500, "YT": 50,  "YC": 200, "SL": 80,  "source": "Toray T1100G"},
    10: {"name": "HTS40/Epoxy",     "E1": 135000, "E2": 9500,  "G12": 4500,  "v12": 0.30, "v23": 0.44, "XT": 2000, "XC": 1300, "YT": 55,  "YC": 200, "SL": 85,  "source": "Toho Tenax"},
    11: {"name": "S2-glass/Epoxy",  "E1": 55000,  "E2": 16000, "G12": 7600,  "v12": 0.26, "v23": 0.35, "XT": 1700, "XC": 1150, "YT": 60,  "YC": 180, "SL": 75,  "source": "AGY"},
    12: {"name": "Kevlar49/Epoxy",  "E1": 80000,  "E2": 5500,  "G12": 2200,  "v12": 0.34, "v23": 0.40, "XT": 1400, "XC": 335,  "YT": 30,  "YC": 158, "SL": 49,  "source": "DuPont/Barbero"},
    13: {"name": "T300/PEEK",       "E1": 134000, "E2": 10100, "G12": 5500,  "v12": 0.28, "v23": 0.43, "XT": 2130, "XC": 1100, "YT": 80,  "YC": 200, "SL": 120, "source": "Soutis 1993"},
    14: {"name": "AS4/PEKK",        "E1": 138000, "E2": 10300, "G12": 5500,  "v12": 0.31, "v23": 0.43, "XT": 2070, "XC": 1360, "YT": 86,  "YC": 215, "SL": 110, "source": "Hexcel HexPly"},
    15: {"name": "Flax/Epoxy",      "E1": 35000,  "E2": 5500,  "G12": 3000,  "v12": 0.30, "v23": 0.35, "XT": 350,  "XC": 150,  "YT": 25,  "YC": 100, "SL": 40,  "source": "Baley 2012"},
    16: {"name": "Basalt/Epoxy",    "E1": 45000,  "E2": 12000, "G12": 5000,  "v12": 0.26, "v23": 0.36, "XT": 1100, "XC": 800,  "YT": 45,  "YC": 140, "SL": 65,  "source": "Fiore 2015"},
    17: {"name": "M55J/Epoxy",      "E1": 340000, "E2": 7000,  "G12": 5000,  "v12": 0.28, "v23": 0.46, "XT": 1800, "XC": 900,  "YT": 40,  "YC": 180, "SL": 65,  "source": "Toray UHM"},
    18: {"name": "T650/Cycom",      "E1": 152000, "E2": 8700,  "G12": 4800,  "v12": 0.31, "v23": 0.44, "XT": 2400, "XC": 1500, "YT": 65,  "YC": 240, "SL": 95,  "source": "Solvay"},
    19: {"name": "IM10/Epoxy",      "E1": 190000, "E2": 9000,  "G12": 5600,  "v12": 0.31, "v23": 0.45, "XT": 3100, "XC": 1600, "YT": 60,  "YC": 210, "SL": 90,  "source": "Hexcel IM10"},
    20: {"name": "Carbon/BMI",      "E1": 155000, "E2": 8500,  "G12": 5000,  "v12": 0.30, "v23": 0.44, "XT": 2000, "XC": 1400, "YT": 55,  "YC": 200, "SL": 80,  "source": "Cytec 5250"},
    21: {"name": "HM-CFRP",         "E1": 230000, "E2": 6500,  "G12": 4500,  "v12": 0.25, "v23": 0.46, "XT": 1200, "XC": 700,  "YT": 35,  "YC": 170, "SL": 55,  "source": "Generic HM"},
    22: {"name": "Jute/Polyester",  "E1": 20000,  "E2": 5000,  "G12": 2500,  "v12": 0.30, "v23": 0.35, "XT": 200,  "XC": 100,  "YT": 20,  "YC": 80,  "SL": 30,  "source": "Wambua 2003"},
}

# =============================================================================
# 2.2 Layup Library — 35 configurations
# =============================================================================
LAYUPS = {
    # --- Canonical (1-12) ---
    1:  {"name": "QI_8",           "angles": [0, 45, -45, 90, 90, -45, 45, 0]},
    2:  {"name": "QI_16",          "angles": [0, 45, -45, 90, 0, 45, -45, 90, 90, -45, 45, 0, 90, -45, 45, 0]},
    3:  {"name": "CP_8",           "angles": [0, 90, 0, 90, 90, 0, 90, 0]},
    4:  {"name": "UD_0_8",         "angles": [0]*8},
    5:  {"name": "UD_90_8",        "angles": [90]*8},
    6:  {"name": "Angle_pm45_4s",  "angles": [45, -45, 45, -45, -45, 45, -45, 45]},
    7:  {"name": "Angle_pm30_4s",  "angles": [30, -30, 30, -30, -30, 30, -30, 30]},
    8:  {"name": "Angle_pm60_4s",  "angles": [60, -60, 60, -60, -60, 60, -60, 60]},
    9:  {"name": "Soft_QI",        "angles": [45, 0, -45, 90, 90, -45, 0, 45]},
    10: {"name": "Hard_QI",        "angles": [0, 0, 45, -45, -45, 45, 0, 0]},
    11: {"name": "UD_45_8",        "angles": [45]*8},
    12: {"name": "Balanced_0_90",  "angles": [0, 90, 90, 0, 0, 90, 90, 0]},
    # --- Industry (13-20) ---
    13: {"name": "Skin_25_50_25",  "angles": [45, -45, 0, 0, 90, 0, 0, -45, 45, 45, -45, 0, 0, 90, 0, 0, -45, 45]},
    14: {"name": "Spar_10_80_10",  "angles": [45, -45, 45, -45, 45, -45, 45, -45, -45, 45, -45, 45, -45, 45, -45, 45]},
    15: {"name": "Fuselage_QI12",  "angles": [0, 45, 90, -45, 0, 45, 45, 0, -45, 90, 45, 0]},
    16: {"name": "Wing_biased",    "angles": [0, 0, 45, -45, 0, 90, 0, -45, 45, 0, 0, 45, -45, 0, 90, 0, -45, 45, 0, 0]},
    17: {"name": "Pressure_vessel", "angles": [55, -55, 55, -55, -55, 55, -55, 55]},
    18: {"name": "Pipe_pm75",      "angles": [75, -75, 75, -75, -75, 75, -75, 75]},
    19: {"name": "DD_20_70",       "angles": [20, 70, -20, -70, -70, -20, 70, 20]},
    20: {"name": "DD_25_65",       "angles": [25, 65, -25, -65, -65, -25, 65, 25]},
    # --- Parametric / edge cases (21-35) ---
    21: {"name": "Angle_pm10_4s",  "angles": [10, -10, 10, -10, -10, 10, -10, 10]},
    22: {"name": "Angle_pm15_4s",  "angles": [15, -15, 15, -15, -15, 15, -15, 15]},
    23: {"name": "Angle_pm20_4s",  "angles": [20, -20, 20, -20, -20, 20, -20, 20]},
    24: {"name": "Balanced_QI_var", "angles": [0, 90, 45, -45, -45, 45, 90, 0]},
    25: {"name": "Asym_0_30_60_90","angles": [0, 30, 60, 90, 0, 30, 60, 90]},
    26: {"name": "Asym_15_45_75",  "angles": [15, 45, 75, 15, 45, 75, 15, 45]},
    27: {"name": "Thick_QI_24",    "angles": [0,45,-45,90]*3 + [90,-45,45,0]*3},
    28: {"name": "Thick_CP_24",    "angles": [0,90]*6 + [90,0]*6},
    29: {"name": "Thin_4ply_QI",   "angles": [0, 45, -45, 90]},
    30: {"name": "Thin_4ply_CP",   "angles": [0, 90, 90, 0]},
    31: {"name": "UD_0_16",        "angles": [0]*16},
    32: {"name": "Mixed_0_pm30_90","angles": [0, 30, -30, 90, 90, -30, 30, 0]},
    33: {"name": "Mixed_0_pm60_90","angles": [0, 60, -60, 90, 90, -60, 60, 0]},
    34: {"name": "Near_UD_pm15",   "angles": [0, 15, -15, 0, 0, -15, 15, 0]},
    35: {"name": "Sandwich_core",  "angles": [0, 45, -45, 90, 90, 90, 90, 90, 90, -45, 45, 0]},
}

# =============================================================================
# 2.4 Boundary Condition Modes
# =============================================================================
BC_MODES = {
    1: "biaxial",            # px on RIGHT, py on TOP/BOTTOM
    2: "tension_comp",       # px on RIGHT, -py on TOP/BOTTOM
    3: "uniaxial_shear",     # px on RIGHT, shear via X-force on TOP
    4: "pure_compression",   # -px on RIGHT, fibre-compression dominated
    5: "buckle_comp",        # compressive reference load + CCX *BUCKLE eigenvalue extraction
    # Mode "pure_shear" was removed: left edge only constrains X-displacement,
    # so a shear couple produces rigid-body rotation artifacts, not a clean shear state.
}

# Number of buckling eigenvalues requested in mode 5.
N_BUCKLE_EIGENVALUES = 4

# =============================================================================
# 2.9 Multi-Fidelity Mesh Control
# =============================================================================
MESH_CONFIGS = {
    "coarse": {"CharLenMax": 5.0, "CharLenMin": 1.0, "CrackSizeMin": 1.0},
    "medium": {"CharLenMax": 3.0, "CharLenMin": 0.5, "CrackSizeMin": 0.5},
    "fine":   {"CharLenMax": 1.5, "CharLenMin": 0.3, "CrackSizeMin": 0.3},
}

# =============================================================================
# Sampling ranges
# =============================================================================
GLOBAL_RANGES = {
    'pressure_x_frac': [0.0,  1.0],   # normalised fraction, scaled per material/layup
    'pressure_y_frac': [0.0,  1.0],   # normalised fraction, scaled per material/layup
    'ply_thickness':   [0.15, 0.15],  # Fixed at reference value (CLT FPF uses 0.15)
}

DEFECT_RANGES = {
    'x':           [15.0, 85.0],
    'y':           [10.0, 40.0],
    'half_length': [4.0,  15.0],
    'width':       [0.15, 0.6],
    'angle':       [0.0,  180.0],
    'roughness':   [0.15, 0.90],
}

# Cutout-specific ranges (for geometry='cutout')
CUTOUT_RANGES = {
    'hole_diameter': [5.0, 20.0],
    'hole_x_frac':   [0.2, 0.8],  # fraction of plate length (inner 60%)
    'hole_y_frac':   [0.2, 0.8],  # fraction of plate width
}

# Curved panel ranges (for geometry='curved')
CURVED_RANGES = {
    'radius': [200.0, 500.0],  # Min 200mm: θ_max≈0.5rad (29°), within shell theory validity
}

# =============================================================================
# Per-material pressure ranges — computed dynamically from CLT FPF
# Placeholder; actual values set after _clt_fpf_uniaxial_x is defined (see below)
# =============================================================================
MATERIAL_PRESSURE_RANGES = {}

# =============================================================================
# CLT-based FPF computation for per-layup pressure scaling
# =============================================================================
def _clt_fpf_uniaxial_x(mat, angles):
    """Compute first-ply-failure pressure (MPa) under uniaxial X-tension.

    Uses full Classical Lamination Theory with ABD matrix:
    1. Build A, B, D matrices from transformed reduced stiffness
    2. For symmetric laminates (B≈0): eps = A^-1 * N
    3. For asymmetric laminates (B≠0): full 6×6 [ABD]^-1 * [N, M]
       (bending-extension coupling amplifies ply stresses)
    4. Compute ply stresses at each z-location in material axes
    5. Check max-stress failure → FPF = 1/max(failure_index)

    Edge loading: Nx = pressure * h_total → FPF_pressure = FPF_Nx / h_total
    """
    E1 = float(mat['E1'])
    E2 = float(mat['E2'])
    v12 = float(mat['v12'])
    G12 = float(mat['G12'])
    XT = float(mat['XT'])
    XC = float(mat['XC'])
    YT = float(mat['YT'])
    YC = float(mat['YC'])
    SL = float(mat['SL'])

    v21 = v12 * E2 / E1
    dd = 1.0 - v12 * v21
    Q11 = E1 / dd
    Q22 = E2 / dd
    Q12 = v12 * E2 / dd
    Q66 = G12

    n_plies = len(angles)
    t_ply = 0.15  # reference ply thickness

    # Build ABD matrices (A=membrane, B=coupling, D=bending)
    h_total = n_plies * t_ply
    A = [[0.0]*3 for _ in range(3)]
    B = [[0.0]*3 for _ in range(3)]
    D = [[0.0]*3 for _ in range(3)]

    # Pre-compute Q-bar for each ply (store for reuse in stress calc)
    Qbar_list = []
    for k, theta_deg in enumerate(angles):
        t = math.radians(theta_deg)
        c = math.cos(t)
        s = math.sin(t)
        c2, s2, cs = c*c, s*s, c*s

        Qb11 = Q11*c2*c2 + 2*(Q12 + 2*Q66)*c2*s2 + Q22*s2*s2
        Qb22 = Q11*s2*s2 + 2*(Q12 + 2*Q66)*c2*s2 + Q22*c2*c2
        Qb12 = (Q11 + Q22 - 4*Q66)*c2*s2 + Q12*(c2*c2 + s2*s2)
        Qb16 = (Q11 - Q12 - 2*Q66)*c2*cs + (Q12 - Q22 + 2*Q66)*s2*cs
        Qb26 = (Q11 - Q12 - 2*Q66)*cs*s2 + (Q12 - Q22 + 2*Q66)*cs*c2
        Qb66 = (Q11 + Q22 - 2*Q12 - 2*Q66)*c2*s2 + Q66*(c2*c2 + s2*s2)
        Qb = [[Qb11, Qb12, Qb16], [Qb12, Qb22, Qb26], [Qb16, Qb26, Qb66]]
        Qbar_list.append(Qb)

        z_bot = -h_total/2 + k * t_ply
        z_top = z_bot + t_ply
        for i in range(3):
            for j in range(3):
                A[i][j] += Qb[i][j] * (z_top - z_bot)
                B[i][j] += 0.5 * Qb[i][j] * (z_top**2 - z_bot**2)
                D[i][j] += (1.0/3.0) * Qb[i][j] * (z_top**3 - z_bot**3)

    # Check if B-matrix is significant (asymmetric laminate)
    b_norm = sum(abs(B[i][j]) for i in range(3) for j in range(3))
    a_norm = sum(abs(A[i][j]) for i in range(3) for j in range(3))
    is_symmetric = b_norm < 0.001 * a_norm

    if is_symmetric:
        # Simple A-matrix inversion: eps = A^-1 * [Nx, 0, 0]
        a, b, c = A[0]
        d, e, f = A[1]
        g, h, k = A[2]
        det = a*(e*k - f*h) - b*(d*k - f*g) + c*(d*h - e*g)
        if abs(det) < 1e-30:
            return 100.0
        inv_det = 1.0 / det
        # Only need first column of A^-1 (for Nx=1)
        eps_x = (e*k - f*h) * inv_det
        eps_y = (f*g - d*k) * inv_det
        gam_xy = (d*h - e*g) * inv_det
        kap_x = kap_y = kap_xy = 0.0
    else:
        # Full 6×6 ABD inversion for asymmetric laminates
        abd = [[0.0]*6 for _ in range(6)]
        for i in range(3):
            for j in range(3):
                abd[i][j] = A[i][j]
                abd[i][j+3] = B[i][j]
                abd[i+3][j] = B[i][j]
                abd[i+3][j+3] = D[i][j]
        # Gauss-Jordan elimination
        aug = [abd[r][:] + [1.0 if r == c else 0.0 for c in range(6)] for r in range(6)]
        for col in range(6):
            max_row = col
            for row in range(col+1, 6):
                if abs(aug[row][col]) > abs(aug[max_row][col]):
                    max_row = row
            aug[col], aug[max_row] = aug[max_row], aug[col]
            if abs(aug[col][col]) < 1e-30:
                return 100.0
            pivot = aug[col][col]
            for j in range(12):
                aug[col][j] /= pivot
            for row in range(6):
                if row != col:
                    factor = aug[row][col]
                    for j in range(12):
                        aug[row][j] -= factor * aug[col][j]
        abd_inv = [aug[r][6:12] for r in range(6)]
        # Response to unit Nx: [eps0, kappa] = abd_inv * [1, 0, 0, 0, 0, 0]
        eps_x = abd_inv[0][0]
        eps_y = abd_inv[1][0]
        gam_xy = abd_inv[2][0]
        kap_x = abd_inv[3][0]
        kap_y = abd_inv[4][0]
        kap_xy = abd_inv[5][0]

    # Check failure in each ply (at ply mid-plane z)
    max_fi = 0.0
    for pk, theta_deg in enumerate(angles):
        z_bot = -h_total/2 + pk * t_ply
        z_mid = z_bot + t_ply / 2.0

        # Total strain at ply mid-plane
        ex = eps_x + z_mid * kap_x
        ey = eps_y + z_mid * kap_y
        gxy = gam_xy + z_mid * kap_xy

        # Global stress = Q-bar × strain
        Qb = Qbar_list[pk]
        sig_x = Qb[0][0]*ex + Qb[0][1]*ey + Qb[0][2]*gxy
        sig_y = Qb[0][1]*ex + Qb[1][1]*ey + Qb[1][2]*gxy
        tau_xy = Qb[0][2]*ex + Qb[1][2]*ey + Qb[2][2]*gxy

        # Transform to material axes
        t = math.radians(theta_deg)
        cc = math.cos(t)
        ss = math.sin(t)
        sig_1 = sig_x*cc*cc + sig_y*ss*ss + 2*tau_xy*cc*ss
        sig_2 = sig_x*ss*ss + sig_y*cc*cc - 2*tau_xy*cc*ss
        sig_12 = -sig_x*cc*ss + sig_y*cc*ss + tau_xy*(cc*cc - ss*ss)

        # Max-stress failure index
        fi_1 = sig_1 / XT if sig_1 >= 0 else abs(sig_1) / XC
        fi_2 = sig_2 / YT if sig_2 >= 0 else abs(sig_2) / YC
        fi_12 = abs(sig_12) / SL if SL > 0 else 0.0
        fi = max(fi_1, fi_2, fi_12)
        if fi > max_fi:
            max_fi = fi

    if max_fi < 1e-15:
        return 1e6

    fpf_Nx = 1.0 / max_fi
    total_t = n_plies * t_ply
    fpf_pressure = fpf_Nx / total_t
    return fpf_pressure


def _clt_fpf_uniaxial_y(mat, angles):
    """Compute first-ply-failure pressure (MPa) under uniaxial Y-tension.

    Same CLT approach as _clt_fpf_uniaxial_x but applies Ny=1 instead of Nx=1.
    Uses column 1 of A^-1 (or abd^-1) instead of column 0.
    """
    E1 = float(mat['E1'])
    E2 = float(mat['E2'])
    v12 = float(mat['v12'])
    G12 = float(mat['G12'])
    XT = float(mat['XT'])
    XC = float(mat['XC'])
    YT = float(mat['YT'])
    YC = float(mat['YC'])
    SL = float(mat['SL'])

    v21 = v12 * E2 / E1
    dd = 1.0 - v12 * v21
    Q11 = E1 / dd
    Q22 = E2 / dd
    Q12 = v12 * E2 / dd
    Q66 = G12

    n_plies = len(angles)
    t_ply = 0.15

    h_total = n_plies * t_ply
    A = [[0.0]*3 for _ in range(3)]
    B = [[0.0]*3 for _ in range(3)]
    D = [[0.0]*3 for _ in range(3)]

    Qbar_list = []
    for k, theta_deg in enumerate(angles):
        t = math.radians(theta_deg)
        c = math.cos(t)
        s = math.sin(t)
        c2, s2, cs = c*c, s*s, c*s

        Qb11 = Q11*c2*c2 + 2*(Q12 + 2*Q66)*c2*s2 + Q22*s2*s2
        Qb22 = Q11*s2*s2 + 2*(Q12 + 2*Q66)*c2*s2 + Q22*c2*c2
        Qb12 = (Q11 + Q22 - 4*Q66)*c2*s2 + Q12*(c2*c2 + s2*s2)
        Qb16 = (Q11 - Q12 - 2*Q66)*c2*cs + (Q12 - Q22 + 2*Q66)*s2*cs
        Qb26 = (Q11 - Q12 - 2*Q66)*cs*s2 + (Q12 - Q22 + 2*Q66)*cs*c2
        Qb66 = (Q11 + Q22 - 2*Q12 - 2*Q66)*c2*s2 + Q66*(c2*c2 + s2*s2)
        Qb = [[Qb11, Qb12, Qb16], [Qb12, Qb22, Qb26], [Qb16, Qb26, Qb66]]
        Qbar_list.append(Qb)

        z_bot = -h_total/2 + k * t_ply
        z_top = z_bot + t_ply
        for i in range(3):
            for j in range(3):
                A[i][j] += Qb[i][j] * (z_top - z_bot)
                B[i][j] += 0.5 * Qb[i][j] * (z_top**2 - z_bot**2)
                D[i][j] += (1.0/3.0) * Qb[i][j] * (z_top**3 - z_bot**3)

    b_norm = sum(abs(B[i][j]) for i in range(3) for j in range(3))
    a_norm = sum(abs(A[i][j]) for i in range(3) for j in range(3))
    is_symmetric = b_norm < 0.001 * a_norm

    if is_symmetric:
        # A^-1: need column 1 (response to Ny=1)
        a, b, c = A[0]
        d, e, f = A[1]
        g, h, k = A[2]
        det = a*(e*k - f*h) - b*(d*k - f*g) + c*(d*h - e*g)
        if abs(det) < 1e-30:
            return 100.0
        inv_det = 1.0 / det
        # Column 1 of A^-1 (cofactors of row 1)
        eps_x = (c*h - b*k) * inv_det
        eps_y = (a*k - c*g) * inv_det
        gam_xy = (b*g - a*h) * inv_det
        kap_x = kap_y = kap_xy = 0.0
    else:
        abd = [[0.0]*6 for _ in range(6)]
        for i in range(3):
            for j in range(3):
                abd[i][j] = A[i][j]
                abd[i][j+3] = B[i][j]
                abd[i+3][j] = B[i][j]
                abd[i+3][j+3] = D[i][j]
        aug = [abd[r][:] + [1.0 if r == c else 0.0 for c in range(6)] for r in range(6)]
        for col in range(6):
            max_row = col
            for row in range(col+1, 6):
                if abs(aug[row][col]) > abs(aug[max_row][col]):
                    max_row = row
            aug[col], aug[max_row] = aug[max_row], aug[col]
            if abs(aug[col][col]) < 1e-30:
                return 100.0
            pivot = aug[col][col]
            for j in range(12):
                aug[col][j] /= pivot
            for row in range(6):
                if row != col:
                    factor = aug[row][col]
                    for j in range(12):
                        aug[row][j] -= factor * aug[col][j]
        abd_inv = [aug[r][6:12] for r in range(6)]
        # Column 1: response to unit Ny
        eps_x = abd_inv[0][1]
        eps_y = abd_inv[1][1]
        gam_xy = abd_inv[2][1]
        kap_x = abd_inv[3][1]
        kap_y = abd_inv[4][1]
        kap_xy = abd_inv[5][1]

    max_fi = 0.0
    for pk, theta_deg in enumerate(angles):
        z_bot = -h_total/2 + pk * t_ply
        z_mid = z_bot + t_ply / 2.0

        ex = eps_x + z_mid * kap_x
        ey = eps_y + z_mid * kap_y
        gxy = gam_xy + z_mid * kap_xy

        Qb = Qbar_list[pk]
        sig_x = Qb[0][0]*ex + Qb[0][1]*ey + Qb[0][2]*gxy
        sig_y = Qb[0][1]*ex + Qb[1][1]*ey + Qb[1][2]*gxy
        tau_xy = Qb[0][2]*ex + Qb[1][2]*ey + Qb[2][2]*gxy

        t = math.radians(theta_deg)
        cc = math.cos(t)
        ss = math.sin(t)
        sig_1 = sig_x*cc*cc + sig_y*ss*ss + 2*tau_xy*cc*ss
        sig_2 = sig_x*ss*ss + sig_y*cc*cc - 2*tau_xy*cc*ss
        sig_12 = -sig_x*cc*ss + sig_y*cc*ss + tau_xy*(cc*cc - ss*ss)

        fi_1 = sig_1 / XT if sig_1 >= 0 else abs(sig_1) / XC
        fi_2 = sig_2 / YT if sig_2 >= 0 else abs(sig_2) / YC
        fi_12 = abs(sig_12) / SL if SL > 0 else 0.0
        fi = max(fi_1, fi_2, fi_12)
        if fi > max_fi:
            max_fi = fi

    if max_fi < 1e-15:
        return 1e6

    fpf_Ny = 1.0 / max_fi
    total_t = n_plies * t_ply
    fpf_pressure = fpf_Ny / total_t
    return fpf_pressure


def _compute_layup_scale_factors():
    """Compute FPF(material, layup) / FPF(material, QI) for all combos.

    Uses CLT FPF under uniaxial X-tension. The scale factor is averaged
    across all 22 materials to get a material-independent layup factor.
    """
    qi_angles = LAYUPS[1]['angles']
    scales = {}

    for lid, layup in LAYUPS.items():
        ratios = []
        for mid, mat in MATERIALS.items():
            fpf_qi = _clt_fpf_uniaxial_x(mat, qi_angles)
            fpf_layup = _clt_fpf_uniaxial_x(mat, layup['angles'])
            if fpf_qi > 1e-9:
                ratios.append(fpf_layup / fpf_qi)
        # Use median ratio across materials (robust to outliers)
        ratios.sort()
        median = ratios[len(ratios) // 2] if ratios else 1.0
        # Clamp to prevent extreme pressure scaling.
        # SCF at defect tips varies much less by layup than CLT FPF does,
        # so narrow the scale range to keep all layups well-calibrated.
        scales[lid] = max(0.4, min(3.0, median))
    return scales

LAYUP_SCALE_FACTORS = _compute_layup_scale_factors()


def _compute_material_pressure_ranges():
    """Compute per-material pressure ranges from CLT FPF on QI layup.

    Defect stress concentration reduces effective FPF by ~7×.
    px_lo = 0.02 × FPF  (~2% of CLT FPF — minimal load)
    px_hi = 0.35 × FPF  (~35% of CLT FPF — well above defect-SCF failure)
    Calibrated against V10 T300/5208: 5-100 MPa with FPF≈285 MPa → 2%-35%.
    """
    qi_angles = LAYUPS[1]['angles']
    ranges = {}
    for mid, mat in MATERIALS.items():
        fpf = _clt_fpf_uniaxial_x(mat, qi_angles)
        lo = round(fpf * 0.02, 1)
        hi = round(fpf * 0.35, 1)
        ranges[mid] = (lo, hi)
    return ranges


MATERIAL_PRESSURE_RANGES = _compute_material_pressure_ranges()


def _compute_material_pressure_ranges_y():
    """Compute per-material Y-pressure ranges from CLT FPF under uniaxial Y-tension.

    Same SCF-adjusted fractions as X-direction.
    """
    qi_angles = LAYUPS[1]['angles']
    ranges = {}
    for mid, mat in MATERIALS.items():
        fpf = _clt_fpf_uniaxial_y(mat, qi_angles)
        lo = round(fpf * 0.02, 1)
        hi = round(fpf * 0.35, 1)
        ranges[mid] = (lo, hi)
    return ranges


MATERIAL_PRESSURE_RANGES_Y = _compute_material_pressure_ranges_y()


def _compute_layup_scale_factors_y():
    """Compute Y-direction layup scale factors: FPF_Y(layup) / FPF_Y(QI)."""
    qi_angles = LAYUPS[1]['angles']
    scales = {}
    for lid, layup in LAYUPS.items():
        ratios = []
        for mid, mat in MATERIALS.items():
            fpf_qi = _clt_fpf_uniaxial_y(mat, qi_angles)
            fpf_layup = _clt_fpf_uniaxial_y(mat, layup['angles'])
            if fpf_qi > 1e-9:
                ratios.append(fpf_layup / fpf_qi)
        ratios.sort()
        median = ratios[len(ratios)//2] if ratios else 1.0
        scales[lid] = max(0.4, min(3.0, median))
    return scales


LAYUP_SCALE_FACTORS_Y = _compute_layup_scale_factors_y()


# Per-material cutout pressure reduction factors
# Based on Lekhnitskii (1968) orthotropic SCF: K_t = 1 + sqrt(2(sqrt(E1/E2)-v12) + E1/G12)
# For a QI laminate, effective properties are near-isotropic → SCF ≈ 3
# Factor = 1 / (SCF_QI_effective) to keep hole-edge stress ≈ flat-plate level
# QI laminates are quasi-isotropic, so SCF ≈ 3 for all materials.
# We use a conservative fixed factor. For UD-biased layups, the layup scale factor
# already reduces pressure (UD layups have higher scale → higher pressure, but also
# higher laminate-level SCF, which partially self-cancels).
CUTOUT_PRESSURE_FACTOR = 0.33  # ≈ 1/3 for quasi-isotropic SCF ≈ 3

# =============================================================================
# CSV columns — extended from batch_100k.py
# =============================================================================
def build_csv_columns():
    cols = [
        'sim_id', 'material_id', 'material_name', 'layup_id', 'layup_name',
        'bc_mode', 'geometry', 'mesh_level', 'n_plies',
        'V1A', 'V2A', 'V3A', 'V4A', 'V1D', 'V2D', 'V3D', 'V4D',
        'n_defects',
    ]
    for di in range(1, MAX_DEFECTS + 1):
        p = f"defect{di}_"
        cols.extend([p+'x', p+'y', p+'half_length', p+'width', p+'angle', p+'roughness',
                     p+'cos_angle', p+'sin_angle', p+'aspect_ratio', p+'norm_x', p+'norm_y',
                     p+'norm_length', p+'boundary_prox', p+'ligament_ratio', p+'sif_estimate'])
    cols.extend([
        'pressure_x', 'pressure_y', 'ply_thickness',
        'min_inter_defect_dist', 'total_crack_area_frac', 'max_sif_estimate', 'min_ligament_ratio',
    ])
    # Cutout-specific
    cols.extend(['hole_diameter', 'hole_x', 'hole_y'])
    # Curved-specific
    cols.append('panel_radius')
    # Solver outputs
    cols.extend([
        'solver_completed', 'n_elements',
        'max_s11', 'min_s11', 'max_s12',
        'tsai_wu_index',
        'max_hashin_ft', 'max_hashin_fc', 'max_hashin_mt', 'max_hashin_mc',
    ])
    # Puck
    cols.extend(['puck_ff', 'puck_iff_a', 'puck_iff_b', 'puck_iff_c'])
    # LaRC05
    cols.extend(['larc_ft', 'larc_fc', 'larc_mt'])
    # Per-defect max Tsai-Wu index (physically meaningful for composites, unlike von Mises)
    for di in range(1, MAX_DEFECTS + 1):
        cols.append(f'max_tsai_wu_defect{di}')
    # Failure flags
    cols.extend(['failed_tsai_wu', 'failed_hashin', 'failed_puck', 'failed_larc'])
    # Post-FPF indicator: 1 if any failure index >= 1.0 (useful metadata for dataset users)
    cols.append('post_fpf')
    # BC mode 5 (*BUCKLE) outputs: fixed-width block of eigenvalues scaled on
    # the reference compressive load written in the CCX *CLOAD block. Populated
    # only when bc_mode == "buckle_comp"; zero-filled otherwise so every row
    # has the same schema.
    for e in range(1, N_BUCKLE_EIGENVALUES + 1):
        cols.append(f'buckle_eig_{e}')
    # Solver dispatch column (task #18) + UMAT SDV damage read-out (task #19).
    # umat_d_{ft,fc,mt,mc}_max are the maximum values of the four Hashin damage
    # variables across the final converged increment. Zero-filled for any row
    # whose solver is not ccx_umat.
    cols.extend([
        'solver',
        'umat_d_ft_max', 'umat_d_fc_max',
        'umat_d_mt_max', 'umat_d_mc_max',
        'umat_n_increments',
    ])
    return cols


def _material_to_umat_constants(mat, Lc_mm=2.0):
    """Derive the 19 UMAT material constants from a MATERIALS-dict entry.

    The exact layout is dictated by ``umat_composite_fatigue.f`` (see
    ``~/ccx_umat/umat_composite_fatigue.f`` lines 41-58):

         1  E1         longitudinal modulus                [MPa]
         2  E2         transverse modulus                  [MPa]
         3  nu12       major Poisson ratio                 [-]
         4  G12        in-plane shear modulus              [MPa]
         5  G13        transverse shear modulus            [MPa]
         6  G23        out-of-plane shear modulus          [MPa]
         7  XT         longitudinal tensile strength       [MPa]
         8  XC         longitudinal compressive strength   [MPa]
         9  YT         transverse tensile strength         [MPa]
        10  YC         transverse compressive strength     [MPa]
        11  SL         in-plane shear strength             [MPa]
        12  ST         transverse shear strength           [MPa]
        13  Gf_ft      fibre-tension fracture energy       [N/mm]
        14  Gf_fc      fibre-compression fracture energy   [N/mm]
        15  Gf_mt      matrix-tension fracture energy      [N/mm]
        16  Gf_mc      matrix-compression fracture energy  [N/mm]
        17  Lc         characteristic element length       [mm]
        18  eta_visc   viscous regularisation              [-]
        19  beta_shear shear damage coupling               [-]

    The elastic and strength constants (1-12) come from the material
    library directly. Fracture energies (13-16) use the Camanho & Dávila
    2002 T300/5208 reference values converted to CCX units (J/m^2 -> N/mm,
    factor 1e-3): fibre modes at 12.5 N/mm, matrix modes at 1.0 N/mm.
    ``Lc`` defaults to 2 mm (medium mesh); ``eta_visc`` defaults to 1e-3
    (typical CDM regularisation, avoids severe stiffness snap-through);
    ``beta_shear`` defaults to 1.0 (full shear-damage coupling).

    This constant layout matches the Fortran source exactly; the previous
    revision of this helper used a Weibull-fatigue layout that is *not*
    what the linked-in umat_composite_fatigue.f expects, which is why the
    earlier smoke attempt diverged in the first Newton-Raphson iteration.
    """
    E1 = float(mat['E1'])
    E2 = float(mat['E2'])
    NU12 = float(mat['v12'])
    G12 = float(mat['G12'])
    # Transverse isotropy: G13 = G12; G23 from E2 and v23.
    v23 = float(mat.get('v23', 0.43))
    G13 = G12
    G23 = E2 / (2.0 * (1.0 + v23))
    XT = float(mat['XT'])
    XC = float(mat['XC'])
    YT = float(mat['YT'])
    YC = float(mat['YC'])
    SL = float(mat['SL'])
    # Transverse shear strength (ST) estimated from Puck fracture plane.
    ST = YC / (2.0 * math.tan(math.radians(53.0)))
    # Fracture energies (N/mm) — Camanho & Dávila (2002) T300/5208.
    Gf_ft = 12.5
    Gf_fc = 12.5
    Gf_mt = 1.0
    Gf_mc = 1.0
    Lc = float(Lc_mm)
    eta_visc = 1.0e-3
    beta_shear = 1.0
    return (
        E1, E2, NU12, G12, G13, G23,
        XT, XC, YT, YC, SL, ST,
        Gf_ft, Gf_fc, Gf_mt, Gf_mc,
        Lc, eta_visc, beta_shear,
    )


def _parse_ccx_umat_sdv(dat_text):
    """Parse the *EL PRINT SDV block from a CCX+UMAT .dat file.

    Returns ``(n_increments, d_ft_max, d_fc_max, d_mt_max, d_mc_max)`` —
    the maxima of the first four state variables across the final converged
    increment. Slots 0..3 correspond to fibre-tensile, fibre-compressive,
    matrix-tensile, matrix-compressive damage variables per the UMAT source.
    Returns all zeros on parse failure (caller treats as a failed sim).
    """
    increments = []
    cur_time = None
    cur_rows = []
    for line in dat_text.splitlines():
        m = re.search(r'internal state variables.*time\s+([\d.eE+\-]+)', line)
        if m:
            if cur_time is not None:
                increments.append((cur_time, cur_rows))
            cur_time = float(m.group(1))
            cur_rows = []
            continue
        toks = line.split()
        # SDV rows are: elem ip sdv1 sdv2 ... sdv14
        if len(toks) >= 6 and cur_time is not None:
            try:
                _eid = int(toks[0]); _ip = int(toks[1])
                sdvs = [float(t) for t in toks[2:]]
                if len(sdvs) >= 4:
                    cur_rows.append(sdvs)
            except ValueError:
                pass
    if cur_time is not None:
        increments.append((cur_time, cur_rows))
    if not increments:
        return (0, 0.0, 0.0, 0.0, 0.0)
    _, last_rows = increments[-1]
    if not last_rows:
        return (len(increments), 0.0, 0.0, 0.0, 0.0)
    d_ft = max(r[0] for r in last_rows)
    d_fc = max(r[1] for r in last_rows)
    d_mt = max(r[2] for r in last_rows)
    d_mc = max(r[3] for r in last_rows)
    return (len(increments), d_ft, d_fc, d_mt, d_mc)

CSV_COLUMNS = build_csv_columns()

# =============================================================================
# Logging
# =============================================================================
_log_fh = None

def log(msg):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    if _log_fh:
        _log_fh.write(line + "\n")
        _log_fh.flush()


# =============================================================================
# 2.3 Dynamic Orientation Generation
# =============================================================================
def generate_orientations(unique_angles):
    oris = {}
    for angle in sorted(set(unique_angles)):
        rad = math.radians(angle)
        c, s = math.cos(rad), math.sin(rad)
        name = f"ORI_{angle}" if angle >= 0 else f"ORI_M{abs(angle)}"
        oris[angle] = (name, f"{c:.7f}, {s:.7f}, 0.0, {-s:.7f}, {c:.7f}, 0.0")
    return oris


# =============================================================================
# 2.6 Lamination Parameter Computation
# =============================================================================
def compute_lamination_params(angles, ply_thickness):
    n = len(angles)
    h = n * ply_thickness
    V1A = V2A = V3A = V4A = 0.0
    V1D = V2D = V3D = V4D = 0.0
    for k, theta_deg in enumerate(angles):
        t = math.radians(theta_deg)
        zk = (-h/2 + (k + 0.5) * ply_thickness)
        tk_over_h = ply_thickness / h
        zk_over_h_sq = (zk / h)**2 * 12
        V1A += math.cos(2*t) * tk_over_h
        V2A += math.sin(2*t) * tk_over_h
        V3A += math.cos(4*t) * tk_over_h
        V4A += math.sin(4*t) * tk_over_h
        V1D += math.cos(2*t) * zk_over_h_sq * tk_over_h
        V2D += math.sin(2*t) * zk_over_h_sq * tk_over_h
        V3D += math.cos(4*t) * zk_over_h_sq * tk_over_h
        V4D += math.sin(4*t) * zk_over_h_sq * tk_over_h
    return V1A, V2A, V3A, V4A, V1D, V2D, V3D, V4D


# =============================================================================
# 2.8 Latin Hypercube Sampling
# =============================================================================
def lhs_sample(param_ranges, n_samples, seed=42):
    from scipy.stats.qmc import LatinHypercube
    dim = len(param_ranges)
    param_names = list(param_ranges.keys())
    sampler = LatinHypercube(d=dim, seed=seed)
    raw = sampler.random(n=n_samples)
    samples_list = []
    for i in range(n_samples):
        sample = {}
        for j, name in enumerate(param_names):
            lo, hi = param_ranges[name]
            sample[name] = lo + raw[i][j] * (hi - lo)
        samples_list.append(sample)
    return samples_list


# =============================================================================
# Crack geometry (carried from batch_100k.py)
# =============================================================================
def validate_crack_bounds(cx, cy, half_length, width, angle_deg,
                          roughness, plate_length, plate_width, margin=2.0):
    max_lateral = width / 2.0 + half_length * 0.3
    t = math.radians(angle_deg)
    dx = abs(half_length * math.cos(t)) + abs(max_lateral * math.sin(t))
    dy = abs(half_length * math.sin(t)) + abs(max_lateral * math.cos(t))
    if cx - dx < margin or cx + dx > plate_length - margin:
        return False
    if cy - dy < margin or cy + dy > plate_width - margin:
        return False
    return True


def overlaps_existing(new_defect, existing_defects, margin=2.0):
    for d in existing_defects:
        dist = math.sqrt((new_defect['x'] - d['x'])**2 + (new_defect['y'] - d['y'])**2)
        min_dist = new_defect['half_length'] + d['half_length'] + margin
        if dist < min_dist:
            return True
    return False


def place_defects_sequentially(n_defects):
    placed = []
    for crack_idx in range(n_defects):
        placed_this_crack = False
        for attempt in range(MAX_PLACEMENT_ATTEMPTS):
            defect = {}
            for pname, (lo, hi) in DEFECT_RANGES.items():
                defect[pname] = random.uniform(lo, hi)
            if defect['width'] < MIN_CRACK_WIDTH:
                defect['width'] = MIN_CRACK_WIDTH
            if not validate_crack_bounds(
                    defect['x'], defect['y'], defect['half_length'],
                    defect['width'], defect['angle'], defect['roughness'],
                    PLATE_L, PLATE_W):
                continue
            if overlaps_existing(defect, placed):
                continue
            placed.append(defect)
            placed_this_crack = True
            break
        if not placed_this_crack:
            return None
    return placed


def crack_polygon_points(cx, cy, half_length, width, angle_deg, roughness):
    angle_rad = math.radians(angle_deg)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    max_dev_rad = math.radians(MAX_ANGLE_DEV_DEG) * roughness

    centerline = [(-half_length, 0.0)]
    x_pos = -half_length
    y_pos = 0.0

    while x_pos < half_length:
        seg_len = random.uniform(CRACK_SEG_LEN_MIN, CRACK_SEG_LEN_MAX)
        deviation = random.uniform(-max_dev_rad, max_dev_rad)
        dx = seg_len * math.cos(deviation)
        dy = seg_len * math.sin(deviation)
        x_pos += dx
        y_pos += dy
        y_pos = max(-half_length * 0.3, min(half_length * 0.3, y_pos))
        centerline.append((x_pos, y_pos))

    if len(centerline) > 2 and centerline[-1][0] > half_length * 1.05:
        px_prev, py_prev = centerline[-2]
        px_last, py_last = centerline[-1]
        dx_seg = px_last - px_prev
        if abs(dx_seg) > 1e-9:
            frac = (half_length - px_prev) / dx_seg
            frac = max(0.0, min(1.0, frac))
            new_y = py_prev + frac * (py_last - py_prev)
            centerline[-1] = (half_length, new_y)

    if len(centerline) < MIN_POLYGON_SEGMENTS // 2:
        refined = [centerline[0]]
        for j in range(1, len(centerline)):
            mid_x = (centerline[j-1][0] + centerline[j][0]) / 2.0
            mid_y = (centerline[j-1][1] + centerline[j][1]) / 2.0
            refined.append((mid_x, mid_y))
            refined.append(centerline[j])
        centerline = refined

    half_w = width / 2.0
    upper, lower = [], []
    total_x_span = 2.0 * half_length
    if total_x_span < 1e-9:
        total_x_span = 1.0

    for i, (px, py) in enumerate(centerline):
        progress = (px + half_length) / total_x_span
        progress = max(0.0, min(1.0, progress))
        taper = 1.0 - (2.0 * abs(progress - 0.5)) ** 1.5
        taper = max(taper, 0.10)
        local_hw = half_w * taper
        upper.append((px, py + local_hw))
        lower.append((px, py - local_hw))

    local_polygon = upper + list(reversed(lower))
    global_points = []
    for lx, ly in local_polygon:
        gx = cx + lx * cos_a - ly * sin_a
        gy = cy + lx * sin_a + ly * cos_a
        global_points.append((round(gx, 6), round(gy, 6)))
    return global_points


def polygon_self_intersects(polygon):
    n = len(polygon)
    if n < 4:
        return False
    def ccw(A, B, C):
        return (C[1]-A[1])*(B[0]-A[0]) > (B[1]-A[1])*(C[0]-A[0])
    def segments_intersect(A, B, C, D):
        return ccw(A,C,D) != ccw(B,C,D) and ccw(A,B,C) != ccw(A,B,D)
    for i in range(n):
        A = polygon[i]
        B = polygon[(i+1) % n]
        for j in range(i+2, n):
            if j == (i-1) % n or (i == 0 and j == n-1):
                continue
            C = polygon[j]
            D = polygon[(j+1) % n]
            if segments_intersect(A, B, C, D):
                return True
    return False


# =============================================================================
# 2.5 Mesh Generation — 3 geometry types
# =============================================================================
def create_plate_with_cracks(polygons, job_name, geometry="flat", mesh_level="medium",
                             hole_diameter=0, hole_x=0, hole_y=0, panel_radius=200):
    import gmsh
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add(job_name)

    mc = MESH_CONFIGS[mesh_level]

    if geometry == "flat":
        plate = gmsh.model.occ.addRectangle(0, 0, 0, PLATE_L, PLATE_W)
    elif geometry == "cutout":
        plate = gmsh.model.occ.addRectangle(0, 0, 0, PLATE_L, PLATE_W)
        r = hole_diameter / 2.0
        hole = gmsh.model.occ.addDisk(hole_x, hole_y, 0, r, r)
        gmsh.model.occ.cut([(2, plate)], [(2, hole)])
        gmsh.model.occ.synchronize()
        # Re-fetch plate tag after boolean
        surfaces = gmsh.model.getEntities(2)
        if not surfaces:
            gmsh.finalize()
            return None, None, None
        # Continue with the boolean result
    elif geometry == "curved":
        R = panel_radius
        theta = PLATE_L / R  # arc length = PLATE_L
        center = gmsh.model.occ.addPoint(0, 0, -R)
        p_start = gmsh.model.occ.addPoint(0, 0, 0)
        p_end = gmsh.model.occ.addPoint(0, R*math.sin(theta), R*math.cos(theta)-R)
        arc = gmsh.model.occ.addCircleArc(p_start, center, p_end)
        gmsh.model.occ.extrude([(1, arc)], PLATE_W, 0, 0)
        gmsh.model.occ.synchronize()

    # Boolean-cut crack slots into the mesh
    if geometry in ("flat", "cutout", "curved"):
        if geometry == "flat":
            gmsh.model.occ.synchronize()
        surfaces_before = gmsh.model.getEntities(2)
        plate_tag = surfaces_before[0][1] if surfaces_before else 1

        slot_surfs = []
        crack_wires = []  # For curved: embed crack edges via fragment
        for polygon in (polygons or []):
            if len(polygon) < 3:
                continue
            pts = []
            if geometry == "curved":
                # Project 2D crack coords onto curved surface
                # Curved panel: arc in Y-Z plane, extruded along X by PLATE_W
                # gx (defect x, [0, PLATE_L]) → arc position: theta = gx/R
                # gy (defect y, [0, PLATE_W]) → X direction (extrusion)
                R = panel_radius
                for gx, gy in polygon:
                    gx = max(0.01, min(PLATE_L - 0.01, gx))
                    gy = max(0.01, min(PLATE_W - 0.01, gy))
                    theta_c = gx / R
                    x_3d = gy  # width/extrusion direction
                    y_3d = R * math.sin(theta_c)
                    z_3d = R * math.cos(theta_c) - R
                    pts.append(gmsh.model.occ.addPoint(x_3d, y_3d, z_3d))
            else:
                for gx, gy in polygon:
                    gx = max(0.01, min(PLATE_L - 0.01, gx))
                    gy = max(0.01, min(PLATE_W - 0.01, gy))
                    pts.append(gmsh.model.occ.addPoint(gx, gy, 0))

            if geometry == "curved":
                # For curved: embed crack outline as wire edges into the surface
                # This creates mesh conforming edges without boolean surface cuts
                n_pts = len(pts)
                for i in range(n_pts):
                    try:
                        ln = gmsh.model.occ.addLine(pts[i], pts[(i+1) % n_pts])
                        crack_wires.append((1, ln))
                    except Exception:
                        pass
            else:
                lines = []
                n_pts = len(pts)
                for i in range(n_pts):
                    lines.append(gmsh.model.occ.addLine(pts[i], pts[(i+1) % n_pts]))
                try:
                    loop = gmsh.model.occ.addCurveLoop(lines)
                    surf = gmsh.model.occ.addPlaneSurface([loop])
                    slot_surfs.append((2, surf))
                except Exception:
                    continue

        if geometry == "curved" and crack_wires:
            # Fragment: embed crack edges into the curved surface
            # This forces mesh edges along crack boundaries
            gmsh.model.occ.fragment([(2, plate_tag)], crack_wires)
        elif slot_surfs:
            gmsh.model.occ.cut([(2, plate_tag)], slot_surfs)

    gmsh.model.occ.synchronize()

    # Physical groups
    surfaces = gmsh.model.getEntities(2)
    gmsh.model.addPhysicalGroup(2, [s[1] for s in surfaces], tag=5, name="plate")

    # Classify boundary curves
    all_curves = gmsh.model.getEntities(1)
    tol = 0.1
    left_c, bottom_c, right_c, top_c = [], [], [], []

    if geometry == "curved":
        # Curved panel: arc in Y-Z plane, extruded along X by PLATE_W.
        # "Length" runs along the arc, "width" along X.
        # Map edges to match flat-plate BC semantics:
        #   left (clamped) = arc start (straight line at y≈0, z≈0)
        #   right (loaded) = arc end (straight line at y≈y_end, z≈z_end)
        #   bottom/top = lateral arc edges (at x=0 and x=PLATE_W)
        for _, tag in all_curves:
            bbox = gmsh.model.getBoundingBox(1, tag)
            xmin, ymin, zmin, xmax, ymax, zmax = bbox
            x_span = xmax - xmin
            if x_span > PLATE_W - 1.0:
                # Straight edge spanning X (width) — these are the "length" ends
                if abs(ymin) < tol and abs(ymax) < tol and abs(zmin) < tol and abs(zmax) < tol:
                    left_c.append(tag)   # Arc start → clamped edge ("left")
                else:
                    right_c.append(tag)  # Arc end → loaded edge ("right")
            elif abs(xmin) < tol and abs(xmax) < tol:
                bottom_c.append(tag)     # Arc at x=0 → lateral ("bottom")
            elif abs(xmin - PLATE_W) < tol and abs(xmax - PLATE_W) < tol:
                top_c.append(tag)        # Arc at x=PLATE_W → lateral ("top")
    else:
        for _, tag in all_curves:
            bbox = gmsh.model.getBoundingBox(1, tag)
            xmin, ymin, _, xmax, ymax, _ = bbox
            if abs(xmin) < tol and abs(xmax) < tol:
                left_c.append(tag)
            elif abs(xmin - PLATE_L) < tol and abs(xmax - PLATE_L) < tol:
                right_c.append(tag)
            elif abs(ymin) < tol and abs(ymax) < tol and xmax - xmin > 1.0:
                bottom_c.append(tag)
            elif abs(ymin - PLATE_W) < tol and abs(ymax - PLATE_W) < tol and xmax - xmin > 1.0:
                top_c.append(tag)

    if left_c: gmsh.model.addPhysicalGroup(1, left_c, tag=1, name="left")
    if bottom_c: gmsh.model.addPhysicalGroup(1, bottom_c, tag=2, name="bottom")
    if right_c: gmsh.model.addPhysicalGroup(1, right_c, tag=3, name="right")
    if top_c: gmsh.model.addPhysicalGroup(1, top_c, tag=4, name="top")

    # Mesh settings
    gmsh.option.setNumber("Mesh.ElementOrder", 2)
    gmsh.option.setNumber("Mesh.SecondOrderIncomplete", 1)
    gmsh.option.setNumber("Mesh.RecombineAll", 0)
    gmsh.option.setNumber("Mesh.Algorithm", 6)
    gmsh.option.setNumber("Mesh.CharacteristicLengthMin", mc["CharLenMin"])
    gmsh.option.setNumber("Mesh.CharacteristicLengthMax", mc["CharLenMax"])

    # Refine near cracks/holes
    crack_curves = []
    edge_set = set(left_c + bottom_c + right_c + top_c)
    for _, tag in all_curves:
        if tag not in edge_set:
            crack_curves.append(tag)

    if crack_curves:
        fd = gmsh.model.mesh.field.add("Distance")
        gmsh.model.mesh.field.setNumbers(fd, "CurvesList", crack_curves)
        gmsh.model.mesh.field.setNumber(fd, "Sampling", 200)
        ft = gmsh.model.mesh.field.add("Threshold")
        gmsh.model.mesh.field.setNumber(ft, "InField", fd)
        gmsh.model.mesh.field.setNumber(ft, "SizeMin", mc["CrackSizeMin"])
        gmsh.model.mesh.field.setNumber(ft, "SizeMax", mc["CharLenMax"])
        gmsh.model.mesh.field.setNumber(ft, "DistMin", mc["CrackSizeMin"])
        gmsh.model.mesh.field.setNumber(ft, "DistMax", 15.0)
        gmsh.model.mesh.field.setAsBackgroundMesh(ft)

    gmsh.model.mesh.generate(2)

    # Extract mesh
    node_tags, node_coords, _ = gmsh.model.mesh.getNodes()
    nodes = {}
    for i, tag in enumerate(node_tags):
        nodes[int(tag)] = (node_coords[3*i], node_coords[3*i+1], node_coords[3*i+2])

    elem_types, elem_tags, elem_node_tags = gmsh.model.mesh.getElements(2)
    elements = []
    for etype, etags, enodes in zip(elem_types, elem_tags, elem_node_tags):
        npe = gmsh.model.mesh.getElementProperties(etype)[3]
        for i, etag in enumerate(etags):
            enlist = [int(enodes[i*npe + j]) for j in range(npe)]
            elements.append((int(etag), npe, enlist))

    bc_sets = {}
    for phys_tag, name in [(1, "left"), (2, "bottom"), (3, "right"), (4, "top")]:
        nset = set()
        try:
            ents = gmsh.model.getEntitiesForPhysicalGroup(1, phys_tag)
            for ent in ents:
                ntags, _, _ = gmsh.model.mesh.getNodes(1, ent, includeBoundary=True)
                nset.update(int(t) for t in ntags)
        except Exception as exc:
            log(f"WARNING: BC extraction failed for '{name}' (phys_tag={phys_tag}): {exc}")
        bc_sets[name] = nset

    corner = min(nodes.keys(), key=lambda n: nodes[n][0]**2 + nodes[n][1]**2 + nodes[n][2]**2)
    bc_sets["corner"] = {corner}

    gmsh.finalize()
    return nodes, elements, bc_sets


# =============================================================================
# Write CalculiX .inp file — extended for materials, layups, BCs
# =============================================================================
def write_ccx_inp(nodes, elements, bc_sets, case, job_name, work_dir,
                   geometry="flat", panel_radius=200):
    mat = MATERIALS[case['material_id']]
    layup_angles = LAYUPS[case['layup_id']]['angles']
    ply_t = case['ply_thickness']
    n_plies = len(layup_angles)
    total_t = n_plies * ply_t
    bc_mode = case['bc_mode']
    solver = case.get('solver', 'ccx_stock')

    filepath = os.path.join(work_dir, f"{job_name}.inp")

    # Derive E3, v13, G13, G23 from transverse isotropy
    E1 = float(mat['E1'])
    E2 = float(mat['E2'])
    E3 = E2
    v12 = float(mat['v12'])
    v13 = v12
    v23 = float(mat.get('v23', 0.45))
    G12 = float(mat['G12'])
    G13 = G12
    G23 = E2 / (2 * (1 + v23))

    with open(filepath, 'w') as f:
        f.write(f"** CompositeBench auto-generated\n*HEADING\nSim {case['sim_id']}\n")

        f.write("*NODE\n")
        for nid in sorted(nodes.keys()):
            x, y, z = nodes[nid]
            f.write(f"  {nid}, {x:.8f}, {y:.8f}, {z:.8f}\n")

        f.write("*ELEMENT, TYPE=S6, ELSET=PLATE\n")
        for eid, npe, enlist in elements:
            node_str = ", ".join(str(n) for n in enlist)
            f.write(f"  {eid}, {node_str}\n")

        if solver == 'ccx_umat':
            # CCX + Hashin-fatigue UMAT — 19 user constants, 14 SDVs.
            # CalculiX routes to ``umat_user`` whenever the material *name*
            # starts with the literal string "USER" (see ccx_2.21/src/
            # umat_main.f line 192). The remaining 76 characters are passed
            # into umat_user as ``amatloc`` and are free-form — we use
            # "USER_COMPFAT" so the .inp is self-documenting.
            umat_name = "USER_COMPFAT"
            umat_consts = _material_to_umat_constants(mat)
            f.write(f"*MATERIAL, NAME={umat_name}\n")
            f.write("*USER MATERIAL, CONSTANTS=19\n")
            # CCX accepts 8 values per line in *USER MATERIAL blocks.
            for k in range(0, len(umat_consts), 8):
                chunk = umat_consts[k:k+8]
                f.write(", ".join(f"{v:.6g}" for v in chunk) + "\n")
            f.write("*DEPVAR\n14\n")
            mat_name_for_section = umat_name
        else:
            f.write(f"*MATERIAL, NAME=COMPOSITE_UD\n")
            f.write("*ELASTIC, TYPE=ENGINEERING CONSTANTS\n")
            f.write(f"{E1}, {E2}, {E3}, {v12}, {v13}, {v23}, {G12}, {G13}\n")
            f.write(f"{G23}\n")
            mat_name_for_section = "COMPOSITE_UD"

        # Dynamic orientations
        oris = generate_orientations(layup_angles)
        for angle in sorted(oris.keys()):
            name, vec = oris[angle]
            f.write(f"*ORIENTATION, NAME={name}, SYSTEM=RECTANGULAR\n{vec}\n")

        # Composite shell section
        f.write("*SHELL SECTION, COMPOSITE, ELSET=PLATE, OFFSET=0\n")
        for angle in layup_angles:
            ori_name = oris[angle][0]
            f.write(f"{ply_t}, 3, {mat_name_for_section}, {ori_name}\n")

        # Node sets
        for bname, nset in bc_sets.items():
            if nset:
                f.write(f"*NSET, NSET={bname.upper()}\n")
                nids = sorted(nset)
                for k in range(0, len(nids), 16):
                    chunk = nids[k:k+16]
                    f.write(", ".join(str(n) for n in chunk) + "\n")

        # Boundary conditions
        px = case['pressure_x']
        py = case['pressure_y']

        if geometry == "curved":
            # Curved panel: LEFT = straight edge at arc start (y≈0, z≈0)
            # Constrain Y (direction 2) to prevent arc-tangent motion
            # Constrain Z (direction 3) on all LEFT nodes to prevent out-of-plane rigid body rotation
            f.write("*BOUNDARY\nLEFT, 2, 2, 0.0\n")
            f.write("LEFT, 3, 3, 0.0\n")
            f.write("CORNER, 1, 1, 0.0\n")  # Pin one node in X to prevent rigid body
        else:
            # Flat/cutout: LEFT = edge at x=0, constrain X (direction 1)
            f.write("*BOUNDARY\nLEFT, 1, 1, 0.0\n")
            f.write("CORNER, 2, 3, 0.0\n")

        # Step card — *BUCKLE for mode 5 (linear eigenvalue extraction of the
        # reference compressive load case), *STATIC otherwise. In both cases
        # the downstream *CLOAD block writes the reference load that *BUCKLE
        # will scale to find the critical eigenvalues.
        #
        # The UMAT path writes a nonlinear *STATIC card with automatic time
        # stepping (initial 0.1 increment, min 1e-4, max 0.25) and up to 80
        # Newton-Raphson attempts per increment — the Hashin-damage UMAT
        # softens the local stiffness once a failure criterion triggers, so
        # 1-shot loading (the default) cannot converge past first-ply
        # failure. NLGEOM is enabled for the UMAT path to keep large-rotation
        # bending under compressive load well-posed.
        #
        # 2026-04-11 UPDATE (Fix 1 for task #18): the UMAT path now uses
        # linear static (``*STEP / *STATIC``) instead of ``*STEP, INC=80,
        # NLGEOM / *STATIC 0.1, 1.0, 1e-4, 0.25``. Root cause (see V11 note
        # §28.15.8): ``umat_composite_fatigue.f`` populates the 6x6
        # constitutive tangent with only C11/C12/C22/C44/C55/C66 (plus
        # C33 = 1e-30) and leaves C13 = C23 = 0. That sparse tangent is
        # fine on a single-element test and fine under linear static, but
        # under NLGEOM + automatic time-stepping on a multi-element mesh
        # with force-controlled CLOAD and the batch's minimal BCs, Newton-
        # Raphson can't converge -- residuals oscillate at ~5-6% of avg
        # force, cutbacks pile up, CCX aborts with ``*ERROR: too many
        # cutbacks`` or ``*ERROR: increment size smaller than minimum``.
        # Linear static solves in one shot, tolerates the sparse tangent,
        # and writes a valid SDV block. Verified working on GCP rung 1
        # 2026-04-11 after 4 Gf/Lc variants all failed identically,
        # proving the tangent is the real issue (not the fracture energy
        # inequality). Trade-off: damage progression past first-ply
        # failure is truncated to a single UMAT evaluation at the final
        # load -- acceptable because the 12-35% FPF sampling range keeps
        # most sims elastic anyway. Fix 2 (populate C13/C23 in the Fortran
        # source + rebuild) is the long-term answer and restores the
        # NLGEOM path for proper post-FPF softening physics.
        if bc_mode == "buckle_comp":
            f.write(f"*STEP, PERTURBATION\n*BUCKLE\n{N_BUCKLE_EIGENVALUES}\n")
        else:
            # Single step card covers stock CCX, CCX+UMAT, and any future
            # implicit-static solver. Linear-static one-shot solve; CCX
            # runs internal Newton iterations to convergence when the
            # material is nonlinear (UMAT), but does not step through
            # increments.
            f.write("*STEP\n*STATIC\n")

        # Apply loads based on BC mode
        n_right = len(bc_sets.get("right", set()))
        n_top = len(bc_sets.get("top", set()))
        n_bottom = len(bc_sets.get("bottom", set()))

        if geometry == "curved":
            # Curved: RIGHT = straight edge at arc end, loads along arc tangent
            # Arc tangent at θ = PLATE_L/R: (0, cos(θ), -sin(θ))
            theta_end = PLATE_L / panel_radius
            ct = math.cos(theta_end)
            st = math.sin(theta_end)

            if bc_mode == "biaxial":
                if n_right > 0:
                    f_total = px * PLATE_W * total_t
                    fy = (f_total * ct) / n_right
                    fz = -(f_total * st) / n_right
                    f.write(f"*CLOAD\nRIGHT, 2, {fy:.8f}\n")
                    f.write(f"*CLOAD\nRIGHT, 3, {fz:.8f}\n")
                # Lateral pressure on BOTTOM/TOP (along X, the width direction)
                if n_top > 0 and py > 0:
                    fx_top = (py * PLATE_L * total_t) / n_top
                    f.write(f"*CLOAD\nTOP, 1, {fx_top:.8f}\n")
                if n_bottom > 0 and py > 0:
                    fx_bot = -(py * PLATE_L * total_t) / n_bottom
                    f.write(f"*CLOAD\nBOTTOM, 1, {fx_bot:.8f}\n")

            elif bc_mode == "tension_comp":
                if n_right > 0:
                    f_total = px * PLATE_W * total_t
                    fy = (f_total * ct) / n_right
                    fz = -(f_total * st) / n_right
                    f.write(f"*CLOAD\nRIGHT, 2, {fy:.8f}\n")
                    f.write(f"*CLOAD\nRIGHT, 3, {fz:.8f}\n")
                if n_top > 0 and py > 0:
                    fx_top = -(py * PLATE_L * total_t) / n_top
                    f.write(f"*CLOAD\nTOP, 1, {fx_top:.8f}\n")
                if n_bottom > 0 and py > 0:
                    fx_bot = (py * PLATE_L * total_t) / n_bottom
                    f.write(f"*CLOAD\nBOTTOM, 1, {fx_bot:.8f}\n")

            elif bc_mode == "uniaxial_shear":
                if n_right > 0:
                    f_total = px * PLATE_W * total_t
                    fy = (f_total * ct) / n_right
                    fz = -(f_total * st) / n_right
                    f.write(f"*CLOAD\nRIGHT, 2, {fy:.8f}\n")
                    f.write(f"*CLOAD\nRIGHT, 3, {fz:.8f}\n")
                if n_top > 0:
                    # Shear: force along arc tangent on lateral edge
                    f_shear = (py * PLATE_L * total_t) / n_top
                    # At lateral edge (arc at x=PLATE_W), tangent varies along arc
                    # Approximate with average Y-component
                    f.write(f"*CLOAD\nTOP, 2, {f_shear:.8f}\n")

            elif bc_mode in ("pure_compression", "buckle_comp"):
                # BC4/5 (curved): compressive line load on RIGHT along the
                # *inward* arc-tangent direction (opposite of the biaxial
                # tensile case). Mode 4 resolves a static stress state; mode
                # 5 re-uses the same load as the reference case for CCX
                # *BUCKLE eigenvalue extraction.
                if n_right > 0:
                    f_total = -abs(px * PLATE_W * total_t)
                    fy = (f_total * ct) / n_right
                    fz = -(f_total * st) / n_right
                    f.write(f"*CLOAD\nRIGHT, 2, {fy:.8f}\n")
                    f.write(f"*CLOAD\nRIGHT, 3, {fz:.8f}\n")

        else:
            # Flat/cutout loading
            if bc_mode == "biaxial":
                # BC1: px on RIGHT, py on TOP and -py on BOTTOM
                if n_right > 0:
                    fx = (px * PLATE_W * total_t) / n_right
                    f.write(f"*CLOAD\nRIGHT, 1, {fx:.8f}\n")
                if n_top > 0 and py > 0:
                    fy_top = (py * PLATE_L * total_t) / n_top
                    f.write(f"*CLOAD\nTOP, 2, {fy_top:.8f}\n")
                if n_bottom > 0 and py > 0:
                    fy_bot = -(py * PLATE_L * total_t) / n_bottom
                    f.write(f"*CLOAD\nBOTTOM, 2, {fy_bot:.8f}\n")

            elif bc_mode == "tension_comp":
                # BC2: px on RIGHT, -py on TOP (compression), +py on BOTTOM
                if n_right > 0:
                    fx = (px * PLATE_W * total_t) / n_right
                    f.write(f"*CLOAD\nRIGHT, 1, {fx:.8f}\n")
                if n_top > 0 and py > 0:
                    fy_top = -(py * PLATE_L * total_t) / n_top
                    f.write(f"*CLOAD\nTOP, 2, {fy_top:.8f}\n")
                if n_bottom > 0 and py > 0:
                    fy_bot = (py * PLATE_L * total_t) / n_bottom
                    f.write(f"*CLOAD\nBOTTOM, 2, {fy_bot:.8f}\n")

            elif bc_mode == "uniaxial_shear":
                # BC3: px on RIGHT, shear via X-force on TOP
                if n_right > 0:
                    fx = (px * PLATE_W * total_t) / n_right
                    f.write(f"*CLOAD\nRIGHT, 1, {fx:.8f}\n")
                if n_top > 0:
                    fs = (py * PLATE_L * total_t) / n_top
                    f.write(f"*CLOAD\nTOP, 1, {fs:.8f}\n")

            elif bc_mode in ("pure_compression", "buckle_comp"):
                # BC4/5 (flat): compressive line load on RIGHT along -X.
                # Uses pressure_x magnitude as the reference compressive
                # membrane load. Mode 4 is a static run (stresses + failure
                # indices); mode 5 re-uses the same load as the reference
                # load case for CCX *BUCKLE eigenvalue extraction, so the
                # reported eigenvalues are critical multipliers of this load.
                if n_right > 0:
                    fx = -abs(px * PLATE_W * total_t) / n_right
                    f.write(f"*CLOAD\nRIGHT, 1, {fx:.8f}\n")

        # Output requests — *EL PRINT is valid for *STATIC. For *BUCKLE CCX
        # writes eigenvalues to the .dat file without requiring *EL PRINT, so
        # we skip the stress print block under mode 5 to keep the .dat clean
        # for parse_buckle_eigenvalues().
        if bc_mode != "buckle_comp":
            f.write("*EL PRINT, ELSET=PLATE\nS\n")
            if solver == 'ccx_umat':
                # Dump all 14 SDVs so _parse_ccx_umat_sdv can lift the max
                # damage variables. CCX writes these under the
                # "internal state variables" block that the parser keys off.
                f.write("*EL PRINT, ELSET=PLATE\nSDV\n")
        f.write("*END STEP\n")


# =============================================================================
# Stress parsing (from batch_100k.py)
# =============================================================================
def parse_buckle_eigenvalues(dat_path, n_expected=N_BUCKLE_EIGENVALUES):
    """Parse CCX *BUCKLE eigenvalue output from a .dat file.

    CCX writes a block of the form:

        B U C K L I N G   F A C T O R   O U T P U T

         MODE NO       BUCKLING
                        FACTOR

              1   0.9153538E+00
              2   0.1126419E+01
              ...

    Note the header word "FACTOR" is wrapped onto its own line — CCX splits
    the column header across two physical lines. The parser therefore keys
    only off the "B U C K L I N G" spaced-letters banner as the block start,
    then skips any non-numeric lines until it finds rows whose first token
    parses as an int (the mode number) and second token parses as a float
    (the eigenvalue / load multiplier).

    Returns a list of eigenvalues right-padded with zeros up to ``n_expected``
    so downstream CSV writers see a fixed-width column set.
    """
    eigs = []
    if not os.path.exists(dat_path):
        return [0.0] * n_expected
    in_block = False
    with open(dat_path, encoding='latin-1') as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            low = stripped.lower()
            # Block start: CCX banner uses spaced letters "B U C K L I N G".
            if ('b u c k l i n g' in low) or ('buckling factor output' in low):
                in_block = True
                continue
            if not in_block:
                continue
            toks = stripped.split()
            if len(toks) >= 2:
                try:
                    mode_no = int(toks[0])
                    eig = float(toks[1].replace('D', 'E'))
                except ValueError:
                    # Header line ("MODE NO", "FACTOR", etc.) — keep scanning.
                    continue
                eigs.append(eig)
                if len(eigs) >= n_expected:
                    break
    if len(eigs) < n_expected:
        eigs.extend([0.0] * (n_expected - len(eigs)))
    return eigs[:n_expected]


def parse_stresses(dat_path):
    stress_data = []
    in_block = False
    with open(dat_path, encoding='latin-1') as f:
        for line in f:
            if 'stresses (elem' in line:
                in_block = True
                continue
            if in_block:
                parts = line.split()
                if len(parts) >= 8:
                    try:
                        eid = int(parts[0])
                        ip = int(parts[1])
                        s11 = float(parts[2])
                        s22 = float(parts[3])
                        s33 = float(parts[4])
                        s12 = float(parts[5])
                        s13 = float(parts[6])
                        s23 = float(parts[7])
                        stress_data.append((eid, ip, s11, s22, s33, s12, s13, s23))
                    except (ValueError, IndexError):
                        if any(kw in line.lower() for kw in ['displacements', 'forces', 'step']):
                            in_block = False
    return stress_data


def percentile(sorted_list, p):
    if not sorted_list:
        return 0.0
    k = (len(sorted_list) - 1) * p
    f_idx = int(k)
    c_idx = min(f_idx + 1, len(sorted_list) - 1)
    d = k - f_idx
    return sorted_list[f_idx] + d * (sorted_list[c_idx] - sorted_list[f_idx])


# =============================================================================
# 2.7 Extended Failure Criteria
# =============================================================================
def compute_metrics(stress_data, element_centroids, defects, mat,
                     geometry="flat", panel_radius=200, full_field=False):
    if not stress_data:
        return None

    XT = float(mat['XT'])
    XC = float(mat['XC'])
    YT = float(mat['YT'])
    YC = float(mat['YC'])
    SL = float(mat['SL'])
    ST = YC / (2.0 * math.tan(math.radians(53)))  # Puck fracture plane approximation

    # Puck parameters (typical values per Puck 2002)
    p_perp_par_plus = 0.30
    p_perp_par_minus = 0.25

    # Puck derived quantities (material-dependent, computed once)
    if SL > 1e-9:
        R_A_perp_perp = SL / (2.0 * p_perp_par_minus) * (math.sqrt(1.0 + 2.0 * p_perp_par_minus * YC / SL) - 1.0)
        p_perp_perp_minus = p_perp_par_minus * R_A_perp_perp / SL
        tau_21c = SL * math.sqrt(1.0 + 2.0 * p_perp_par_minus * YC / SL)
    else:
        R_A_perp_perp = 1e-9
        p_perp_perp_minus = 0.25
        tau_21c = 1e-9

    # LaRC05 in-situ correction
    YT_is = 1.12 * math.sqrt(2) * YT

    # Tsai-Wu coefficients
    F1 = 1.0/XT - 1.0/XC
    F2 = 1.0/YT - 1.0/YC
    F11 = 1.0/(XT * XC)
    F22 = 1.0/(YT * YC)
    F66 = 1.0/(SL * SL)
    F12 = -0.5 * math.sqrt(F11 * F22)

    all_s11, all_s12 = [], []
    all_tw, all_hft, all_hfc, all_hmt, all_hmc = [], [], [], [], []
    all_puck_ff, all_puck_iff_a, all_puck_iff_b, all_puck_iff_c = [], [], [], []
    all_larc_ft, all_larc_fc, all_larc_mt = [], [], []
    elem_tw = {}  # per-element max Tsai-Wu (physically meaningful for composites)
    # Per-element field data (for HDF5 full-field output)
    if full_field:
        elem_fields = {}  # {eid: [max_s11, max_s22, max_s12, max_tw, max_hft, max_puck_ff, max_larc_ft]}

    for eid, ip, s11, s22, s33, s12, s13, s23 in stress_data:
        # Skip non-finite stress values (solver blow-up)
        if not (math.isfinite(s11) and math.isfinite(s22) and math.isfinite(s33)
                and math.isfinite(s12) and math.isfinite(s13) and math.isfinite(s23)):
            continue

        all_s11.append(s11)
        all_s12.append(abs(s12))

        # Tsai-Wu
        tw = F1*s11 + F2*s22 + F11*s11**2 + F22*s22**2 + F66*s12**2 + 2*F12*s11*s22
        all_tw.append(tw)

        # Hashin
        hft = (s11/XT)**2 + (s12/SL)**2 if s11 > 0 else 0.0
        hfc = (s11/XC)**2 if s11 < 0 else 0.0
        hmt = (s22/YT)**2 + (s12/SL)**2 if s22 > 0 else 0.0
        hmc = (s22/(2*ST))**2 + ((YC/(2*ST))**2 - 1)*(s22/YC) + (s12/SL)**2 if s22 < 0 else 0.0
        all_hft.append(hft)
        all_hfc.append(hfc)
        all_hmt.append(hmt)
        all_hmc.append(hmc)

        # Puck fibre failure
        puck_ff = abs(s11) / (XT if s11 >= 0 else XC)
        all_puck_ff.append(puck_ff)

        # Puck IFF (inter-fibre failure)
        if s22 >= 0:
            # Mode A
            denom_SL = SL if abs(SL) > 1e-9 else 1e-9
            denom_YT = YT if abs(YT) > 1e-9 else 1e-9
            iff_a = math.sqrt((s12/denom_SL)**2 + (1 - p_perp_par_plus*denom_YT/denom_SL)**2 * (s22/denom_YT)**2) + p_perp_par_plus*s22/denom_SL
            all_puck_iff_a.append(iff_a)
            all_puck_iff_b.append(0.0)
            all_puck_iff_c.append(0.0)
        else:
            s12_abs = abs(s12)
            s22_abs = abs(s22)
            # Mode B vs C threshold per Puck 2002: |s22/s12| <= R_A_perp_perp / tau_21c
            if s12_abs > 1e-9 and s22_abs / s12_abs <= R_A_perp_perp / tau_21c:
                # Mode B — shear dominated transverse compression
                denom_SL = SL if SL > 1e-9 else 1e-9
                iff_b = (1.0/denom_SL) * (math.sqrt(s12**2 + (p_perp_par_minus*s22)**2) + p_perp_par_minus*s22)
                all_puck_iff_a.append(0.0)
                all_puck_iff_b.append(iff_b)
                all_puck_iff_c.append(0.0)
            else:
                # Mode C (wedge fracture) — Puck 2002, uses p_perp_perp_minus
                denom_YC = YC if YC > 1e-9 else 1e-9
                denom_SL = SL if SL > 1e-9 else 1e-9
                iff_c = ((s12/(2*(1+p_perp_perp_minus)*denom_SL))**2 + (s22/denom_YC)**2) * (denom_YC/s22_abs) if s22_abs > 1e-9 else 0.0
                all_puck_iff_a.append(0.0)
                all_puck_iff_b.append(0.0)
                all_puck_iff_c.append(iff_c)

        # LaRC05 (Pinho et al. 2005, Composites Part A)
        denom_YT_is = YT_is if abs(YT_is) > 1e-9 else 1e-9
        denom_SL2 = SL if abs(SL) > 1e-9 else 1e-9
        # Fiber tension: max stress with shear interaction
        if s11 > 0:
            larc_ft_val = (s11/XT) + (s12/SL)**2
        else:
            larc_ft_val = 0.0
        # Fiber compression: kinking-based criterion (simplified Pinho/Davila)
        # Misalignment angle phi0 ≈ SL/G12 (initial fiber waviness, ~1-2 deg)
        if s11 < 0 and abs(SL) > 1e-9:
            G12_val = float(mat['G12'])
            phi0 = SL / G12_val if G12_val > 1e-9 else 0.02
            # Stress in misaligned frame
            s22m = s11 * phi0**2 + s22 + 2 * abs(s12) * phi0
            s12m = abs(s11 * phi0) + abs(s12)
            # Matrix failure in kink band (Puck-like on misaligned stresses)
            if s22m >= 0:
                larc_fc_val = (s22m / denom_YT_is)**2 + (s12m / SL)**2
            else:
                larc_fc_val = (s12m / (SL - p_perp_par_minus * s22m))**2
        else:
            larc_fc_val = 0.0
        # Matrix tension with in-situ correction
        larc_mt_val = (s22/denom_YT_is)**2 + (s12/denom_SL2)**2 if s22 > 0 else 0.0
        all_larc_ft.append(larc_ft_val)
        all_larc_fc.append(larc_fc_val)
        all_larc_mt.append(larc_mt_val)

        if eid not in elem_tw:
            elem_tw[eid] = []
        elem_tw[eid].append(tw)

        if full_field:
            if eid not in elem_fields:
                elem_fields[eid] = [0.0] * 7  # s11, s22, s12, tw, hft, puck_ff, larc_ft
            ef = elem_fields[eid]
            ef[0] = max(ef[0], abs(s11))
            ef[1] = max(ef[1], abs(s22))
            ef[2] = max(ef[2], abs(s12))
            ef[3] = max(ef[3], tw)
            ef[4] = max(ef[4], hft)
            ef[5] = max(ef[5], puck_ff)
            ef[6] = max(ef[6], larc_ft_val)

    # Guard: if all stresses were non-finite, no valid data remains
    if not all_s11:
        return None

    # Aggregate
    all_s11_s = sorted(all_s11)
    all_s12_s = sorted(all_s12)

    # Stress values: use 99.9th percentile to handle mesh singularities
    max_s11 = percentile(all_s11_s, 0.999)
    min_s11 = all_s11_s[0]
    max_s12 = percentile(all_s12_s, 0.999)

    # Failure indices: use 99.9th percentile to filter mesh singularities at crack tips.
    # True max() is dominated by a single integration point at the crack-tip singularity,
    # giving unphysically high values. 99.9th percentile captures the near-tip damage zone
    # while being robust to mesh-dependent stress artifacts.
    all_tw_s = sorted(all_tw)
    tsai_wu_index = percentile(all_tw_s, 0.999)

    max_hft = percentile(sorted(all_hft), 0.999)
    max_hfc = percentile(sorted(all_hfc), 0.999)
    max_hmt = percentile(sorted(all_hmt), 0.999)
    max_hmc = percentile(sorted(all_hmc), 0.999)

    max_puck_ff = percentile(sorted(all_puck_ff), 0.999)
    max_puck_iff_a = percentile(sorted(all_puck_iff_a), 0.999)
    max_puck_iff_b = percentile(sorted(all_puck_iff_b), 0.999)
    max_puck_iff_c = percentile(sorted(all_puck_iff_c), 0.999)

    max_larc_ft = percentile(sorted(all_larc_ft), 0.999)
    max_larc_fc = percentile(sorted(all_larc_fc), 0.999)
    max_larc_mt = percentile(sorted(all_larc_mt), 0.999)

    # Per-defect max Tsai-Wu index (localized damage severity)
    tw_per_defect = []
    for di in range(MAX_DEFECTS):
        if di < len(defects):
            d = defects[di]
            dcx, dcy = d['x'], d['y']
            if geometry == "curved":
                # Project defect 2D coords to 3D curved surface
                R = panel_radius
                theta_c = dcx / R
                dc3d = (dcy, R * math.sin(theta_c), R * math.cos(theta_c) - R)
            else:
                dc3d = (dcx, dcy, 0.0)
            local_max = 0.0
            for eid, tw_list in elem_tw.items():
                if eid in element_centroids:
                    ec = element_centroids[eid]
                    dist = math.sqrt((ec[0]-dc3d[0])**2 + (ec[1]-dc3d[1])**2 + (ec[2]-dc3d[2])**2)
                    if dist <= CRACK_SEARCH_BUFFER + d['half_length']:
                        for tw_val in tw_list:
                            if tw_val > local_max:
                                local_max = tw_val
            tw_per_defect.append(local_max)
        else:
            tw_per_defect.append(0.0)

    result = {
        'n_elements': len(set(eid for eid, *_ in stress_data)),
        'max_s11': max_s11, 'min_s11': min_s11, 'max_s12': max_s12,
        'tsai_wu_index': tsai_wu_index,
        'max_hashin_ft': max_hft, 'max_hashin_fc': max_hfc,
        'max_hashin_mt': max_hmt, 'max_hashin_mc': max_hmc,
        'puck_ff': max_puck_ff, 'puck_iff_a': max_puck_iff_a,
        'puck_iff_b': max_puck_iff_b, 'puck_iff_c': max_puck_iff_c,
        'larc_ft': max_larc_ft, 'larc_fc': max_larc_fc, 'larc_mt': max_larc_mt,
        'tw_per_defect': tw_per_defect,
        'failed_tsai_wu': 1 if tsai_wu_index >= 1.0 else 0,
        'failed_hashin': 1 if (max_hft >= 1.0 or max_hfc >= 1.0 or max_hmt >= 1.0 or max_hmc >= 1.0) else 0,
        'failed_puck': 1 if (max_puck_ff >= 1.0 or max_puck_iff_a >= 1.0 or max_puck_iff_b >= 1.0 or max_puck_iff_c >= 1.0) else 0,
        'failed_larc': 1 if (max_larc_ft >= 1.0 or max_larc_fc >= 1.0 or max_larc_mt >= 1.0) else 0,
    }
    if full_field:
        result['elem_fields'] = elem_fields
        result['element_centroids'] = element_centroids
    return result


def compute_element_centroids(nodes, elements):
    """Compute element centroids. Returns dict {eid: (x, y, z)}."""
    centroids = {}
    for eid, npe, enlist in elements:
        xs, ys, zs = [], [], []
        for nid in enlist:
            if nid in nodes:
                xs.append(nodes[nid][0])
                ys.append(nodes[nid][1])
                zs.append(nodes[nid][2] if len(nodes[nid]) > 2 else 0.0)
        if xs:
            centroids[eid] = (sum(xs)/len(xs), sum(ys)/len(ys), sum(zs)/len(zs))
    return centroids


def compute_min_inter_defect_dist(defects):
    if len(defects) < 2:
        return 0.0
    min_dist = float('inf')
    for i in range(len(defects)):
        for j in range(i+1, len(defects)):
            d = math.sqrt((defects[i]['x']-defects[j]['x'])**2 + (defects[i]['y']-defects[j]['y'])**2)
            if d < min_dist:
                min_dist = d
    return min_dist


def compute_defect_features(d, pressure_x, pressure_y):
    x, y = d['x'], d['y']
    hl = d['half_length']
    w = d['width']
    angle_rad = math.radians(d['angle'])
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    aspect_ratio = hl / w if w > 1e-9 else 0.0
    norm_x = x / PLATE_L
    norm_y = y / PLATE_W
    norm_length = (2*hl) / PLATE_W
    boundary_prox = min(x, PLATE_L-x, y, PLATE_W-y)
    crack_proj = 2 * hl * abs(sin_a)
    ligament_ratio = max(0.0, (PLATE_W - crack_proj) / PLATE_W)
    sigma = abs(pressure_x * sin_a**2 + pressure_y * cos_a**2)
    a = hl
    a_over_W = (2*a) / PLATE_W
    if a_over_W < 0.95:
        F_corr = (1.0 - 0.025*a_over_W**2 + 0.06*a_over_W**4) / math.sqrt(math.cos(math.pi * a_over_W / 2))
    else:
        F_corr = 5.0
    sif = sigma * math.sqrt(math.pi * a) * F_corr
    return {
        'cos_angle': round(cos_a, 6), 'sin_angle': round(sin_a, 6),
        'aspect_ratio': round(aspect_ratio, 6), 'norm_x': round(norm_x, 6),
        'norm_y': round(norm_y, 6), 'norm_length': round(norm_length, 6),
        'boundary_prox': round(boundary_prox, 6), 'ligament_ratio': round(ligament_ratio, 6),
        'sif_estimate': round(sif, 6),
    }


# =============================================================================
# CSV I/O
# =============================================================================
def load_completed_sims(csv_path):
    completed = set()
    if not os.path.exists(csv_path):
        return completed
    try:
        with open(csv_path, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    completed.add(int(row['sim_id']))
                except (ValueError, KeyError):
                    pass
    except Exception:
        pass
    return completed


def write_csv_header(csv_path):
    if not os.path.exists(csv_path):
        with open(csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNS)


def append_csv_row(csv_path, row_dict):
    row = [row_dict.get(col, 0) for col in CSV_COLUMNS]
    import io
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(row)
    line = buf.getvalue()
    with open(csv_path, 'a', newline='') as f:
        _lock_file(f)
        try:
            f.write(line)
        finally:
            _unlock_file(f)


def build_row(sim_id, sample, mat, metrics=None, error=False, n_elements=0,
              buckle_eigs=None, umat_sdv=None):
    row = {'sim_id': sim_id}
    row['material_id'] = sample['material_id']
    row['material_name'] = MATERIALS[sample['material_id']]['name']
    row['layup_id'] = sample['layup_id']
    row['layup_name'] = LAYUPS[sample['layup_id']]['name']
    row['solver'] = sample.get('solver', 'ccx_stock')
    row['bc_mode'] = sample['bc_mode']
    row['geometry'] = sample['geometry']
    row['mesh_level'] = sample['mesh_level']

    angles = LAYUPS[sample['layup_id']]['angles']
    row['n_plies'] = len(angles)

    # Lamination parameters
    lp = compute_lamination_params(angles, sample['ply_thickness'])
    for i, name in enumerate(['V1A','V2A','V3A','V4A','V1D','V2D','V3D','V4D']):
        row[name] = round(lp[i], 6)

    row['n_defects'] = sample['n_defects']

    all_sifs, all_ligaments = [], []
    total_crack_area = 0.0

    for di in range(MAX_DEFECTS):
        prefix = f"defect{di+1}_"
        if di < len(sample['defects']):
            d = sample['defects'][di]
            row[prefix+'x'] = round(d['x'], 6)
            row[prefix+'y'] = round(d['y'], 6)
            row[prefix+'half_length'] = round(d['half_length'], 6)
            row[prefix+'width'] = round(d['width'], 6)
            row[prefix+'angle'] = round(d['angle'], 6)
            row[prefix+'roughness'] = round(d['roughness'], 6)
            feats = compute_defect_features(d, sample['pressure_x'], sample['pressure_y'])
            for fname, fval in feats.items():
                row[prefix+fname] = fval
            all_sifs.append(feats['sif_estimate'])
            all_ligaments.append(feats['ligament_ratio'])
            total_crack_area += d['half_length'] * d['width'] * 2
        else:
            for field in ['x','y','half_length','width','angle','roughness',
                          'cos_angle','sin_angle','aspect_ratio','norm_x','norm_y',
                          'norm_length','boundary_prox','ligament_ratio','sif_estimate']:
                row[prefix+field] = 0

    row['pressure_x'] = round(sample['pressure_x'], 6)
    row['pressure_y'] = round(sample['pressure_y'], 6)
    row['ply_thickness'] = round(sample['ply_thickness'], 6)
    row['min_inter_defect_dist'] = round(compute_min_inter_defect_dist(sample['defects']), 6)

    plate_area = PLATE_L * PLATE_W
    row['total_crack_area_frac'] = round(total_crack_area / plate_area, 6)
    row['max_sif_estimate'] = round(max(all_sifs) if all_sifs else 0.0, 6)
    row['min_ligament_ratio'] = round(min(all_ligaments) if all_ligaments else 1.0, 6)

    # Geometry-specific
    row['hole_diameter'] = round(sample.get('hole_diameter', 0), 6)
    row['hole_x'] = round(sample.get('hole_x', 0), 6)
    row['hole_y'] = round(sample.get('hole_y', 0), 6)
    row['panel_radius'] = round(sample.get('panel_radius', 0), 6)

    if error or metrics is None:
        row['solver_completed'] = 'ERROR'
        row['n_elements'] = n_elements
        for col in ['max_s11','min_s11','max_s12','tsai_wu_index',
                     'max_hashin_ft','max_hashin_fc','max_hashin_mt','max_hashin_mc',
                     'puck_ff','puck_iff_a','puck_iff_b','puck_iff_c',
                     'larc_ft','larc_fc','larc_mt']:
            row[col] = 0
        for di in range(MAX_DEFECTS):
            row[f'max_tsai_wu_defect{di+1}'] = 0
        row['failed_tsai_wu'] = 0
        row['failed_hashin'] = 0
        row['failed_puck'] = 0
        row['failed_larc'] = 0
        row['post_fpf'] = 0
    else:
        row['solver_completed'] = 'YES'
        row['n_elements'] = metrics['n_elements']
        for key in ['max_s11','min_s11','max_s12','tsai_wu_index',
                     'max_hashin_ft','max_hashin_fc','max_hashin_mt','max_hashin_mc',
                     'puck_ff','puck_iff_a','puck_iff_b','puck_iff_c',
                     'larc_ft','larc_fc','larc_mt']:
            row[key] = round(metrics[key], 6)
        for di in range(MAX_DEFECTS):
            row[f'max_tsai_wu_defect{di+1}'] = round(metrics['tw_per_defect'][di], 6)
        row['failed_tsai_wu'] = metrics['failed_tsai_wu']
        row['failed_hashin'] = metrics['failed_hashin']
        row['failed_puck'] = metrics['failed_puck']
        row['failed_larc'] = metrics['failed_larc']
        row['post_fpf'] = 1 if any([
            metrics['failed_tsai_wu'], metrics['failed_hashin'],
            metrics['failed_puck'], metrics['failed_larc']
        ]) else 0

    # Buckle eigenvalues — zero-fill for non-buckle modes, write the parsed
    # eigenvalues for mode 5. This keeps the CSV schema fixed-width.
    eigs = buckle_eigs if buckle_eigs else [0.0] * N_BUCKLE_EIGENVALUES
    for i in range(N_BUCKLE_EIGENVALUES):
        val = eigs[i] if i < len(eigs) else 0.0
        row[f'buckle_eig_{i+1}'] = round(float(val), 6)

    # UMAT damage SDV read-out — zero-fill for non-UMAT solvers, write the
    # parsed max damage variables (d_ft, d_fc, d_mt, d_mc) and increment
    # count for ccx_umat runs. Keeps the CSV schema fixed-width so CSV
    # readers do not have to branch on solver.
    if umat_sdv is None:
        umat_sdv = (0, 0.0, 0.0, 0.0, 0.0)
    row['umat_n_increments'] = int(umat_sdv[0])
    row['umat_d_ft_max'] = round(float(umat_sdv[1]), 6)
    row['umat_d_fc_max'] = round(float(umat_sdv[2]), 6)
    row['umat_d_mt_max'] = round(float(umat_sdv[3]), 6)
    row['umat_d_mc_max'] = round(float(umat_sdv[4]), 6)

    return row


def write_hdf5_fields(sim_id, metrics, hdf5_dir):
    """Write per-element field data to an individual HDF5 file.

    Creates hdf5_dir/sim_{id}.h5 with datasets:
      centroids: (N, 3) float32 — element centroid x,y,z
      fields: (N, 7) float32 — max |s11|, |s22|, |s12|, TW, Hashin_FT, Puck_FF, LaRC_FT
      elem_ids: (N,) int32 — element IDs
    Field columns: [abs_s11, abs_s22, abs_s12, tsai_wu, hashin_ft, puck_ff, larc_ft]
    """
    if not HAS_HDF5 or not metrics.get('elem_fields'):
        return
    ef = metrics['elem_fields']
    ec = metrics['element_centroids']
    eids = sorted(ef.keys())
    if not eids:
        return

    n = len(eids)
    centroids_arr = np.zeros((n, 3), dtype=np.float32)
    fields_arr = np.zeros((n, 7), dtype=np.float32)
    eid_arr = np.array(eids, dtype=np.int32)

    for i, eid in enumerate(eids):
        if eid in ec:
            centroids_arr[i] = ec[eid]
        fields_arr[i] = ef[eid]

    try:
        block_dir = os.path.join(hdf5_dir, f"block_{sim_id // 1000}")
        os.makedirs(block_dir, exist_ok=True)
        fpath = os.path.join(block_dir, f"sim_{sim_id}.h5")
        with h5py.File(fpath, 'w') as hf:
            hf.create_dataset('elem_ids', data=eid_arr, compression='gzip', compression_opts=1)
            hf.create_dataset('centroids', data=centroids_arr, compression='gzip', compression_opts=1)
            hf.create_dataset('fields', data=fields_arr, compression='gzip', compression_opts=1)
    except Exception:
        pass  # Don't fail the sim if HDF5 write fails


# =============================================================================
# Worker — runs ONE simulation
# =============================================================================
def run_single_sim(args):
    sim_id, sample, polygons = args
    job_name = f"cnet_sim{sim_id}"
    mat = MATERIALS[sample['material_id']]
    solver = sample.get('solver', 'ccx_stock')
    t0 = time.time()

    # Solver dispatch (task #18): OR and Aster backends are not yet wired
    # into this batch runner — emit a clearly-marked error row so the CSV
    # stays schema-consistent and the failure-rate watchdog treats them
    # correctly without having to special-case NOT_IMPLEMENTED states.
    if solver in ('or', 'aster'):
        return build_row(sim_id, sample, mat, error=True)

    # Pick the CCX binary based on the solver string. Stock CCX is the
    # 2.23 Win/Linux build; ccx_umat is a 2.21 build with the Hashin-
    # fatigue UMAT linked in.
    if solver == 'ccx_umat':
        ccx_binary = CCX_UMAT_EXE
    else:
        ccx_binary = CCX_EXE

    if polygons is None:
        return build_row(sim_id, sample, mat, error=True)

    tmp_dir = tempfile.mkdtemp(prefix=f"cnet_{sim_id}_", dir=WORK_DIR)

    try:
        result = create_plate_with_cracks(
            polygons, job_name,
            geometry=sample['geometry'], mesh_level=sample['mesh_level'],
            hole_diameter=sample.get('hole_diameter', 0),
            hole_x=sample.get('hole_x', 0),
            hole_y=sample.get('hole_y', 0),
            panel_radius=sample.get('panel_radius', 200),
        )
        if result[0] is None:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return build_row(sim_id, sample, mat, error=True)
        nodes, elements, bc_sets = result
        n_elements = len(elements)
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return build_row(sim_id, sample, mat, error=True)

    case = {
        'sim_id': sim_id,
        'material_id': sample['material_id'],
        'layup_id': sample['layup_id'],
        'bc_mode': sample['bc_mode'],
        'pressure_x': sample['pressure_x'],
        'pressure_y': sample['pressure_y'],
        'ply_thickness': sample['ply_thickness'],
        'solver': solver,
    }
    write_ccx_inp(nodes, elements, bc_sets, case, job_name, tmp_dir,
                   geometry=sample['geometry'],
                   panel_radius=sample.get('panel_radius', 200))

    try:
        solver_timeout = UMAT_SOLVER_TIMEOUT if solver == 'ccx_umat' else SOLVER_TIMEOUT
        subprocess.run(
            [ccx_binary, job_name],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=solver_timeout, cwd=tmp_dir)
        dat_check = os.path.join(tmp_dir, f"{job_name}.dat")
        if not os.path.exists(dat_check) or os.path.getsize(dat_check) < 100:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return build_row(sim_id, sample, mat, error=True, n_elements=n_elements)
        # Check .sta file for solver warnings (convergence issues, singularities)
        sta_path = os.path.join(tmp_dir, f"{job_name}.sta")
        if os.path.exists(sta_path):
            try:
                with open(sta_path, 'r') as sf:
                    sta_text = sf.read()
                for keyword in ('WARNING', 'ERROR', 'singular', 'diverge', 'no convergence'):
                    if keyword.lower() in sta_text.lower():
                        log(f"  WARN: sim {sim_id} .sta contains '{keyword}': {sta_path}")
                        break
            except Exception:
                pass
    except (subprocess.TimeoutExpired, Exception):
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return build_row(sim_id, sample, mat, error=True, n_elements=n_elements)

    dat_path = os.path.join(tmp_dir, f"{job_name}.dat")

    # BC mode 5 (*BUCKLE): the .dat file contains buckling eigenvalues but
    # no *EL PRINT stress block, so skip the standard stress path entirely
    # and populate only the buckle_eig_* columns. Failure indices and stress
    # extremes are left at zero for this mode (static-stress semantics do
    # not apply to a linear eigenvalue problem).
    if sample['bc_mode'] == "buckle_comp":
        try:
            eigs = parse_buckle_eigenvalues(dat_path)
        except Exception:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return build_row(sim_id, sample, mat, error=True, n_elements=n_elements)
        # A successful *BUCKLE run must yield at least one positive eigenvalue;
        # if we got nothing, treat it as a solver error so the failed-sim
        # bookkeeping stays consistent.
        if not any(e > 0.0 for e in eigs):
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return build_row(sim_id, sample, mat, error=True,
                             n_elements=n_elements, buckle_eigs=eigs)
        row = build_row(sim_id, sample, mat, metrics=None, error=False,
                        n_elements=n_elements, buckle_eigs=eigs)
        # Override solver_completed="ERROR" that build_row sets for metrics=None.
        row['solver_completed'] = 'YES'
        row['n_elements'] = n_elements
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return row

    try:
        stress_data = parse_stresses(dat_path)
        if not stress_data:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return build_row(sim_id, sample, mat, error=True, n_elements=n_elements)
        element_centroids = compute_element_centroids(nodes, elements)
        metrics = compute_metrics(stress_data, element_centroids, sample['defects'], mat,
                                   geometry=sample['geometry'],
                                   panel_radius=sample.get('panel_radius', 200),
                                   full_field=SAVE_HDF5)
        if metrics is None:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return build_row(sim_id, sample, mat, error=True, n_elements=n_elements)
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return build_row(sim_id, sample, mat, error=True, n_elements=n_elements)

    # UMAT SDV read-out (task #19): parse max damage variables (d_ft, d_fc,
    # d_mt, d_mc) from the SDV block the *EL PRINT card emits. Zero-filled
    # for stock CCX runs since they don't have user state variables.
    umat_sdv = None
    if solver == 'ccx_umat':
        try:
            with open(dat_path, 'r', encoding='latin-1') as f:
                dat_text = f.read()
            umat_sdv = _parse_ccx_umat_sdv(dat_text)
        except Exception:
            umat_sdv = (0, 0.0, 0.0, 0.0, 0.0)

    # Write full-field HDF5 data if enabled
    if SAVE_HDF5 and HDF5_PATH:
        write_hdf5_fields(sim_id, metrics, HDF5_PATH)

    row = build_row(sim_id, sample, mat, metrics=metrics, n_elements=n_elements,
                    umat_sdv=umat_sdv)
    shutil.rmtree(tmp_dir, ignore_errors=True)
    return row


# =============================================================================
# Sample generation
# =============================================================================
def _combo_seed(base_seed, mat_id, layup_id, bc_id):
    """Derive a deterministic per-combo seed from the base seed and combo IDs.

    This ensures that the same (material, layup, BC) combo generates identical
    physical configurations (defects, loads) regardless of what other combos are
    in the batch. Critical for mesh convergence studies: running the same combo
    at coarse/medium/fine mesh produces directly comparable results.
    """
    # Use a simple mixing function; values are small ints so collisions are impossible
    return base_seed * 1000000 + mat_id * 10000 + layup_id * 100 + bc_id


def generate_samples(material_ids, layup_ids, bc_ids, geometry, mesh_level,
                     sims_per_combo, seed=2026, solver_ids=None):
    """Generate all sample configurations.

    Uses per-combo seeding: each (material, layup, BC) combination gets its own
    deterministic LHS sample and defect RNG stream. This ensures identical physical
    configurations across mesh levels for mesh convergence studies.

    If ``solver_ids`` is provided (list of solver dispatch ints from SOLVERS),
    the solver is rotated across samples in each combo so every (mat, layup, BC)
    bin gets an even split of solver labels. This is the simplest per-combo
    mirror distribution and keeps the sims_per_combo count exact for round
    multiples — if sims_per_combo is not divisible by len(solver_ids), the
    remainder samples fall on the first solver in the list.
    """
    if solver_ids is None or not solver_ids:
        solver_ids = [DEFAULT_SOLVER_ID]
    combos = list(itertools.product(material_ids, layup_ids, bc_ids))
    total_sims = len(combos) * sims_per_combo
    log(f"  Combinations: {len(combos)} (mats={len(material_ids)} x layups={len(layup_ids)} x bcs={len(bc_ids)})")
    log(f"  Sims per combo: {sims_per_combo}")
    log(f"  Solvers: {[SOLVERS[i] for i in solver_ids]}")
    log(f"  Total sims: {total_sims}")

    # Build parameter ranges (geometry-dependent)
    ranges = dict(GLOBAL_RANGES)
    if geometry == "cutout":
        ranges.update(CUTOUT_RANGES)
    elif geometry == "curved":
        ranges.update(CURVED_RANGES)

    all_samples = []

    for mat_id, layup_id, bc_id in combos:
        # Per-combo seed ensures identical samples across mesh tiers
        cseed = _combo_seed(seed, mat_id, layup_id, bc_id)
        combo_samples = lhs_sample(ranges, sims_per_combo, seed=cseed)
        random.seed(cseed)

        for s in range(sims_per_combo):
            gs = combo_samples[s]

            # Place defects (all geometries — curved cracks projected onto surface)
            n_def_target = random.randint(1, MAX_DEFECTS)
            n_def = n_def_target
            defects = place_defects_sequentially(n_def_target)
            if defects is None:
                placed = False
                for fallback_n in range(n_def_target - 1, 0, -1):
                    defects = place_defects_sequentially(fallback_n)
                    if defects is not None:
                        log(f"  WARN: defect placement fell back {n_def_target}->{fallback_n} for combo ({mat_id},{layup_id},{bc_id}) sim {s}")
                        n_def = fallback_n
                        placed = True
                        break
                if not placed:
                    log(f"  WARN: defect placement failed entirely (target={n_def_target}) for combo ({mat_id},{layup_id},{bc_id}) sim {s}")
                    defects = []
                    n_def = 0

            # Per-material/layup pressure scaling
            px_lo, px_hi = MATERIAL_PRESSURE_RANGES[mat_id]
            layup_scale = LAYUP_SCALE_FACTORS[layup_id]
            px_lo_scaled = px_lo * layup_scale
            px_hi_scaled = px_hi * layup_scale

            # Cutout geometry: reduce pressure to account for SCF at hole edge
            if geometry == "cutout":
                px_lo_scaled *= CUTOUT_PRESSURE_FACTOR
                px_hi_scaled *= CUTOUT_PRESSURE_FACTOR

            pressure_x = px_lo_scaled + gs['pressure_x_frac'] * (px_hi_scaled - px_lo_scaled)
            # Y-pressure: proper CLT-based scaling (same approach as X)
            py_lo, py_hi = MATERIAL_PRESSURE_RANGES_Y[mat_id]
            layup_scale_y = LAYUP_SCALE_FACTORS_Y[layup_id]
            py_lo_scaled = py_lo * layup_scale_y
            py_hi_scaled = py_hi * layup_scale_y
            if geometry == "cutout":
                py_lo_scaled *= CUTOUT_PRESSURE_FACTOR
                py_hi_scaled *= CUTOUT_PRESSURE_FACTOR
            pressure_y = gs['pressure_y_frac'] * py_hi_scaled

            # Rotate solver across samples within a combo so every combo
            # gets a balanced split between the requested backends.
            solver_name = SOLVERS[solver_ids[s % len(solver_ids)]]

            sample = {
                'material_id': mat_id,
                'layup_id': layup_id,
                'bc_mode': BC_MODES[bc_id],
                'geometry': geometry,
                'mesh_level': mesh_level,
                'n_defects': n_def,
                'pressure_x': pressure_x,
                'pressure_y': pressure_y,
                'ply_thickness': gs['ply_thickness'],
                'defects': defects,
                'solver': solver_name,
            }

            if geometry == "cutout":
                sample['hole_diameter'] = gs['hole_diameter']
                sample['hole_x'] = gs['hole_x_frac'] * PLATE_L
                sample['hole_y'] = gs['hole_y_frac'] * PLATE_W
                # Remove defects that overlap with the hole
                hole_r = gs['hole_diameter'] / 2.0
                hx, hy = sample['hole_x'], sample['hole_y']
                margin = 2.0
                filtered = []
                for d in defects:
                    dist = math.sqrt((d['x'] - hx)**2 + (d['y'] - hy)**2)
                    if dist > hole_r + d['half_length'] + margin:
                        filtered.append(d)
                if len(filtered) < len(defects):
                    log(f"  INFO: removed {len(defects)-len(filtered)} defect(s) overlapping hole")
                defects = filtered
                sample['defects'] = defects
                sample['n_defects'] = len(defects)
            elif geometry == "curved":
                sample['panel_radius'] = gs['radius']

            all_samples.append(sample)

    random.seed(seed + 999)
    random.shuffle(all_samples)
    return all_samples


def generate_polygons(all_samples, seed=2026):
    """Generate crack polygons for all samples.

    Uses per-defect seeding derived from defect parameters so that the same
    physical defect always produces the same rough crack shape, regardless of
    sample ordering or what other samples are in the batch. This is critical
    for mesh convergence studies where identical crack geometries must be meshed
    at different fidelity levels.
    """
    all_polygons = []
    failures = 0
    for sample in all_samples:
        crack_polys = []
        valid = True
        for di, d in enumerate(sample['defects']):
            # Per-defect seed: deterministic from combo + defect parameters
            # int() truncation of float params is fine — just needs to be consistent
            defect_seed = (seed + 7777
                           + sample['material_id'] * 100000
                           + sample['layup_id'] * 1000
                           + int(d['x'] * 100) + int(d['y'] * 100)
                           + int(d['half_length'] * 100) + di)
            random.seed(defect_seed)
            poly = crack_polygon_points(
                d['x'], d['y'], d['half_length'],
                d['width'], d['angle'], d['roughness'])
            if polygon_self_intersects(poly):
                valid = False
                break
            crack_polys.append(poly)
        if valid:
            all_polygons.append(crack_polys)
        else:
            all_polygons.append(None)
            failures += 1
    return all_polygons, failures


# =============================================================================
# CLI argument parsing
# =============================================================================
def parse_range(s):
    """Parse '1-5' or '1,3,5' or '1-3,7-9' into list of ints."""
    result = []
    for part in s.split(','):
        if '-' in part:
            a, b = part.split('-', 1)
            result.extend(range(int(a), int(b)+1))
        else:
            result.append(int(part))
    return sorted(set(result))


def parse_args():
    parser = argparse.ArgumentParser(description="CompositeBench batch runner")
    parser.add_argument('--materials', type=str, default='1',
                        help='Material IDs: "1-22" or "1,5,8" (default: 1)')
    parser.add_argument('--layups', type=str, default='1',
                        help='Layup IDs: "1-35" or "1,3,6" (default: 1)')
    parser.add_argument('--bcs', type=str, default='1',
                        help='BC mode IDs: "1-5" or "1,2" (default: 1)')
    parser.add_argument('--solvers', type=str, default=str(DEFAULT_SOLVER_ID),
                        help=(f'Solver dispatch IDs: "1-4" or "1,2" '
                              f'(1=ccx_stock, 2=ccx_umat, 3=or, 4=aster; '
                              f'default: {DEFAULT_SOLVER_ID})'))
    parser.add_argument('--geometry', type=str, default='flat',
                        choices=['flat', 'cutout', 'curved'],
                        help='Geometry type (default: flat)')
    parser.add_argument('--mesh', type=str, default='medium',
                        choices=['coarse', 'medium', 'fine'],
                        help='Mesh level (default: medium)')
    parser.add_argument('--sims-per-combo', type=int, default=100,
                        help='Simulations per material/layup/BC combo (default: 100)')
    parser.add_argument('--workers', type=int, default=NUM_WORKERS,
                        help=f'Parallel workers (default: {NUM_WORKERS})')
    parser.add_argument('--vm-id', type=int, default=1,
                        help='This VM number (1-indexed, default: 1)')
    parser.add_argument('--vm-total', type=int, default=1,
                        help='Total VMs in campaign (default: 1)')
    parser.add_argument('--test', type=int, default=0,
                        help='Smoke test: run N sims only')
    parser.add_argument('--seed', type=int, default=2026,
                        help='Random seed (default: 2026)')
    parser.add_argument('--output-dir', type=str, default=None,
                        help='Output directory (default: auto)')
    parser.add_argument('--hdf5', action='store_true', default=False,
                        help='Save per-element full-field data to HDF5 (requires h5py, numpy)')
    return parser.parse_args()


# =============================================================================
# Main
# =============================================================================
def main():
    global _log_fh, WORK_DIR, CCX_EXE, SAVE_HDF5, HDF5_PATH

    args = parse_args()

    if args.output_dir:
        WORK_DIR = args.output_dir

    os.makedirs(WORK_DIR, exist_ok=True)

    if args.hdf5:
        if not HAS_HDF5:
            print("ERROR: --hdf5 requires h5py and numpy. Install with: pip install h5py numpy",
                  file=sys.stderr)
            sys.exit(1)
        SAVE_HDF5 = True
        HDF5_PATH = os.path.join(WORK_DIR, f"fields_{args.geometry}_{args.seed}")
        os.makedirs(HDF5_PATH, exist_ok=True)

    material_ids = parse_range(args.materials)
    layup_ids = parse_range(args.layups)
    bc_ids = parse_range(args.bcs)
    solver_ids = parse_range(args.solvers)

    # Validate IDs against known dictionaries
    bad = [m for m in material_ids if m not in MATERIALS]
    if bad:
        print(f"ERROR: Unknown material ID(s): {bad}. Valid: 1-{max(MATERIALS.keys())}", file=sys.stderr)
        sys.exit(1)
    bad = [l for l in layup_ids if l not in LAYUPS]
    if bad:
        print(f"ERROR: Unknown layup ID(s): {bad}. Valid: 1-{max(LAYUPS.keys())}", file=sys.stderr)
        sys.exit(1)
    bad = [b for b in bc_ids if b not in BC_MODES]
    if bad:
        print(f"ERROR: Unknown BC ID(s): {bad}. Valid: 1-{max(BC_MODES.keys())}", file=sys.stderr)
        sys.exit(1)
    bad = [s for s in solver_ids if s not in SOLVERS]
    if bad:
        print(f"ERROR: Unknown solver ID(s): {bad}. Valid: 1-{max(SOLVERS.keys())}", file=sys.stderr)
        sys.exit(1)
    # Warn if the UMAT solver is requested but its binary is missing.
    if 2 in solver_ids and not os.path.exists(CCX_UMAT_EXE):
        print(f"ERROR: --solvers includes 2 (ccx_umat) but binary missing: "
              f"{CCX_UMAT_EXE}", file=sys.stderr)
        sys.exit(1)

    # Validate material strengths are positive (prevent ZeroDivisionError in failure criteria)
    strength_keys = ['XT', 'XC', 'YT', 'YC', 'SL']
    for mid in material_ids:
        m = MATERIALS[mid]
        bad_s = [k for k in strength_keys if m.get(k, 0) <= 0]
        if bad_s:
            print(f"ERROR: Material {mid} ({m['name']}) has non-positive strength(s): "
                  f"{', '.join(f'{k}={m.get(k,0)}' for k in bad_s)}", file=sys.stderr)
            sys.exit(1)

    vm_id = args.vm_id
    vm_total = args.vm_total
    n_workers = args.workers

    tag = f"vm{vm_id}_{args.geometry}_{args.mesh}"
    OUTPUT_CSV = os.path.join(WORK_DIR, f"results_{tag}.csv")
    LOG_FILE = os.path.join(WORK_DIR, f"batch_{tag}.log")
    _log_fh = open(LOG_FILE, 'a')

    try:
        log("="*75)
        log(f"CompositeBench -- VM{vm_id}/{vm_total}")
        log(f"  Materials: {material_ids}")
        log(f"  Layups: {layup_ids}")
        log(f"  BCs: {bc_ids}")
        log(f"  Solvers: {solver_ids} -> {[SOLVERS[i] for i in solver_ids]}")
        log(f"  Geometry: {args.geometry}, Mesh: {args.mesh}")
        log(f"  Sims/combo: {args.sims_per_combo}, Workers: {n_workers}")
        log(f"  Output: {OUTPUT_CSV}")
        log(f"  CCX_EXE:      {CCX_EXE}")
        log(f"  CCX_UMAT_EXE: {CCX_UMAT_EXE}")
        log("="*75)

        if 1 in solver_ids and not os.path.exists(CCX_EXE):
            log(f"ERROR: stock CCX solver not found: {CCX_EXE}")
            return

        # Step 1: Generate samples
        log("\nStep 1: Generating samples...")
        t0 = time.time()
        all_samples = generate_samples(
            material_ids, layup_ids, bc_ids,
            args.geometry, args.mesh, args.sims_per_combo, seed=args.seed,
            solver_ids=solver_ids)
        log(f"  Generated {len(all_samples)} samples in {time.time()-t0:.1f}s")

        # Step 2: VM slicing
        n_total = len(all_samples)
        chunk_size = n_total // vm_total
        start_idx = (vm_id - 1) * chunk_size
        end_idx = n_total if vm_id == vm_total else vm_id * chunk_size
        my_samples = all_samples[start_idx:end_idx]
        log(f"\n  VM{vm_id} slice: samples {start_idx}-{end_idx} ({len(my_samples)} sims)")

        # Step 3: Generate polygons for my slice
        log("\nStep 2: Generating crack polygons...")
        all_polygons, poly_failures = generate_polygons(my_samples, seed=args.seed)
        log(f"  {len(my_samples) - poly_failures} valid, {poly_failures} self-intersecting")

        # Step 4: Resume check
        completed_sims = load_completed_sims(OUTPUT_CSV)
        write_csv_header(OUTPUT_CSV)
        log(f"\nStep 3: Resume check -- {len(completed_sims)} sims already in CSV")

        # Step 5: Build work list
        work_items = []
        for i, sample in enumerate(my_samples):
            sim_id = start_idx + i + 1
            if sim_id in completed_sims:
                continue
            work_items.append((sim_id, sample, all_polygons[i]))

        log(f"  After resume skip: {len(work_items)} sims to run")

        if args.test > 0:
            work_items = work_items[:args.test]
            log(f"\n*** TEST MODE: running {args.test} sims only ***")

        to_run = len(work_items)
        if to_run == 0:
            log("Nothing to run!")
            return

        log(f"\nStep 4: Running {to_run} sims with {n_workers} workers...")
        log("-"*75)

        # Step 6: Parallel execution
        t_batch = time.time()
        n_success = 0
        n_fail = 0
        last_backup = 0
        last_cleanup = time.time()

        with Pool(processes=n_workers) as pool:
            for i, row in enumerate(pool.imap_unordered(run_single_sim, work_items, chunksize=1)):
                is_ok = row['solver_completed'] == 'YES'
                append_csv_row(OUTPUT_CSV, row)

                if is_ok:
                    n_success += 1
                else:
                    n_fail += 1

                done = n_success + n_fail

                if done % 50 == 0 or done == to_run:
                    elapsed = time.time() - t_batch
                    rate = done / elapsed if elapsed > 0 else 0
                    eta = (to_run - done) / rate if rate > 0 else 0
                    fail_pct = 100.0 * n_fail / done if done > 0 else 0
                    log(f"  [{done}/{to_run}] {n_success} OK, {n_fail} ERR ({fail_pct:.1f}%) | "
                        f"{elapsed/60:.1f}min, ETA {eta/60:.1f}min | {rate*60:.1f} sims/min")

                if done >= MIN_SIMS_FOR_FAIL_CHECK and n_fail / done > MAX_FAIL_RATE:
                    log(f"\n!!! SAFETY PAUSE: {100*n_fail/done:.1f}% failure rate !!!")
                    backup = OUTPUT_CSV.replace('.csv', f'_safepause_{done}.csv')
                    shutil.copy2(OUTPUT_CSV, backup)
                    log(f"  Backup: {backup}")
                    pool.terminate()
                    pool.join()
                    # Clean up orphaned temp dirs from terminated workers
                    import glob as glob_mod
                    orphan_dirs = [d for d in glob_mod.glob(os.path.join(WORK_DIR, "cnet_*"))
                                   if os.path.isdir(d)]
                    for d in orphan_dirs:
                        shutil.rmtree(d, ignore_errors=True)
                    if orphan_dirs:
                        log(f"  Cleaned {len(orphan_dirs)} orphaned temp dirs")
                    sys.exit(1)

                if done - last_backup >= BACKUP_INTERVAL:
                    backup = OUTPUT_CSV.replace('.csv', f'_backup_{done}.csv')
                    try:
                        shutil.copy2(OUTPUT_CSV, backup)
                    except Exception:
                        pass
                    last_backup = done

                # Periodic orphan tmpdir cleanup (every 10 min)
                if time.time() - last_cleanup > 600:
                    import glob as glob_mod
                    orphan_dirs = [d for d in glob_mod.glob(os.path.join(WORK_DIR, "cnet_*"))
                                   if os.path.isdir(d)]
                    stale_cutoff = time.time() - 600  # 10 min age
                    cleaned = 0
                    for d in orphan_dirs:
                        try:
                            if os.path.getmtime(d) < stale_cutoff:
                                shutil.rmtree(d, ignore_errors=True)
                                cleaned += 1
                        except OSError:
                            pass
                    if cleaned:
                        log(f"  Cleanup: removed {cleaned} orphaned temp dirs")
                    last_cleanup = time.time()

        t_total = time.time() - t_batch
        log("\n" + "="*75)
        log("BATCH COMPLETE")
        log("="*75)
        log(f"  Ran: {n_success + n_fail}, Success: {n_success}, Failed: {n_fail}")
        log(f"  Fail rate: {100*n_fail/(n_success+n_fail):.1f}%" if (n_success+n_fail) > 0 else "  N/A")
        log(f"  Time: {t_total:.1f}s ({t_total/60:.1f}min)")
        if n_success + n_fail > 0:
            log(f"  Speed: {(n_success+n_fail)/(t_total/60):.1f} sims/min")
        log(f"  Output: {OUTPUT_CSV}")
        log("="*75)

        final = OUTPUT_CSV.replace('.csv', '_final.csv')
        try:
            shutil.copy2(OUTPUT_CSV, final)
        except Exception:
            pass
    finally:
        _log_fh.close()


if __name__ == "__main__":
    main()
