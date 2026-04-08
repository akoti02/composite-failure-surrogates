"""
================================================================================
RP3 V2 ML PIPELINE — ELLIPTICAL DEFECTS, 7 INPUTS, RICH OUTPUTS
================================================================================
Project: ML Surrogate Model for Structural Failure Prediction
Author: Artur
Supervisor: Dr. Terence Macquart
University of Bristol - AENG30017 Research Project 3

V2 UPGRADE from V1:
    - 7 input features (was 3): defect_x, defect_y, semi_major, aspect_ratio,
      angle_deg, plate_thickness, applied_pressure
    - 300 samples via Latin Hypercube Sampling (was 100 via grid)
    - Multiple regression targets: max_mises, yield_margin, max_disp
    - 5-fold cross-validation for ALL models (sklearn + PyTorch NN)
    - Neural network hyperparameter search across 10 architectures
    - Report-quality figures at 300 DPI

EXPECTED CSV: simulation_results_v2.csv (300 rows × 18 columns)
================================================================================
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')
import seaborn as sns
from datetime import datetime
import os
import json
import warnings
warnings.filterwarnings('ignore')

# PyTorch
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader

# Scikit-learn
from sklearn.model_selection import train_test_split, KFold, StratifiedKFold, cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    mean_squared_error, mean_absolute_error, r2_score,
    accuracy_score, precision_score, recall_score, f1_score,
    confusion_matrix, classification_report, roc_curve, auc
)
from sklearn.linear_model import LogisticRegression, LinearRegression, Ridge
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor

# ============================================================================
# CONFIGURATION
# ============================================================================
RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)
torch.manual_seed(RANDOM_SEED)

DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

DATA_PATH = '/mnt/user-data/uploads/simulation_results_v2.csv'
OUTPUT_DIR = '/home/claude/v2_figures'
os.makedirs(OUTPUT_DIR, exist_ok=True)

# V2 feature and target definitions
INPUT_FEATURES = ['defect_x', 'defect_y', 'semi_major', 'aspect_ratio',
                  'angle_deg', 'plate_thickness', 'applied_pressure']
REGRESSION_TARGET = 'max_mises'
SECONDARY_TARGETS = ['yield_margin', 'max_disp']
CLASSIFICATION_TARGET = 'failed'
YIELD_STRENGTH = 250.0

# Training config
TEST_SIZE = 0.2
K_FOLDS = 5
BATCH_SIZE = 32
EPOCHS = 300
LEARNING_RATE = 0.001
EARLY_STOPPING_PATIENCE = 25

# Consistent colour scheme
COLOURS = {
    'Random Forest': '#2ecc71',
    'Gradient Boosting': '#e67e22',
    'Linear Regression': '#3498db',
    'Ridge Regression': '#9b59b6',
    'Logistic Regression': '#3498db',
    'Neural Network': '#e74c3c',
}
sns.set_style('whitegrid')
plt.rcParams.update({'font.size': 11, 'figure.dpi': 150})


# ============================================================================
# DATA LOADING
# ============================================================================
def load_v2_data(filepath):
    """Load and validate the V2 CSV (300 rows × 18 columns)."""
    print(f"Loading V2 data from: {filepath}")
    print("-" * 60)

    df = pd.read_csv(filepath)
    print(f"Loaded {len(df)} rows × {len(df.columns)} columns")

    # Validate required columns
    required = INPUT_FEATURES + [REGRESSION_TARGET, CLASSIFICATION_TARGET, 'yield_margin', 'max_disp']
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    # Remove any ERROR rows
    original = len(df)
    df[REGRESSION_TARGET] = pd.to_numeric(df[REGRESSION_TARGET], errors='coerce')
    df = df.dropna(subset=[REGRESSION_TARGET])
    df[CLASSIFICATION_TARGET] = df[CLASSIFICATION_TARGET].astype(int)
    removed = original - len(df)
    if removed > 0:
        print(f"Removed {removed} invalid rows")

    # Summary
    print(f"\nV2 Dataset Summary:")
    print(f"  Samples:          {len(df)}")
    print(f"  Input features:   {len(INPUT_FEATURES)} ({', '.join(INPUT_FEATURES)})")
    for feat in INPUT_FEATURES:
        print(f"    {feat:20s}: [{df[feat].min():.2f}, {df[feat].max():.2f}]")
    print(f"  max_mises range:  [{df['max_mises'].min():.1f}, {df['max_mises'].max():.1f}] MPa")
    print(f"  yield_margin:     [{df['yield_margin'].min():.3f}, {df['yield_margin'].max():.3f}]")
    print(f"  max_disp:         [{df['max_disp'].min():.4f}, {df['max_disp'].max():.4f}] mm")
    n_failed = df[CLASSIFICATION_TARGET].sum()
    print(f"  Failed:           {n_failed}/{len(df)} ({n_failed/len(df)*100:.1f}%)")
    print(f"  Not failed:       {len(df)-n_failed}/{len(df)} ({(len(df)-n_failed)/len(df)*100:.1f}%)")

    return df


# ============================================================================
# PyTorch DATASET & MODELS
# ============================================================================
class DefectDataset(Dataset):
    def __init__(self, X, y, task='regression'):
        self.X = torch.FloatTensor(X)
        if task == 'regression':
            self.y = torch.FloatTensor(y).unsqueeze(1)
        else:
            self.y = torch.LongTensor(y)
        self.task = task

    def __len__(self):
        return len(self.X)

    def __getitem__(self, idx):
        return self.X[idx], self.y[idx]


class RegressionNet(nn.Module):
    def __init__(self, input_size=7, hidden_sizes=[128, 64, 32], dropout_rate=0.15):
        super().__init__()
        layers = []
        prev = input_size
        for h in hidden_sizes:
            layers += [nn.Linear(prev, h), nn.ReLU(), nn.Dropout(dropout_rate)]
            prev = h
        layers.append(nn.Linear(prev, 1))
        self.network = nn.Sequential(*layers)

    def forward(self, x):
        return self.network(x)


class ClassificationNet(nn.Module):
    def __init__(self, input_size=7, hidden_sizes=[128, 64, 32], dropout_rate=0.15):
        super().__init__()
        layers = []
        prev = input_size
        for h in hidden_sizes:
            layers += [nn.Linear(prev, h), nn.ReLU(), nn.Dropout(dropout_rate)]
            prev = h
        layers.append(nn.Linear(prev, 2))
        self.network = nn.Sequential(*layers)

    def forward(self, x):
        return self.network(x)


class EarlyStopping:
    def __init__(self, patience=20, min_delta=0.0001):
        self.patience = patience
        self.min_delta = min_delta
        self.counter = 0
        self.best_loss = None
        self.early_stop = False
        self.best_state = None

    def __call__(self, val_loss, model):
        if self.best_loss is None:
            self.best_loss = val_loss
            self.best_state = {k: v.clone() for k, v in model.state_dict().items()}
        elif val_loss > self.best_loss - self.min_delta:
            self.counter += 1
            if self.counter >= self.patience:
                self.early_stop = True
        else:
            self.best_loss = val_loss
            self.best_state = {k: v.clone() for k, v in model.state_dict().items()}
            self.counter = 0

    def load_best(self, model):
        if self.best_state:
            model.load_state_dict(self.best_state)


# ============================================================================
# TRAINING FUNCTIONS
# ============================================================================
def train_nn_regression(model, train_loader, val_loader, epochs=300, lr=0.001,
                        patience=25, device='cpu', verbose=True):
    model = model.to(device)
    criterion = nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=lr, weight_decay=1e-5)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=10, factor=0.5)
    es = EarlyStopping(patience=patience)
    history = {'train_loss': [], 'val_loss': []}

    for epoch in range(epochs):
        model.train()
        train_loss = 0.0
        for X_b, y_b in train_loader:
            X_b, y_b = X_b.to(device), y_b.to(device)
            optimizer.zero_grad()
            loss = criterion(model(X_b), y_b)
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * X_b.size(0)
        train_loss /= len(train_loader.dataset)

        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for X_b, y_b in val_loader:
                X_b, y_b = X_b.to(device), y_b.to(device)
                val_loss += criterion(model(X_b), y_b).item() * X_b.size(0)
        val_loss /= len(val_loader.dataset)

        history['train_loss'].append(train_loss)
        history['val_loss'].append(val_loss)
        scheduler.step(val_loss)

        if verbose and (epoch + 1) % 50 == 0:
            print(f"  Epoch {epoch+1}/{epochs} — Train: {train_loss:.2f}, Val: {val_loss:.2f}")

        es(val_loss, model)
        if es.early_stop:
            if verbose:
                print(f"  Early stopping at epoch {epoch+1}")
            es.load_best(model)
            break

    return history


def train_nn_classification(model, train_loader, val_loader, epochs=300, lr=0.001,
                            patience=25, device='cpu', verbose=True):
    model = model.to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=lr, weight_decay=1e-5)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=10, factor=0.5)
    es = EarlyStopping(patience=patience)
    history = {'train_loss': [], 'val_loss': [], 'train_acc': [], 'val_acc': []}

    for epoch in range(epochs):
        model.train()
        t_loss, t_correct = 0.0, 0
        for X_b, y_b in train_loader:
            X_b, y_b = X_b.to(device), y_b.to(device)
            optimizer.zero_grad()
            out = model(X_b)
            loss = criterion(out, y_b)
            loss.backward()
            optimizer.step()
            t_loss += loss.item() * X_b.size(0)
            t_correct += (out.argmax(1) == y_b).sum().item()
        t_loss /= len(train_loader.dataset)
        t_acc = t_correct / len(train_loader.dataset)

        model.eval()
        v_loss, v_correct = 0.0, 0
        with torch.no_grad():
            for X_b, y_b in val_loader:
                X_b, y_b = X_b.to(device), y_b.to(device)
                out = model(X_b)
                v_loss += criterion(out, y_b).item() * X_b.size(0)
                v_correct += (out.argmax(1) == y_b).sum().item()
        v_loss /= len(val_loader.dataset)
        v_acc = v_correct / len(val_loader.dataset)

        history['train_loss'].append(t_loss)
        history['val_loss'].append(v_loss)
        history['train_acc'].append(t_acc)
        history['val_acc'].append(v_acc)
        scheduler.step(v_loss)

        if verbose and (epoch + 1) % 50 == 0:
            print(f"  Epoch {epoch+1}/{epochs} — TrLoss: {t_loss:.4f}, TrAcc: {t_acc:.3f}, "
                  f"VaLoss: {v_loss:.4f}, VaAcc: {v_acc:.3f}")

        es(v_loss, model)
        if es.early_stop:
            if verbose:
                print(f"  Early stopping at epoch {epoch+1}")
            es.load_best(model)
            break

    return history


# ============================================================================
# 5-FOLD CV FOR ALL MODELS
# ============================================================================
def cv_all_models_regression(X, y, k=5):
    """5-fold CV for all regression models including NN."""
    print(f"\n{'='*60}")
    print(f"5-FOLD CROSS-VALIDATION — REGRESSION (target: {REGRESSION_TARGET})")
    print(f"{'='*60}")

    kf = KFold(n_splits=k, shuffle=True, random_state=RANDOM_SEED)
    all_results = {}

    # Sklearn models
    sklearn_models = {
        'Linear Regression': LinearRegression(),
        'Ridge Regression': Ridge(alpha=1.0),
        'Random Forest': RandomForestRegressor(n_estimators=200, max_depth=None,
                                                min_samples_leaf=3, random_state=RANDOM_SEED),
        'Gradient Boosting': GradientBoostingRegressor(n_estimators=200, max_depth=4,
                                                        learning_rate=0.1, random_state=RANDOM_SEED),
    }

    for name, model in sklearn_models.items():
        r2_scores = cross_val_score(model, X, y, cv=kf, scoring='r2')
        neg_rmse = cross_val_score(model, X, y, cv=kf, scoring='neg_root_mean_squared_error')
        rmse_scores = -neg_rmse

        all_results[name] = {
            'R2_folds': r2_scores, 'RMSE_folds': rmse_scores,
            'R2_mean': r2_scores.mean(), 'R2_std': r2_scores.std(),
            'RMSE_mean': rmse_scores.mean(), 'RMSE_std': rmse_scores.std(),
        }
        print(f"  {name:25s}: R² = {r2_scores.mean():.4f} ± {r2_scores.std():.4f}, "
              f"RMSE = {rmse_scores.mean():.1f} ± {rmse_scores.std():.1f}")

    # Neural Network CV
    print(f"\n  Neural Network (5-fold CV)...")
    nn_r2_folds, nn_rmse_folds = [], []
    for fold, (train_idx, val_idx) in enumerate(kf.split(X)):
        X_tr, X_va = X[train_idx], X[val_idx]
        y_tr, y_va = y[train_idx], y[val_idx]

        tr_ds = DefectDataset(X_tr, y_tr, 'regression')
        va_ds = DefectDataset(X_va, y_va, 'regression')
        tr_dl = DataLoader(tr_ds, batch_size=BATCH_SIZE, shuffle=True)
        va_dl = DataLoader(va_ds, batch_size=BATCH_SIZE, shuffle=False)

        model = RegressionNet(input_size=len(INPUT_FEATURES))
        train_nn_regression(model, tr_dl, va_dl, epochs=EPOCHS, lr=LEARNING_RATE,
                           patience=EARLY_STOPPING_PATIENCE, device=DEVICE, verbose=False)

        model.eval()
        preds, acts = [], []
        with torch.no_grad():
            for xb, yb in va_dl:
                preds.extend(model(xb.to(DEVICE)).cpu().numpy().flatten())
                acts.extend(yb.numpy().flatten())
        preds, acts = np.array(preds), np.array(acts)
        nn_r2_folds.append(r2_score(acts, preds))
        nn_rmse_folds.append(np.sqrt(mean_squared_error(acts, preds)))
        print(f"    Fold {fold+1}: R² = {nn_r2_folds[-1]:.4f}, RMSE = {nn_rmse_folds[-1]:.1f}")

    nn_r2_folds = np.array(nn_r2_folds)
    nn_rmse_folds = np.array(nn_rmse_folds)
    all_results['Neural Network'] = {
        'R2_folds': nn_r2_folds, 'RMSE_folds': nn_rmse_folds,
        'R2_mean': nn_r2_folds.mean(), 'R2_std': nn_r2_folds.std(),
        'RMSE_mean': nn_rmse_folds.mean(), 'RMSE_std': nn_rmse_folds.std(),
    }
    print(f"  {'Neural Network':25s}: R² = {nn_r2_folds.mean():.4f} ± {nn_r2_folds.std():.4f}, "
          f"RMSE = {nn_rmse_folds.mean():.1f} ± {nn_rmse_folds.std():.1f}")

    return all_results


def cv_all_models_classification(X, y, k=5):
    """5-fold CV for all classification models including NN."""
    print(f"\n{'='*60}")
    print(f"5-FOLD CROSS-VALIDATION — CLASSIFICATION (target: {CLASSIFICATION_TARGET})")
    print(f"{'='*60}")

    skf = StratifiedKFold(n_splits=k, shuffle=True, random_state=RANDOM_SEED)
    all_results = {}

    sklearn_models = {
        'Logistic Regression': LogisticRegression(random_state=RANDOM_SEED, max_iter=1000),
        'Random Forest': RandomForestClassifier(n_estimators=200, random_state=RANDOM_SEED),
        'Gradient Boosting': GradientBoostingClassifier(n_estimators=200, random_state=RANDOM_SEED),
    }

    for name, model in sklearn_models.items():
        f1_scores = cross_val_score(model, X, y, cv=skf, scoring='f1')
        acc_scores = cross_val_score(model, X, y, cv=skf, scoring='accuracy')

        all_results[name] = {
            'F1_folds': f1_scores, 'Acc_folds': acc_scores,
            'F1_mean': f1_scores.mean(), 'F1_std': f1_scores.std(),
            'Acc_mean': acc_scores.mean(), 'Acc_std': acc_scores.std(),
        }
        print(f"  {name:25s}: F1 = {f1_scores.mean():.4f} ± {f1_scores.std():.4f}, "
              f"Acc = {acc_scores.mean():.4f} ± {acc_scores.std():.4f}")

    # Neural Network CV
    print(f"\n  Neural Network (5-fold CV)...")
    nn_f1_folds, nn_acc_folds = [], []
    for fold, (train_idx, val_idx) in enumerate(skf.split(X, y)):
        X_tr, X_va = X[train_idx], X[val_idx]
        y_tr, y_va = y[train_idx], y[val_idx]

        tr_ds = DefectDataset(X_tr, y_tr, 'classification')
        va_ds = DefectDataset(X_va, y_va, 'classification')
        tr_dl = DataLoader(tr_ds, batch_size=BATCH_SIZE, shuffle=True)
        va_dl = DataLoader(va_ds, batch_size=BATCH_SIZE, shuffle=False)

        model = ClassificationNet(input_size=len(INPUT_FEATURES))
        train_nn_classification(model, tr_dl, va_dl, epochs=EPOCHS, lr=LEARNING_RATE,
                               patience=EARLY_STOPPING_PATIENCE, device=DEVICE, verbose=False)

        model.eval()
        preds, acts = [], []
        with torch.no_grad():
            for xb, yb in va_dl:
                preds.extend(model(xb.to(DEVICE)).argmax(1).cpu().numpy())
                acts.extend(yb.numpy())
        preds, acts = np.array(preds), np.array(acts)
        nn_f1_folds.append(f1_score(acts, preds, zero_division=0))
        nn_acc_folds.append(accuracy_score(acts, preds))
        print(f"    Fold {fold+1}: F1 = {nn_f1_folds[-1]:.4f}, Acc = {nn_acc_folds[-1]:.4f}")

    nn_f1_folds = np.array(nn_f1_folds)
    nn_acc_folds = np.array(nn_acc_folds)
    all_results['Neural Network'] = {
        'F1_folds': nn_f1_folds, 'Acc_folds': nn_acc_folds,
        'F1_mean': nn_f1_folds.mean(), 'F1_std': nn_f1_folds.std(),
        'Acc_mean': nn_acc_folds.mean(), 'Acc_std': nn_acc_folds.std(),
    }
    print(f"  {'Neural Network':25s}: F1 = {nn_f1_folds.mean():.4f} ± {nn_f1_folds.std():.4f}, "
          f"Acc = {nn_acc_folds.mean():.4f} ± {nn_acc_folds.std():.4f}")

    return all_results


# ============================================================================
# NN HYPERPARAMETER SEARCH
# ============================================================================
def nn_hyperparameter_search(X, y, k=5):
    """Search 10 NN architectures to find the best for V2 data."""
    print(f"\n{'='*60}")
    print("NEURAL NETWORK HYPERPARAMETER SEARCH (Regression)")
    print(f"{'='*60}")

    configs = [
        {'name': '[128,64,32] dr=0.15 lr=1e-3', 'hidden': [128,64,32], 'dropout': 0.15, 'lr': 0.001},
        {'name': '[256,128,64] dr=0.15 lr=1e-3', 'hidden': [256,128,64], 'dropout': 0.15, 'lr': 0.001},
        {'name': '[128,64,32] dr=0.0 lr=1e-3', 'hidden': [128,64,32], 'dropout': 0.0, 'lr': 0.001},
        {'name': '[64,32] dr=0.1 lr=1e-3', 'hidden': [64,32], 'dropout': 0.1, 'lr': 0.001},
        {'name': '[128,64,32] dr=0.15 lr=5e-4', 'hidden': [128,64,32], 'dropout': 0.15, 'lr': 0.0005},
        {'name': '[256,128,64,32] dr=0.1 lr=1e-3', 'hidden': [256,128,64,32], 'dropout': 0.1, 'lr': 0.001},
        {'name': '[128,128,64,32] dr=0.2 lr=1e-3', 'hidden': [128,128,64,32], 'dropout': 0.2, 'lr': 0.001},
        {'name': '[64,32,16] dr=0.0 lr=2e-3', 'hidden': [64,32,16], 'dropout': 0.0, 'lr': 0.002},
        {'name': '[256,128] dr=0.1 lr=1e-3', 'hidden': [256,128], 'dropout': 0.1, 'lr': 0.001},
        {'name': '[128,64,32] dr=0.3 lr=1e-3', 'hidden': [128,64,32], 'dropout': 0.3, 'lr': 0.001},
    ]

    kf = KFold(n_splits=k, shuffle=True, random_state=RANDOM_SEED)
    results = []

    for i, cfg in enumerate(configs):
        print(f"\n  Config {i+1}/10: {cfg['name']}")
        fold_r2s = []
        for fold, (tr_idx, va_idx) in enumerate(kf.split(X)):
            X_tr, X_va = X[tr_idx], X[va_idx]
            y_tr, y_va = y[tr_idx], y[va_idx]

            tr_dl = DataLoader(DefectDataset(X_tr, y_tr, 'regression'), batch_size=BATCH_SIZE, shuffle=True)
            va_dl = DataLoader(DefectDataset(X_va, y_va, 'regression'), batch_size=BATCH_SIZE, shuffle=False)

            model = RegressionNet(input_size=len(INPUT_FEATURES),
                                  hidden_sizes=cfg['hidden'], dropout_rate=cfg['dropout'])
            train_nn_regression(model, tr_dl, va_dl, epochs=EPOCHS, lr=cfg['lr'],
                               patience=EARLY_STOPPING_PATIENCE, device=DEVICE, verbose=False)

            model.eval()
            preds, acts = [], []
            with torch.no_grad():
                for xb, yb in va_dl:
                    preds.extend(model(xb.to(DEVICE)).cpu().numpy().flatten())
                    acts.extend(yb.numpy().flatten())
            fold_r2s.append(r2_score(np.array(acts), np.array(preds)))

        fold_r2s = np.array(fold_r2s)
        results.append({
            'name': cfg['name'], 'config': cfg,
            'R2_mean': fold_r2s.mean(), 'R2_std': fold_r2s.std(),
            'R2_folds': fold_r2s
        })
        print(f"    → R² = {fold_r2s.mean():.4f} ± {fold_r2s.std():.4f}")

    # Sort by mean R²
    results.sort(key=lambda x: x['R2_mean'], reverse=True)
    print(f"\n  Best config: {results[0]['name']} (R² = {results[0]['R2_mean']:.4f})")
    return results


# ============================================================================
# FINAL MODEL TRAINING (for plots requiring predictions)
# ============================================================================
def train_final_models(X, y_reg, y_clf, test_size=0.2):
    """Train all models on a single train/test split for prediction plots."""
    X_train, X_test, yr_train, yr_test, yc_train, yc_test = train_test_split(
        X, y_reg, y_clf, test_size=test_size, random_state=RANDOM_SEED
    )

    # Further split train into train/val for NN
    X_tr, X_val, yr_tr, yr_val, yc_tr, yc_val = train_test_split(
        X_train, yr_train, yc_train, test_size=0.15, random_state=RANDOM_SEED
    )

    results = {'regression': {}, 'classification': {}}

    # --- Regression ---
    print(f"\n{'='*60}")
    print("FINAL MODEL TRAINING — REGRESSION")
    print(f"{'='*60}")

    reg_models = {
        'Linear Regression': LinearRegression(),
        'Ridge Regression': Ridge(alpha=1.0),
        'Random Forest': RandomForestRegressor(n_estimators=200, min_samples_leaf=3, random_state=RANDOM_SEED),
        'Gradient Boosting': GradientBoostingRegressor(n_estimators=200, max_depth=4, random_state=RANDOM_SEED),
    }
    for name, model in reg_models.items():
        model.fit(X_tr, yr_tr)
        preds = model.predict(X_test)
        r2 = r2_score(yr_test, preds)
        rmse = np.sqrt(mean_squared_error(yr_test, preds))
        mae = mean_absolute_error(yr_test, preds)
        results['regression'][name] = {
            'R2': r2, 'RMSE': rmse, 'MAE': mae,
            'predictions': preds, 'model': model
        }
        print(f"  {name:25s}: R² = {r2:.4f}, RMSE = {rmse:.1f}, MAE = {mae:.1f}")

    # NN regression
    tr_dl = DataLoader(DefectDataset(X_tr, yr_tr, 'regression'), batch_size=BATCH_SIZE, shuffle=True)
    va_dl = DataLoader(DefectDataset(X_val, yr_val, 'regression'), batch_size=BATCH_SIZE, shuffle=False)
    te_dl = DataLoader(DefectDataset(X_test, yr_test, 'regression'), batch_size=BATCH_SIZE, shuffle=False)

    nn_reg = RegressionNet(input_size=len(INPUT_FEATURES))
    history_reg = train_nn_regression(nn_reg, tr_dl, va_dl, epochs=EPOCHS, lr=LEARNING_RATE,
                                      patience=EARLY_STOPPING_PATIENCE, device=DEVICE)
    nn_reg.eval()
    nn_preds, nn_acts = [], []
    with torch.no_grad():
        for xb, yb in te_dl:
            nn_preds.extend(nn_reg(xb.to(DEVICE)).cpu().numpy().flatten())
            nn_acts.extend(yb.numpy().flatten())
    nn_preds, nn_acts = np.array(nn_preds), np.array(nn_acts)
    r2 = r2_score(nn_acts, nn_preds)
    rmse = np.sqrt(mean_squared_error(nn_acts, nn_preds))
    results['regression']['Neural Network'] = {
        'R2': r2, 'RMSE': rmse, 'MAE': mean_absolute_error(nn_acts, nn_preds),
        'predictions': nn_preds, 'history': history_reg
    }
    print(f"  {'Neural Network':25s}: R² = {r2:.4f}, RMSE = {rmse:.1f}")

    # --- Classification ---
    print(f"\n{'='*60}")
    print("FINAL MODEL TRAINING — CLASSIFICATION")
    print(f"{'='*60}")

    clf_models = {
        'Logistic Regression': LogisticRegression(random_state=RANDOM_SEED, max_iter=1000),
        'Random Forest': RandomForestClassifier(n_estimators=200, random_state=RANDOM_SEED),
        'Gradient Boosting': GradientBoostingClassifier(n_estimators=200, random_state=RANDOM_SEED),
    }
    for name, model in clf_models.items():
        model.fit(X_tr, yc_tr)
        preds = model.predict(X_test)
        probs = model.predict_proba(X_test)[:, 1]
        results['classification'][name] = {
            'Accuracy': accuracy_score(yc_test, preds),
            'F1': f1_score(yc_test, preds, zero_division=0),
            'predictions': preds, 'probabilities': probs, 'model': model
        }
        print(f"  {name:25s}: Acc = {results['classification'][name]['Accuracy']:.4f}, "
              f"F1 = {results['classification'][name]['F1']:.4f}")

    # NN classification
    tr_dl_c = DataLoader(DefectDataset(X_tr, yc_tr, 'classification'), batch_size=BATCH_SIZE, shuffle=True)
    va_dl_c = DataLoader(DefectDataset(X_val, yc_val, 'classification'), batch_size=BATCH_SIZE, shuffle=False)
    te_dl_c = DataLoader(DefectDataset(X_test, yc_test, 'classification'), batch_size=BATCH_SIZE, shuffle=False)

    nn_clf = ClassificationNet(input_size=len(INPUT_FEATURES))
    history_clf = train_nn_classification(nn_clf, tr_dl_c, va_dl_c, epochs=EPOCHS, lr=LEARNING_RATE,
                                          patience=EARLY_STOPPING_PATIENCE, device=DEVICE)
    nn_clf.eval()
    nn_preds_c, nn_acts_c, nn_probs_c = [], [], []
    with torch.no_grad():
        for xb, yb in te_dl_c:
            out = nn_clf(xb.to(DEVICE))
            nn_preds_c.extend(out.argmax(1).cpu().numpy())
            nn_acts_c.extend(yb.numpy())
            nn_probs_c.extend(torch.softmax(out, 1)[:, 1].cpu().numpy())
    nn_preds_c, nn_acts_c, nn_probs_c = np.array(nn_preds_c), np.array(nn_acts_c), np.array(nn_probs_c)
    results['classification']['Neural Network'] = {
        'Accuracy': accuracy_score(nn_acts_c, nn_preds_c),
        'F1': f1_score(nn_acts_c, nn_preds_c, zero_division=0),
        'predictions': nn_preds_c, 'probabilities': nn_probs_c,
        'history': history_clf
    }
    print(f"  {'Neural Network':25s}: Acc = {results['classification']['Neural Network']['Accuracy']:.4f}, "
          f"F1 = {results['classification']['Neural Network']['F1']:.4f}")

    return results, X_test, yr_test, yc_test, X_tr, yr_tr


# ============================================================================
# PLOTTING FUNCTIONS (report-quality, 300 DPI)
# ============================================================================
def save_fig(fig, name):
    path = os.path.join(OUTPUT_DIR, name)
    fig.savefig(path, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f"  Saved: {name}")
    return path


def plot_01_data_distribution(df):
    """Figure 1: V2 input parameter distributions."""
    fig, axes = plt.subplots(2, 4, figsize=(18, 9))
    fig.suptitle('V2 Dataset — Input Parameter Distributions (300 samples, LHS)', fontsize=16, fontweight='bold')
    axes = axes.flatten()

    for i, feat in enumerate(INPUT_FEATURES):
        ax = axes[i]
        ax.hist(df[feat], bins=25, color='#3498db', edgecolor='white', alpha=0.8)
        ax.set_xlabel(feat.replace('_', ' ').title(), fontsize=11)
        ax.set_ylabel('Count', fontsize=11)
        ax.axvline(df[feat].mean(), color='#e74c3c', linestyle='--', linewidth=1.5, label=f'Mean: {df[feat].mean():.1f}')
        ax.legend(fontsize=9)

    # Use last subplot for target distribution
    ax = axes[7]
    ax.hist(df['max_mises'], bins=25, color='#e74c3c', edgecolor='white', alpha=0.8)
    ax.set_xlabel('Max von Mises Stress (MPa)', fontsize=11)
    ax.set_ylabel('Count', fontsize=11)
    ax.axvline(YIELD_STRENGTH, color='black', linestyle='--', linewidth=2, label=f'Yield = {YIELD_STRENGTH} MPa')
    ax.legend(fontsize=9)

    fig.tight_layout(rect=[0, 0, 1, 0.95])
    return save_fig(fig, 'fig01_v2_data_distribution.png')


def plot_02_correlation_matrix(df):
    """Figure 2: Feature correlation heatmap."""
    cols = INPUT_FEATURES + ['max_mises', 'yield_margin', 'max_disp']
    corr = df[cols].corr()

    fig, ax = plt.subplots(figsize=(12, 10))
    mask = np.triu(np.ones_like(corr, dtype=bool), k=1)
    sns.heatmap(corr, mask=mask, annot=True, fmt='.2f', cmap='RdBu_r',
                center=0, square=True, ax=ax, linewidths=0.5,
                xticklabels=[c.replace('_', '\n') for c in cols],
                yticklabels=[c.replace('_', '\n') for c in cols])
    ax.set_title('V2 Feature Correlation Matrix (7 inputs + 3 outputs)', fontsize=14, fontweight='bold')
    fig.tight_layout()
    return save_fig(fig, 'fig02_v2_correlation_matrix.png')


def plot_03_r2_comparison(cv_results):
    """Figure 3: R² bar chart with error bars from 5-fold CV."""
    fig, ax = plt.subplots(figsize=(10, 6))
    names = list(cv_results.keys())
    means = [cv_results[n]['R2_mean'] for n in names]
    stds = [cv_results[n]['R2_std'] for n in names]
    colors = [COLOURS.get(n, '#95a5a6') for n in names]

    bars = ax.bar(names, means, yerr=stds, capsize=8, color=colors, edgecolor='white',
                  linewidth=1.5, alpha=0.85, error_kw={'linewidth': 2})
    ax.set_ylabel('R² Score (5-fold CV)', fontsize=13)
    ax.set_title('V2 Regression — Model Comparison (max_mises prediction)', fontsize=14, fontweight='bold')
    ax.set_ylim(0, 1.05)
    for bar, m, s in zip(bars, means, stds):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + s + 0.02,
                f'{m:.3f}', ha='center', va='bottom', fontweight='bold', fontsize=11)
    ax.axhline(y=0.9, color='gray', linestyle=':', alpha=0.5, label='R² = 0.9 reference')
    ax.legend(fontsize=10)
    fig.tight_layout()
    return save_fig(fig, 'fig03_v2_r2_comparison.png')


def plot_04_actual_vs_predicted(final_results, y_test):
    """Figure 4: Actual vs predicted scatter (best sklearn + NN)."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # Find best sklearn model
    sklearn_names = [n for n in final_results['regression'] if n != 'Neural Network']
    best_sk = max(sklearn_names, key=lambda n: final_results['regression'][n]['R2'])

    for ax, name in zip(axes, [best_sk, 'Neural Network']):
        res = final_results['regression'][name]
        preds = res['predictions']
        r2 = res['R2']
        ax.scatter(y_test, preds, alpha=0.5, s=30, color=COLOURS.get(name, '#95a5a6'), edgecolors='white', linewidth=0.5)
        lims = [min(y_test.min(), preds.min()) - 20, max(y_test.max(), preds.max()) + 20]
        ax.plot(lims, lims, 'k--', linewidth=1.5, alpha=0.6, label='Perfect prediction')
        ax.set_xlim(lims)
        ax.set_ylim(lims)
        ax.set_xlabel('Actual max_mises (MPa)', fontsize=12)
        ax.set_ylabel('Predicted max_mises (MPa)', fontsize=12)
        ax.set_title(f'{name} — R² = {r2:.4f}', fontsize=13, fontweight='bold')
        ax.legend(fontsize=10)
        ax.set_aspect('equal')

    fig.suptitle('V2 Regression — Actual vs Predicted', fontsize=14, fontweight='bold')
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    return save_fig(fig, 'fig04_v2_actual_vs_predicted.png')


