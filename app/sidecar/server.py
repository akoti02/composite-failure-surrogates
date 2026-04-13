"""RP3 Sidecar — stdin/stdout JSON-RPC server for ML inference."""
import sys
import os
import json
import traceback

# Ensure UTF-8 on Windows
if sys.platform == "win32":
    import io
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8")
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

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


def handle_load_models():
    global _models, _scalers, _feature_names
    _models, _scalers, _feature_names, status = load_all_models()
    return {"ok": True, "count": len(_models), "status": status}


def handle_predict(params):
    if _models is None:
        return {"ok": False, "error": "Models not loaded"}
    if not isinstance(params, dict):
        return {"ok": False, "error": "Invalid params: expected dict"}
    raw = params
    features = build_feature_vector(raw, _feature_names)
    results = {}
    for target, model_entry in _models.items():
        scaler = _scalers.get(target)
        if scaler is None:
            continue
        try:
            val = predict_single(model_entry, scaler, features)
            results[target] = val
        except Exception as e:
            results[target] = None
            sys.stderr.write(f"WARN predict {target}: {e}\n")
    return {"ok": True, "results": results}


def main():
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
            resp = {"ok": False, "error": str(e), "trace": traceback.format_exc()}
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
