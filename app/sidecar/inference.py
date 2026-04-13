"""RP3 inference engine — extracted from surrogate_app.py (model loading + prediction)."""
import sys
import os
import io
import math
import pickle
import base64
import logging
import numpy as np

_log = logging.getLogger("rp3.inference")

# ============================================================================
# PHYSICS / PLATE CONSTANTS
# ============================================================================
PLATE_LENGTH = 100.0   # mm
PLATE_WIDTH  = 50.0    # mm
MAX_DEFECTS  = 5

# ============================================================================
# MODEL BLOBS — lazy import from _models_data
# ============================================================================
MODEL_BLOBS = None


def _ensure_blobs():
    global MODEL_BLOBS
    if MODEL_BLOBS is not None:
        return
    from _models_data import MODEL_BLOBS as _blobs
    MODEL_BLOBS = _blobs


# ============================================================================
# MODEL REGISTRY
# ============================================================================
REGRESSION_MODELS = {
    "tsai_wu_index":   "nn_reg_tsai_wu_index.pt",
    "max_mises":       "pinn_reg_max_mises.pt",
    "max_s11":         "pinn_reg_max_s11.pt",
    "min_s11":         "xgboost_reg_min_s11.pkl",
    "max_s12":         "nn_reg_max_s12.pt",
    "max_hashin_ft":   "nn_reg_max_hashin_ft.pt",
    "max_hashin_fc":   "xgboost_reg_max_hashin_fc.pkl",
    "max_hashin_mt":   "nn_reg_max_hashin_mt.pt",
    "max_hashin_mc":   "xgboost_reg_max_hashin_mc.pkl",
}

CLASSIFICATION_MODELS = {
    "failed_tsai_wu":  "xgboost_clf_failed_tsai_wu.pkl",
    "failed_hashin":   "xgboost_clf_failed_hashin.pkl",
}

PER_DEFECT_MISES = {
    i: f"xgboost_reg_max_mises_defect{i}.pkl" for i in range(1, MAX_DEFECTS + 1)
}


# ============================================================================
# SCALER KEY DERIVATION & BLOB LOADING
# ============================================================================
def _scaler_key(model_file: str) -> str:
    base = model_file.rsplit(".", 1)[0]
    parts = base.split("_", 1)
    suffix = parts[1] if len(parts) > 1 else parts[0]
    return f"scaler_{suffix}.pkl"


def _load_blob(fname: str):
    _ensure_blobs()
    raw = base64.b85decode(MODEL_BLOBS[fname])
    return pickle.loads(raw)


# ============================================================================
# NUMPY NET — pure-numpy inference replacing PyTorch
# ============================================================================
class _NumpyNet:
    def __init__(self, data: dict):
        self._layers = data["layers"]
        self._out_W = data["output"]["W"]
        self._out_b = data["output"]["b"]

    def __call__(self, x):
        h = np.asarray(x, dtype=np.float64)
        if h.ndim == 1:
            h = h.reshape(1, -1)
        eps = 1e-5
        for layer in self._layers:
            h = h @ layer["W"].T + layer["b"]
            h = np.maximum(h, 0.0)
            h = (h - layer["bn_mean"]) / np.sqrt(layer["bn_var"] + eps)
            h = h * layer["bn_weight"] + layer["bn_bias"]
        h = h @ self._out_W.T + self._out_b
        return float(h[0, 0])


