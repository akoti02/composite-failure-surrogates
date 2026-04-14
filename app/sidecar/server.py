"""RP3 Sidecar — stdin/stdout JSON-RPC server for ML inference."""
import sys
import os
import json
import math
import traceback
import time
import logging

# Set up file logging (stderr is discarded by Tauri on Windows)
_LOG_DIR = os.path.join(os.path.expanduser("~"), ".rp3")
os.makedirs(_LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(_LOG_DIR, "sidecar.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("rp3-sidecar")

# Ensure UTF-8 on Windows
if sys.platform == "win32":
    try:
        import io
        sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8")
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
    except Exception as e:
        log.warning(f"UTF-8 wrapper failed: {e}")

# Resolve base dir for PyInstaller
if getattr(sys, "frozen", False):
    _BASE = sys._MEIPASS
else:
    _BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _BASE)

from inference import load_all_models, build_feature_vector, predict_single

_models = None
_scalers = None
_feature_names = None


def _sanitize_value(val):
    """Replace NaN/Inf with None to prevent JSON serialization crash."""
    if val is None:
        return None
    if isinstance(val, (bool,)):
        return val
    # Handle numpy scalar types (np.float64, np.int64, etc.)
    try:
        import numpy as np
        if isinstance(val, (np.floating, np.complexfloating)):
            val = float(val)
        elif isinstance(val, np.integer):
            return int(val)
        elif isinstance(val, np.bool_):
            return bool(val)
    except ImportError:
        pass
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        if not math.isfinite(val):
            return None
        return val
    return val


def _sanitize_response(obj):
    """Recursively sanitize a response dict for JSON safety."""
    if isinstance(obj, dict):
        return {k: _sanitize_response(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_response(v) for v in obj]
    return _sanitize_value(obj)


def handle_load_models():
    global _models, _scalers, _feature_names
    t0 = time.time()
    try:
        _models, _scalers, _feature_names, status = load_all_models()
    except Exception as e:
        log.error(f"Model loading failed: {e}\n{traceback.format_exc()}")
        return {"ok": False, "error": f"Model loading failed: {e}"}
    elapsed = time.time() - t0
    count = len(_models) if _models else 0
    log.info(f"Loaded {count} models in {elapsed:.1f}s — {status}")
    return {"ok": True, "count": count, "status": status,
            "load_time_s": round(elapsed, 2)}


def _validate_params(params):
    """Validate and clamp input parameters to training-data bounds."""
    clamped = dict(params)
    # Clamp pressure to [-500, 500] MPa
    for key in ("pressure_x", "pressure_y"):
        if key in clamped:
            try:
                clamped[key] = max(-500.0, min(500.0, float(clamped[key])))
            except (TypeError, ValueError):
                clamped[key] = 0.0
    # Clamp n_defects to [1, 5]
    try:
        clamped["n_defects"] = max(1, min(5, int(clamped.get("n_defects", 1))))
    except (TypeError, ValueError):
        clamped["n_defects"] = 1
    # Validate material_id and layup_id against known sets
    valid_materials = {1, 5, 8, 12, 15}
    valid_layups = {1, 3, 4, 6, 7, 13}
    valid_bcs = {"tension_comp", "biaxial", "uniaxial_shear"}
    try:
        mid = int(clamped.get("material_id", 1))
        clamped["material_id"] = mid if mid in valid_materials else 1
    except (TypeError, ValueError):
        clamped["material_id"] = 1
    try:
        lid = int(clamped.get("layup_id", 1))
        clamped["layup_id"] = lid if lid in valid_layups else 1
    except (TypeError, ValueError):
        clamped["layup_id"] = 1
    if clamped.get("bc_mode") not in valid_bcs:
        clamped["bc_mode"] = "tension_comp"
    # Clamp defect geometry per defect
    n = clamped["n_defects"]
    for i in range(1, n + 1):
        for key, lo, hi, default in [
            (f"defect{i}_x", 0, 100, 50),
            (f"defect{i}_y", 0, 50, 25),
            (f"defect{i}_half_length", 0.1, 50, 5),
            (f"defect{i}_width", 0.01, 10, 0.5),
            (f"defect{i}_angle", -90, 90, 0),
            (f"defect{i}_roughness", 0, 1, 0.5),
        ]:
            try:
                clamped[key] = max(lo, min(hi, float(clamped.get(key, default))))
            except (TypeError, ValueError):
                clamped[key] = default
    return clamped


# Regression targets that should never be negative (physical floor = 0)
_NON_NEGATIVE_TARGETS = {
    "tsai_wu_index", "max_hashin_ft", "max_hashin_mt", "max_hashin_mc",
}


def handle_predict(params):
    if _models is None:
        return {"ok": False, "error": "Models not loaded"}
    if not isinstance(params, dict):
        return {"ok": False, "error": "Invalid params: expected dict"}
    params = _validate_params(params)
    features = build_feature_vector(params, _feature_names)
    results = {}
    errors = {}
    for target, model_entry in _models.items():
        scaler = _scalers.get(target)
        if scaler is None:
            continue
        try:
            val = predict_single(model_entry, scaler, features, target_name=target)
            # Clamp failure indices to >= 0 (negative is physically meaningless)
            if target in _NON_NEGATIVE_TARGETS and val is not None and val < 0:
                val = 0.0
            results[target] = val
        except Exception as e:
            results[target] = None
            errors[target] = str(e)
            log.warning(f"Prediction failed for {target}: {e}")
    resp = {"ok": True, "results": results}
    if errors:
        resp["warnings"] = errors
    return resp


def main():
    log.info("Sidecar started")
    # Watchdog: self-terminate if no input for 120 seconds (parent likely crashed)
    import select
    _IDLE_TIMEOUT = 120  # seconds
    _last_input = time.time()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            cmd = msg.get("cmd")
            if cmd == "load_models":
                resp = handle_load_models()
            elif cmd == "predict":
                resp = handle_predict(msg.get("params", {}))
            elif cmd == "ping":
                resp = {"ok": True, "pong": True}
            else:
                resp = {"ok": False, "error": f"Unknown command: {cmd}"}
        except Exception as e:
            log.error(f"Command failed: {e}\n{traceback.format_exc()}")
            resp = {"ok": False, "error": str(e)}
        # Sanitize entire response to prevent NaN/Inf JSON crash
        resp = _sanitize_response(resp)
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()
    log.info("Sidecar stdin closed, exiting")


if __name__ == "__main__":
    main()
