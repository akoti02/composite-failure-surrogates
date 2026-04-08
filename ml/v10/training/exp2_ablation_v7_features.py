"""
Experiment 2: Controlled Ablation — V7 Features on V10 Data
============================================================
Quantifies the value of engineered features by training on V10 data (101K)
using only the 68 raw V7-era features (no engineered features).

Compares:
  A) V7 raw features only (35 features: n_defects + 5×6 defect params + pressure_x/y + ply_thickness + layup_rotation)
  B) V10 full features (98 features: raw + engineered)

Uses XGBoost regression with 5-fold CV for all regression targets.
"""
import numpy as np
import pandas as pd
from sklearn.model_selection import KFold
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from xgboost import XGBRegressor
import json
import time

# ---------------------------------------------------------------------------
CSV_PATH = "/home/akoti/sims/results_merged_101k.csv"
RANDOM_SEED = 42
N_FOLDS = 5

REG_TARGETS = [
    'max_mises', 'max_s11', 'min_s11', 'max_s12',
    'tsai_wu_index',
    'max_hashin_ft', 'max_hashin_fc', 'max_hashin_mt', 'max_hashin_mc',
]

EXCLUDE = {
    'sim_id', 'solver_completed', 'n_elements',
    'tsai_wu_index', 'max_mises', 'max_s11', 'min_s11', 'max_s12',
    'max_hashin_ft', 'max_hashin_fc', 'max_hashin_mt', 'max_hashin_mc',
    'max_mises_defect1', 'max_mises_defect2', 'max_mises_defect3',
    'max_mises_defect4', 'max_mises_defect5',
    'failed_tsai_wu', 'failed_hashin',
}

# V7-era raw features (no engineered features)
# These are the basic geometric + loading parameters
V7_RAW_FEATURES = ['n_defects']
for i in range(1, 6):
    V7_RAW_FEATURES += [
        f'defect{i}_x', f'defect{i}_y',
        f'defect{i}_half_length', f'defect{i}_width',
        f'defect{i}_angle', f'defect{i}_roughness',
    ]
V7_RAW_FEATURES += ['pressure_x', 'pressure_y', 'ply_thickness', 'layup_rotation']
# Total: 1 + 30 + 4 = 35 raw features

# ---------------------------------------------------------------------------

def main():
    t0 = time.time()
    print("=" * 70)
    print("EXPERIMENT 2: ABLATION STUDY — V7 FEATURES vs V10 FEATURES")
    print("=" * 70)

    # Load data
    df = pd.read_csv(CSV_PATH)
    if 'solver_completed' in df.columns:
        df = df[df['solver_completed'].astype(str).str.upper() == 'YES'].copy()
    print(f"Loaded {len(df)} samples")

    # Full V10 features
    v10_features = [c for c in df.columns if c not in EXCLUDE]
    # V7 raw features (subset)
    v7_features = [c for c in V7_RAW_FEATURES if c in df.columns]

    print(f"V7 raw features: {len(v7_features)}")
    print(f"V10 full features: {len(v10_features)}")
    print(f"Engineered features (V10 - V7): {len(v10_features) - len(v7_features)}")

    X_v7 = df[v7_features].values.astype(np.float64)
    X_v10 = df[v10_features].values.astype(np.float64)

    results = {}

    for target in REG_TARGETS:
        if target not in df.columns:
            print(f"  Skipping {target} — not in CSV")
            continue

        print(f"\n{'='*60}")
        print(f"TARGET: {target}")
        print(f"{'='*60}")

        y = df[target].values.astype(np.float64)

        target_results = {}

        for feat_name, X_all in [('V7_raw_35', X_v7), ('V10_full_98', X_v10)]:
            print(f"\n  --- Feature set: {feat_name} ({X_all.shape[1]} features) ---")

            kf = KFold(n_splits=N_FOLDS, shuffle=True, random_state=RANDOM_SEED)
            fold_metrics = []

            for fold_i, (train_idx, test_idx) in enumerate(kf.split(X_all)):
                X_tr, X_te = X_all[train_idx], X_all[test_idx]
                y_tr, y_te = y[train_idx], y[test_idx]

                scaler = StandardScaler()
                X_tr = scaler.fit_transform(X_tr)
                X_te = scaler.transform(X_te)

                reg = XGBRegressor(
                    n_estimators=500,
                    max_depth=8,
                    learning_rate=0.05,
                    n_jobs=-1,
                    random_state=RANDOM_SEED,
                    verbosity=0,
                )
                reg.fit(X_tr, y_tr)
                y_pred = reg.predict(X_te)

                fold_metrics.append({
                    'rmse': float(np.sqrt(mean_squared_error(y_te, y_pred))),
                    'mae': float(mean_absolute_error(y_te, y_pred)),
                    'r2': float(r2_score(y_te, y_pred)),
                })

            # Aggregate
            avg = {}
            for metric in ['rmse', 'mae', 'r2']:
                vals = [fm[metric] for fm in fold_metrics]
                avg[metric] = {'mean': float(np.mean(vals)), 'std': float(np.std(vals))}

            target_results[feat_name] = avg

            print(f"    RMSE: {avg['rmse']['mean']:.4f} ± {avg['rmse']['std']:.4f}")
            print(f"    MAE:  {avg['mae']['mean']:.4f} ± {avg['mae']['std']:.4f}")
            print(f"    R²:   {avg['r2']['mean']:.4f} ± {avg['r2']['std']:.4f}")

        # Compute improvement
        r2_v7 = target_results['V7_raw_35']['r2']['mean']
        r2_v10 = target_results['V10_full_98']['r2']['mean']
        improvement = r2_v10 - r2_v7
        pct = (improvement / max(abs(r2_v7), 1e-9)) * 100
        print(f"\n  >> R² improvement from engineered features: {improvement:+.4f} ({pct:+.1f}%)")
        target_results['r2_improvement'] = float(improvement)
        target_results['r2_improvement_pct'] = float(pct)

        results[target] = target_results

    # Save results
    out_path = "/home/akoti/sims/exp2_ablation_results.json"
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {out_path}")
    print(f"Total time: {time.time() - t0:.1f}s")


if __name__ == '__main__':
    main()
