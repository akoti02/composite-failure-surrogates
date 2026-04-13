"""
================================================================================
RP3 V11 MACHINE LEARNING PIPELINE — COMPOSITEBENCH 67.5K MULTI-MATERIAL SURROGATE
================================================================================
Project: ML Surrogate Model for Composite Failure Prediction
Author: Artur Akoev
Supervisor: Dr. Terence Macquart
University of Bristol — AENG30017 Research Project 3

PURPOSE:
    Train ML surrogate models on V11 CompositeBench simulation data (67,500 samples).
    Multi-material (5), multi-layup (6), multi-BC (3) composite plates with 1-5
    crack-like defects. Predicts stress fields, 4 failure criteria (Tsai-Wu,
    Hashin, Puck, LaRC05), and binary failure classification.

    Two solvers feed the dataset:
      - CalculiX + UMAT (implicit, progressive damage) — ~47% of rows
      - OpenRadioss (explicit, element deletion fallback) — ~53% of rows
    Both produce identical output columns for stress and failure indices.
    UMAT damage variables (umat_d_*) are VALIDATION EVIDENCE ONLY, not targets.

KEY DIFFERENCES FROM V10:
    1. 67,500 samples across 5 materials x 6 layups x 3 BCs (vs 101k, 1 mat, 1 layup)
    2. 144 CSV columns (vs 117) — material_id, layup_id, bc_mode as categoricals
    3. 4 failure criteria: Tsai-Wu, Hashin, Puck, LaRC05 (vs 2: Tsai-Wu, Hashin)
    4. Class imbalance: 62% fail / 37% no-fail — MUST mitigate
    5. solver_origin column: 'ccx_umat' vs 'or_fallback' — include as feature
    6. Per-defect Tsai-Wu hotspots (max_tsai_wu_defect1..5) need log-transform
    7. V2A, V4A are always zero (symmetric layups) — drop from features
    8. No max_mises column (V11 uses percentile-filtered stress instead)

DATA QUALITY FIXES APPLIED AT LOAD TIME:
    - Drop rows where solver_completed != 'YES'
    - Cap umat_d_ft/fc/mt/mc_max to [0, 1] (6-10 OOB sims)
    - Log-transform max_tsai_wu_defect{1..5} columns
    - Drop V2A, V4A (always zero — symmetric layups, B matrix = 0)

EXPECTED CSV: results_merged_v11.csv (merged from 17 server shards)
    or pass --csv-dir to point at a directory of results_vm{1..17}_flat_coarse.csv

USAGE:
    1. pip install catboost shap optuna mapie
    2. Merge 17 CSVs or point --csv-dir at the shard directory
    3. Run: python v11_ml_pipeline.py
    4. Figures saved as fig_v11_*.png at 300 DPI in figures_v11/

================================================================================
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
import os
import glob
import copy
import warnings
import time
import argparse
warnings.filterwarnings('ignore')

# Scikit-learn
from sklearn.model_selection import (
    KFold, RepeatedKFold, RepeatedStratifiedKFold, train_test_split, StratifiedKFold
)
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import (
    mean_squared_error, mean_absolute_error, r2_score,
    accuracy_score, precision_score, recall_score, f1_score,
    confusion_matrix, roc_curve, auc
)
from sklearn.linear_model import LinearRegression, Ridge, LogisticRegression
from sklearn.ensemble import (
    RandomForestClassifier, RandomForestRegressor,
    GradientBoostingClassifier, GradientBoostingRegressor
)
from sklearn.multioutput import MultiOutputRegressor
from xgboost import XGBRegressor, XGBClassifier

# PyTorch
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader

# Optional libraries
try:
    from catboost import CatBoostRegressor, CatBoostClassifier
    HAS_CATBOOST = True
except ImportError:
    HAS_CATBOOST = False

try:
    import shap
    HAS_SHAP = True
except ImportError:
    HAS_SHAP = False

try:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    HAS_OPTUNA = True
except ImportError:
    HAS_OPTUNA = False

try:
    from mapie.regression import CrossConformalRegressor
    HAS_MAPIE = True
except ImportError:
    HAS_MAPIE = False


# ==============================================================================
# CONFIGURATION
# ==============================================================================

RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)
torch.manual_seed(RANDOM_SEED)
DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

# Training settings
K_FOLDS = 5
N_REPEATS = 3
TEST_SIZE = 0.2
VAL_SIZE = 0.2
BATCH_SIZE = 64
EPOCHS = 300
LEARNING_RATE = 0.001
EARLY_STOPPING_PATIENCE = 30
OPTUNA_N_TRIALS = 50

# Explicit target lists for expensive analyses (avoid fragile [:3] slicing)
GPR_TARGETS = ['tsai_wu_index', 'max_hashin_ft', 'max_s11']
CONFORMAL_TARGETS = ['tsai_wu_index', 'max_hashin_ft', 'max_s11']
MC_TARGETS = ['tsai_wu_index', 'max_hashin_ft']

# Regression targets that get log1p-transformed at load time (huge dynamic range)
SKEWED_REG_TARGETS = ['tsai_wu_index', 'max_hashin_ft', 'max_hashin_mt', 'max_hashin_mc']

# Physics constants
PLATE_LENGTH = 100.0   # mm
PLATE_WIDTH = 50.0     # mm
MAX_DEFECTS = 5

# V11 campaign materials (5 selected)
MATERIALS = {
    1:  'T300/5208',
    5:  'IM7/8552',
    8:  'E-glass/Epoxy',
    12: 'Kevlar49/Epoxy',
    15: 'Flax/Epoxy',
}

# V11 campaign layups (6 selected, ALL symmetric — B matrix = 0)
LAYUPS = {
    1:  'QI_8',
    3:  'CP_8',
    4:  'UD_0_8',
    6:  'Angle_pm45_4s',
    7:  'Angle_pm30_4s',
    13: 'Skin_25_50_25',
}

# V11 boundary conditions
BC_MODES = ['tension_comp', 'biaxial', 'uniaxial_shear']

# Output directory
FIG_DIR = os.path.join(os.path.expanduser('~'), 'Downloads', 'figures_v11')

# --- Regression targets ---
# Note: umat_d_* are NOT targets — they are validation evidence only.
REG_TARGETS = [
    'tsai_wu_index',
    'max_hashin_ft',
    # max_hashin_fc EXCLUDED — 92% zeros (fiber compression damage is rare in this
    # tension/shear-dominated dataset). Produces garbage R² for every model type.
    # Fiber compression failure is still captured by failed_hashin classification.
    'max_hashin_mt',
    'max_hashin_mc',
    'max_s11',
    'min_s11',
    'max_s12',
]

# --- Classification targets ---
CLF_TARGETS = [
    'failed_tsai_wu',
    'failed_hashin',
    'failed_puck',
    'failed_larc',
]

# --- Columns to DROP before feature selection ---
# These are outputs, metadata, or always-zero columns
DROP_COLS = {
    'sim_id', 'solver_completed', 'solver', 'n_elements',
    'V2A', 'V4A',  # always zero (symmetric layups, B=0)
    'ply_thickness',  # constant 0.15mm across entire campaign
    'buckle_eig_1', 'buckle_eig_2', 'buckle_eig_3', 'buckle_eig_4',  # always zero (no buckle BC)
    'hole_diameter', 'hole_x', 'hole_y', 'panel_radius',  # always zero (flat geometry only)
    'post_fpf',  # derived from failure indices, not independent
    # UMAT damage — validation evidence, NOT features or targets
    'umat_d_ft_max', 'umat_d_fc_max', 'umat_d_mt_max', 'umat_d_mc_max',
    'umat_n_increments',
}

# --- Columns that need log-transform at load time ---
LOG_TRANSFORM_COLS = [
    'max_tsai_wu_defect1', 'max_tsai_wu_defect2', 'max_tsai_wu_defect3',
    'max_tsai_wu_defect4', 'max_tsai_wu_defect5',
]

# CLASS IMBALANCE — weights computed dynamically from data in load_data().
# These are module-level defaults overwritten at runtime.
CLASS_WEIGHT_RATIO = 1.67   # fallback if load_data doesn't set it
XGBOOST_SCALE_POS_WEIGHT = 0.6  # fallback


# ==============================================================================
# DATA LOADING & CLEANING
# ==============================================================================

def load_data(filepath=None, csv_dir=None):
    """
    Load V11 CompositeBench data.

    Args:
        filepath: path to merged CSV (results_merged_v11.csv)
        csv_dir: path to directory of server shards (results_vm{1..17}_flat_coarse.csv)

    Returns:
        DataFrame with cleaned data
    """
    print("=" * 60)
    print("LOADING V11 COMPOSITEBENCH DATA")
    print("=" * 60)

    if csv_dir and os.path.isdir(csv_dir):
        shard_files = sorted(glob.glob(os.path.join(csv_dir, 'results_vm*_flat_coarse.csv')))
        if not shard_files:
            raise FileNotFoundError(f"No shard CSVs found in {csv_dir}")
        print(f"  Found {len(shard_files)} server shards — merging...")
        dfs = []
        for f in shard_files:
            shard = pd.read_csv(f)
            print(f"    {os.path.basename(f)}: {len(shard)} rows")
            dfs.append(shard)
        df = pd.concat(dfs, ignore_index=True)
        print(f"  Merged: {len(df)} total rows")
    elif filepath and os.path.exists(filepath):
        df = pd.read_csv(filepath)
        print(f"  Loaded {len(df)} rows from {os.path.basename(filepath)}")
    else:
        raise FileNotFoundError(
            "No data source. Pass --csv (merged file) or --csv-dir (shard directory)."
        )

    n_total = len(df)

    # --- Fix 1: Drop solver failures ---
    if 'solver_completed' in df.columns:
        df = df[df['solver_completed'] == 'YES'].copy()
        n_dropped = n_total - len(df)
        if n_dropped > 0:
            print(f"  Dropped {n_dropped} solver failures ({100*n_dropped/n_total:.1f}%)")

    # --- Fix 2: Cap UMAT damage to [0, 1] ---
    umat_cols = ['umat_d_ft_max', 'umat_d_fc_max', 'umat_d_mt_max', 'umat_d_mc_max']
    for col in umat_cols:
        if col in df.columns:
            oob = (df[col] > 1.001) | (df[col] < -0.001)
            n_oob = oob.sum()
            if n_oob > 0:
                print(f"  Capped {n_oob} OOB values in {col} to [0, 1]")
                df[col] = df[col].clip(0.0, 1.0)

    # --- Fix 3: Clip extreme stress values (mesh singularity safety net) ---
    # Production data already uses 0.1th/99.9th percentile filtering, but the
    # smoke data and any edge cases may still have raw singularity values.
    stress_clip_cols = {'max_s11': (0, 10000), 'min_s11': (-10000, 0), 'max_s12': (0, 10000)}
    for col, (lo, hi) in stress_clip_cols.items():
        if col in df.columns:
            n_clipped = ((df[col] < lo) | (df[col] > hi)).sum()
            if n_clipped > 0:
                print(f"  Clipped {n_clipped} extreme values in {col} to [{lo}, {hi}]")
                df[col] = df[col].clip(lo, hi)

    # --- Fix 4: Log-transform skewed regression targets ---
    # tsai_wu_index (0.002–3217), max_hashin_ft/mt/mc have huge dynamic ranges.
    # Without log-transform, MSE is dominated by outliers and small values are invisible.
    # Using log1p (log(1+x)) — handles zeros gracefully, inverts with expm1.
    # NOT applied to: max_hashin_fc (92% zeros, log won't help), max_s11/min_s11/max_s12 (linear scale).
    for col in SKEWED_REG_TARGETS:
        if col in df.columns:
            raw_max = df[col].max()
            raw_min = df[col].min()
            df[col] = np.log1p(df[col].clip(lower=0))
            print(f"  Log1p-transformed {col} (raw range [{raw_min:.4f}, {raw_max:.2f}])")

    # --- Fix 5: Log-transform per-defect Tsai-Wu hotspots ---
    for col in LOG_TRANSFORM_COLS:
        if col in df.columns:
            raw_max = df[col].max()
            df[col] = np.log10(df[col].clip(lower=0) + 1.0)
            print(f"  Log-transformed {col} (raw max was {raw_max:.2e})")

    # --- Fix 6: Coerce numeric columns ---
    skip_categorical = {'material_name', 'layup_name', 'bc_mode', 'geometry',
                        'mesh_level', 'solver', 'solver_origin', 'solver_completed'}
    for col in df.columns:
        if col not in skip_categorical:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # --- Fix 7: Drop rows with NaN in key targets ---
    key_cols = [c for c in REG_TARGETS + CLF_TARGETS if c in df.columns]
    n_before = len(df)
    df = df.dropna(subset=key_cols)
    n_nan = n_before - len(df)
    if n_nan > 0:
        print(f"  Dropped {n_nan} rows with NaN in target columns")

    # --- Summary ---
    print(f"\n  Final dataset: {len(df)} samples")
    print(f"  Materials: {sorted(df['material_id'].unique())}")
    print(f"  Layups:    {sorted(df['layup_id'].unique())}")
    print(f"  BCs:       {sorted(df['bc_mode'].unique())}")

    # Class balance report + dynamic weight computation
    global CLASS_WEIGHT_RATIO, XGBOOST_SCALE_POS_WEIGHT
    if 'failed_tsai_wu' in df.columns:
        n_fail = int(df['failed_tsai_wu'].sum())
        n_nofail = len(df) - n_fail
        if n_nofail > 0 and n_fail > 0:
            CLASS_WEIGHT_RATIO = n_fail / n_nofail  # upweight minority (no-fail)
            XGBOOST_SCALE_POS_WEIGHT = n_nofail / n_fail  # XGBoost: downweight positive
        print(f"\n  CLASS BALANCE: {n_fail} fail ({100*n_fail/len(df):.0f}%) / "
              f"{n_nofail} no-fail ({100*n_nofail/len(df):.0f}%)")
        print(f"  DYNAMIC WEIGHTS: class_weight_ratio={CLASS_WEIGHT_RATIO:.3f}, "
              f"xgb_scale_pos_weight={XGBOOST_SCALE_POS_WEIGHT:.3f}")

    # Solver origin breakdown
    if 'solver_origin' in df.columns:
        origins = df['solver_origin'].value_counts()
        print(f"  SOLVER ORIGIN: {dict(origins)}")

    return df


# ==============================================================================
# FEATURE ENGINEERING
# ==============================================================================

def engineer_features(df):
    """
    Create physics-informed features for V11 multi-material dataset.
    Extends V10 engineering with material- and layup-aware features.
    """
    df = df.copy()
    n_engineered = 0

    # --- Encode categoricals ---
    # material_id, layup_id: already numeric IDs — keep as-is for tree models
    # bc_mode: one-hot encode
    if 'bc_mode' in df.columns:
        bc_dummies = pd.get_dummies(df['bc_mode'], prefix='bc', dtype=float)
        df = pd.concat([df, bc_dummies], axis=1)
        n_engineered += len(bc_dummies.columns)

    # solver_origin: binary encode (ccx_umat=0, or_fallback=1)
    if 'solver_origin' in df.columns:
        df['is_or_fallback'] = (df['solver_origin'] == 'or_fallback').astype(float)
        n_engineered += 1

    # --- Load ratio and total pressure ---
    if 'pressure_x' in df.columns and 'pressure_y' in df.columns:
        df['load_ratio'] = np.arctan2(df['pressure_y'], df['pressure_x'])
        df['total_pressure'] = np.sqrt(df['pressure_x']**2 + df['pressure_y']**2)
        n_engineered += 2

    # --- Crack area ratio (total crack area / plate area) ---
    plate_area = PLATE_LENGTH * PLATE_WIDTH
    total_crack_area = pd.Series(0.0, index=df.index)
    for i in range(1, MAX_DEFECTS + 1):
        hl_col = f'defect{i}_half_length'
        w_col = f'defect{i}_width'
        if hl_col in df.columns and w_col in df.columns:
            total_crack_area += df[hl_col] * 2.0 * df[w_col]
    df['crack_area_ratio'] = total_crack_area / plate_area
    n_engineered += 1

    # --- Total crack length normalized ---
    total_crack_len = pd.Series(0.0, index=df.index)
    for i in range(1, MAX_DEFECTS + 1):
        hl_col = f'defect{i}_half_length'
        if hl_col in df.columns:
            total_crack_len += df[hl_col] * 2.0
    df['total_crack_length_norm'] = total_crack_len / PLATE_WIDTH
    n_engineered += 1

    # --- Max crack-to-width ratio ---
    max_crack_len = pd.Series(0.0, index=df.index)
    for i in range(1, MAX_DEFECTS + 1):
        hl_col = f'defect{i}_half_length'
        if hl_col in df.columns:
            max_crack_len = np.maximum(max_crack_len, df[hl_col] * 2.0)
    df['max_crack_width_ratio'] = max_crack_len / PLATE_WIDTH
    n_engineered += 1

    # --- Crack alignment with load direction ---
    for i in range(1, MAX_DEFECTS + 1):
        ang_col = f'defect{i}_angle'
        if ang_col in df.columns and 'pressure_x' in df.columns and 'pressure_y' in df.columns:
            load_angle = np.degrees(np.arctan2(df['pressure_y'], df['pressure_x'] + 1e-6))
            angle_diff = np.abs(df[ang_col] - load_angle) % 180
            df[f'defect{i}_load_alignment'] = np.minimum(angle_diff, 180 - angle_diff) / 90.0
            n_engineered += 1

    # --- Material stiffness ratio (E1/E2) as interaction feature ---
    # Already captured by V1A/V3A laminate params, but explicit ratio helps trees
    if 'material_id' in df.columns:
        mat_e1e2 = {1: 13.5, 5: 18.88, 8: 4.53, 12: 14.55, 15: 6.36}
        df['material_e1_e2_ratio'] = df['material_id'].map(mat_e1e2).fillna(10.0)
        n_engineered += 1

    # --- Defect density (n_defects / plate_area) ---
    if 'n_defects' in df.columns:
        df['defect_density'] = df['n_defects'] / plate_area
        n_engineered += 1

    print(f"  Engineered {n_engineered} new features")
    return df


# ==============================================================================
# COLUMN DETECTION
# ==============================================================================

def detect_columns(df):
    """Auto-detect input features, regression targets, and classification targets."""
    all_cols = list(df.columns)

    reg_targets = [t for t in REG_TARGETS if t in all_cols]
    clf_targets = [t for t in CLF_TARGETS if t in all_cols]

    # Everything that is not a target, not in DROP_COLS, and not categorical string
    known_outputs = set(reg_targets + clf_targets)
    # NOTE: 'larc_in_situ_applied' and 'nonlinear_regime_warning' are pre-sim
    # input flags (determined by layup/BC before solver runs), NOT outputs.
    # They must NOT be caught by the keyword filter below.
    input_flags = {'larc_in_situ_applied', 'nonlinear_regime_warning'}

    output_keywords = [
        'max_s11', 'min_s11', 'max_s12', 'tsai_wu', 'hashin', 'puck_',
        'larc_ft', 'larc_fc', 'larc_mt',
        'failed_', 'n_elements', 'solver_completed', 'solver_origin',
        'umat_d_', 'umat_n_', 'buckle_eig', 'post_fpf',
        'max_tsai_wu_defect',
    ]
    output_cols = set()
    for col in all_cols:
        if col in input_flags:
            continue  # these are input features, not outputs
        for kw in output_keywords:
            if kw in col:
                output_cols.add(col)

    # String columns that can't be features directly
    string_cols = {'material_name', 'layup_name', 'bc_mode', 'geometry',
                   'mesh_level', 'solver', 'solver_origin'}

    features = [
        col for col in all_cols
        if col not in DROP_COLS
        and col not in known_outputs
        and col not in output_cols
        and col not in string_cols
    ]

    detected = {
        'features': features,
        'reg_targets': reg_targets,
        'clf_targets': clf_targets,
    }

    print(f"\n{'='*60}")
    print("COLUMN DETECTION")
    print(f"{'='*60}")
    print(f"  Input features:         {len(features)}")
    print(f"  Regression targets:     {reg_targets}")
    print(f"  Classification targets: {clf_targets}")
    print(f"  Dropped columns:        {len(DROP_COLS)}")
    print(f"{'='*60}\n")

    return detected


# ==============================================================================
# PREPROCESSING
# ==============================================================================

def preprocess(df, feature_names, target_name, task='regression'):
    """Extract features and target. NO scaling here — scaling happens inside CV folds
    to prevent data leakage (test data must not inform training statistics)."""
    X = df[feature_names].values.astype(np.float64)
    y = df[target_name].values.astype(np.float64)
    if task == 'classification':
        y = y.astype(int)
    return X, y


# ==============================================================================
# PYTORCH COMPONENTS
# ==============================================================================

class FEADataset(Dataset):
    def __init__(self, X, y, task='regression'):
        self.X = torch.FloatTensor(X)
        if task == 'regression':
            if y.ndim == 1:
                self.y = torch.FloatTensor(y).unsqueeze(1)
            else:
                self.y = torch.FloatTensor(y)
        else:
            self.y = torch.LongTensor(y)
        self.task = task

    def __len__(self):
        return len(self.X)

    def __getitem__(self, idx):
        return self.X[idx], self.y[idx]


class RegressionNet(nn.Module):
    def __init__(self, input_size=32, hidden_sizes=(256, 128, 64), dropout_rate=0.3):
        super().__init__()
        layers = []
        prev = input_size
        for h in hidden_sizes:
            layers += [nn.Linear(prev, h), nn.ReLU(), nn.BatchNorm1d(h), nn.Dropout(dropout_rate)]
            prev = h
        layers.append(nn.Linear(prev, 1))
        self.network = nn.Sequential(*layers)

    def forward(self, x):
        return self.network(x)


class MultiOutputNet(nn.Module):
    def __init__(self, input_size=32, shared_sizes=(256, 128),
                 head_size=64, n_outputs=8, dropout_rate=0.3):
        super().__init__()
        shared_layers = []
        prev = input_size
        for h in shared_sizes:
            shared_layers += [nn.Linear(prev, h), nn.ReLU(),
                              nn.BatchNorm1d(h), nn.Dropout(dropout_rate)]
            prev = h
        self.shared = nn.Sequential(*shared_layers)
        self.heads = nn.ModuleList([
            nn.Sequential(
                nn.Linear(prev, head_size), nn.ReLU(),
                nn.BatchNorm1d(head_size), nn.Dropout(dropout_rate * 0.5),
                nn.Linear(head_size, 1)
            )
            for _ in range(n_outputs)
        ])

    def forward(self, x):
        shared_out = self.shared(x)
        return torch.cat([head(shared_out) for head in self.heads], dim=1)


class PhysicsInformedLoss(nn.Module):
    """MSE + penalty for physically impossible predictions."""
    def __init__(self, physics_weight=0.1):
        super().__init__()
        self.mse = nn.MSELoss()
        self.physics_weight = physics_weight

    def forward(self, pred, target):
        data_loss = self.mse(pred, target)
        neg_penalty = torch.mean(torch.relu(-pred))
        return data_loss + self.physics_weight * neg_penalty


class FocalLoss(nn.Module):
    """Focal loss for class imbalance — down-weights easy examples."""
    def __init__(self, alpha=None, gamma=2.0):
        super().__init__()
        self.alpha = alpha  # class weights tensor
        self.gamma = gamma

    def forward(self, logits, targets):
        ce = nn.functional.cross_entropy(logits, targets, weight=self.alpha, reduction='none')
        pt = torch.exp(-ce)
        return ((1 - pt) ** self.gamma * ce).mean()


class ClassificationNet(nn.Module):
    def __init__(self, input_size=32, hidden_sizes=(256, 128, 64), dropout_rate=0.3):
        super().__init__()
        layers = []
        prev = input_size
        for h in hidden_sizes:
            layers += [nn.Linear(prev, h), nn.ReLU(), nn.BatchNorm1d(h), nn.Dropout(dropout_rate)]
            prev = h
        layers.append(nn.Linear(prev, 2))
        self.network = nn.Sequential(*layers)

    def forward(self, x):
        return self.network(x)


class EarlyStopping:
    def __init__(self, patience=20, min_delta=1e-4):
        self.patience = patience
        self.min_delta = min_delta
        self.counter = 0
        self.best_loss = None
        self.early_stop = False
        self.best_state = None

    def __call__(self, val_loss, model):
        if self.best_loss is None or val_loss < self.best_loss - self.min_delta:
            self.best_loss = val_loss
            self.best_state = {k: v.clone() for k, v in model.state_dict().items()}
            self.counter = 0
        else:
            self.counter += 1
            if self.counter >= self.patience:
                self.early_stop = True

    def load_best(self, model):
        if self.best_state:
            model.load_state_dict(self.best_state)


# ==============================================================================
# TRAINING FUNCTIONS
# ==============================================================================

def train_nn_regression(X_train, y_train, X_val, y_val, input_size,
                        epochs=EPOCHS, lr=LEARNING_RATE, patience=EARLY_STOPPING_PATIENCE,
                        use_physics_loss=False, verbose=True):
    train_loader = DataLoader(FEADataset(X_train, y_train), batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(FEADataset(X_val, y_val), batch_size=BATCH_SIZE, shuffle=False)

    model = RegressionNet(input_size=input_size).to(DEVICE)
    criterion = PhysicsInformedLoss(0.1) if use_physics_loss else nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=10, factor=0.5)
    es = EarlyStopping(patience=patience)
    history = {'train_loss': [], 'val_loss': []}

    for epoch in range(epochs):
        model.train()
        train_loss = 0.0
        for Xb, yb in train_loader:
            Xb, yb = Xb.to(DEVICE), yb.to(DEVICE)
            optimizer.zero_grad()
            loss = criterion(model(Xb), yb)
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * Xb.size(0)
        train_loss /= len(train_loader.dataset)

        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for Xb, yb in val_loader:
                Xb, yb = Xb.to(DEVICE), yb.to(DEVICE)
                val_loss += criterion(model(Xb), yb).item() * Xb.size(0)
        val_loss /= len(val_loader.dataset)

        history['train_loss'].append(train_loss)
        history['val_loss'].append(val_loss)
        scheduler.step(val_loss)

        if verbose and (epoch + 1) % 50 == 0:
            print(f"  Epoch {epoch+1}/{epochs} — Train: {train_loss:.6f}, Val: {val_loss:.6f}")

        es(val_loss, model)
        if es.early_stop:
            if verbose:
                print(f"  Early stopping at epoch {epoch+1}")
            es.load_best(model)
            break

    return model, history


def train_nn_classification(X_train, y_train, X_val, y_val, input_size,
                            epochs=EPOCHS, lr=LEARNING_RATE, patience=EARLY_STOPPING_PATIENCE,
                            use_focal_loss=True, verbose=True):
    """Train classification NN with focal loss for class imbalance."""
    train_loader = DataLoader(FEADataset(X_train, y_train, 'classification'),
                              batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(FEADataset(X_val, y_val, 'classification'),
                            batch_size=BATCH_SIZE, shuffle=False)

    model = ClassificationNet(input_size=input_size).to(DEVICE)

    if use_focal_loss:
        # Class weights: no-fail (0) gets 1.67x, fail (1) gets 1.0x
        alpha = torch.FloatTensor([CLASS_WEIGHT_RATIO, 1.0]).to(DEVICE)
        criterion = FocalLoss(alpha=alpha, gamma=2.0)
    else:
        criterion = nn.CrossEntropyLoss()

    optimizer = optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=10, factor=0.5)
    es = EarlyStopping(patience=patience)

    for epoch in range(epochs):
        model.train()
        train_loss = 0.0
        for Xb, yb in train_loader:
            Xb, yb = Xb.to(DEVICE), yb.to(DEVICE)
            optimizer.zero_grad()
            loss = criterion(model(Xb), yb)
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * Xb.size(0)
        train_loss /= len(train_loader.dataset)

        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for Xb, yb in val_loader:
                Xb, yb = Xb.to(DEVICE), yb.to(DEVICE)
                val_loss += criterion(model(Xb), yb).item() * Xb.size(0)
        val_loss /= len(val_loader.dataset)

        scheduler.step(val_loss)
        es(val_loss, model)
        if es.early_stop:
            if verbose:
                print(f"  Early stopping at epoch {epoch+1}")
            es.load_best(model)
            break

    return model


def predict_nn(model, X, task='regression'):
    model.eval()
    with torch.no_grad():
        X_t = torch.FloatTensor(X).to(DEVICE)
        out = model(X_t).cpu().numpy()
    if task == 'regression':
        return out.flatten()
    else:
        return out.argmax(axis=1)


def predict_multioutput_nn(model, X):
    model.eval()
    with torch.no_grad():
        return model(torch.FloatTensor(X).to(DEVICE)).cpu().numpy()


# ==============================================================================
# OPTUNA TUNING
# ==============================================================================

def optuna_tune_xgboost(X, y, task='regression', n_trials=OPTUNA_N_TRIALS):
    """Tune XGBoost with Optuna. Handles class imbalance for classification."""
    def objective(trial):
        params = {
            'n_estimators': trial.suggest_int('n_estimators', 100, 1000),
            'max_depth': trial.suggest_int('max_depth', 3, 10),
            'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.3, log=True),
            'subsample': trial.suggest_float('subsample', 0.6, 1.0),
            'colsample_bytree': trial.suggest_float('colsample_bytree', 0.6, 1.0),
            'min_child_weight': trial.suggest_int('min_child_weight', 1, 10),
            'reg_alpha': trial.suggest_float('reg_alpha', 1e-8, 10.0, log=True),
            'reg_lambda': trial.suggest_float('reg_lambda', 1e-8, 10.0, log=True),
            'random_state': RANDOM_SEED,
        }
        if task == 'classification':
            params['scale_pos_weight'] = XGBOOST_SCALE_POS_WEIGHT
            model = XGBClassifier(**params, use_label_encoder=False, eval_metric='logloss')
        else:
            model = XGBRegressor(**params)

        if task == 'classification':
            kf = StratifiedKFold(n_splits=3, shuffle=True, random_state=RANDOM_SEED)
        else:
            kf = KFold(n_splits=3, shuffle=True, random_state=RANDOM_SEED)
        scores = []
        for train_idx, val_idx in kf.split(X, y):
            model.fit(X[train_idx], y[train_idx])
            if task == 'classification':
                pred = model.predict(X[val_idx])
                scores.append(f1_score(y[val_idx], pred))
            else:
                pred = model.predict(X[val_idx])
                scores.append(r2_score(y[val_idx], pred))
        return np.mean(scores)

    study = optuna.create_study(direction='maximize')
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    best_params = study.best_params
    best_params['random_state'] = RANDOM_SEED
    if task == 'classification':
        best_params['scale_pos_weight'] = XGBOOST_SCALE_POS_WEIGHT
        return XGBClassifier(**best_params, use_label_encoder=False, eval_metric='logloss')
    else:
        return XGBRegressor(**best_params)


# ==============================================================================
# CROSS-VALIDATION
# ==============================================================================

def repeated_kfold_cv(X, y, feature_names, target_name, task='regression',
                      n_splits=K_FOLDS, n_repeats=N_REPEATS):
    """Run repeated K-fold CV across multiple model types."""
    print(f"\n  {'='*50}")
    print(f"  TARGET: {target_name} ({task})")
    print(f"  {'='*50}")

    if task == 'regression':
        models = {
            'Linear': LinearRegression(),
            'Ridge': Ridge(alpha=1.0),
            'Random Forest': RandomForestRegressor(n_estimators=200, random_state=RANDOM_SEED, n_jobs=-1),
            'XGBoost': XGBRegressor(n_estimators=300, max_depth=6, learning_rate=0.1,
                                     random_state=RANDOM_SEED),
        }
        if HAS_CATBOOST:
            models['CatBoost'] = CatBoostRegressor(iterations=300, depth=6, learning_rate=0.1,
                                                     random_seed=RANDOM_SEED, verbose=0)
        kf = RepeatedKFold(n_splits=n_splits, n_repeats=n_repeats, random_state=RANDOM_SEED)
        metric_fn = r2_score
        metric_name = 'R2'
    else:
        models = {
            'Logistic': LogisticRegression(max_iter=1000, class_weight={0: CLASS_WEIGHT_RATIO, 1: 1.0}),
            'Random Forest': RandomForestClassifier(n_estimators=200, random_state=RANDOM_SEED,
                                                      class_weight={0: CLASS_WEIGHT_RATIO, 1: 1.0}, n_jobs=-1),
            'XGBoost': XGBClassifier(n_estimators=300, max_depth=6, learning_rate=0.1,
                                      scale_pos_weight=XGBOOST_SCALE_POS_WEIGHT,
                                      random_state=RANDOM_SEED, use_label_encoder=False,
                                      eval_metric='logloss'),
        }
        if HAS_CATBOOST:
            models['CatBoost'] = CatBoostClassifier(iterations=300, depth=6, learning_rate=0.1,
                                                      random_seed=RANDOM_SEED, verbose=0,
                                                      class_weights={0: CLASS_WEIGHT_RATIO, 1: 1.0})
        kf = RepeatedStratifiedKFold(n_splits=n_splits, n_repeats=n_repeats, random_state=RANDOM_SEED)
        metric_fn = f1_score
        metric_name = 'F1'

    summary = {}
    last_models = {}

    for mname, model_template in models.items():
        scores = []
        for fold_idx, (train_idx, val_idx) in enumerate(kf.split(X, y if task == 'classification' else None)):
            # Scale INSIDE the fold — fit on train only, transform val
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X[train_idx])
            X_val_scaled = scaler.transform(X[val_idx])

            # For classification: compute class weights from TRAIN fold only
            if task == 'classification':
                n_pos = y[train_idx].sum()
                n_neg = len(train_idx) - n_pos
                fold_cwr = n_pos / max(n_neg, 1)  # class weight ratio for this fold
                fold_xgb_spw = n_neg / max(n_pos, 1)
                model = copy.deepcopy(model_template)
                # Update class weights for this fold
                if hasattr(model, 'class_weight'):
                    model.set_params(class_weight={0: fold_cwr, 1: 1.0})
                if hasattr(model, 'scale_pos_weight'):
                    model.set_params(scale_pos_weight=fold_xgb_spw)
                if hasattr(model, 'class_weights'):
                    model.set_params(class_weights={0: fold_cwr, 1: 1.0})
            else:
                model = copy.deepcopy(model_template)

            model.fit(X_train_scaled, y[train_idx])
            pred = model.predict(X_val_scaled)
            scores.append(metric_fn(y[val_idx], pred))

        summary[mname] = {
            metric_name: {'mean': np.mean(scores), 'std': np.std(scores)},
        }
        last_models[mname] = model
        print(f"    {mname:20s} {metric_name}: {np.mean(scores):.4f} +/- {np.std(scores):.4f}")

    # Neural network (single split — scale on train only)
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=TEST_SIZE, random_state=RANDOM_SEED,
                                                stratify=y if task == 'classification' else None)
    nn_scaler = StandardScaler()
    X_tr_scaled = nn_scaler.fit_transform(X_tr)
    X_te_scaled = nn_scaler.transform(X_te)
    val_split = int(len(X_tr_scaled) * 0.8)

    if task == 'regression':
        nn_model, _ = train_nn_regression(X_tr_scaled[:val_split], y_tr[:val_split],
                                           X_tr_scaled[val_split:], y_tr[val_split:],
                                           X.shape[1], verbose=False)
        nn_pred = predict_nn(nn_model, X_te_scaled)
        nn_score = r2_score(y_te, nn_pred)
        summary['Neural Net'] = {metric_name: {'mean': nn_score, 'std': 0.0}}

        # PINN
        pinn_model, _ = train_nn_regression(X_tr_scaled[:val_split], y_tr[:val_split],
                                             X_tr_scaled[val_split:], y_tr[val_split:],
                                             X.shape[1], use_physics_loss=True, verbose=False)
        pinn_pred = predict_nn(pinn_model, X_te_scaled)
        pinn_score = r2_score(y_te, pinn_pred)
        summary['PINN'] = {metric_name: {'mean': pinn_score, 'std': 0.0}}
        print(f"    {'Neural Net':20s} {metric_name}: {nn_score:.4f}")
        print(f"    {'PINN':20s} {metric_name}: {pinn_score:.4f}")
    else:
        nn_model = train_nn_classification(X_tr_scaled[:val_split], y_tr[:val_split],
                                            X_tr_scaled[val_split:], y_tr[val_split:],
                                            X.shape[1], verbose=False)
        nn_pred = predict_nn(nn_model, X_te_scaled, 'classification')
        nn_score = f1_score(y_te, nn_pred)
        summary['Neural Net (Focal)'] = {metric_name: {'mean': nn_score, 'std': 0.0}}
        print(f"    {'Neural Net (Focal)':20s} {metric_name}: {nn_score:.4f}")

    return summary, last_models


# ==============================================================================
# PLOTTING
# ==============================================================================

def ensure_fig_dir():
    os.makedirs(FIG_DIR, exist_ok=True)

def save_fig(fig, filename):
    ensure_fig_dir()
    path = os.path.join(FIG_DIR, filename)
    fig.savefig(path, dpi=300, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {filename}")


def plot_data_overview(df, features, detected):
    """Plot dataset overview: class balance, material distribution, feature correlations."""
    # Class balance
    if 'failed_tsai_wu' in df.columns:
        fig, axes = plt.subplots(1, 4, figsize=(20, 5))
        for ax, target in zip(axes, CLF_TARGETS):
            if target in df.columns:
                counts = df[target].value_counts()
                ax.bar(['No-fail', 'Fail'], [counts.get(0, 0), counts.get(1, 0)],
                       color=['#2ecc71', '#e74c3c'])
                ax.set_title(target)
                ax.set_ylabel('Count')
        fig.suptitle('V11 Class Balance (62% fail / 37% no-fail)', fontsize=14)
        save_fig(fig, 'fig_v11_class_balance.png')

    # Material x Layup x BC heatmap
    if all(c in df.columns for c in ['material_name', 'layup_name', 'bc_mode']):
        fig, ax = plt.subplots(figsize=(12, 8))
        pivot = df.groupby(['material_name', 'layup_name']).size().unstack(fill_value=0)
        sns.heatmap(pivot, annot=True, fmt='d', cmap='YlOrRd', ax=ax)
        ax.set_title('Samples per Material x Layup')
        save_fig(fig, 'fig_v11_material_layup_heatmap.png')

    # Solver origin by material
    if 'solver_origin' in df.columns and 'material_name' in df.columns:
        fig, ax = plt.subplots(figsize=(10, 6))
        ct = pd.crosstab(df['material_name'], df['solver_origin'], normalize='index') * 100
        ct.plot(kind='bar', stacked=True, ax=ax, color=['#3498db', '#e67e22'])
        ax.set_ylabel('Percentage')
        ax.set_title('Solver Origin by Material (CCX vs OR fallback)')
        ax.legend(title='Solver')
        save_fig(fig, 'fig_v11_solver_origin_by_material.png')


def plot_cv_comparison(summary, target_name, task='regression'):
    metric_name = 'R2' if task == 'regression' else 'F1'
    models = list(summary.keys())
    means = [summary[m][metric_name]['mean'] for m in models]
    stds = [summary[m][metric_name]['std'] for m in models]

    fig, ax = plt.subplots(figsize=(10, 6))
    colors = ['#e74c3c' if m < 0 else '#3498db' for m in means]
    bars = ax.barh(models, means, xerr=stds, color=colors, alpha=0.8)
    ax.set_xlabel(metric_name)
    ax.set_title(f'{target_name} — Model Comparison ({metric_name})')
    x_min = min(min(means) - 0.1, 0)
    ax.set_xlim(x_min, 1.05)
    ax.axvline(x=0, color='black', linewidth=0.5, linestyle='-')
    for bar, mean in zip(bars, means):
        ax.text(max(mean + 0.01, 0.02), bar.get_y() + bar.get_height()/2, f'{mean:.3f}',
                va='center', fontsize=10)
    save_fig(fig, f'fig_v11_cv_{target_name}.png')


def plot_regression_scatter(y_true, y_pred, target_name, model_name, log_transformed=False):
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.scatter(y_true, y_pred, alpha=0.3, s=5, color='#3498db')
    lims = [min(y_true.min(), y_pred.min()), max(y_true.max(), y_pred.max())]
    ax.plot(lims, lims, 'r--', linewidth=2)
    r2 = r2_score(y_true, y_pred)
    if log_transformed:
        ax.set_xlabel('True (log1p scale)')
        ax.set_ylabel('Predicted (log1p scale)')
        ax.set_title(f'{target_name} — {model_name} (R²={r2:.4f}, log1p-transformed)')
    else:
        ax.set_xlabel('True')
        ax.set_ylabel('Predicted')
        ax.set_title(f'{target_name} — {model_name} (R²={r2:.4f})')
    save_fig(fig, f'fig_v11_scatter_{target_name}_{model_name.replace(" ", "_")}.png')


def plot_feature_importance(model, feature_names, target_name, model_name='XGBoost'):
    if not hasattr(model, 'feature_importances_'):
        return
    importances = model.feature_importances_
    indices = np.argsort(importances)[-20:]  # top 20

    fig, ax = plt.subplots(figsize=(10, 8))
    ax.barh([feature_names[i] for i in indices], importances[indices], color='#2ecc71')
    ax.set_xlabel('Importance')
    ax.set_title(f'{target_name} — Top 20 Features ({model_name})')
    save_fig(fig, f'fig_v11_importance_{target_name}_{model_name.replace(" ", "_")}.png')


# ==============================================================================
# SHAP ANALYSIS
# ==============================================================================

def plot_shap_analysis(model, X, feature_names, target_name, model_name='XGBoost'):
    """SHAP feature importance — beeswarm + bar plots."""
    if not HAS_SHAP:
        return
    try:
        n_samples = min(500, len(X))
        X_sample = X[:n_samples]
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X_sample)

        # Beeswarm
        fig, ax = plt.subplots(figsize=(12, 8))
        shap.summary_plot(shap_values, X_sample, feature_names=feature_names,
                          max_display=20, show=False)
        save_fig(plt.gcf(), f'fig_v11_shap_{target_name}_{model_name.replace(" ", "_")}.png')

        # Bar
        fig, ax = plt.subplots(figsize=(10, 8))
        shap.summary_plot(shap_values, X_sample, feature_names=feature_names,
                          plot_type='bar', max_display=20, show=False)
        save_fig(plt.gcf(), f'fig_v11_shap_bar_{target_name}_{model_name.replace(" ", "_")}.png')
    except Exception as e:
        print(f"  SHAP failed for {target_name}: {e}")


# ==============================================================================
# CONFUSION MATRIX
# ==============================================================================

def plot_confusion_matrix_fig(y_true, y_pred, target_name, model_name):
    """Plot confusion matrix heatmap."""
    cm = confusion_matrix(y_true, y_pred)
    fig, ax = plt.subplots(figsize=(6, 6))
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', ax=ax,
                xticklabels=['No-fail', 'Fail'], yticklabels=['No-fail', 'Fail'])
    ax.set_xlabel('Predicted')
    ax.set_ylabel('Actual')
    ax.set_title(f'{target_name} — {model_name}')
    save_fig(fig, f'fig_v11_confusion_{target_name}_{model_name.replace(" ", "_")}.png')


# ==============================================================================
# ROC CURVES
# ==============================================================================

def plot_roc_curves(y_true, probs_dict, target_name):
    """Plot ROC curves for multiple models on one figure."""
    fig, ax = plt.subplots(figsize=(8, 8))
    for model_name, y_prob in probs_dict.items():
        fpr, tpr, _ = roc_curve(y_true, y_prob)
        roc_auc = auc(fpr, tpr)
        ax.plot(fpr, tpr, label=f'{model_name} (AUC={roc_auc:.3f})')
    ax.plot([0, 1], [0, 1], 'k--', label='Random')
    ax.set_xlabel('False Positive Rate')
    ax.set_ylabel('True Positive Rate')
    ax.set_title(f'{target_name} — ROC Curves')
    ax.legend(loc='lower right')
    save_fig(fig, f'fig_v11_roc_{target_name}.png')


# ==============================================================================
# GAUSSIAN PROCESS REGRESSION
# ==============================================================================

def run_gpr(X_train, y_train, X_test, y_test, target_name):
    """GPR with Matern kernel — returns predictions + uncertainty."""
    from sklearn.gaussian_process import GaussianProcessRegressor
    from sklearn.gaussian_process.kernels import Matern, WhiteKernel, ConstantKernel

    # Subsample for O(n³) scalability
    max_gpr = 500
    if len(X_train) > max_gpr:
        idx = np.random.choice(len(X_train), max_gpr, replace=False)
        X_tr_gpr, y_tr_gpr = X_train[idx], y_train[idx]
        print(f"    GPR subsampled to {max_gpr} points")
    else:
        X_tr_gpr, y_tr_gpr = X_train, y_train

    kernel = ConstantKernel(1.0) * Matern(nu=2.5) + WhiteKernel(noise_level=1e-3)
    gpr = GaussianProcessRegressor(kernel=kernel, n_restarts_optimizer=5,
                                    normalize_y=True, random_state=RANDOM_SEED)
    gpr.fit(X_tr_gpr, y_tr_gpr)
    y_pred, y_std = gpr.predict(X_test, return_std=True)

    r2 = r2_score(y_test, y_pred)
    print(f"    {target_name}: GPR R²={r2:.4f}, mean_std={y_std.mean():.4f}")
    return y_pred, y_std, {'R2': r2, 'mean_std': y_std.mean()}, gpr


def plot_gpr_uncertainty(y_true, y_pred, y_std, target_name):
    """Plot GPR predictions with confidence bands."""
    sort_idx = np.argsort(y_true)
    y_true_s = y_true[sort_idx]
    y_pred_s = y_pred[sort_idx]
    y_std_s = y_std[sort_idx]

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.scatter(range(len(y_true_s)), y_true_s, s=5, alpha=0.5, label='Actual', color='black')
    ax.plot(range(len(y_pred_s)), y_pred_s, color='#3498db', label='GPR mean')
    ax.fill_between(range(len(y_pred_s)), y_pred_s - 2*y_std_s, y_pred_s + 2*y_std_s,
                     alpha=0.2, color='#3498db', label='95% CI')
    ax.set_xlabel('Sample (sorted by true value)')
    ax.set_ylabel(target_name)
    ax.set_title(f'{target_name} — GPR Uncertainty')
    ax.legend()
    save_fig(fig, f'fig_v11_gpr_{target_name}.png')


# ==============================================================================
# CONFORMAL PREDICTION
# ==============================================================================

def run_conformal_prediction(X_train, y_train, X_test, y_test, target_name):
    """Conformal prediction with MAPIE — distribution-free prediction intervals."""
    if not HAS_MAPIE:
        print(f"    Skipping conformal for {target_name} (MAPIE not installed)")
        return None, None, None

    base_model = XGBRegressor(n_estimators=200, max_depth=5, learning_rate=0.05,
                               random_state=RANDOM_SEED)
    ccr = CrossConformalRegressor(base_model, cv=5)
    ccr.fit_conformalize(X_train, y_train)
    y_pred = ccr.predict(X_test)
    _, y_intervals = ccr.predict_interval(X_test)

    lower = y_intervals[:, 0, 0]
    upper = y_intervals[:, 1, 0]
    coverage = np.mean((y_test >= lower) & (y_test <= upper))
    avg_width = np.mean(upper - lower)

    print(f"    {target_name}: Coverage={coverage:.3f}, Avg width={avg_width:.3f}")
    return y_pred, y_intervals, {'coverage': coverage, 'avg_width': avg_width}


def plot_conformal_intervals(y_true, y_pred, y_intervals, target_name):
    """Plot conformal prediction intervals."""
    if y_intervals is None:
        return
    lower = y_intervals[:, 0, 0]
    upper = y_intervals[:, 1, 0]
    coverage = np.mean((y_true >= lower) & (y_true <= upper))

    sort_idx = np.argsort(y_true)
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.scatter(range(len(y_true)), y_true[sort_idx], s=5, color='black', label='Actual')
    ax.plot(range(len(y_pred)), y_pred[sort_idx], color='#e74c3c', label='Predicted')
    ax.fill_between(range(len(y_true)), lower[sort_idx], upper[sort_idx],
                     alpha=0.2, color='#2ecc71', label=f'90% PI (cov={coverage:.1%})')
    ax.set_xlabel('Sample (sorted)')
    ax.set_ylabel(target_name)
    ax.set_title(f'{target_name} — Conformal Prediction Intervals')
    ax.legend()
    save_fig(fig, f'fig_v11_conformal_{target_name}.png')


# ==============================================================================
# MC DROPOUT UNCERTAINTY
# ==============================================================================

def mc_dropout_predict(model, X, n_forward=50):
    """MC Dropout — run inference N times with dropout active, get mean + std."""
    model.train()  # keep dropout active
    all_preds = []
    with torch.no_grad():
        X_t = torch.FloatTensor(X).to(DEVICE)
        for _ in range(n_forward):
            pred = model(X_t).cpu().numpy().flatten()
            all_preds.append(pred)
    all_preds = np.array(all_preds)
    return all_preds.mean(axis=0), all_preds.std(axis=0)


def plot_mc_dropout_uncertainty(y_true, y_mean, y_std, target_name):
    """Plot MC dropout predictions with uncertainty bands."""
    sort_idx = np.argsort(y_true)
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.scatter(range(len(y_true)), y_true[sort_idx], s=5, color='black', label='Actual')
    ax.plot(range(len(y_mean)), y_mean[sort_idx], color='#e74c3c', label='MC mean')
    ax.fill_between(range(len(y_mean)),
                     y_mean[sort_idx] - 2*y_std[sort_idx],
                     y_mean[sort_idx] + 2*y_std[sort_idx],
                     alpha=0.2, color='#e74c3c', label='95% CI (2σ)')
    ax.set_xlabel('Sample (sorted)')
    ax.set_ylabel(target_name)
    ax.set_title(f'{target_name} — MC Dropout Uncertainty')
    ax.legend()
    save_fig(fig, f'fig_v11_mc_dropout_{target_name}.png')


# ==============================================================================
# RESULTS EXPORT
# ==============================================================================

def export_results(all_reg_summaries, all_clf_summaries, detected, n_samples, elapsed):
    """Export results summary to text file."""
    ensure_fig_dir()
    path = os.path.join(FIG_DIR, 'v11_results_summary.txt')

    with open(path, 'w', encoding='utf-8') as f:
        f.write("=" * 70 + "\n")
        f.write("V11 COMPOSITEBENCH ML PIPELINE — RESULTS SUMMARY\n")
        f.write("=" * 70 + "\n")
        f.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Samples: {n_samples}\n")
        f.write(f"Features: {len(detected['features'])}\n")
        f.write(f"Elapsed: {elapsed:.1f}s\n\n")

        f.write(f"Class weights: CLASS_WEIGHT_RATIO={CLASS_WEIGHT_RATIO:.3f}, "
                f"XGBOOST_SCALE_POS_WEIGHT={XGBOOST_SCALE_POS_WEIGHT:.3f}\n\n")

        f.write("REGRESSION RESULTS\n")
        f.write("-" * 50 + "\n")
        for target, summary in all_reg_summaries.items():
            tag = " (log1p-transformed)" if target in SKEWED_REG_TARGETS else ""
            f.write(f"\n  {target}{tag}:\n")
            for model, metrics in summary.items():
                r2 = metrics['R2']
                f.write(f"    {model:20s} R2: {r2['mean']:.4f} +/- {r2['std']:.4f}\n")

        f.write("\nCLASSIFICATION RESULTS\n")
        f.write("-" * 50 + "\n")
        for target, summary in all_clf_summaries.items():
            f.write(f"\n  {target}:\n")
            for model, metrics in summary.items():
                f1 = metrics['F1']
                f.write(f"    {model:20s} F1: {f1['mean']:.4f} +/- {f1['std']:.4f}\n")

    print(f"\n  Results saved to {path}")


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description='V11 CompositeBench ML Pipeline')
    parser.add_argument('--csv', type=str, default=None, help='Path to merged CSV')
    parser.add_argument('--csv-dir', type=str, default=None, help='Path to shard directory')
    args = parser.parse_args()

    # Default paths
    if args.csv is None and args.csv_dir is None:
        default_merged = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '..', '..', '..', 'Data', 'V11', 'results_merged_v11.csv'
        )
        default_shard_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '..', '..', '..', 'Data', 'V11', 'shards'
        )
        if os.path.exists(default_merged):
            args.csv = default_merged
        elif os.path.isdir(default_shard_dir):
            args.csv_dir = default_shard_dir
        else:
            print("ERROR: No data found. Pass --csv or --csv-dir.")
            sys.exit(1)

    start_time = time.time()

    print("=" * 70)
    print("V11 COMPOSITEBENCH ML PIPELINE")
    print("5 materials x 6 layups x 3 BCs x 750/combo = 67,500 sims")
    print("=" * 70)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Device:    {DEVICE}")
    print(f"Libraries: CatBoost={'YES' if HAS_CATBOOST else 'NO'}, "
          f"SHAP={'YES' if HAS_SHAP else 'NO'}, "
          f"Optuna={'YES' if HAS_OPTUNA else 'NO'}, "
          f"MAPIE={'YES' if HAS_MAPIE else 'NO'}")
    print("=" * 70)

    # ==================== STEP 1: LOAD DATA ====================
    df = load_data(filepath=args.csv, csv_dir=args.csv_dir)

    if len(df) < 50:
        print(f"ERROR: Only {len(df)} samples after cleaning — too few to train. Check data source.")
        sys.exit(1)

    # ==================== STEP 2: FEATURE ENGINEERING ====================
    print(f"\n{'='*60}")
    print("FEATURE ENGINEERING")
    print(f"{'='*60}")
    df = engineer_features(df)

    # ==================== STEP 3: DETECT COLUMNS ====================
    detected = detect_columns(df)
    features = detected['features']
    n_features = len(features)

    print(f"Dataset shape: {df.shape}")
    print(f"\nTarget statistics:")
    target_cols = [c for c in detected['reg_targets'] + detected['clf_targets'] if c in df.columns]
    if target_cols:
        print(df[target_cols].describe().to_string())

    # ==================== STEP 4: DATA OVERVIEW PLOTS ====================
    print(f"\n{'='*60}")
    print("DATA OVERVIEW PLOTS")
    print(f"{'='*60}")
    plot_data_overview(df, features, detected)

    # ==================== STEP 5: REGRESSION — REPEATED K-FOLD CV ====================
    all_reg_summaries = {}
    all_reg_models = {}

    for target in detected['reg_targets']:
        X, y = preprocess(df, features, target, task='regression')
        summary, last_models = repeated_kfold_cv(X, y, features, target, task='regression')
        all_reg_summaries[target] = summary
        all_reg_models[target] = last_models

        plot_cv_comparison(summary, target, task='regression')

        # Feature importance + SHAP (must use scaled X — model was trained on scaled data)
        shap_scaler = StandardScaler()
        X_scaled_for_shap = shap_scaler.fit_transform(X)
        for mname in ['XGBoost', 'CatBoost', 'Random Forest']:
            if mname in last_models and hasattr(last_models[mname], 'feature_importances_'):
                plot_feature_importance(last_models[mname], features, target, mname)
                plot_shap_analysis(last_models[mname], X_scaled_for_shap, features, target, mname)
                break

        # Scatter plot (best model — scale inside split)
        X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=TEST_SIZE, random_state=RANDOM_SEED)
        sc = StandardScaler()
        X_tr_s, X_te_s = sc.fit_transform(X_tr), sc.transform(X_te)
        best_name = max(summary, key=lambda m: summary[m]['R2']['mean'])
        if 'Neural' in best_name or 'PINN' in best_name:
            vs = int(len(X_tr_s) * 0.8)
            nn_m, _ = train_nn_regression(X_tr_s[:vs], y_tr[:vs], X_tr_s[vs:], y_tr[vs:],
                                          n_features, use_physics_loss=('PINN' in best_name), verbose=False)
            y_pred = predict_nn(nn_m, X_te_s)
        else:
            best_m = copy.deepcopy(last_models[best_name])
            best_m.fit(X_tr_s, y_tr)
            y_pred = best_m.predict(X_te_s)
        plot_regression_scatter(y_te, y_pred, target, best_name,
                                log_transformed=(target in SKEWED_REG_TARGETS))

    # ==================== STEP 6: CLASSIFICATION — WITH CLASS IMBALANCE HANDLING ====================
    all_clf_summaries = {}

    for target in detected['clf_targets']:
        X, y = preprocess(df, features, target, task='classification')
        summary, last_models = repeated_kfold_cv(X, y, features, target, task='classification')
        all_clf_summaries[target] = summary
        plot_cv_comparison(summary, target, task='classification')

        # Confusion matrix + ROC curves (on hold-out split — scale inside)
        X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=TEST_SIZE,
                                                    random_state=RANDOM_SEED, stratify=y)
        sc = StandardScaler()
        X_tr_s, X_te_s = sc.fit_transform(X_tr), sc.transform(X_te)
        probs_dict = {}
        for mname in ['XGBoost', 'CatBoost', 'Random Forest']:
            if mname in last_models:
                m = copy.deepcopy(last_models[mname])
                m.fit(X_tr_s, y_tr)
                y_pred_clf = m.predict(X_te_s)
                plot_confusion_matrix_fig(y_te, y_pred_clf, target, mname)
                if hasattr(m, 'predict_proba'):
                    probs_dict[mname] = m.predict_proba(X_te_s)[:, 1]
        if probs_dict:
            plot_roc_curves(y_te, probs_dict, target)

    # ==================== STEP 7: OPTUNA TUNING ====================
    if HAS_OPTUNA and detected['reg_targets']:
        print(f"\n{'='*60}")
        print("OPTUNA HYPERPARAMETER TUNING")
        print(f"{'='*60}")
        primary_target = 'tsai_wu_index' if 'tsai_wu_index' in detected['reg_targets'] else detected['reg_targets'][0]
        X, y = preprocess(df, features, primary_target, task='regression')
        # Optuna internally does CV, so pass unscaled X — the objective fn should scale per fold
        # For now, scale the full X for Optuna (acceptable: Optuna is hyperparameter selection, not final eval)
        tuned_xgb = optuna_tune_xgboost(X, y, task='regression')
        X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=TEST_SIZE, random_state=RANDOM_SEED)
        sc = StandardScaler()
        X_tr_s, X_te_s = sc.fit_transform(X_tr), sc.transform(X_te)
        tuned_xgb.fit(X_tr_s, y_tr)
        y_pred = tuned_xgb.predict(X_te_s)
        tuned_r2 = r2_score(y_te, y_pred)
        print(f"  Tuned XGBoost R2 on {primary_target}: {tuned_r2:.4f}")
        plot_regression_scatter(y_te, y_pred, primary_target, 'XGBoost (Optuna)',
                                log_transformed=(primary_target in SKEWED_REG_TARGETS))

        # Also tune classification
        if detected['clf_targets']:
            primary_clf = 'failed_tsai_wu' if 'failed_tsai_wu' in detected['clf_targets'] else detected['clf_targets'][0]
            X, y = preprocess(df, features, primary_clf, task='classification')
            tuned_clf = optuna_tune_xgboost(X, y, task='classification')
            X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=TEST_SIZE,
                                                        random_state=RANDOM_SEED, stratify=y)
            sc = StandardScaler()
            X_tr_s, X_te_s = sc.fit_transform(X_tr), sc.transform(X_te)
            tuned_clf.fit(X_tr_s, y_tr)
            y_pred = tuned_clf.predict(X_te_s)
            tuned_f1 = f1_score(y_te, y_pred)
            print(f"  Tuned XGBoost F1 on {primary_clf}: {tuned_f1:.4f}")

    # ==================== STEP 8: GPR WITH UNCERTAINTY ====================
    print(f"\n{'='*60}")
    print("GAUSSIAN PROCESS REGRESSION (with uncertainty)")
    print(f"{'='*60}")
    for target in [t for t in GPR_TARGETS if t in detected['reg_targets']]:
        X, y = preprocess(df, features, target, task='regression')
        X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=TEST_SIZE, random_state=RANDOM_SEED)
        s = StandardScaler()
        X_tr_s, X_te_s = s.fit_transform(X_tr), s.transform(X_te)
        y_pred_gpr, y_std_gpr, gpr_metrics, _ = run_gpr(X_tr_s, y_tr, X_te_s, y_te, target)
        plot_gpr_uncertainty(y_te, y_pred_gpr, y_std_gpr, target)

    # ==================== STEP 9: CONFORMAL PREDICTION ====================
    if HAS_MAPIE:
        print(f"\n{'='*60}")
        print("CONFORMAL PREDICTION (MAPIE)")
        print(f"{'='*60}")
        for target in [t for t in CONFORMAL_TARGETS if t in detected['reg_targets']]:
            X, y = preprocess(df, features, target, task='regression')
            X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=TEST_SIZE, random_state=RANDOM_SEED)
            s = StandardScaler()
            X_tr_s, X_te_s = s.fit_transform(X_tr), s.transform(X_te)
            y_pred_cp, y_intervals_cp, cp_metrics = run_conformal_prediction(X_tr_s, y_tr, X_te_s, y_te, target)
            if y_intervals_cp is not None:
                plot_conformal_intervals(y_te, y_pred_cp, y_intervals_cp, target)

    # ==================== STEP 10: MC DROPOUT UNCERTAINTY ====================
    print(f"\n{'='*60}")
    print("MC DROPOUT UNCERTAINTY")
    print(f"{'='*60}")
    for target in [t for t in MC_TARGETS if t in detected['reg_targets']]:
        X, y = preprocess(df, features, target, task='regression')
        X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=TEST_SIZE, random_state=RANDOM_SEED)
        s = StandardScaler()
        X_tr_s, X_te_s = s.fit_transform(X_tr), s.transform(X_te)
        val_split = int(len(X_tr_s) * 0.8)
        nn_model, _ = train_nn_regression(X_tr_s[:val_split], y_tr[:val_split],
                                           X_tr_s[val_split:], y_tr[val_split:],
                                           n_features, use_physics_loss=True, verbose=False)
        y_mean_mc, y_std_mc = mc_dropout_predict(nn_model, X_te_s)
        mc_r2 = r2_score(y_te, y_mean_mc)
        print(f"  {target}: MC Dropout R²={mc_r2:.4f}, mean_std={y_std_mc.mean():.4f}")
        plot_mc_dropout_uncertainty(y_te, y_mean_mc, y_std_mc, target)

    # ==================== STEP 11: MULTI-OUTPUT NEURAL NETWORK ====================
    if len(detected['reg_targets']) > 1:
        print(f"\n{'='*60}")
        print("MULTI-OUTPUT NEURAL NETWORK")
        print(f"{'='*60}")

        reg_targets = detected['reg_targets']
        X_all = df[features].values.astype(np.float64)
        y_all = df[reg_targets].values.astype(np.float64)

        # Split FIRST, then scale — prevents data leakage
        X_tr_raw, X_te_raw, y_tr_raw, y_te_raw = train_test_split(
            X_all, y_all, test_size=TEST_SIZE, random_state=RANDOM_SEED)

        scaler_X = StandardScaler()
        X_tr = scaler_X.fit_transform(X_tr_raw)
        X_te = scaler_X.transform(X_te_raw)
        scaler_Y = StandardScaler()
        y_tr = scaler_Y.fit_transform(y_tr_raw)
        y_te = scaler_Y.transform(y_te_raw)
        val_split = int(len(X_tr) * 0.8)

        train_loader = DataLoader(FEADataset(X_tr[:val_split], y_tr[:val_split]),
                                  batch_size=BATCH_SIZE, shuffle=True)
        val_loader = DataLoader(FEADataset(X_tr[val_split:], y_tr[val_split:]),
                                batch_size=BATCH_SIZE, shuffle=False)

        mo_model = MultiOutputNet(input_size=n_features, n_outputs=len(reg_targets)).to(DEVICE)
        criterion = PhysicsInformedLoss(0.1)
        optimizer = optim.Adam(mo_model.parameters(), lr=LEARNING_RATE, weight_decay=1e-4)
        scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=10, factor=0.5)
        es = EarlyStopping(patience=EARLY_STOPPING_PATIENCE)

        for epoch in range(EPOCHS):
            mo_model.train()
            t_loss = 0.0
            for Xb, yb in train_loader:
                Xb, yb = Xb.to(DEVICE), yb.to(DEVICE)
                optimizer.zero_grad()
                loss = criterion(mo_model(Xb), yb)
                loss.backward()
                optimizer.step()
                t_loss += loss.item() * Xb.size(0)
            t_loss /= len(train_loader.dataset)

            mo_model.eval()
            v_loss = 0.0
            with torch.no_grad():
                for Xb, yb in val_loader:
                    Xb, yb = Xb.to(DEVICE), yb.to(DEVICE)
                    v_loss += criterion(mo_model(Xb), yb).item() * Xb.size(0)
            v_loss /= len(val_loader.dataset)
            scheduler.step(v_loss)

            if (epoch + 1) % 50 == 0:
                print(f"  Epoch {epoch+1}/{EPOCHS} — Train: {t_loss:.6f}, Val: {v_loss:.6f}")

            es(v_loss, mo_model)
            if es.early_stop:
                print(f"  Early stopping at epoch {epoch+1}")
                es.load_best(mo_model)
                break

        y_pred_multi = predict_multioutput_nn(mo_model, X_te)
        y_te_orig = scaler_Y.inverse_transform(y_te)
        y_pred_orig = scaler_Y.inverse_transform(y_pred_multi)

        print("\n  Multi-Output NN Results:")
        for i, target in enumerate(reg_targets):
            r2 = r2_score(y_te_orig[:, i], y_pred_orig[:, i])
            print(f"    {target:20s} R2: {r2:.4f}")

    # ==================== STEP 12: EXPORT RESULTS ====================
    elapsed = time.time() - start_time
    export_results(all_reg_summaries, all_clf_summaries, detected, len(df), elapsed)

    print(f"\n{'='*70}")
    print(f"V11 PIPELINE COMPLETE — {elapsed:.1f}s elapsed")
    print(f"{'='*70}")


if __name__ == '__main__':
    main()