# ============================================================================
# MODEL LOADING
# ============================================================================
def load_all_models(progress_callback=None):
    _ensure_blobs()
    models = {}
    scalers = {}
    status_lines = []
    total = len(REGRESSION_MODELS) + len(CLASSIFICATION_MODELS) + len(PER_DEFECT_MISES)
    loaded_count = [0]

    def _tick():
        loaded_count[0] += 1
        if progress_callback is not None:
            progress_callback(loaded_count[0], total)

    feature_names = _load_blob("feature_names.pkl")

    # Regression models
    for target, mfile in REGRESSION_MODELS.items():
        skey = _scaler_key(mfile)
        try:
            scaler = _load_blob(skey)
        except Exception as exc:
            status_lines.append(f"SKIP {target}: scaler {skey} missing ({exc})")
            continue

        loaded = False
        npw_name = mfile.replace(".pt", ".npw")
        if npw_name in MODEL_BLOBS:
            try:
                data = _load_blob(npw_name)
                models[target] = ("npw", _NumpyNet(data))
                scalers[target] = scaler
                status_lines.append(f"OK {target} [npw]")
                loaded = True
            except Exception as exc:
                status_lines.append(f"WARN {target}: npw failed ({exc})")

        if not loaded and mfile.endswith(".pkl"):
            try:
                model = _load_blob(mfile)
                models[target] = ("xgb", model)
                scalers[target] = scaler
                status_lines.append(f"OK {target} [xgb]")
                loaded = True
            except Exception as exc:
                status_lines.append(f"FAIL {target}: {exc}")

        if not loaded:
            status_lines.append(f"FAIL {target}: no loadable model")
        _tick()

    # Classification models
    for target, mfile in CLASSIFICATION_MODELS.items():
        skey = _scaler_key(mfile)
        try:
            scaler = _load_blob(skey)
            model = _load_blob(mfile)
            models[target] = ("xgb_clf", model)
            scalers[target] = scaler
            status_lines.append(f"OK {target} [xgb_clf]")
        except Exception as exc:
            status_lines.append(f"FAIL {target}: {exc}")
        _tick()

    # Per-defect mises models
    for i, mfile in PER_DEFECT_MISES.items():
        target = f"max_mises_defect{i}"
        skey = f"scaler_reg_max_mises_defect{i}.pkl"
        try:
            scaler = _load_blob(skey)
        except Exception as exc:
            status_lines.append(f"SKIP {target}: scaler missing ({exc})")
            continue

        loaded = False
        if mfile.endswith(".pkl") and mfile in MODEL_BLOBS:
            try:
                model = _load_blob(mfile)
                models[target] = ("xgb", model)
                scalers[target] = scaler
                status_lines.append(f"OK {target} [xgb]")
                loaded = True
            except Exception as e:
                status_lines.append(f"WARN {target} [xgb]: {e}")

        if not loaded:
            npw_name = mfile.replace(".pkl", ".npw")
            if npw_name in MODEL_BLOBS:
                try:
                    data = _load_blob(npw_name)
                    models[target] = ("npw", _NumpyNet(data))
                    scalers[target] = scaler
                    status_lines.append(f"OK {target} [npw]")
                    loaded = True
                except Exception as e:
                    status_lines.append(f"WARN {target} [npw]: {e}")

        if not loaded:
            status_lines.append(f"FAIL {target}: no loadable model")
        _tick()

    status = "\n".join(status_lines)
    return models, scalers, feature_names, status


# ============================================================================
# PREDICTION
# ============================================================================
def predict_single(model_entry, scaler, features: np.ndarray):
    kind, model = model_entry
    scaled = scaler.transform(features.reshape(1, -1))
    if kind == "npw":
        return model(scaled)
    elif kind == "xgb":
        return float(model.predict(scaled)[0])
    elif kind == "xgb_clf":
        return int(model.predict(scaled)[0])
    return None


# ============================================================================
# FEATURE VECTOR CONSTRUCTION
# ============================================================================
def _safe_float(v, default=0.0):
    """Convert to float, replacing NaN/inf with default."""
    try:
        f = float(v)
        return f if math.isfinite(f) else default
    except (TypeError, ValueError):
        return default

