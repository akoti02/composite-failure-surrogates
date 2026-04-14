"""RP3 V11 inference engine — multi-material, multi-layup, multi-BC surrogate."""
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
# V11 MATERIALS (5 selected for campaign)
# ============================================================================
V11_MATERIALS = {
    1:  {"name": "T300/5208",      "E1": 135000, "E2": 10000, "G12": 5200, "v12": 0.27, "e1_e2_ratio": 13.5},
    5:  {"name": "IM7/8552",       "E1": 171400, "E2": 9080,  "G12": 5290, "v12": 0.32, "e1_e2_ratio": 18.88},
    8:  {"name": "E-glass/Epoxy",  "E1": 39000,  "E2": 8600,  "G12": 3800, "v12": 0.28, "e1_e2_ratio": 4.53},
    12: {"name": "Kevlar49/Epoxy", "E1": 80000,  "E2": 5500,  "G12": 2200, "v12": 0.34, "e1_e2_ratio": 14.55},
    15: {"name": "Flax/Epoxy",     "E1": 35000,  "E2": 5500,  "G12": 3000, "v12": 0.30, "e1_e2_ratio": 6.36},
}

# ============================================================================
# V11 LAYUPS (6 selected, ALL symmetric — B matrix = 0)
# ============================================================================
V11_LAYUPS = {
    1:  {"name": "QI_8",          "angles": [0, 45, -45, 90, 90, -45, 45, 0]},
    3:  {"name": "CP_8",          "angles": [0, 90, 0, 90, 90, 0, 90, 0]},
    4:  {"name": "UD_0_8",        "angles": [0, 0, 0, 0, 0, 0, 0, 0]},
    6:  {"name": "Angle_pm45_4s", "angles": [45, -45, 45, -45, -45, 45, -45, 45]},
    7:  {"name": "Angle_pm30_4s", "angles": [30, -30, 30, -30, -30, 30, -30, 30]},
    13: {"name": "Skin_25_50_25", "angles": [45, -45, 0, 0, 90, 0, 0, -45, 45,
                                              45, -45, 0, 0, 90, 0, 0, -45, 45]},
}

# ============================================================================
# V11 BOUNDARY CONDITIONS
# ============================================================================
V11_BC_MODES = ["tension_comp", "biaxial", "uniaxial_shear"]

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
# MODEL REGISTRY (V11 — XGBoost only, all trained on 67.5k samples)
# ============================================================================
REGRESSION_MODELS = {
    "tsai_wu_index":   "xgboost_reg_tsai_wu_index.pkl",
    "max_hashin_ft":   "xgboost_reg_max_hashin_ft.pkl",
    "max_hashin_mt":   "xgboost_reg_max_hashin_mt.pkl",
    "max_hashin_mc":   "xgboost_reg_max_hashin_mc.pkl",
    "max_s11":         "xgboost_reg_max_s11.pkl",
    "min_s11":         "xgboost_reg_min_s11.pkl",
    "max_s12":         "xgboost_reg_max_s12.pkl",
}

CLASSIFICATION_MODELS = {
    "failed_tsai_wu":  "xgboost_clf_failed_tsai_wu.pkl",
    "failed_hashin":   "xgboost_clf_failed_hashin.pkl",
    "failed_puck":     "xgboost_clf_failed_puck.pkl",
    "failed_larc":     "xgboost_clf_failed_larc.pkl",
}