def plot_05_feature_importance(X_train, y_train, feature_names):
    """Figure 5: RF feature importance (V2 — 7 features)."""
    rf = RandomForestRegressor(n_estimators=200, min_samples_leaf=3, random_state=RANDOM_SEED)
    rf.fit(X_train, y_train)
    importances = rf.feature_importances_
    idx = np.argsort(importances)[::-1]

    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.bar(range(len(importances)), importances[idx], color='#2ecc71', edgecolor='white',
                  linewidth=1.5, alpha=0.85)
    ax.set_xticks(range(len(importances)))
    ax.set_xticklabels([feature_names[i].replace('_', '\n') for i in idx], fontsize=11)
    ax.set_ylabel('Feature Importance', fontsize=13)
    ax.set_title('V2 Random Forest — Feature Importance (7 inputs → max_mises)', fontsize=14, fontweight='bold')
    for bar, imp in zip(bars, importances[idx]):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.005,
                f'{imp:.1%}', ha='center', va='bottom', fontweight='bold', fontsize=11)
    fig.tight_layout()
    return save_fig(fig, 'fig05_v2_feature_importance.png')


def plot_06_confusion_matrix(final_results, y_test_clf):
    """Figure 6: Confusion matrices for best sklearn + NN."""
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    sklearn_names = [n for n in final_results['classification'] if n != 'Neural Network']
    best_sk = max(sklearn_names, key=lambda n: final_results['classification'][n]['F1'])

    for ax, name in zip(axes, [best_sk, 'Neural Network']):
        cm = confusion_matrix(y_test_clf, final_results['classification'][name]['predictions'])
        sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', ax=ax, cbar=False,
                    xticklabels=['Not Failed', 'Failed'], yticklabels=['Not Failed', 'Failed'],
                    annot_kws={'size': 16})
        ax.set_xlabel('Predicted', fontsize=12)
        ax.set_ylabel('Actual', fontsize=12)
        f1 = final_results['classification'][name]['F1']
        ax.set_title(f'{name} — F1 = {f1:.4f}', fontsize=13, fontweight='bold')

    fig.suptitle('V2 Classification — Confusion Matrices', fontsize=14, fontweight='bold')
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    return save_fig(fig, 'fig06_v2_confusion_matrix.png')


