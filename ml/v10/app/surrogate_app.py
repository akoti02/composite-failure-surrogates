"""
================================================================================
RP3 — COMPOSITE FAILURE SURROGATE APPLICATION
================================================================================
Project : ML Surrogate Model for Structural Failure Prediction
Author  : Artur Akoev
Supervisor: Dr. Terence Macquart
University of Bristol — AENG30017 Research Project 3

PURPOSE:
    Desktop GUI application for real-time composite damage predictions.
    Uses pre-trained ML models (neural networks + XGBoost) to predict
    stress fields, Tsai-Wu index, Hashin damage modes, and failure
    for CFRP plates with 1-5 crack-like defects under biaxial loading.

    Models are embedded as base85-encoded blobs in _models_data.py.
    PyTorch is replaced by pure-numpy inference (_NumpyNet) for the
    bundled exe, so torch is not required at runtime.

USAGE:
    python surrogate_app.py          # run from source
    pyinstaller RP3.spec --noconfirm # build exe

================================================================================
"""

import sys
import os
import io
import platform
import ctypes
import math
import time
import pickle
import base64
import threading
import traceback
import numpy as np

# ---------------------------------------------------------------------------
# Stdout / stderr UTF-8 wrapping (Windows cp1252 fix)
# ---------------------------------------------------------------------------
if sys.stdout and hasattr(sys.stdout, "buffer") and not isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "buffer") and not isinstance(sys.stderr, io.TextIOWrapper):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Resolve base path for PyInstaller bundled exe
# ---------------------------------------------------------------------------
if getattr(sys, "frozen", False):
    _BASE_DIR = sys._MEIPASS
    sys.path.insert(0, _BASE_DIR)
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# CustomTkinter — DPI-aware setup
# ---------------------------------------------------------------------------
import customtkinter as ctk
from CTkToolTip import CTkToolTip

import re as _re  # used in _ensure_visible for geometry parsing

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Color palette — zinc neutrals + indigo accent (Linear/Vercel inspired)
_COL_BG         = "#18181b"   # zinc-900
_COL_BG_DARK    = "#09090b"   # zinc-950
_COL_PANEL      = "#1e1e22"   # custom zinc
_COL_PANEL_ALT  = "#27272a"   # zinc-800
_COL_ACCENT     = "#6366f1"   # indigo-500
_COL_ACCENT2    = "#818cf8"   # indigo-400
_COL_SUCCESS    = "#34d399"   # emerald-400
_COL_WARNING    = "#fbbf24"   # amber-400
_COL_DANGER     = "#f87171"   # red-400
_COL_TEXT        = "#f4f4f5"   # zinc-100
_COL_TEXT_DIM    = "#a1a1aa"   # zinc-400
_COL_BORDER      = "#3f3f46"   # zinc-700
_COL_CARD        = "#23232a"   # slightly lighter panel
_COL_CANVAS_BG   = "#131316"   # very dark for canvas
_COL_SAFE_BG     = "#052e16"   # dark green
_COL_WARN_BG     = "#422006"   # dark amber
_COL_CRIT_BG     = "#450a0a"   # dark red


# ============================================================================
# TEST MODE flag (set by test harness to disable animations / splash)
# ============================================================================
_TEST_MODE = False

# ============================================================================
# LOGGING
# ============================================================================
import logging

if getattr(sys, "frozen", False):
    _log_dir = os.path.join(os.path.expanduser("~"), "AppData", "Local", "RP3")
    os.makedirs(_log_dir, exist_ok=True)
    _log_path = os.path.join(_log_dir, "rp3.log")
else:
    _log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rp3.log")
class _FlushFileHandler(logging.FileHandler):
    """FileHandler that flushes after every write — ensures no log loss on crash."""
    def emit(self, record):
        super().emit(record)
        self.flush()

_log_handler = _FlushFileHandler(_log_path)
_log_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
_log = logging.getLogger("rp3")
_log.setLevel(logging.INFO)
_log.addHandler(_log_handler)

import atexit
atexit.register(logging.shutdown)

def _global_excepthook(exc_type, exc_val, exc_tb):
    _log.error("Unhandled exception", exc_info=(exc_type, exc_val, exc_tb))
sys.excepthook = _global_excepthook

# ============================================================================
# PHYSICS / PLATE CONSTANTS
# ============================================================================
PLATE_LENGTH = 100.0   # mm
PLATE_WIDTH  = 50.0    # mm
MAX_DEFECTS  = 5

# ============================================================================
# ANIMATION UTILITIES
# ============================================================================


def _animate(widget, duration_ms, callback, on_done=None, fps=60):
    """Run an ease-out cubic animation over *duration_ms* milliseconds.

    *callback(t)* is called each frame with t in [0, 1] (eased).
    *on_done()* is called once when the animation completes.
    """
    interval = max(1, int(1000 / fps))
    total_frames = max(1, int(duration_ms / interval))
    frame = [0]

    def _step():
        frame[0] += 1
        raw_t = min(frame[0] / total_frames, 1.0)
        t = 1.0 - (1.0 - raw_t) ** 3          # ease-out cubic
        callback(t)
        if raw_t < 1.0:
            widget.after(interval, _step)
        elif on_done is not None:
            on_done()

    widget.after(interval, _step)


def _lerp_hex(c1: str, c2: str, t: float) -> str:
    """Linearly interpolate between two hex colours."""
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


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
# TORCH — lazy optional import
# ============================================================================
TORCH_AVAILABLE = None
_torch = None
_nn = None


def _ensure_torch():
    global TORCH_AVAILABLE, _torch, _nn
    if TORCH_AVAILABLE is not None:
        return TORCH_AVAILABLE
    try:
        import torch
        import torch.nn as nn
        _torch = torch
        _nn = nn
        TORCH_AVAILABLE = True
    except ImportError:
        TORCH_AVAILABLE = False
    return TORCH_AVAILABLE


# ============================================================================
# REGRESSION NET (PyTorch) — same architecture as training pipeline
# ============================================================================


def _make_regression_net(input_size, hidden_sizes=(512, 256, 128, 64), dropout_rate=0.2):
    """Build a Sequential regression network matching the training code."""
    nn = _nn
    layers = []
    prev = input_size
    for h in hidden_sizes:
        layers.extend([
            nn.Linear(prev, h),
            nn.ReLU(),
            nn.BatchNorm1d(h),
            nn.Dropout(dropout_rate),
        ])
        prev = h
    layers.append(nn.Linear(prev, 1))
    return nn.Sequential(*layers)


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

# Per-defect mises models (defect 1-5)
PER_DEFECT_MISES = {
    i: f"xgboost_reg_max_mises_defect{i}.pkl" for i in range(1, MAX_DEFECTS + 1)
}

# ============================================================================
# SCALER KEY DERIVATION & BLOB LOADING
# ============================================================================


def _scaler_key(model_file: str) -> str:
    """Derive scaler pickle name from model filename.

    nn_reg_tsai_wu_index.pt  ->  scaler_reg_tsai_wu_index.pkl
    xgboost_clf_failed_hashin.pkl  ->  scaler_clf_failed_hashin.pkl
    """
    base = model_file.rsplit(".", 1)[0]           # strip extension
    parts = base.split("_", 1)                    # split at first _
    suffix = parts[1] if len(parts) > 1 else parts[0]
    return f"scaler_{suffix}.pkl"


def _load_blob(fname: str):
    """Load a model or scaler from the base85-encoded blob store."""
    _ensure_blobs()
    raw = base64.b85decode(MODEL_BLOBS[fname])
    return pickle.loads(raw)


# ============================================================================
# NUMPY NET — pure-numpy inference replacing PyTorch
# ============================================================================


class _NumpyNet:
    """Minimal inference engine matching RegressionNet architecture.

    Architecture per hidden block:  Linear -> ReLU -> BatchNorm (-> Dropout no-op)
    Final block:  Linear(prev, 1)
    """

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
            h = h @ layer["W"].T + layer["b"]        # Linear
            h = np.maximum(h, 0.0)                     # ReLU
            h = (h - layer["bn_mean"]) / np.sqrt(layer["bn_var"] + eps)   # BN
            h = h * layer["bn_weight"] + layer["bn_bias"]
        h = h @ self._out_W.T + self._out_b           # Output linear
        return float(h[0, 0])


# ============================================================================
# MODEL LOADING
# ============================================================================
_models_lock = threading.Lock()


