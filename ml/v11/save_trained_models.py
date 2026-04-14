"""
Save trained V11 models to disk.
Reuses the production pipeline's data loading, feature engineering, and model definitions.
Trains best models on full train split and saves with joblib/torch.
"""
import sys, os, io, time, warnings, copy
warnings.filterwarnings('ignore')

import numpy as np
import joblib
import torch

# Import everything from the production pipeline
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from v11_ml_pipeline import (
    load_data, engineer_features, detect_columns, preprocess,
    SKEWED_REG_TARGETS, RANDOM_SEED, TEST_SIZE, BATCH_SIZE, EPOCHS,
    LEARNING_RATE, EARLY_STOPPING_PATIENCE, DEVICE,
    RegressionNet, MultiOutputNet, ClassificationNet, PhysicsInformedLoss,
    FocalLoss, FEADataset, EarlyStopping,
    train_nn_regression, predict_nn,
    CLASS_WEIGHT_RATIO, XGBOOST_SCALE_POS_WEIGHT,
)

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from xgboost import XGBRegressor, XGBClassifier
from catboost import CatBoostRegressor, CatBoostClassifier
from torch.utils.data import DataLoader
import torch.optim as optim


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--csv', type=str, default=None)
    parser.add_argument('--csv-dir', type=str, default=None)
    parser.add_argument('--out', type=str, default=os.path.join(os.path.expanduser('~'),
                        'Downloads', 'v11_trained_models'))
    args = parser.parse_args()

    # Find data
    if args.csv is None and args.csv_dir is None:
        candidates = [
            os.path.join(os.path.dirname(__file__), 'results_merged_v11_final.csv'),
            os.path.join(os.path.dirname(__file__), '..', '..', 'Data', 'V11',
                         'results_merged_v11_final.csv'),
            os.path.join(os.path.dirname(__file__), '..', '..', '..', 'Data', 'V11',
                         'results_merged_v11_final.csv'),
        ]
        for c in candidates:
            if os.path.exists(c):
                args.csv = c
                break

    os.makedirs(args.out, exist_ok=True)
    start = time.time()

    print("=" * 70)
    print("V11 MODEL SAVING — Training best models and serializing to disk")
    print("=" * 70)

    # Load and engineer
    df = load_data(filepath=args.csv, csv_dir=args.csv_dir)
    df = engineer_features(df)
    detected = detect_columns(df)
    features = detected['features']
    n_features = len(features)

    # Save feature list
    joblib.dump(features, os.path.join(args.out, 'feature_names.joblib'))
    print(f"\nSaved feature names ({len(features)} features)")

    # Save metadata
    metadata = {
        'n_samples': len(df),
        'n_features': n_features,
        'feature_names': features,
        'reg_targets': detected['reg_targets'],
        'clf_targets': detected['clf_targets'],
        'skewed_targets': SKEWED_REG_TARGETS,
        'random_seed': RANDOM_SEED,
        'test_size': TEST_SIZE,
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    joblib.dump(metadata, os.path.join(args.out, 'metadata.joblib'))

    # ============================================================
    # REGRESSION MODELS — train best for each target
    # ============================================================
    print(f"\n{'='*60}")
    print("TRAINING & SAVING REGRESSION MODELS")
    print(f"{'='*60}")

    for target in detected['reg_targets']:
        print(f"\n--- {target} ---")
        X, y = preprocess(df, features, target, task='regression')
        X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=TEST_SIZE,
                                                    random_state=RANDOM_SEED)
        scaler = StandardScaler()
        X_tr_s = scaler.fit_transform(X_tr)
        X_te_s = scaler.transform(X_te)

        # Save scaler
        joblib.dump(scaler, os.path.join(args.out, f'scaler_reg_{target}.joblib'))

        # --- XGBoost ---
        xgb = XGBRegressor(n_estimators=300, max_depth=8, learning_rate=0.1,
                           subsample=0.8, colsample_bytree=0.8,
                           random_state=RANDOM_SEED, n_jobs=-1)
        xgb.fit(X_tr_s, y_tr)
        from sklearn.metrics import r2_score
        r2 = r2_score(y_te, xgb.predict(X_te_s))
        print(f"  XGBoost R²={r2:.4f}")
        joblib.dump(xgb, os.path.join(args.out, f'xgboost_reg_{target}.joblib'))

        # --- CatBoost ---
        cb = CatBoostRegressor(iterations=300, depth=8, learning_rate=0.1,
                               random_seed=RANDOM_SEED, verbose=0)
        cb.fit(X_tr_s, y_tr)
        r2 = r2_score(y_te, cb.predict(X_te_s))
        print(f"  CatBoost R²={r2:.4f}")
        cb.save_model(os.path.join(args.out, f'catboost_reg_{target}.cbm'))

        # --- Random Forest ---
        rf = RandomForestRegressor(n_estimators=200, max_depth=None,
                                   random_state=RANDOM_SEED, n_jobs=-1)
        rf.fit(X_tr_s, y_tr)
        r2 = r2_score(y_te, rf.predict(X_te_s))
        print(f"  RF R²={r2:.4f}")
        joblib.dump(rf, os.path.join(args.out, f'rf_reg_{target}.joblib'))

        # --- PINN (Neural Net with physics loss) ---
        val_split = int(len(X_tr_s) * 0.8)
        pinn, _ = train_nn_regression(X_tr_s[:val_split], y_tr[:val_split],
                                       X_tr_s[val_split:], y_tr[val_split:],
                                       n_features, use_physics_loss=True, verbose=False)
        y_pred_nn = predict_nn(pinn, X_te_s)
        r2 = r2_score(y_te, y_pred_nn)
        print(f"  PINN R²={r2:.4f}")
        torch.save(pinn.state_dict(), os.path.join(args.out, f'pinn_reg_{target}.pt'))

    # ============================================================
    # CLASSIFICATION MODELS — train best for each target
    # ============================================================
    print(f"\n{'='*60}")
    print("TRAINING & SAVING CLASSIFICATION MODELS")
    print(f"{'='*60}")

    from sklearn.metrics import f1_score

    for target in detected['clf_targets']:
        print(f"\n--- {target} ---")
        X, y = preprocess(df, features, target, task='classification')
        X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=TEST_SIZE,
                                                    random_state=RANDOM_SEED, stratify=y)
        scaler = StandardScaler()
        X_tr_s = scaler.fit_transform(X_tr)
        X_te_s = scaler.transform(X_te)

        joblib.dump(scaler, os.path.join(args.out, f'scaler_clf_{target}.joblib'))

        # Dynamic class weights from this split
        n_fail = int(y_tr.sum())
        n_nofail = len(y_tr) - n_fail
        cw_ratio = n_fail / max(n_nofail, 1)
        xgb_spw = n_nofail / max(n_fail, 1)

        # --- XGBoost ---
        xgb_clf = XGBClassifier(n_estimators=300, max_depth=8, learning_rate=0.1,
                                subsample=0.8, colsample_bytree=0.8,
                                scale_pos_weight=xgb_spw,
                                random_state=RANDOM_SEED, n_jobs=-1,
                                eval_metric='logloss')
        xgb_clf.fit(X_tr_s, y_tr)
        f1 = f1_score(y_te, xgb_clf.predict(X_te_s))
        print(f"  XGBoost F1={f1:.4f}")
        joblib.dump(xgb_clf, os.path.join(args.out, f'xgboost_clf_{target}.joblib'))

        # --- CatBoost ---
        cb_clf = CatBoostClassifier(iterations=300, depth=8, learning_rate=0.1,
                                     class_weights={0: cw_ratio, 1: 1.0},
                                     random_seed=RANDOM_SEED, verbose=0)
        cb_clf.fit(X_tr_s, y_tr)
        f1 = f1_score(y_te, cb_clf.predict(X_te_s))
        print(f"  CatBoost F1={f1:.4f}")
        cb_clf.save_model(os.path.join(args.out, f'catboost_clf_{target}.cbm'))

        # --- Random Forest ---
        rf_clf = RandomForestClassifier(n_estimators=200, max_depth=None,
                                         class_weight={0: cw_ratio, 1: 1.0},
                                         random_state=RANDOM_SEED, n_jobs=-1)
        rf_clf.fit(X_tr_s, y_tr)
        f1 = f1_score(y_te, rf_clf.predict(X_te_s))
        print(f"  RF F1={f1:.4f}")
        joblib.dump(rf_clf, os.path.join(args.out, f'rf_clf_{target}.joblib'))

    # ============================================================
    # MULTI-OUTPUT NEURAL NETWORK
    # ============================================================
    print(f"\n{'='*60}")
    print("TRAINING & SAVING MULTI-OUTPUT NEURAL NETWORK")
    print(f"{'='*60}")

    reg_targets = detected['reg_targets']
    X_all = df[features].values.astype(np.float64)
    y_all = df[reg_targets].values.astype(np.float64)

    X_tr_raw, X_te_raw, y_tr_raw, y_te_raw = train_test_split(
        X_all, y_all, test_size=TEST_SIZE, random_state=RANDOM_SEED)

    scaler_X = StandardScaler()
    X_tr = scaler_X.fit_transform(X_tr_raw)
    X_te = scaler_X.transform(X_te_raw)
    scaler_Y = StandardScaler()
    y_tr = scaler_Y.fit_transform(y_tr_raw)
    y_te = scaler_Y.transform(y_te_raw)

    joblib.dump(scaler_X, os.path.join(args.out, 'scaler_multioutput_X.joblib'))
    joblib.dump(scaler_Y, os.path.join(args.out, 'scaler_multioutput_Y.joblib'))

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

    # Evaluate
    from sklearn.metrics import r2_score
    mo_model.eval()
    with torch.no_grad():
        X_te_t = torch.FloatTensor(X_te).to(DEVICE)
        y_pred_scaled = mo_model(X_te_t).cpu().numpy()
    y_pred_orig = scaler_Y.inverse_transform(y_pred_scaled)
    y_te_orig = scaler_Y.inverse_transform(y_te)

    print("\n  Multi-Output NN Results:")
    for i, t in enumerate(reg_targets):
        r2 = r2_score(y_te_orig[:, i], y_pred_orig[:, i])
        print(f"    {t:24s} R²={r2:.4f}")

    torch.save(mo_model.state_dict(), os.path.join(args.out, 'multioutput_nn.pt'))
    # Also save model config for reconstruction
    joblib.dump({
        'input_size': n_features,
        'n_outputs': len(reg_targets),
        'reg_targets': reg_targets,
    }, os.path.join(args.out, 'multioutput_nn_config.joblib'))

    # ============================================================
    # SUMMARY
    # ============================================================
    elapsed = time.time() - start
    saved_files = sorted(os.listdir(args.out))
    print(f"\n{'='*70}")
    print(f"MODEL SAVING COMPLETE — {elapsed:.1f}s elapsed")
    print(f"Output directory: {args.out}")
    print(f"Files saved: {len(saved_files)}")
    for f in saved_files:
        sz = os.path.getsize(os.path.join(args.out, f))
        print(f"  {f:50s} {sz/1024:.1f} KB")
    print(f"{'='*70}")


if __name__ == '__main__':
    main()
