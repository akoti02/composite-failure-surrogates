"""
Export trained models to _models_data.py as base85-encoded blobs.

Converts PyTorch .pt files to .npw (numpy weights) format for torch-free inference,
then packs all models, scalers, and feature names into a single Python module.

Usage:
    python export_models.py
"""

import os
import sys
import pickle
import base64
import io
import numpy as np

MODELS_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "figures_v10", "trained_models")
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_models_data.py")


def pt_to_npw(pt_path: str) -> bytes:
    """Convert a PyTorch .pt RegressionNet to .npw (numpy weights) bytes.

    Architecture: Sequential(Linear, ReLU, BN, Dropout) x N + Linear(1)
    Indices per block: 0=Linear, 1=ReLU, 2=BN, 3=Dropout
    """
    import torch
    model = torch.load(pt_path, map_location="cpu", weights_only=False)
    if hasattr(model, "state_dict"):
        sd = model.state_dict()
    else:
        sd = model

    # Parse layers from state_dict keys like "network.0.weight", "network.2.running_mean"
    # Block stride = 4 (Linear, ReLU, BatchNorm, Dropout)
    layer_indices = set()
    for key in sd:
        parts = key.split(".")
        if len(parts) >= 3 and parts[0] == "network":
            idx = int(parts[1])
            layer_indices.add(idx)

    max_idx = max(layer_indices)

    # Find hidden layer blocks: each starts at idx 0, 4, 8, ...
    # The output layer is the last Linear (no BN after it)
    layers = []
    idx = 0
    while idx < max_idx:
        # Check if this is a Linear layer (has weight and bias)
        w_key = f"network.{idx}.weight"
        if w_key not in sd:
            idx += 1
            continue

        # Check if there's a BatchNorm 2 positions ahead
        bn_key = f"network.{idx + 2}.weight"
        if bn_key in sd:
            # Hidden layer block: Linear + ReLU + BN + Dropout
            layer = {
                "W": sd[f"network.{idx}.weight"].numpy().astype(np.float64),
                "b": sd[f"network.{idx}.bias"].numpy().astype(np.float64),
                "bn_weight": sd[f"network.{idx + 2}.weight"].numpy().astype(np.float64),
                "bn_bias": sd[f"network.{idx + 2}.bias"].numpy().astype(np.float64),
                "bn_mean": sd[f"network.{idx + 2}.running_mean"].numpy().astype(np.float64),
                "bn_var": sd[f"network.{idx + 2}.running_var"].numpy().astype(np.float64),
            }
            layers.append(layer)
            idx += 4  # Skip past Dropout
        else:
            # This is the output Linear layer
            break

    # Output layer
    out_W = sd[f"network.{idx}.weight"].numpy().astype(np.float64)
    out_b = sd[f"network.{idx}.bias"].numpy().astype(np.float64)

    data = {
        "layers": layers,
        "output": {"W": out_W, "b": out_b},
    }

    buf = io.BytesIO()
    pickle.dump(data, buf, protocol=pickle.HIGHEST_PROTOCOL)
    return buf.getvalue()


def file_to_blob(path: str) -> bytes:
    """Read a file and return its raw bytes."""
    with open(path, "rb") as f:
        return f.read()


def main():
    if not os.path.isdir(MODELS_DIR):
        print(f"ERROR: Models directory not found: {MODELS_DIR}")
        sys.exit(1)

    blobs = {}
    files = sorted(os.listdir(MODELS_DIR))

    for fname in files:
        fpath = os.path.join(MODELS_DIR, fname)
        if not os.path.isfile(fpath):
            continue

        if fname.endswith(".pt"):
            # Convert PyTorch to numpy weights
            npw_name = fname.replace(".pt", ".npw")
            print(f"  Converting {fname} -> {npw_name}")
            raw = pt_to_npw(fpath)
            blobs[npw_name] = base64.b85encode(raw)
            # Also keep .pt version for torch-available inference
            print(f"  Packing {fname}")
            blobs[fname] = base64.b85encode(file_to_blob(fpath))
        elif fname.endswith(".pkl"):
            print(f"  Packing {fname}")
            blobs[fname] = base64.b85encode(file_to_blob(fpath))
        else:
            print(f"  Skipping {fname}")

    print(f"\nTotal blobs: {len(blobs)}")

    # Write _models_data.py
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write('"""Auto-generated model data. Do not edit manually."""\n\n')
        f.write("MODEL_BLOBS = {\n")
        for key in sorted(blobs.keys()):
            encoded = blobs[key].decode("ascii")
            f.write(f'    "{key}": b"{encoded}",\n')
        f.write("}\n")

    size_mb = os.path.getsize(OUTPUT_FILE) / (1024 * 1024)
    print(f"\nWrote {OUTPUT_FILE}")
    print(f"Size: {size_mb:.1f} MB")


if __name__ == "__main__":
    main()