# Regression targets that were log1p-transformed during training
SKEWED_REG_TARGETS = {"tsai_wu_index", "max_hashin_ft", "max_hashin_mt", "max_hashin_mc"}


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
# CLT LAMINATE STIFFNESS COMPUTATION
# ============================================================================
def _compute_laminate_params(material_id: int, layup_id: int):
    """Compute laminate stiffness parameters V1A, V3A, V1D..V4D for the given
    material and layup combination. Returns dict with these values."""
    mat = V11_MATERIALS.get(material_id, V11_MATERIALS[1])
    layup = V11_LAYUPS.get(layup_id, V11_LAYUPS[1])
    angles = layup["angles"]
    n_plies = len(angles)
    t_ply = 0.15  # mm, fixed in V11 campaign
    h = n_plies * t_ply

    E1, E2, G12, v12 = mat["E1"], mat["E2"], mat["G12"], mat["v12"]
    v21 = v12 * E2 / E1
    denom = 1.0 - v12 * v21
    Q11 = E1 / denom
    Q22 = E2 / denom
    Q12 = v12 * E2 / denom
    Q66 = G12

    # ABD assembly
    A = np.zeros((3, 3))
    D = np.zeros((3, 3))
    z_bot = -h / 2.0

    for k, theta_deg in enumerate(angles):
        z_k = z_bot + k * t_ply
        z_k1 = z_k + t_ply
        rad = math.radians(theta_deg)
        c, s = math.cos(rad), math.sin(rad)
        c2, s2, cs = c*c, s*s, c*s

        Qb = np.array([
            [Q11*c2*c2 + 2*(Q12+2*Q66)*c2*s2 + Q22*s2*s2,
             (Q11+Q22-4*Q66)*c2*s2 + Q12*(c2*c2+s2*s2),
             (Q11-Q12-2*Q66)*c2*cs - (Q22-Q12-2*Q66)*s2*cs],
            [(Q11+Q22-4*Q66)*c2*s2 + Q12*(c2*c2+s2*s2),
             Q11*s2*s2 + 2*(Q12+2*Q66)*c2*s2 + Q22*c2*c2,
             (Q11-Q12-2*Q66)*cs*s2 - (Q22-Q12-2*Q66)*cs*c2],
            [(Q11-Q12-2*Q66)*c2*cs - (Q22-Q12-2*Q66)*s2*cs,
             (Q11-Q12-2*Q66)*cs*s2 - (Q22-Q12-2*Q66)*cs*c2,
             (Q11+Q22-2*Q12-2*Q66)*c2*s2 + Q66*(c2*c2+s2*s2)],
        ])

        A += Qb * (z_k1 - z_k)
        D += Qb * (z_k1**3 - z_k**3) / 3.0

    # Extract lamination parameters (matching training pipeline)
    V1A = A[0, 0]
    V3A = A[1, 1]
    V1D = D[0, 0]
    V2D = D[0, 1]
    V3D = D[1, 1]
    V4D = D[2, 2]

    return {
        "n_plies": n_plies,
        "V1A": V1A, "V3A": V3A,
        "V1D": V1D, "V2D": V2D, "V3D": V3D, "V4D": V4D,
    }


# ============================================================================
# MODEL LOADING
# ============================================================================
def load_all_models(progress_callback=None):
    _ensure_blobs()
    models = {}
    scalers = {}
    status_lines = []
    total = len(REGRESSION_MODELS) + len(CLASSIFICATION_MODELS)
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
            model = _load_blob(mfile)
            models[target] = ("xgb", model)
            scalers[target] = scaler
            status_lines.append(f"OK {target} [xgb]")
        except Exception as exc:
            status_lines.append(f"FAIL {target}: {exc}")
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

    status = "\n".join(status_lines)
    return models, scalers, feature_names, status


# ============================================================================
# PREDICTION
# ============================================================================
def predict_single(model_entry, scaler, features: np.ndarray, target_name: str = ""):
    kind, model = model_entry
    scaled = scaler.transform(features.reshape(1, -1)).astype(np.float32)
    if kind == "xgb":
        # inplace_predict avoids DMatrix construction overhead
        try:
            val = float(model.inplace_predict(scaled)[0])
        except (AttributeError, TypeError):
            val = float(model.predict(scaled)[0])
        # Inverse log1p transform for skewed targets (trained on log1p(y))
        if target_name in SKEWED_REG_TARGETS:
            val = float(np.expm1(val))
        return val
    elif kind == "xgb_clf":
        return int(model.predict(scaled)[0])
    return None


# ============================================================================
# FEATURE VECTOR CONSTRUCTION (V11 — 109 features)
# ============================================================================
def _safe_float(v, default=0.0):
    try:
        f = float(v)
        return f if math.isfinite(f) else default
    except (TypeError, ValueError):
        return default