def load_all_models(progress_callback=None):
    """Load all regression, classification, and per-defect models.

    Returns (models_dict, scalers_dict, feature_names, status_text).
    Prefers .npw over .pt for neural networks.
    *progress_callback(loaded, total)* is called after each model.
    """
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

    # Feature names
    feature_names = _load_blob("feature_names.pkl")

    # --- Regression models ---
    for target, mfile in REGRESSION_MODELS.items():
        skey = _scaler_key(mfile)
        try:
            scaler = _load_blob(skey)
        except Exception as exc:
            status_lines.append(f"SKIP {target}: scaler {skey} missing ({exc})")
            continue

        loaded = False

        # Try .npw first (torch-free)
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

        # Fall back to .pt
        if not loaded and mfile.endswith(".pt") and _ensure_torch():
            try:
                raw = base64.b85decode(MODEL_BLOBS[mfile])
                buf = io.BytesIO(raw)
                net = _torch.load(buf, map_location="cpu", weights_only=False)
                net.eval()
                models[target] = ("nn", net)
                scalers[target] = scaler
                status_lines.append(f"OK {target} [pt]")
                loaded = True
            except Exception as exc:
                status_lines.append(f"WARN {target}: pt failed ({exc})")

        # .pkl (XGBoost)
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

    # --- Classification models ---
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

    # --- Per-defect mises models ---
    for i, mfile in PER_DEFECT_MISES.items():
        target = f"max_mises_defect{i}"
        skey = f"scaler_reg_max_mises_defect{i}.pkl"
        try:
            scaler = _load_blob(skey)
        except Exception as exc:
            status_lines.append(f"SKIP {target}: scaler missing ({exc})")
            continue

        loaded = False

        # Try .pkl first (XGBoost)
        if mfile.endswith(".pkl") and mfile in MODEL_BLOBS:
            try:
                model = _load_blob(mfile)
                models[target] = ("xgb", model)
                scalers[target] = scaler
                status_lines.append(f"OK {target} [xgb]")
                loaded = True
            except Exception:
                pass

        # Fall back to .pt
        if not loaded:
            pt_name = mfile.replace(".pkl", ".pt")
            npw_name = mfile.replace(".pkl", ".npw")
            if npw_name in MODEL_BLOBS:
                try:
                    data = _load_blob(npw_name)
                    models[target] = ("npw", _NumpyNet(data))
                    scalers[target] = scaler
                    status_lines.append(f"OK {target} [npw]")
                    loaded = True
                except Exception:
                    pass
            if not loaded and pt_name in MODEL_BLOBS and _ensure_torch():
                try:
                    raw = base64.b85decode(MODEL_BLOBS[pt_name])
                    buf = io.BytesIO(raw)
                    net = _torch.load(buf, map_location="cpu", weights_only=False)
                    net.eval()
                    models[target] = ("nn", net)
                    scalers[target] = scaler
                    status_lines.append(f"OK {target} [pt]")
                    loaded = True
                except Exception:
                    pass

        if not loaded:
            status_lines.append(f"FAIL {target}: no loadable model")
        _tick()

    status = "\n".join(status_lines)
    _log.info("Models loaded:\n%s", status)
    return models, scalers, feature_names, status


# ============================================================================
# FEATURE VECTOR CONSTRUCTION
# ============================================================================


def build_feature_vector(raw: dict, feature_names: list) -> np.ndarray:
    """Build the 98-element feature vector expected by the models.

    *raw* contains UI-provided values:
        n_defects, pressure_x, pressure_y, ply_thickness, layup_rotation,
        defect{1-5}_{x, y, half_length, width, angle, roughness}

    Engineered features are computed to match the training pipeline.
    """
    n_def = int(raw.get("n_defects", 1))

    # ---- Per-defect raw + engineered features ----
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

        # Engineered
        feats[f"defect{i}_cos_angle"] = math.cos(math.radians(ang))
        feats[f"defect{i}_sin_angle"] = math.sin(math.radians(ang))
        feats[f"defect{i}_aspect_ratio"] = (2.0 * hl / w) if w > 0 else 0.0
        feats[f"defect{i}_norm_x"] = (x - PLATE_LENGTH / 2) / PLATE_LENGTH
        feats[f"defect{i}_norm_y"] = (y - PLATE_WIDTH / 2) / PLATE_WIDTH
        feats[f"defect{i}_norm_length"] = 2.0 * hl / PLATE_WIDTH

        # Boundary proximity (min distance to any edge, normalised)
        bp = max(min(x, PLATE_LENGTH - x, y, PLATE_WIDTH - y), 0.0) / (PLATE_WIDTH / 2) if i <= n_def else 0.0
        feats[f"defect{i}_boundary_prox"] = bp

        # Ligament ratio (smallest remaining material / plate width)
        lig = min(y - hl, PLATE_WIDTH - y - hl) / PLATE_WIDTH if (i <= n_def and hl > 0) else 1.0
        feats[f"defect{i}_ligament_ratio"] = max(lig, 0.0)

        # Stress intensity factor estimate (KI ~ sigma * sqrt(pi * a))
        px = float(raw.get("pressure_x", 1.0))
        py = float(raw.get("pressure_y", 0.0))
        sigma_approx = math.sqrt(px ** 2 + py ** 2)
        sif = sigma_approx * math.sqrt(math.pi * hl) if hl > 0 else 0.0
        feats[f"defect{i}_sif_estimate"] = sif

    # ---- Global features ----
    px = float(raw.get("pressure_x", 1.0))
    py = float(raw.get("pressure_y", 0.0))
    pt_ = float(raw.get("ply_thickness", 0.125))
    lr  = float(raw.get("layup_rotation", 0.0))

    feats["pressure_x"] = px
    feats["pressure_y"] = py
    feats["ply_thickness"] = pt_
    feats["layup_rotation"] = lr

    # Min inter-defect distance
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
        min_dist = 0.0
    feats["min_inter_defect_dist"] = min_dist

    # Total crack area fraction
    total_crack_area = 0.0
    for i in range(1, n_def + 1):
        hl = float(raw.get(f"defect{i}_half_length", 5.0))
        w  = float(raw.get(f"defect{i}_width", 0.5))
        total_crack_area += 2.0 * hl * w
    feats["total_crack_area_frac"] = total_crack_area / (PLATE_LENGTH * PLATE_WIDTH)

    # Max SIF estimate
    max_sif = 0.0
    for i in range(1, n_def + 1):
        k = feats.get(f"defect{i}_sif_estimate", 0.0)
        max_sif = max(max_sif, k)
    feats["max_sif_estimate"] = max_sif

    # Min ligament ratio
    min_lig = 1.0
    for i in range(1, n_def + 1):
        min_lig = min(min_lig, feats.get(f"defect{i}_ligament_ratio", 1.0))
    feats["min_ligament_ratio"] = min_lig

    # Load ratio & total pressure
    feats["load_ratio"] = py / (abs(px) + 1e-6)
    feats["total_pressure"] = math.sqrt(px ** 2 + py ** 2)

    # Total crack length normalised
    total_crack_len = 0.0
    for i in range(1, n_def + 1):
        total_crack_len += 2.0 * float(raw.get(f"defect{i}_half_length", 5.0))
    feats["total_crack_length_norm"] = total_crack_len / PLATE_WIDTH

    # Max crack-to-width ratio
    max_clen = 0.0
    for i in range(1, n_def + 1):
        max_clen = max(max_clen, 2.0 * float(raw.get(f"defect{i}_half_length", 5.0)))
    feats["max_crack_width_ratio"] = max_clen / PLATE_WIDTH

    # Per-defect load alignment
    load_angle = math.degrees(math.atan2(py, px))
    for i in range(1, MAX_DEFECTS + 1):
        ang = feats.get(f"defect{i}_angle", 0.0)
        diff = abs(ang - load_angle) % 180
        feats[f"defect{i}_load_alignment"] = min(diff, 180 - diff) / 90.0

    # Per-defect distance from centre
    for i in range(1, MAX_DEFECTS + 1):
        nx = feats.get(f"defect{i}_norm_x", 0.0)
        ny = feats.get(f"defect{i}_norm_y", 0.0)
        feats[f"defect{i}_dist_center"] = math.sqrt(nx ** 2 + ny ** 2)

    # ---- Assemble in feature_names order ----
    vec = np.array([feats.get(f, 0.0) for f in feature_names], dtype=np.float64)
    return vec


# ============================================================================
# PREDICTION
# ============================================================================


def predict_single(model_entry, scaler, features: np.ndarray):
    """Run a single model prediction. Returns float or int."""
    kind, model = model_entry
    scaled = scaler.transform(features.reshape(1, -1))
    if kind == "npw":
        return model(scaled)
    elif kind == "nn":
        with _torch.no_grad():
            t = _torch.tensor(scaled, dtype=_torch.float32)
            return model(t).item()
    elif kind == "xgb":
        return float(model.predict(scaled)[0])
    elif kind == "xgb_clf":
        return int(model.predict(scaled)[0])
    return None


