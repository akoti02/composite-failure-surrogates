"""
Experiment 1: Class Weight Balancing for XGBoost Classifiers
============================================================
Tests whether adjusting scale_pos_weight improves recall on minority class
for failed_tsai_wu and failed_hashin classification targets.

Compares: default (no balancing) vs auto (neg/pos ratio) vs manual (2x, 5x, 10x)
Uses 5-fold stratified CV on the 101K dataset.
"""
import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    confusion_matrix, roc_auc_score
)
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier
import json
import time

# ---------------------------------------------------------------------------
CSV_PATH = "/home/akoti/sims/results_merged_101k.csv"
RANDOM_SEED = 42
N_FOLDS = 5

CLF_TARGETS = ['failed_tsai_wu', 'failed_hashin']

EXCLUDE = {
    'sim_id', 'solver_completed', 'n_elements',
    'tsai_wu_index', 'max_mises', 'max_s11', 'min_s11', 'max_s12',
    'max_hashin_ft', 'max_hashin_fc', 'max_hashin_mt', 'max_hashin_mc',
    'max_mises_defect1', 'max_mises_defect2', 'max_mises_defect3',
    'max_mises_defect4', 'max_mises_defect5',
    'failed_tsai_wu', 'failed_hashin',
}

# ---------------------------------------------------------------------------

def main():
    t0 = time.time()
    print("=" * 70)
    print("EXPERIMENT 1: CLASS WEIGHT BALANCING")
    print("=" * 70)

    # Load data
    df = pd.read_csv(CSV_PATH)
    if 'solver_completed' in df.columns:
        df = df[df['solver_completed'].astype(str).str.upper() == 'YES'].copy()
    print(f"Loaded {len(df)} samples")

    features = [c for c in df.columns if c not in EXCLUDE]
    X = df[features].values.astype(np.float64)
    print(f"Features: {len(features)}")

    results = {}

    for target in CLF_TARGETS:
        print(f"\n{'='*60}")
        print(f"TARGET: {target}")
        print(f"{'='*60}")

        y = df[target].values.astype(int)
        n_pos = y.sum()
        n_neg = len(y) - n_pos
        ratio = n_neg / max(n_pos, 1)
        print(f"  Class distribution: {n_neg} neg / {n_pos} pos (ratio={ratio:.2f})")

        # Weight configurations to test
        weight_configs = {
            'default (1.0)': 1.0,
            f'auto ({ratio:.1f})': ratio,
            'mild (2.0)': 2.0,
            'moderate (5.0)': 5.0,
            'aggressive (10.0)': 10.0,
        }

        target_results = {}

        for config_name, spw in weight_configs.items():
            print(f"\n  --- scale_pos_weight = {spw:.1f} ({config_name}) ---")

            skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=RANDOM_SEED)
            fold_metrics = []

            for fold_i, (train_idx, test_idx) in enumerate(skf.split(X, y)):
                X_tr, X_te = X[train_idx], X[test_idx]
                y_tr, y_te = y[train_idx], y[test_idx]

                scaler = StandardScaler()
                X_tr = scaler.fit_transform(X_tr)
                X_te = scaler.transform(X_te)

                clf = XGBClassifier(
                    n_estimators=300,
                    max_depth=6,
                    learning_rate=0.1,
                    scale_pos_weight=spw,
                    eval_metric='logloss',
                    n_jobs=-1,
                    random_state=RANDOM_SEED,
                    verbosity=0,
                )
                clf.fit(X_tr, y_tr)
                y_pred = clf.predict(X_te)
                y_prob = clf.predict_proba(X_te)[:, 1]

                fold_metrics.append({
                    'accuracy': accuracy_score(y_te, y_pred),
                    'precision': precision_score(y_te, y_pred, zero_division=0),
                    'recall': recall_score(y_te, y_pred, zero_division=0),
                    'f1': f1_score(y_te, y_pred, zero_division=0),
                    'roc_auc': roc_auc_score(y_te, y_prob),
                    'cm': confusion_matrix(y_te, y_pred).tolist(),
                })

            # Aggregate
            avg = {}
            for metric in ['accuracy', 'precision', 'recall', 'f1', 'roc_auc']:
                vals = [fm[metric] for fm in fold_metrics]
                avg[metric] = {'mean': float(np.mean(vals)), 'std': float(np.std(vals))}

            # Sum confusion matrices
            cm_sum = np.zeros((2, 2), dtype=int)
            for fm in fold_metrics:
                cm_sum += np.array(fm['cm'])
            avg['confusion_matrix'] = cm_sum.tolist()

            target_results[config_name] = avg

            print(f"    Accuracy:  {avg['accuracy']['mean']:.4f} ± {avg['accuracy']['std']:.4f}")
            print(f"    Precision: {avg['precision']['mean']:.4f} ± {avg['precision']['std']:.4f}")
            print(f"    Recall:    {avg['recall']['mean']:.4f} ± {avg['recall']['std']:.4f}")
            print(f"    F1:        {avg['f1']['mean']:.4f} ± {avg['f1']['std']:.4f}")
            print(f"    ROC AUC:   {avg['roc_auc']['mean']:.4f} ± {avg['roc_auc']['std']:.4f}")
            print(f"    CM (sum):  TN={cm_sum[0,0]} FP={cm_sum[0,1]} FN={cm_sum[1,0]} TP={cm_sum[1,1]}")

        results[target] = target_results

    # Save results
    out_path = "/home/akoti/sims/exp1_class_weights_results.json"
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {out_path}")
    print(f"Total time: {time.time() - t0:.1f}s")


if __name__ == '__main__':
    main()