def plot_07_roc_curves(final_results, y_test_clf):
    """Figure 7: ROC curves for all classifiers."""
    fig, ax = plt.subplots(figsize=(8, 7))
    for name in final_results['classification']:
        probs = final_results['classification'][name].get('probabilities')
        if probs is not None:
            fpr, tpr, _ = roc_curve(y_test_clf, probs)
            roc_auc = auc(fpr, tpr)
            ax.plot(fpr, tpr, linewidth=2, label=f'{name} (AUC = {roc_auc:.3f})',
                    color=COLOURS.get(name, '#95a5a6'))
    ax.plot([0, 1], [0, 1], 'k--', alpha=0.4, linewidth=1)
    ax.set_xlabel('False Positive Rate', fontsize=12)
    ax.set_ylabel('True Positive Rate', fontsize=12)
    ax.set_title('V2 Classification — ROC Curves', fontsize=14, fontweight='bold')
    ax.legend(fontsize=10, loc='lower right')
    fig.tight_layout()
    return save_fig(fig, 'fig07_v2_roc_curves.png')


def plot_08_nn_training_history(final_results):
    """Figure 8: NN training history (loss curves)."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Regression
    h_reg = final_results['regression']['Neural Network']['history']
    axes[0].plot(h_reg['train_loss'], label='Training', linewidth=2, color='#3498db')
    axes[0].plot(h_reg['val_loss'], label='Validation', linewidth=2, color='#e74c3c')
    axes[0].set_xlabel('Epoch', fontsize=12)
    axes[0].set_ylabel('MSE Loss', fontsize=12)
    axes[0].set_title('Regression NN — Training History', fontsize=13, fontweight='bold')
    axes[0].legend(fontsize=10)

    # Classification
    h_clf = final_results['classification']['Neural Network']['history']
    axes[1].plot(h_clf['train_loss'], label='Train Loss', linewidth=2, color='#3498db')
    axes[1].plot(h_clf['val_loss'], label='Val Loss', linewidth=2, color='#e74c3c')
    axes[1].set_xlabel('Epoch', fontsize=12)
    axes[1].set_ylabel('Cross-Entropy Loss', fontsize=12)
    axes[1].set_title('Classification NN — Training History', fontsize=13, fontweight='bold')
    axes[1].legend(fontsize=10)

    fig.suptitle('V2 Neural Network Training Curves', fontsize=14, fontweight='bold')
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    return save_fig(fig, 'fig08_v2_nn_training_history.png')


def plot_09_cv_boxplots(cv_reg, cv_clf):
    """Figure 9: CV box plots for all models."""
    fig, axes = plt.subplots(1, 2, figsize=(15, 6))

    # Regression R²
    names_r = list(cv_reg.keys())
    data_r = [cv_reg[n]['R2_folds'] for n in names_r]
    bp1 = axes[0].boxplot(data_r, labels=[n.replace(' ', '\n') for n in names_r],
                          patch_artist=True, widths=0.6)
    for patch, name in zip(bp1['boxes'], names_r):
        patch.set_facecolor(COLOURS.get(name, '#95a5a6'))
        patch.set_alpha(0.7)
    for i, d in enumerate(data_r):
        axes[0].scatter([i+1]*len(d), d, color='black', s=30, zorder=5, alpha=0.7)
    axes[0].set_ylabel('R² Score', fontsize=13)
    axes[0].set_title('Regression — 5-Fold CV R² Distribution', fontsize=13, fontweight='bold')

    # Classification F1
    names_c = list(cv_clf.keys())
    data_c = [cv_clf[n]['F1_folds'] for n in names_c]
    bp2 = axes[1].boxplot(data_c, labels=[n.replace(' ', '\n') for n in names_c],
                          patch_artist=True, widths=0.6)
    for patch, name in zip(bp2['boxes'], names_c):
        patch.set_facecolor(COLOURS.get(name, '#95a5a6'))
        patch.set_alpha(0.7)
    for i, d in enumerate(data_c):
        axes[1].scatter([i+1]*len(d), d, color='black', s=30, zorder=5, alpha=0.7)
    axes[1].set_ylabel('F1 Score', fontsize=13)
    axes[1].set_title('Classification — 5-Fold CV F1 Distribution', fontsize=13, fontweight='bold')

    fig.suptitle('V2 Cross-Validation Results Distribution', fontsize=14, fontweight='bold')
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    return save_fig(fig, 'fig09_v2_cv_boxplots.png')


def plot_10_nn_hyperparameter_search(hp_results):
    """Figure 10: NN hyperparameter search results."""
    fig, ax = plt.subplots(figsize=(12, 6))
    names = [r['name'] for r in hp_results]
    means = [r['R2_mean'] for r in hp_results]
    stds = [r['R2_std'] for r in hp_results]

    colors = ['#2ecc71' if i == 0 else '#3498db' for i in range(len(names))]
    bars = ax.barh(range(len(names)), means, xerr=stds, capsize=5, color=colors,
                   edgecolor='white', linewidth=1.5, alpha=0.85)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=10)
    ax.set_xlabel('R² Score (5-fold CV)', fontsize=13)
    ax.set_title('V2 Neural Network — Hyperparameter Search (10 configurations)', fontsize=14, fontweight='bold')
    ax.invert_yaxis()

    for i, (m, s) in enumerate(zip(means, stds)):
        ax.text(m + s + 0.01, i, f'{m:.4f}', va='center', fontweight='bold', fontsize=10)

    fig.tight_layout()
    return save_fig(fig, 'fig10_v2_nn_hyperparameter_search.png')


def plot_11_stress_location_map(df):
    """Figure 11: Spatial map of peak stress locations relative to defects."""
    fig, ax = plt.subplots(figsize=(12, 7))

    # Plot plate outline
    ax.add_patch(plt.Rectangle((0, 0), 100, 50, fill=False, edgecolor='black', linewidth=2))

    # Defect centres
    ax.scatter(df['defect_x'], df['defect_y'], s=20, alpha=0.3, color='#3498db',
               label='Defect centres', zorder=3)

    # Peak stress locations, coloured by stress magnitude
    sc = ax.scatter(df['max_mises_x'], df['max_mises_y'], c=df['max_mises'],
                    cmap='hot_r', s=15, alpha=0.6, zorder=4, edgecolors='none')
    cbar = plt.colorbar(sc, ax=ax, shrink=0.8)
    cbar.set_label('Peak von Mises Stress (MPa)', fontsize=11)

    ax.set_xlabel('x (mm)', fontsize=12)
    ax.set_ylabel('y (mm)', fontsize=12)
    ax.set_title('V2 — Peak Stress Locations on Plate (300 simulations)', fontsize=14, fontweight='bold')
    ax.set_xlim(-5, 105)
    ax.set_ylim(-5, 55)
    ax.set_aspect('equal')
    ax.legend(fontsize=10, loc='upper left')
    fig.tight_layout()
    return save_fig(fig, 'fig11_v2_stress_location_map.png')


def plot_12_yield_margin_distribution(df):
    """Figure 12: Yield margin distribution with failure threshold."""
    fig, ax = plt.subplots(figsize=(10, 6))
    safe = df[df['failed'] == 0]['yield_margin']
    failed = df[df['failed'] == 1]['yield_margin']

    ax.hist(safe, bins=20, alpha=0.7, color='#2ecc71', edgecolor='white', label=f'Safe (n={len(safe)})')
    ax.hist(failed, bins=20, alpha=0.7, color='#e74c3c', edgecolor='white', label=f'Failed (n={len(failed)})')
    ax.axvline(x=1.0, color='black', linestyle='--', linewidth=2.5, label='Yield threshold (σ/σ_Y = 1.0)')
    ax.set_xlabel('Yield Margin (σ_max / σ_Y)', fontsize=13)
    ax.set_ylabel('Count', fontsize=13)
    ax.set_title('V2 Yield Margin Distribution — Safe vs Failed', fontsize=14, fontweight='bold')
    ax.legend(fontsize=11)
    fig.tight_layout()
    return save_fig(fig, 'fig12_v2_yield_margin_distribution.png')


# ============================================================================
# MAIN
# ============================================================================
def main():
    print("=" * 70)
    print("RP3 V2 ML PIPELINE — ELLIPTICAL DEFECTS")
    print("=" * 70)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Device: {DEVICE}")
    print("=" * 70)

    # Step 1: Load data
    df = load_v2_data(DATA_PATH)

    # Step 2: Preprocess
    scaler = StandardScaler()
    X = scaler.fit_transform(df[INPUT_FEATURES].values)
    y_reg = df[REGRESSION_TARGET].values
    y_clf = df[CLASSIFICATION_TARGET].values

    print(f"\nScaled features: {X.shape}")
    print(f"Regression target: {y_reg.shape} (max_mises)")
    print(f"Classification target: {y_clf.shape} (failed — {y_clf.sum()}/{len(y_clf)} positive)")

    # Step 3: Data visualisation
    print(f"\n{'='*60}")
    print("GENERATING DATA VISUALISATION FIGURES")
    print(f"{'='*60}")
    plot_01_data_distribution(df)
    plot_02_correlation_matrix(df)
    plot_11_stress_location_map(df)
    plot_12_yield_margin_distribution(df)

    # Step 4: 5-fold CV for all models
    cv_reg = cv_all_models_regression(X, y_reg, k=K_FOLDS)
    cv_clf = cv_all_models_classification(X, y_clf, k=K_FOLDS)

    # Step 5: NN hyperparameter search
    hp_results = nn_hyperparameter_search(X, y_reg, k=K_FOLDS)

    # Step 6: Final model training (for prediction plots)
    final_results, X_test, y_test_reg, y_test_clf, X_train, y_train_reg = train_final_models(
        X, y_reg, y_clf, test_size=TEST_SIZE
    )

    # Step 7: Generate remaining figures
    print(f"\n{'='*60}")
    print("GENERATING MODEL PERFORMANCE FIGURES")
    print(f"{'='*60}")
    plot_03_r2_comparison(cv_reg)
    plot_04_actual_vs_predicted(final_results, y_test_reg)
    plot_05_feature_importance(X_train, y_train_reg, INPUT_FEATURES)
    plot_06_confusion_matrix(final_results, y_test_clf)
    plot_07_roc_curves(final_results, y_test_clf)
    plot_08_nn_training_history(final_results)
    plot_09_cv_boxplots(cv_reg, cv_clf)
    plot_10_nn_hyperparameter_search(hp_results)

    # Step 8: Summary
    print(f"\n{'='*70}")
    print("V2 ML PIPELINE — RESULTS SUMMARY")
    print(f"{'='*70}")

    print(f"\n--- Regression (5-fold CV) — Predicting max_mises ---")
    print(f"{'Model':25s} {'R² (mean±std)':20s} {'RMSE (mean±std)':20s}")
    print("-" * 65)
    for name in cv_reg:
        r = cv_reg[name]
        print(f"{name:25s} {r['R2_mean']:.4f} ± {r['R2_std']:.4f}     {r['RMSE_mean']:.1f} ± {r['RMSE_std']:.1f}")

    print(f"\n--- Classification (5-fold CV) — Predicting failed ---")
    print(f"{'Model':25s} {'F1 (mean±std)':20s} {'Acc (mean±std)':20s}")
    print("-" * 65)
    for name in cv_clf:
        r = cv_clf[name]
        print(f"{name:25s} {r['F1_mean']:.4f} ± {r['F1_std']:.4f}     {r['Acc_mean']:.4f} ± {r['Acc_std']:.4f}")

    print(f"\n--- NN Hyperparameter Search (top 3) ---")
    for i, r in enumerate(hp_results[:3]):
        print(f"  {i+1}. {r['name']} → R² = {r['R2_mean']:.4f} ± {r['R2_std']:.4f}")

    print(f"\n--- V1 vs V2 Comparison ---")
    print(f"{'Metric':25s} {'V1 (100 samples, 3 inputs)':30s} {'V2 (300 samples, 7 inputs)':30s}")
    print("-" * 85)
    best_r2_v2 = max(cv_reg[n]['R2_mean'] for n in cv_reg)
    best_name_v2 = max(cv_reg, key=lambda n: cv_reg[n]['R2_mean'])
    print(f"{'Best RF R² (CV)':25s} {'0.916 (single split)':30s} {cv_reg.get('Random Forest', {}).get('R2_mean', 0):.4f} ± {cv_reg.get('Random Forest', {}).get('R2_std', 0):.4f}")
    print(f"{'Best overall R² (CV)':25s} {'0.916 (RF, single)':30s} {best_r2_v2:.4f} ({best_name_v2})")
    print(f"{'NN R² (CV)':25s} {'0.58 (single split)':30s} {cv_reg.get('Neural Network', {}).get('R2_mean', 0):.4f} ± {cv_reg.get('Neural Network', {}).get('R2_std', 0):.4f}")
    print(f"{'Input features':25s} {'3':30s} {'7':30s}")
    print(f"{'Samples':25s} {'100':30s} {'300':30s}")
    print(f"{'Sampling':25s} {'Grid (5x5x4)':30s} {'LHS (300)':30s}")

    # Save summary to JSON
    summary = {
        'timestamp': datetime.now().isoformat(),
        'dataset': {'samples': len(df), 'inputs': len(INPUT_FEATURES), 'features': INPUT_FEATURES},
        'regression_cv': {n: {'R2_mean': float(cv_reg[n]['R2_mean']), 'R2_std': float(cv_reg[n]['R2_std']),
                               'RMSE_mean': float(cv_reg[n]['RMSE_mean']), 'RMSE_std': float(cv_reg[n]['RMSE_std'])}
                          for n in cv_reg},
        'classification_cv': {n: {'F1_mean': float(cv_clf[n]['F1_mean']), 'F1_std': float(cv_clf[n]['F1_std']),
                                   'Acc_mean': float(cv_clf[n]['Acc_mean']), 'Acc_std': float(cv_clf[n]['Acc_std'])}
                               for n in cv_clf},
        'nn_hp_search_top3': [{'name': r['name'], 'R2_mean': float(r['R2_mean']), 'R2_std': float(r['R2_std'])}
                              for r in hp_results[:3]],
    }
    summary_path = os.path.join(OUTPUT_DIR, 'v2_results_summary.json')
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"\nResults summary saved to: {summary_path}")

    print(f"\n{'='*70}")
    print("V2 ML PIPELINE COMPLETE — 12 figures generated")
    print(f"{'='*70}")


if __name__ == '__main__':
    main()