# ============================================================================
# ICON CACHING
# ============================================================================
_ICO_CACHE = os.path.join(os.path.expanduser("~"), "AppData", "Local", "RP3", "cache")
_ICO_VERSION = "3"


def _get_icon_path() -> str:
    """Return path to rp3.ico, caching in AppData if running from exe."""
    src = os.path.join(_BASE_DIR, "rp3.ico")
    if os.path.exists(src):
        # Cache a copy for faster startup next time
        try:
            os.makedirs(_ICO_CACHE, exist_ok=True)
            ver_file = os.path.join(_ICO_CACHE, ".ico_version")
            cached = os.path.join(_ICO_CACHE, "rp3.ico")
            need_copy = True
            if os.path.exists(ver_file) and os.path.exists(cached):
                with open(ver_file) as f:
                    if f.read().strip() == _ICO_VERSION:
                        need_copy = False
            if need_copy:
                import shutil
                shutil.copy2(src, cached)
                with open(ver_file, "w") as f:
                    f.write(_ICO_VERSION)
        except Exception:
            pass
        return src
    # Try cache
    cached = os.path.join(_ICO_CACHE, "rp3.ico")
    if os.path.exists(cached):
        return cached
    return ""


# ============================================================================
# PRESETS — Quick-start scenarios for common use cases
# ============================================================================
_PRESETS = {
    "Single Central Crack": {
        "n_defects": 1, "pressure_x": 100.0, "pressure_y": 0.0,
        "ply_thickness": 0.125, "layup_rotation": 0.0,
        "defects": [
            {"x": 50.0, "y": 25.0, "half_length": 5.0, "width": 0.5, "angle": 0.0, "roughness": 0.5},
        ],
    },
    "Biaxial Loading": {
        "n_defects": 2, "pressure_x": 100.0, "pressure_y": 100.0,
        "ply_thickness": 0.125, "layup_rotation": 0.0,
        "defects": [
            {"x": 35.0, "y": 20.0, "half_length": 5.0, "width": 0.5, "angle": 0.0, "roughness": 0.5},
            {"x": 65.0, "y": 30.0, "half_length": 5.0, "width": 0.5, "angle": 90.0, "roughness": 0.5},
        ],
    },
    "Severe Multi-Defect": {
        "n_defects": 5, "pressure_x": 200.0, "pressure_y": 50.0,
        "ply_thickness": 0.125, "layup_rotation": 0.0,
        "defects": [
            {"x": 50.0, "y": 25.0, "half_length": 10.0, "width": 1.0, "angle": 0.0, "roughness": 0.8},
            {"x": 30.0, "y": 15.0, "half_length": 7.0, "width": 0.5, "angle": 45.0, "roughness": 0.6},
            {"x": 70.0, "y": 35.0, "half_length": 8.0, "width": 0.7, "angle": -30.0, "roughness": 0.7},
            {"x": 25.0, "y": 40.0, "half_length": 4.0, "width": 0.3, "angle": 90.0, "roughness": 0.4},
            {"x": 80.0, "y": 10.0, "half_length": 6.0, "width": 0.5, "angle": 15.0, "roughness": 0.5},
        ],
    },
    "Edge Crack (Critical)": {
        "n_defects": 1, "pressure_x": 150.0, "pressure_y": 0.0,
        "ply_thickness": 0.125, "layup_rotation": 0.0,
        "defects": [
            {"x": 50.0, "y": 3.0, "half_length": 8.0, "width": 0.5, "angle": 0.0, "roughness": 0.7},
        ],
    },
    "Light Surface Damage": {
        "n_defects": 3, "pressure_x": 50.0, "pressure_y": 0.0,
        "ply_thickness": 0.125, "layup_rotation": 0.0,
        "defects": [
            {"x": 40.0, "y": 20.0, "half_length": 2.0, "width": 0.2, "angle": 0.0, "roughness": 0.3},
            {"x": 60.0, "y": 30.0, "half_length": 1.5, "width": 0.2, "angle": 45.0, "roughness": 0.3},
            {"x": 50.0, "y": 25.0, "half_length": 2.5, "width": 0.3, "angle": -20.0, "roughness": 0.4},
        ],
    },
}

# Defect colour palette (one per defect index)
_DEFECT_COLORS = ["#f472b6", "#38bdf8", "#a78bfa", "#fb923c", "#4ade80"]


# ############################################################################
#                          SURROGATE APP  (CTk)
# ############################################################################
import tkinter as tk