def build_feature_vector(raw: dict, feature_names: list) -> np.ndarray:
    """Build the 109-element feature vector matching V11 training pipeline."""
    n_def = max(1, min(int(raw.get("n_defects", 1)), MAX_DEFECTS))
    material_id = int(raw.get("material_id", 1))
    layup_id = int(raw.get("layup_id", 1))
    bc_mode = str(raw.get("bc_mode", "tension_comp"))

    feats = {}

    # Material and layup IDs
    feats["material_id"] = float(material_id)
    feats["layup_id"] = float(layup_id)

    # Laminate stiffness parameters (computed from material + layup)
    lam = _compute_laminate_params(material_id, layup_id)
    feats["n_plies"] = float(lam["n_plies"])
    feats["V1A"] = lam["V1A"]
    feats["V3A"] = lam["V3A"]
    feats["V1D"] = lam["V1D"]
    feats["V2D"] = lam["V2D"]
    feats["V3D"] = lam["V3D"]
    feats["V4D"] = lam["V4D"]

    # Defect features
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

        if hl > 0:
            lig = min(y - hl, PLATE_WIDTH - y - hl) / PLATE_WIDTH
        else:
            lig = 0.0
        feats[f"defect{i}_ligament_ratio"] = max(lig, 0.0)

        px = _safe_float(raw.get("pressure_x", 1.0), 1.0)
        py = _safe_float(raw.get("pressure_y", 0.0))
        sigma_approx = math.sqrt(px ** 2 + py ** 2)
        sif = sigma_approx * math.sqrt(math.pi * hl) if hl > 0 else 0.0
        feats[f"defect{i}_sif_estimate"] = sif

    # Loading
    px = _safe_float(raw.get("pressure_x", 1.0), 1.0)
    py = _safe_float(raw.get("pressure_y", 0.0))
    feats["pressure_x"] = px
    feats["pressure_y"] = py

    # Global defect metrics
    positions = []
    for i in range(1, n_def + 1):
        positions.append((
            float(raw.get(f"defect{i}_x", PLATE_LENGTH / 2)),
            float(raw.get(f"defect{i}_y", PLATE_WIDTH / 2)),
        ))
    min_dist = 999.0
    for a in range(len(positions)):
        for b in range(a + 1, len(positions)):
            d = math.sqrt((positions[a][0] - positions[b][0]) ** 2
                          + (positions[a][1] - positions[b][1]) ** 2)
            min_dist = min(min_dist, d)
    if len(positions) < 2:
        min_dist = 0.0
    feats["min_inter_defect_dist"] = min_dist

    total_crack_area = 0.0
    for i in range(1, n_def + 1):
        hl = float(raw.get(f"defect{i}_half_length", 5.0))
        w  = float(raw.get(f"defect{i}_width", 0.5))
        total_crack_area += 2.0 * hl * w
    feats["total_crack_area_frac"] = total_crack_area / (PLATE_LENGTH * PLATE_WIDTH)

    max_sif = 0.0
    for i in range(1, n_def + 1):
        max_sif = max(max_sif, feats.get(f"defect{i}_sif_estimate", 0.0))
    feats["max_sif_estimate"] = max_sif

    min_lig = 1.0
    for i in range(1, n_def + 1):
        min_lig = min(min_lig, feats.get(f"defect{i}_ligament_ratio", 1.0))
    feats["min_ligament_ratio"] = min_lig

    # LaRC in-situ flag: UD layups get no boost
    layup_info = V11_LAYUPS.get(layup_id, V11_LAYUPS[1])
    unique_angles = len(set(layup_info["angles"]))
    feats["larc_in_situ_applied"] = 0.0 if unique_angles <= 1 else 1.0

    # Nonlinear regime warning: ±45-dominated under shear
    pm45_count = sum(1 for a in layup_info["angles"] if abs(a) == 45)
    feats["nonlinear_regime_warning"] = 1.0 if (pm45_count / len(layup_info["angles"]) > 0.5
                                                 and bc_mode == "uniaxial_shear") else 0.0

    # One-hot BC encoding
    feats["bc_biaxial"] = 1.0 if bc_mode == "biaxial" else 0.0
    feats["bc_tension_comp"] = 1.0 if bc_mode == "tension_comp" else 0.0
    feats["bc_uniaxial_shear"] = 1.0 if bc_mode == "uniaxial_shear" else 0.0

    # Solver origin (at inference time, always 0 — we're not using OR fallback)
    feats["is_or_fallback"] = 0.0

    # Engineered features
    feats["load_ratio"] = math.atan2(py, px)
    feats["total_pressure"] = math.sqrt(px ** 2 + py ** 2)

    total_crack_len = 0.0
    for i in range(1, n_def + 1):
        total_crack_len += 2.0 * float(raw.get(f"defect{i}_half_length", 5.0))
    feats["crack_area_ratio"] = total_crack_area / (PLATE_LENGTH * PLATE_WIDTH)
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

    # Material E1/E2 ratio
    mat = V11_MATERIALS.get(material_id, V11_MATERIALS[1])
    feats["material_e1_e2_ratio"] = mat["e1_e2_ratio"]

    # Defect density
    feats["defect_density"] = float(n_def) / (PLATE_LENGTH * PLATE_WIDTH)

    # Assemble in feature_names order
    vec = np.array([feats.get(f, 0.0) for f in feature_names], dtype=np.float64)
    return vec