def build_feature_vector(raw: dict, feature_names: list) -> np.ndarray:
    n_def = max(1, min(int(raw.get("n_defects", 1)), MAX_DEFECTS))
    feats = {}
    feats["n_defects"] = float(n_def)

    for i in range(1, MAX_DEFECTS + 1):
        if i <= n_def:
            x   = float(raw.get(f"defect{i}_x", PLATE_LENGTH / 2))
            y   = float(raw.get(f"defect{i}_y", PLATE_WIDTH / 2))
            hl  = float(raw.get(f"defect{i}_half_length", 5.0))
            w   = float(raw.get(f"defect{i}_width", 0.5))
            ang = float(raw.get(f"defect{i}_angle", 0.0))
            rou = float(raw.get(f"defect{i}_roughness", 0.5))
        else:
            x, y, hl, w, ang, rou = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0

        feats[f"defect{i}_x"] = x
        feats[f"defect{i}_y"] = y
        feats[f"defect{i}_half_length"] = hl
        feats[f"defect{i}_width"] = w
        feats[f"defect{i}_angle"] = ang
        feats[f"defect{i}_roughness"] = rou

        feats[f"defect{i}_cos_angle"] = math.cos(math.radians(ang))
        feats[f"defect{i}_sin_angle"] = math.sin(math.radians(ang))
        feats[f"defect{i}_aspect_ratio"] = (2.0 * hl / w) if w > 0 else 0.0
        feats[f"defect{i}_norm_x"] = (x - PLATE_LENGTH / 2) / PLATE_LENGTH
        feats[f"defect{i}_norm_y"] = (y - PLATE_WIDTH / 2) / PLATE_WIDTH
        feats[f"defect{i}_norm_length"] = 2.0 * hl / PLATE_WIDTH

        bp = max(min(x, PLATE_LENGTH - x, y, PLATE_WIDTH - y), 0.0) / (PLATE_WIDTH / 2) if i <= n_def else 0.0
        feats[f"defect{i}_boundary_prox"] = bp

        lig = min(y - hl, PLATE_WIDTH - y - hl) / PLATE_WIDTH if (i <= n_def and hl > 0) else 1.0
        feats[f"defect{i}_ligament_ratio"] = max(lig, 0.0)

        px = _safe_float(raw.get("pressure_x", 1.0), 1.0)
        py = _safe_float(raw.get("pressure_y", 0.0))
        sigma_approx = math.sqrt(px ** 2 + py ** 2)
        sif = sigma_approx * math.sqrt(math.pi * hl) if hl > 0 else 0.0
        feats[f"defect{i}_sif_estimate"] = sif

    px = _safe_float(raw.get("pressure_x", 1.0), 1.0)
    py = _safe_float(raw.get("pressure_y", 0.0))
    pt_ = _safe_float(raw.get("ply_thickness", 0.125), 0.125)
    lr  = _safe_float(raw.get("layup_rotation", 0.0))

    feats["pressure_x"] = px
    feats["pressure_y"] = py
    feats["ply_thickness"] = pt_
    feats["layup_rotation"] = lr

    positions = []
    for i in range(1, n_def + 1):
        positions.append((
            float(raw.get(f"defect{i}_x", PLATE_LENGTH / 2)),
            float(raw.get(f"defect{i}_y", PLATE_WIDTH / 2)),
        ))
    min_dist = 999.0
    for a in range(len(positions)):
        for b in range(a + 1, len(positions)):
            d = math.sqrt(
                (positions[a][0] - positions[b][0]) ** 2
                + (positions[a][1] - positions[b][1]) ** 2
            )
            min_dist = min(min_dist, d)
    if len(positions) < 2:
        min_dist = 0.0  # matches training pipeline: single defect → 0 (zero-padded like defect2..5)
    feats["min_inter_defect_dist"] = min_dist

    total_crack_area = 0.0
    for i in range(1, n_def + 1):
        hl = float(raw.get(f"defect{i}_half_length", 5.0))
        w  = float(raw.get(f"defect{i}_width", 0.5))
        total_crack_area += 2.0 * hl * w
    feats["total_crack_area_frac"] = total_crack_area / (PLATE_LENGTH * PLATE_WIDTH)

    max_sif = 0.0
    for i in range(1, n_def + 1):
        k = feats.get(f"defect{i}_sif_estimate", 0.0)
        max_sif = max(max_sif, k)
    feats["max_sif_estimate"] = max_sif

    min_lig = 1.0
    for i in range(1, n_def + 1):
        min_lig = min(min_lig, feats.get(f"defect{i}_ligament_ratio", 1.0))
    feats["min_ligament_ratio"] = min_lig

    feats["load_ratio"] = max(-20.0, min(20.0, py / (abs(px) + 1e-6)))
    feats["total_pressure"] = math.sqrt(px ** 2 + py ** 2)

    total_crack_len = 0.0
    for i in range(1, n_def + 1):
        total_crack_len += 2.0 * float(raw.get(f"defect{i}_half_length", 5.0))
    feats["total_crack_length_norm"] = total_crack_len / PLATE_WIDTH

    max_clen = 0.0
    for i in range(1, n_def + 1):
        max_clen = max(max_clen, 2.0 * float(raw.get(f"defect{i}_half_length", 5.0)))
    feats["max_crack_width_ratio"] = max_clen / PLATE_WIDTH

    load_angle = math.degrees(math.atan2(py, px))
    for i in range(1, MAX_DEFECTS + 1):
        ang = feats.get(f"defect{i}_angle", 0.0)
        diff = abs(ang - load_angle) % 180
        feats[f"defect{i}_load_alignment"] = min(diff, 180 - diff) / 90.0

    for i in range(1, MAX_DEFECTS + 1):
        nx = feats.get(f"defect{i}_norm_x", 0.0)
        ny = feats.get(f"defect{i}_norm_y", 0.0)
        feats[f"defect{i}_dist_center"] = math.sqrt(nx ** 2 + ny ** 2)

    vec = np.array([feats.get(f, 0.0) for f in feature_names], dtype=np.float64)
    return vec