class SurrogateApp(ctk.CTk):
    """Main application window."""

    # -----------------------------------------------------------------------
    #  __init__
    # -----------------------------------------------------------------------
    def __init__(self):
        super().__init__()
        self._alive = True

        # Catch Tkinter callback exceptions (after(), button handlers, etc.)
        self.report_callback_exception = self._on_tk_error

        # Title & icon
        self.title("RP3 — Composite Failure Surrogate")
        ico = _get_icon_path()
        if ico:
            try:
                self.iconbitmap(ico)
            except Exception:
                pass

        # ---- Geometry ----
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w = min(1440, max(800, sw - 60))
        h = min(860, max(600, sh - 60))
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self._init_geo = f"{w}x{h}+{x}+{y}"
        self.geometry(self._init_geo)
        self.minsize(min(w, 1100), min(h, 650))
        self.configure(fg_color=_COL_BG)

        # ---- Internal state ----
        self._models = {}
        self._scalers = {}
        self._feature_names = []
        self._model_status = ""
        self._n_defects = tk.IntVar(value=3)
        self._defect_widgets = {}      # {defect_idx: {field: widget}}
        self._result_labels = {}
        self._model_load_result = None
        self._predict_result = None
        self._predict_poll_count = 0
        self._hide_progress_timer = None
        self._last_results = None      # store last prediction for verdict

        # Resize state
        self._is_resizing = False

        # Build splash FIRST (covers window during UI build — no flicker)
        self._build_splash()

        # Build UI (under the splash overlay)
        self._build_ui()

        # Start async model loading
        self._load_models_async()

        # Keyboard shortcuts
        self.bind("<Return>", lambda e: self._on_predict())

        # Defer geometry until after CTk's internal deiconify (which runs via after())
        self.after(0, self._apply_init_geometry)

        # Ensure visible (try twice — CTk mainloop may re-withdraw)
        self.after(500, self._ensure_visible)
        self.after(1500, self._ensure_visible)

    # -----------------------------------------------------------------------
    #  Destroy override
    # -----------------------------------------------------------------------
    def destroy(self):
        _log.info("App destroy called")
        self._alive = False
        super().destroy()

    @staticmethod
    def _on_tk_error(exc_type, exc_val, exc_tb):
        """Log exceptions from Tkinter callbacks (after(), bindings, etc.)."""
        _log.error("Tkinter callback error", exc_info=(exc_type, exc_val, exc_tb))

    # -----------------------------------------------------------------------
    #  _ensure_visible
    # -----------------------------------------------------------------------
    def _apply_init_geometry(self):
        """Apply initial geometry after CTk's internal deiconify has run."""
        self.deiconify()
        self.geometry(self._init_geo)
        self.update_idletasks()
        self.lift()
        self.focus_force()
        _log.info("Window shown: %dx%d", self.winfo_width(), self.winfo_height())

    def _force_show_win32(self):
        """Force the window visible via Win32 API — PyInstaller workaround."""
        try:
            hwnd = self.winfo_id()
            ctypes.windll.user32.ShowWindow(hwnd, 5)  # SW_SHOW
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            self.geometry(self._init_geo)
        except Exception:
            pass

    def _ensure_visible(self):
        """Make sure the window is on-screen and properly sized after startup."""
        try:
            geo = self.geometry()
            m = _re.match(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", geo)
            if not m:
                return
            w, h, x, y = int(m[1]), int(m[2]), int(m[3]), int(m[4])
            if w < 400 or h < 300:
                self.deiconify()
                self.geometry(self._init_geo)
                self.update_idletasks()
                return
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            nx = max(0, min(x, sw - w))
            ny = max(0, min(y, sh - h))
            if nx != x or ny != y:
                self.geometry(f"+{nx}+{ny}")
        except Exception:
            pass

    # ===================================================================
    #  UI BUILDING
    # ===================================================================

    def _build_ui(self):
        """Build the main application layout."""
        # ---- Header ----
        self._header = ctk.CTkFrame(self, height=56, fg_color=_COL_BG_DARK, corner_radius=0)
        self._header.pack(fill="x", side="top")
        self._header.pack_propagate(False)

        self._title_label = ctk.CTkLabel(
            self._header,
            text="RP3  |  Composite Failure Surrogate",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=_COL_TEXT,
        )
        self._title_label.pack(side="left", padx=20, pady=10)

        # Preset selector in header
        preset_names = ["Load a preset..."] + list(_PRESETS.keys())
        self._preset_var = tk.StringVar(value=preset_names[0])
        self._preset_menu = ctk.CTkOptionMenu(
            self._header,
            variable=self._preset_var,
            values=preset_names,
            command=self._apply_preset,
            width=200, height=30,
            fg_color=_COL_PANEL_ALT,
            button_color=_COL_BORDER,
            button_hover_color=_COL_ACCENT,
            dropdown_fg_color=_COL_PANEL,
            dropdown_hover_color=_COL_ACCENT,
            font=ctk.CTkFont(size=12),
            dropdown_font=ctk.CTkFont(size=12),
        )
        self._preset_menu.pack(side="left", padx=(20, 0), pady=10)
        CTkToolTip(self._preset_menu,
                   message="Quick-start: load a pre-configured damage scenario",
                   bg_color=_COL_PANEL_ALT, border_color=_COL_BORDER, border_width=1)

        self._status_dot = ctk.CTkLabel(
            self._header, text="\u25cf", font=ctk.CTkFont(size=12),
            text_color=_COL_WARNING,
        )
        self._status_dot.pack(side="right", padx=(0, 8), pady=10)

        self._status_label = ctk.CTkLabel(
            self._header, text="Loading models...",
            font=ctk.CTkFont(size=11), text_color=_COL_TEXT_DIM,
        )
        self._status_label.pack(side="right", padx=(0, 4), pady=10)

        # ---- Main panel (grid: 2 columns) ----
        self._main = tk.Frame(self, bg=_COL_BG)
        self._main.pack(fill="both", expand=True, padx=8, pady=(4, 0))
        self._main.columnconfigure(0, weight=5, minsize=380)
        self._main.columnconfigure(1, weight=6, minsize=380)
        self._main.rowconfigure(0, weight=1)

        # Left panel — inputs
        self._left_scroll = ctk.CTkScrollableFrame(
            self._main, fg_color=_COL_PANEL, corner_radius=8,
            label_text="  Input Parameters",
            label_font=ctk.CTkFont(size=13, weight="bold"),
            label_text_color=_COL_TEXT,
            label_fg_color=_COL_PANEL_ALT,
            scrollbar_button_color=_COL_BORDER,
            scrollbar_button_hover_color=_COL_ACCENT,
        )
        self._left_scroll.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=4)

        # Right panel — results
        self._right_scroll = ctk.CTkScrollableFrame(
            self._main, fg_color=_COL_PANEL, corner_radius=8,
            label_text="  Prediction Results",
            label_font=ctk.CTkFont(size=13, weight="bold"),
            label_text_color=_COL_TEXT,
            label_fg_color=_COL_PANEL_ALT,
            scrollbar_button_color=_COL_BORDER,
            scrollbar_button_hover_color=_COL_ACCENT,
        )
        self._right_scroll.grid(row=0, column=1, sticky="nsew", padx=(4, 0), pady=4)

        # Build input fields
        self._build_inputs()

        # Build result placeholders
        self._build_results()

        # Hide per-defect result rows beyond the initial n_defects
        self._sync_defect_result_rows()

        # ---- Footer ----
        self._footer = ctk.CTkFrame(self, height=32, fg_color=_COL_BG_DARK, corner_radius=0)
        self._footer.pack(fill="x", side="bottom")
        self._footer.pack_propagate(False)

        self._footer_label = ctk.CTkLabel(
            self._footer,
            text="University of Bristol  |  AENG30017  |  Artur Akoev  |  Press Enter to predict",
            font=ctk.CTkFont(size=10),
            text_color=_COL_TEXT_DIM,
        )
        self._footer_label.pack(side="left", padx=16, pady=4)

    # -----------------------------------------------------------------------
    #  INPUT FIELDS
    # -----------------------------------------------------------------------

    def _build_inputs(self):
        parent = self._left_scroll
        _tt_kw = dict(bg_color=_COL_PANEL_ALT, border_color=_COL_BORDER, border_width=1)

        # ---- Plate preview canvas ----
        self._add_section_header(parent, "Plate Preview")
        canvas_frame = ctk.CTkFrame(parent, fg_color=_COL_CANVAS_BG, corner_radius=8, height=180)
        canvas_frame.pack(fill="x", padx=12, pady=(0, 8))
        canvas_frame.pack_propagate(False)
        self._plate_canvas = tk.Canvas(
            canvas_frame, bg=_COL_CANVAS_BG, highlightthickness=0, height=170,
        )
        self._plate_canvas.pack(fill="both", expand=True, padx=4, pady=4)
        self._draw_plate_canvas()

        # ---- Loading conditions ----
        self._add_section_header(parent, "Loading Conditions")

        self._pressure_x = self._add_entry(parent, "Pressure X (MPa)", "100.0",
                                           tooltip="Horizontal force applied to the plate")
        self._pressure_y = self._add_entry(parent, "Pressure Y (MPa)", "0.0",
                                           tooltip="Vertical force applied to the plate")

        # ---- Material ----
        self._add_section_header(parent, "Material & Layup")

        self._ply_thickness = self._add_entry(parent, "Ply Thickness (mm)", "0.125",
                                              tooltip="Thickness of a single ply layer (default 0.125 mm for carbon fibre)")
        self._layup_rotation = self._add_entry(parent, "Layup Rotation (\u00b0)", "0.0",
                                               tooltip="Rotation angle of the [0/45/-45/90]s stacking sequence")

        # ---- Defect count ----
        self._add_section_header(parent, "Damage Configuration")

        self._n_defects_slider = self._add_slider(
            parent, "Number of Defects", 1, 5, self._n_defects.get(),
            command=self._on_n_defects_changed, integer=True,
        )
        CTkToolTip(self._n_defects_slider,
                   message="How many cracks/defects are present in the plate (1-5)",
                   **_tt_kw)

        # ---- Defect parameters ----
        self._defect_frames = {}
        for i in range(1, MAX_DEFECTS + 1):
            color = _DEFECT_COLORS[(i - 1) % len(_DEFECT_COLORS)]

            frame = ctk.CTkFrame(parent, fg_color="transparent")

            # Defect header with coloured indicator
            hdr = ctk.CTkFrame(frame, fg_color="transparent")
            hdr.pack(fill="x", padx=12, pady=(12, 4))
            ctk.CTkLabel(
                hdr, text="\u25cf", font=ctk.CTkFont(size=14),
                text_color=color, width=20,
            ).pack(side="left")
            ctk.CTkLabel(
                hdr, text=f"Defect {i}", font=ctk.CTkFont(size=12, weight="bold"),
                text_color=_COL_ACCENT, anchor="w",
            ).pack(side="left", padx=(4, 0))
            sep = ctk.CTkFrame(frame, height=1, fg_color=_COL_BORDER)
            sep.pack(fill="x", padx=12, pady=(0, 6))

            widgets = {}
            widgets["x"] = self._add_entry(frame, "X Position (mm)", str(PLATE_LENGTH / 2),
                                           tooltip=f"Horizontal position of defect {i} on the plate (0-{PLATE_LENGTH})")
            widgets["y"] = self._add_entry(frame, "Y Position (mm)", str(PLATE_WIDTH / 2),
                                           tooltip=f"Vertical position of defect {i} on the plate (0-{PLATE_WIDTH})")
            widgets["half_length"] = self._add_entry(frame, "Half-Length (mm)", "5.0",
                                                     tooltip="Half the total crack length (larger = more severe)")
            widgets["width"] = self._add_entry(frame, "Width (mm)", "0.5",
                                               tooltip="Opening width of the crack")
            widgets["angle"] = self._add_entry(frame, "Angle (\u00b0)", "0.0",
                                               tooltip="Orientation of the crack (0\u00b0 = horizontal)")
            widgets["roughness"] = self._add_entry(frame, "Roughness", "0.5",
                                                   tooltip="Surface roughness of the crack (0 = smooth, 1 = rough)")

            self._defect_widgets[i] = widgets
            self._defect_frames[i] = frame

        self._on_n_defects_changed(self._n_defects.get())

        # ---- Predict button ----
        self._predict_btn = ctk.CTkButton(
            parent,
            text="Run Prediction",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=48,
            fg_color=_COL_ACCENT,
            hover_color=_COL_ACCENT2,
            corner_radius=12,
            command=self._on_predict,
        )
        self._predict_btn.pack(fill="x", padx=16, pady=(16, 8))
        CTkToolTip(self._predict_btn,
                   message="Run all ML models on the current configuration (Enter)",
                   **_tt_kw)

        # ---- Reset button ----
        self._reset_btn = ctk.CTkButton(
            parent,
            text="Reset to Defaults",
            font=ctk.CTkFont(size=12),
            height=32,
            fg_color=_COL_PANEL_ALT,
            hover_color=_COL_BORDER,
            text_color=_COL_TEXT_DIM,
            corner_radius=8,
            command=self._on_reset,
        )
        self._reset_btn.pack(fill="x", padx=16, pady=(0, 8))

        # ---- Progress bar (hidden until prediction) ----
        self._progress = ctk.CTkProgressBar(parent, height=6, fg_color=_COL_BG_DARK,
                                             progress_color=_COL_ACCENT)
        self._progress.pack(fill="x", padx=16, pady=(0, 8))
        self._progress.set(0)
        self._progress_frame = self._progress
        self._progress.pack_forget()

    # -----------------------------------------------------------------------
    #  PLATE CANVAS
    # -----------------------------------------------------------------------

    def _draw_plate_canvas(self):
        """Draw the plate outline and defect positions on the preview canvas."""
        c = self._plate_canvas
        c.delete("all")

        # Wait for canvas to be sized
        c.update_idletasks()
        cw = c.winfo_width()
        ch = c.winfo_height()
        if cw < 10 or ch < 10:
            cw, ch = 400, 170

        # Margins and scale
        mx, my = 50, 20
        pw = cw - 2 * mx
        ph = ch - 2 * my
        scale_x = pw / PLATE_LENGTH
        scale_y = ph / PLATE_WIDTH

        def to_canvas(px, py):
            return mx + px * scale_x, my + py * scale_y

        # Plate outline
        x0, y0 = to_canvas(0, 0)
        x1, y1 = to_canvas(PLATE_LENGTH, PLATE_WIDTH)
        c.create_rectangle(x0, y0, x1, y1, outline="#52525b", width=2, fill="#1c1c20")

        # Grid lines (subtle)
        for gx in range(0, int(PLATE_LENGTH) + 1, 25):
            cx_pos, _ = to_canvas(gx, 0)
            _, cy0 = to_canvas(0, 0)
            _, cy1 = to_canvas(0, PLATE_WIDTH)
            c.create_line(cx_pos, cy0, cx_pos, cy1, fill="#2a2a30", dash=(2, 4))
        for gy in range(0, int(PLATE_WIDTH) + 1, 25):
            _, cy_pos = to_canvas(0, gy)
            cx0, _ = to_canvas(0, 0)
            cx1, _ = to_canvas(PLATE_LENGTH, 0)
            c.create_line(cx0, cy_pos, cx1, cy_pos, fill="#2a2a30", dash=(2, 4))

        # Axis labels
        c.create_text(mx + pw / 2, ch - 3, text=f"{PLATE_LENGTH} mm",
                      fill=_COL_TEXT_DIM, font=("Segoe UI", 9))
        c.create_text(mx - 30, my + ph / 2, text=f"{PLATE_WIDTH}\nmm",
                      fill=_COL_TEXT_DIM, font=("Segoe UI", 8), justify="center")

        # Load arrows
        try:
            px_val = float(self._pressure_x.get() or "0")
        except (ValueError, AttributeError):
            px_val = 0
        try:
            py_val = float(self._pressure_y.get() or "0")
        except (ValueError, AttributeError):
            py_val = 0

        arrow_color = "#60a5fa"
        if abs(px_val) > 0.01:
            mid_y = my + ph / 2
            direction = 1 if px_val > 0 else -1
            for frac in [0.25, 0.5, 0.75]:
                ay = my + ph * frac
                if direction > 0:
                    c.create_line(x0 - 18, ay, x0 - 3, ay, fill=arrow_color, width=2, arrow="last", arrowshape=(8, 10, 4))
                else:
                    c.create_line(x0 - 3, ay, x0 - 18, ay, fill=arrow_color, width=2, arrow="last", arrowshape=(8, 10, 4))
        if abs(py_val) > 0.01:
            direction = 1 if py_val > 0 else -1
            for frac in [0.25, 0.5, 0.75]:
                ax = mx + pw * frac
                if direction > 0:
                    c.create_line(ax, y0 - 18, ax, y0 - 3, fill=arrow_color, width=2, arrow="last", arrowshape=(8, 10, 4))
                else:
                    c.create_line(ax, y0 - 3, ax, y0 - 18, fill=arrow_color, width=2, arrow="last", arrowshape=(8, 10, 4))

        # Defects
        n = self._n_defects.get()
        for i in range(1, n + 1):
            if i not in self._defect_widgets:
                continue
            ws = self._defect_widgets[i]
            try:
                dx = float(ws["x"].get() or "0")
                dy = float(ws["y"].get() or "0")
                dhl = float(ws["half_length"].get() or "0")
                dang = float(ws["angle"].get() or "0")
            except (ValueError, AttributeError):
                continue

            color = _DEFECT_COLORS[(i - 1) % len(_DEFECT_COLORS)]
            cx, cy = to_canvas(dx, dy)

            # Draw crack as a rotated line
            rad = math.radians(dang)
            half_px = dhl * scale_x
            x_a = cx - half_px * math.cos(rad)
            y_a = cy - half_px * math.sin(rad)
            x_b = cx + half_px * math.cos(rad)
            y_b = cy + half_px * math.sin(rad)
            c.create_line(x_a, y_a, x_b, y_b, fill=color, width=3, capstyle="round")

            # Label
            c.create_text(cx, cy - 10, text=str(i), fill=color,
                          font=("Segoe UI", 9, "bold"))

    def _schedule_canvas_redraw(self, *_args):
        """Debounced canvas redraw — called when inputs change."""
        if hasattr(self, "_canvas_redraw_id"):
            try:
                self.after_cancel(self._canvas_redraw_id)
            except Exception:
                pass
        self._canvas_redraw_id = self.after(150, self._draw_plate_canvas)

    # -----------------------------------------------------------------------
    #  PRESETS
    # -----------------------------------------------------------------------

    def _apply_preset(self, name):
        """Load a preset configuration into the input fields."""
        if name not in _PRESETS:
            return
        preset = _PRESETS[name]
        if preset is None:
            return

        # Global fields
        self._pressure_x.delete(0, "end")
        self._pressure_x.insert(0, str(preset["pressure_x"]))
        self._pressure_y.delete(0, "end")
        self._pressure_y.insert(0, str(preset["pressure_y"]))
        self._ply_thickness.delete(0, "end")
        self._ply_thickness.insert(0, str(preset["ply_thickness"]))
        self._layup_rotation.delete(0, "end")
        self._layup_rotation.insert(0, str(preset["layup_rotation"]))

        # Defect count
        n = preset["n_defects"]
        self._n_defects_slider.set(n)
        self._on_n_defects_changed(n)

        # Defect fields
        defects = preset.get("defects", [])
        for i in range(1, MAX_DEFECTS + 1):
            if i in self._defect_widgets:
                ws = self._defect_widgets[i]
                if i <= len(defects):
                    d = defects[i - 1]
                    for field in ("x", "y", "half_length", "width", "angle", "roughness"):
                        ws[field].delete(0, "end")
                        ws[field].insert(0, str(d.get(field, "0")))
                else:
                    # Reset unused defects to defaults
                    defaults = {"x": str(PLATE_LENGTH / 2), "y": str(PLATE_WIDTH / 2),
                                "half_length": "5.0", "width": "0.5", "angle": "0.0", "roughness": "0.5"}
                    for field, val in defaults.items():
                        ws[field].delete(0, "end")
                        ws[field].insert(0, val)

        # Redraw canvas
        self._draw_plate_canvas()

        # Flash the preset menu to confirm
        if not _TEST_MODE:
            self._status_label.configure(text=f"Loaded: {name}")
            self._status_dot.configure(text_color=_COL_ACCENT2)

    # -----------------------------------------------------------------------
    #  RESET & DEFECT COUNT
    # -----------------------------------------------------------------------

    def _on_reset(self):
        """Reset all input fields to their default values."""
        _defaults = {
            self._pressure_x: "100.0",
            self._pressure_y: "0.0",
            self._ply_thickness: "0.125",
            self._layup_rotation: "0.0",
        }
        for widget, val in _defaults.items():
            widget.delete(0, "end")
            widget.insert(0, val)
        for i in range(1, MAX_DEFECTS + 1):
            if i in self._defect_widgets:
                ws = self._defect_widgets[i]
                _def_vals = {
                    "x": str(PLATE_LENGTH / 2),
                    "y": str(PLATE_WIDTH / 2),
                    "half_length": "5.0",
                    "width": "0.5",
                    "angle": "0.0",
                    "roughness": "0.5",
                }
                for field, val in _def_vals.items():
                    ws[field].delete(0, "end")
                    ws[field].insert(0, val)
        self._n_defects_slider.set(3)
        self._on_n_defects_changed(3)
        # Clear results
        for key, lbl in self._result_labels.items():
            lbl.configure(text="--", text_color=_COL_TEXT)
        # Reset verdict
        self._update_verdict(None)
        # Reset preset selector
        self._preset_var.set("Load a preset...")
        # Redraw canvas
        self._draw_plate_canvas()

    def _on_n_defects_changed(self, value):
        n = int(float(value))
        self._n_defects.set(n)
        for i in range(1, MAX_DEFECTS + 1):
            if i <= n:
                self._defect_frames[i].pack(fill="x", padx=4, pady=(4, 0))
            else:
                self._defect_frames[i].pack_forget()
        self._sync_defect_result_rows()
        self._schedule_canvas_redraw()

    def _sync_defect_result_rows(self):
        """Show/hide per-defect result rows to match current n_defects."""
        n = self._n_defects.get()
        for i in range(1, MAX_DEFECTS + 1):
            key = f"max_mises_defect{i}"
            if key not in self._result_labels:
                continue
            lbl = self._result_labels[key]
            try:
                if i <= n:
                    lbl.master.pack(fill="x", padx=8, pady=2)
                else:
                    lbl.configure(text="--", text_color=_COL_TEXT_DIM)
                    lbl.master.pack_forget()
            except Exception:
                pass

    # -----------------------------------------------------------------------
    #  RESULT PANEL
    # -----------------------------------------------------------------------

    def _build_results(self):
        parent = self._right_scroll

        # ---- Verdict summary card ----
        self._verdict_frame = ctk.CTkFrame(parent, fg_color=_COL_CARD, corner_radius=12, height=90)
        self._verdict_frame.pack(fill="x", padx=8, pady=(8, 12))
        self._verdict_frame.pack_propagate(False)

        verdict_inner = ctk.CTkFrame(self._verdict_frame, fg_color="transparent")
        verdict_inner.pack(expand=True, fill="both", padx=16, pady=12)

        self._verdict_icon = ctk.CTkLabel(
            verdict_inner, text="\u2014",
            font=ctk.CTkFont(size=28), text_color=_COL_TEXT_DIM,
            width=40,
        )
        self._verdict_icon.pack(side="left", padx=(0, 12))

        verdict_text_frame = ctk.CTkFrame(verdict_inner, fg_color="transparent")
        verdict_text_frame.pack(side="left", fill="both", expand=True)

        self._verdict_title = ctk.CTkLabel(
            verdict_text_frame, text="Awaiting Analysis",
            font=ctk.CTkFont(size=18, weight="bold"), text_color=_COL_TEXT_DIM,
            anchor="w",
        )
        self._verdict_title.pack(fill="x", anchor="w")

        self._verdict_desc = ctk.CTkLabel(
            verdict_text_frame,
            text="Configure your plate and press Run Prediction",
            font=ctk.CTkFont(size=11), text_color=_COL_TEXT_DIM,
            anchor="w",
        )
        self._verdict_desc.pack(fill="x", anchor="w")

        # ---- Result sections ----
        _friendly_labels = {
            "max_mises":       "Peak Stress (von Mises)",
            "max_s11":         "Max Fibre-Direction Stress",
            "min_s11":         "Min Fibre-Direction Stress",
            "max_s12":         "Peak Shear Stress",
            "tsai_wu_index":   "Tsai-Wu Failure Index",
            "failed_tsai_wu":  "Tsai-Wu Verdict",
            "max_hashin_ft":   "Fibre Tension Damage",
            "max_hashin_fc":   "Fibre Compression Damage",
            "max_hashin_mt":   "Matrix Tension Damage",
            "max_hashin_mc":   "Matrix Compression Damage",
            "failed_hashin":   "Hashin Verdict",
        }

        _tooltips = {
            "max_mises":       "Combined stress measure \u2014 higher values indicate more severe loading",
            "max_s11":         "Maximum stress along the fibre direction (tension)",
            "min_s11":         "Minimum stress along the fibre direction (compression)",
            "max_s12":         "Maximum in-plane shear stress between fibres",
            "tsai_wu_index":   "Failure index: < 1.0 = safe, \u2265 1.0 = predicted failure",
            "failed_tsai_wu":  "Binary prediction: will the plate fail under Tsai-Wu criterion?",
            "max_hashin_ft":   "Fibre breakage under tension \u2014 index \u2265 1.0 means damage",
            "max_hashin_fc":   "Fibre buckling under compression \u2014 index \u2265 1.0 means damage",
            "max_hashin_mt":   "Cracking between fibres under tension \u2014 index \u2265 1.0 means damage",
            "max_hashin_mc":   "Crushing between fibres under compression \u2014 index \u2265 1.0 means damage",
            "failed_hashin":   "Binary prediction: will the plate fail under any Hashin mode?",
        }

        sections = [
            ("Stress Analysis", "How much force the plate is under", [
                ("max_mises", _friendly_labels["max_mises"]),
                ("max_s11", _friendly_labels["max_s11"]),
                ("min_s11", _friendly_labels["min_s11"]),
                ("max_s12", _friendly_labels["max_s12"]),
            ]),
            ("Failure Assessment", "Will the plate break?", [
                ("tsai_wu_index", _friendly_labels["tsai_wu_index"]),
                ("failed_tsai_wu", _friendly_labels["failed_tsai_wu"]),
            ]),
            ("Damage Modes", "How might the plate fail?", [
                ("max_hashin_ft", _friendly_labels["max_hashin_ft"]),
                ("max_hashin_fc", _friendly_labels["max_hashin_fc"]),
                ("max_hashin_mt", _friendly_labels["max_hashin_mt"]),
                ("max_hashin_mc", _friendly_labels["max_hashin_mc"]),
                ("failed_hashin", _friendly_labels["failed_hashin"]),
            ]),
            ("Per-Defect Stress", "Stress concentration at each defect", [
                (f"max_mises_defect{i}", f"Defect {i} \u2014 Peak Stress") for i in range(1, MAX_DEFECTS + 1)
            ]),
        ]

        _tt_kw = dict(bg_color=_COL_PANEL_ALT, border_color=_COL_BORDER, border_width=1)

        for sec_title, sec_desc, items in sections:
            self._add_section_header(parent, sec_title)
            # Section description
            ctk.CTkLabel(
                parent, text=sec_desc,
                font=ctk.CTkFont(size=11), text_color=_COL_TEXT_DIM,
                anchor="w",
            ).pack(fill="x", padx=14, pady=(0, 6))

            for key, label in items:
                row = ctk.CTkFrame(parent, fg_color=_COL_PANEL_ALT, corner_radius=6, height=36)
                row.pack(fill="x", padx=8, pady=2)
                row.pack_propagate(False)

                # Coloured indicator for per-defect rows
                if key.startswith("max_mises_defect"):
                    idx = int(key[-1])
                    color = _DEFECT_COLORS[(idx - 1) % len(_DEFECT_COLORS)]
                    ctk.CTkLabel(
                        row, text="\u25cf", font=ctk.CTkFont(size=10),
                        text_color=color, width=16,
                    ).pack(side="left", padx=(8, 0))

                name_lbl = ctk.CTkLabel(
                    row, text=label, font=ctk.CTkFont(size=12),
                    text_color=_COL_TEXT_DIM, anchor="w",
                )
                name_lbl.pack(side="left", padx=10, pady=4)

                val_lbl = ctk.CTkLabel(
                    row, text="--", font=ctk.CTkFont(size=13, weight="bold"),
                    text_color=_COL_TEXT, anchor="e",
                )
                val_lbl.pack(side="right", padx=10, pady=4)
                self._result_labels[key] = val_lbl

                # Tooltip
                if key in _tooltips:
                    CTkToolTip(row, message=_tooltips[key], **_tt_kw)

    # -----------------------------------------------------------------------
    #  VERDICT CARD
    # -----------------------------------------------------------------------

    def _update_verdict(self, results):
        """Update the verdict summary card based on prediction results."""
        if results is None:
            self._verdict_frame.configure(fg_color=_COL_CARD)
            self._verdict_icon.configure(text="\u2014", text_color=_COL_TEXT_DIM)
            self._verdict_title.configure(text="Awaiting Analysis", text_color=_COL_TEXT_DIM)
            self._verdict_desc.configure(text="Configure your plate and press Run Prediction")
            return

        tw = results.get("tsai_wu_index")
        ftw = results.get("failed_tsai_wu")
        fh = results.get("failed_hashin")

        # Determine severity
        is_failed = (ftw == 1 or fh == 1)
        is_warning = False
        if tw is not None and math.isfinite(tw):
            if tw >= 1.0:
                is_failed = True
            elif tw >= 0.8:
                is_warning = True

        if is_failed:
            self._verdict_frame.configure(fg_color=_COL_CRIT_BG)
            self._verdict_icon.configure(text="\u26A0", text_color=_COL_DANGER)
            self._verdict_title.configure(text="FAILURE PREDICTED", text_color=_COL_DANGER)
            desc = "The plate is predicted to fail under these conditions."
            if tw is not None and math.isfinite(tw):
                desc += f" Tsai-Wu index: {tw:.3f}"
            self._verdict_desc.configure(text=desc, text_color="#fca5a5")
        elif is_warning:
            self._verdict_frame.configure(fg_color=_COL_WARN_BG)
            self._verdict_icon.configure(text="\u26A0", text_color=_COL_WARNING)
            self._verdict_title.configure(text="CAUTION \u2014 Near Failure", text_color=_COL_WARNING)
            desc = f"Tsai-Wu index is {tw:.3f} \u2014 approaching the failure threshold of 1.0"
            self._verdict_desc.configure(text=desc, text_color="#fde68a")
        else:
            self._verdict_frame.configure(fg_color=_COL_SAFE_BG)
            self._verdict_icon.configure(text="\u2713", text_color=_COL_SUCCESS)
            self._verdict_title.configure(text="SAFE", text_color=_COL_SUCCESS)
            desc = "The plate is predicted to survive under these conditions."
            if tw is not None and math.isfinite(tw):
                desc += f" Tsai-Wu index: {tw:.3f}"
            self._verdict_desc.configure(text=desc, text_color="#86efac")

        # Animate verdict card appearance
        if not _TEST_MODE:
            self._pulse_verdict()

    def _pulse_verdict(self):
        """Brief scale pulse on the verdict card for visual feedback."""
        try:
            original_fg = self._verdict_frame.cget("fg_color")
            flash_color = _lerp_hex(
                original_fg if isinstance(original_fg, str) else original_fg[0],
                "#ffffff", 0.15)

            def _flash(t):
                try:
                    if t < 0.5:
                        c = _lerp_hex(
                            original_fg if isinstance(original_fg, str) else original_fg[0],
                            flash_color, t * 2)
                    else:
                        c = _lerp_hex(flash_color,
                                      original_fg if isinstance(original_fg, str) else original_fg[0],
                                      (t - 0.5) * 2)
                    self._verdict_frame.configure(fg_color=c)
                except Exception:
                    pass

            _animate(self, 400, _flash, fps=30)
        except Exception:
            pass

    # -----------------------------------------------------------------------
    #  WIDGET HELPERS
    # -----------------------------------------------------------------------

    def _add_section_header(self, parent, text):
        lbl = ctk.CTkLabel(
            parent, text=text, font=ctk.CTkFont(size=12, weight="bold"),
            text_color=_COL_ACCENT, anchor="w",
        )
        lbl.pack(fill="x", padx=12, pady=(12, 4))
        sep = ctk.CTkFrame(parent, height=1, fg_color=_COL_BORDER)
        sep.pack(fill="x", padx=12, pady=(0, 6))

    def _add_entry(self, parent, label, default="", tooltip=None):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(
            frame, text=label, font=ctk.CTkFont(size=12),
            text_color=_COL_TEXT_DIM, width=180, anchor="w",
        ).pack(side="left")
        entry = ctk.CTkEntry(
            frame, width=120, height=30,
            fg_color=_COL_BG_DARK, border_color=_COL_BORDER,
            text_color=_COL_TEXT, font=ctk.CTkFont(size=12),
        )
        entry.pack(side="right", padx=(4, 0))
        entry.insert(0, default)

        # Bind input changes to canvas redraw
        entry.bind("<KeyRelease>", self._schedule_canvas_redraw)

        if tooltip:
            _tt_kw = dict(bg_color=_COL_PANEL_ALT, border_color=_COL_BORDER, border_width=1)
            CTkToolTip(entry, message=tooltip, **_tt_kw)

        return entry

    def _add_slider(self, parent, label, from_, to_, default, command=None, integer=False):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(
            frame, text=label, font=ctk.CTkFont(size=12),
            text_color=_COL_TEXT_DIM, width=180, anchor="w",
        ).pack(side="left")

        val_lbl = ctk.CTkLabel(
            frame, text=str(int(default) if integer else default),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=_COL_TEXT, width=30,
        )
        val_lbl.pack(side="right", padx=(4, 0))

        def _on_slide(v):
            if integer:
                v = int(float(v))
            val_lbl.configure(text=str(v))
            if command:
                command(v)

        slider = ctk.CTkSlider(
            frame, from_=from_, to=to_,
            number_of_steps=int(to_ - from_) if integer else 100,
            command=_on_slide,
            fg_color=_COL_BG_DARK, progress_color=_COL_ACCENT,
            button_color=_COL_ACCENT2,
        )
        slider.set(default)
        slider.pack(side="right", padx=(8, 4), fill="x", expand=True)
        return slider

    # ===================================================================
    #  SPLASH SCREEN
    # ===================================================================

    def _build_splash(self):
        """Overlay splash screen shown during model loading."""
        self._splash = ctk.CTkFrame(self, fg_color=_COL_BG)
        self._splash.place(relx=0, rely=0, relwidth=1, relheight=1)

        inner = ctk.CTkFrame(self._splash, fg_color="transparent")
        inner.place(relx=0.5, rely=0.4, anchor="center")

        ctk.CTkLabel(
            inner, text="RP3",
            font=ctk.CTkFont(size=48, weight="bold"),
            text_color=_COL_ACCENT,
        ).pack(pady=(0, 4))

        ctk.CTkLabel(
            inner, text="Composite Failure Surrogate",
            font=ctk.CTkFont(size=16),
            text_color=_COL_TEXT_DIM,
        ).pack(pady=(0, 8))

        ctk.CTkLabel(
            inner, text="University of Bristol  |  AENG30017",
            font=ctk.CTkFont(size=11),
            text_color=_COL_BORDER,
        ).pack(pady=(0, 24))

        self._splash_status = ctk.CTkLabel(
            inner, text="Loading models...",
            font=ctk.CTkFont(size=13),
            text_color=_COL_TEXT_DIM,
        )
        self._splash_status.pack(pady=(0, 12))

        self._splash_progress = ctk.CTkProgressBar(
            inner, width=320, height=6,
            fg_color=_COL_BG_DARK, progress_color=_COL_ACCENT,
        )
        self._splash_progress.pack()
        self._splash_progress.set(0)

    def _dismiss_splash(self):
        """Smoothly fade out the splash screen."""
        if self._splash is None:
            return

        if _TEST_MODE:
            self._splash.destroy()
            self._splash = None
            return

        def _slide(t):
            try:
                self._splash.place_configure(rely=-t, relheight=1)
            except Exception:
                pass

        def _done():
            try:
                self._splash.destroy()
            except Exception:
                pass
            self._splash = None
            self._recalc_scroll_regions()
            # Initial canvas draw after splash dismissed
            self.after(100, self._draw_plate_canvas)

        _animate(self, 400, _slide, on_done=_done, fps=30)

    # ===================================================================
    #  MODEL LOADING (async)
    # ===================================================================

    def _load_models_async(self):
        self._model_load_result = None
        self._model_load_progress = [0, 1]

        def _progress(loaded, total):
            self._model_load_progress[0] = loaded
            self._model_load_progress[1] = total

        def _worker():
            try:
                m, s, fn, st = load_all_models(progress_callback=_progress)
                self._model_load_result = (m, s, fn, st, None)
            except Exception as exc:
                self._model_load_result = (None, None, None, None, exc)

        self._loader_thread = threading.Thread(target=_worker, daemon=True)
        self._loader_thread.start()
        self._poll_model_load()

    def _poll_model_load(self):
        if self._model_load_result is not None:
            m, s, fn, st, err = self._model_load_result
            self._model_load_result = None
            if err is not None:
                self._on_models_error(err)
            else:
                self._on_models_loaded(m, s, fn, st)
        elif self._alive:
            loaded, total = self._model_load_progress
            if self._splash is not None and total > 0:
                try:
                    self._splash_progress.set(loaded / total)
                    self._splash_status.configure(
                        text=f"Loading models\u2026 ({loaded}/{total})")
                except Exception:
                    pass
            self.after(80, self._poll_model_load)

    def _on_models_loaded(self, models, scalers, feature_names, status):
        with _models_lock:
            self._models = models
            self._scalers = scalers
            self._feature_names = feature_names
            self._model_status = status

        n = len(models)
        expected = len(REGRESSION_MODELS) + len(CLASSIFICATION_MODELS) + len(PER_DEFECT_MISES)
        if n < expected:
            self._status_label.configure(text=f"{n}/{expected} models loaded")
            self._status_dot.configure(text_color=_COL_WARNING)
        else:
            self._status_label.configure(text=f"Ready \u2014 {n} models loaded")
            self._status_dot.configure(text_color=_COL_SUCCESS)
        _log.info("Models ready: %d/%d loaded", n, expected)

        self._dismiss_splash()

    def _on_models_error(self, err):
        self._status_label.configure(text=f"Model load error")
        self._status_dot.configure(text_color=_COL_DANGER)
        _log.error("Model load error: %s", err)
        self._dismiss_splash()

    # ===================================================================
    #  PREDICTION
    # ===================================================================

    def _gather_raw(self) -> dict:
        """Collect all input values from the UI."""
        raw = {}
        n = self._n_defects.get()
        raw["n_defects"] = n
        raw["pressure_x"] = float(self._pressure_x.get() or "0")
        raw["pressure_y"] = float(self._pressure_y.get() or "0")
        raw["ply_thickness"] = float(self._ply_thickness.get() or "0.125")
        raw["layup_rotation"] = float(self._layup_rotation.get() or "0")

        for i in range(1, MAX_DEFECTS + 1):
            if i <= n and i in self._defect_widgets:
                ws = self._defect_widgets[i]
                raw[f"defect{i}_x"] = float(ws["x"].get() or "0")
                raw[f"defect{i}_y"] = float(ws["y"].get() or "0")
                raw[f"defect{i}_half_length"] = float(ws["half_length"].get() or "0")
                raw[f"defect{i}_width"] = float(ws["width"].get() or "0")
                raw[f"defect{i}_angle"] = float(ws["angle"].get() or "0")
                raw[f"defect{i}_roughness"] = float(ws["roughness"].get() or "0")
        return raw

    def _on_predict(self):
        """Run prediction synchronously on the main thread.

        XGBoost 3.x segfaults when predict() is called from a background
        thread while tkinter runs on the main thread, so predictions are
        executed inline.  The models are lightweight (~100 ms total) so
        the brief UI freeze is imperceptible.
        """
        if self._predict_btn.cget("state") == "disabled":
            return
        with _models_lock:
            if not self._models:
                return
            models_snap = dict(self._models)
            scalers_snap = dict(self._scalers)
            fn_snap = list(self._feature_names)

        try:
            raw = self._gather_raw()
        except ValueError as e:
            _log.warning("Invalid input: %s", e)
            self._status_label.configure(text="Invalid input \u2014 check fields")
            self._status_dot.configure(text_color=_COL_DANGER)
            return

        n_def = raw["n_defects"]

        if self._hide_progress_timer is not None:
            self.after_cancel(self._hide_progress_timer)
            self._hide_progress_timer = None

        self._predict_btn.configure(state="disabled", text="Analysing...")
        self._progress.set(0)
        self._progress.pack(fill="x", padx=16, pady=(0, 8))

        try:
            features = build_feature_vector(raw, fn_snap)
            results = {}
            for target, model_entry in models_snap.items():
                scaler = scalers_snap.get(target)
                if scaler is None:
                    continue
                val = predict_single(model_entry, scaler, features)
                results[target] = val
            self._on_predict_done(results, n_def)
        except Exception as exc:
            self._on_predict_error(exc)

    def _on_predict_error(self, error):
        _log.error("Prediction error: %s", error)
        self._predict_btn.configure(state="normal", text="Run Prediction")
        self._progress.pack_forget()
        self._status_label.configure(text="Prediction error \u2014 see log")
        self._status_dot.configure(text_color=_COL_DANGER)

    def _on_predict_done(self, results, n_def):
        self._predict_btn.configure(state="normal", text="Run Prediction")
        self._progress.set(1.0)
        self._hide_progress_timer = self.after(300, self._progress.pack_forget)

        self._status_label.configure(text="Analysis complete")
        self._status_dot.configure(text_color=_COL_SUCCESS)

        self._last_results = results
        self._display_results(results, n_def)
        self._update_verdict(results)

    # ===================================================================
    #  DISPLAY RESULTS
    # ===================================================================

    def _display_results(self, results, n_def):
        """Populate the results panel with prediction values."""
        # Stress results
        for key in ("max_mises", "max_s11", "min_s11", "max_s12"):
            if key in self._result_labels:
                val = results.get(key)
                text = self._fmt_stress(val)
                colour = self._stress_colour(val)
                self._result_labels[key].configure(text=text, text_color=colour)

        # Tsai-Wu index
        if "tsai_wu_index" in self._result_labels:
            val = results.get("tsai_wu_index")
            text, colour = self._fmt_index(val, threshold=1.0)
            self._result_labels["tsai_wu_index"].configure(text=text, text_color=colour)

        # Tsai-Wu classification
        if "failed_tsai_wu" in self._result_labels:
            val = results.get("failed_tsai_wu")
            text, colour = self._fmt_bool(val)
            self._result_labels["failed_tsai_wu"].configure(text=text, text_color=colour)

        # Hashin indices
        for key in ("max_hashin_ft", "max_hashin_fc", "max_hashin_mt", "max_hashin_mc"):
            if key in self._result_labels:
                val = results.get(key)
                text, colour = self._fmt_index(val, threshold=1.0)
                self._result_labels[key].configure(text=text, text_color=colour)

        # Hashin classification
        if "failed_hashin" in self._result_labels:
            val = results.get("failed_hashin")
            text, colour = self._fmt_bool(val)
            self._result_labels["failed_hashin"].configure(text=text, text_color=colour)

        # Per-defect Mises
        for i in range(1, MAX_DEFECTS + 1):
            key = f"max_mises_defect{i}"
            if key in self._result_labels:
                if i <= n_def:
                    val = results.get(key)
                    text = self._fmt_stress(val)
                    colour = self._stress_colour(val)
                    self._result_labels[key].configure(text=text, text_color=colour)
                else:
                    self._result_labels[key].configure(text="--", text_color=_COL_TEXT_DIM)

    # ===================================================================
    #  FORMATTERS
    # ===================================================================

    def _fmt_stress(self, val):
        """Format a stress value in MPa."""
        if val is None:
            return "--"
        if not math.isfinite(val):
            return "ERROR"
        return f"{val:,.2f} MPa"

    def _fmt_index(self, val, threshold=1.0):
        """Format a failure index with colour coding."""
        if val is None:
            return "--", _COL_TEXT
        if not math.isfinite(val):
            return "ERROR", _COL_DANGER
        text = f"{val:.4f}"
        if val >= threshold:
            return text, _COL_DANGER
        elif val >= threshold * 0.8:
            return text, _COL_WARNING
        else:
            return text, _COL_SUCCESS

    def _fmt_bool(self, val):
        """Format a classification result (0/1) with colour."""
        if val is None:
            return "--", _COL_TEXT
        try:
            if not math.isfinite(val):
                return "ERROR", _COL_DANGER
        except (TypeError, ValueError):
            return "ERROR", _COL_DANGER
        v = int(val)
        if v == 0:
            return "PASS", _COL_SUCCESS
        else:
            return "FAIL", _COL_DANGER

    def _stress_colour(self, val):
        """Return colour for a stress value based on magnitude."""
        if val is None or not math.isfinite(val):
            return _COL_DANGER
        return _COL_TEXT

    # ===================================================================
    #  SCROLL REGION RECALC
    # ===================================================================

    def _recalc_scroll_regions(self):
        """Force scrollable frames to recalculate their content size."""
        try:
            self._left_scroll.update_idletasks()
            self._right_scroll.update_idletasks()
        except Exception:
            pass


# ############################################################################
#                              MAIN
# ############################################################################

def main():
    _log.info("main() starting")
    try:
        app = SurrogateApp()
        _log.info("SurrogateApp created, entering mainloop")
        app.mainloop()
        _log.info("mainloop exited normally")
    except Exception:
        _log.error("FATAL crash in main()", exc_info=True)
        # Also write to a separate crash file as backup
        import traceback as _tb
        _crash_path = os.path.join(
            os.path.expanduser("~"), "AppData", "Local", "RP3", "crash.log")
        try:
            with open(_crash_path, "w") as f:
                f.write("RP3 CRASH REPORT\n")
                f.write(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                _tb.print_exc(file=f)
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
