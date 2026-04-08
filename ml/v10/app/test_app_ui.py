"""
RP3 Surrogate App — Test Suite
================================
Tests model loading, prediction correctness, feature construction,
and basic UI startup / interaction.

Run:  python -m pytest test_app_ui.py -v
"""

import os
import sys
import math
import pytest
import numpy as np

# Ensure we can import from the project directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Enable test mode before importing the app
import surrogate_app
surrogate_app._TEST_MODE = True

from surrogate_app import (
    load_all_models,
    build_feature_vector,
    predict_single,
    _NumpyNet,
    _ensure_blobs,
    _models_lock,
    PLATE_LENGTH,
    PLATE_WIDTH,
    MAX_DEFECTS,
    REGRESSION_MODELS,
    CLASSIFICATION_MODELS,
    PER_DEFECT_MISES,
)


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture(scope="session")
def models_and_scalers():
    """Load all models once for the entire test session."""
    m, s, fn, status = load_all_models()
    return m, s, fn, status


@pytest.fixture(scope="session")
def models(models_and_scalers):
    return models_and_scalers[0]


@pytest.fixture(scope="session")
def scalers(models_and_scalers):
    return models_and_scalers[1]


@pytest.fixture(scope="session")
def feature_names(models_and_scalers):
    return models_and_scalers[2]


def _default_raw(n_defects=3, pressure_x=100.0, pressure_y=0.0):
    """Build a default raw input dict."""
    raw = {
        "n_defects": n_defects,
        "pressure_x": pressure_x,
        "pressure_y": pressure_y,
        "ply_thickness": 0.125,
        "layup_rotation": 0.0,
    }
    for i in range(1, MAX_DEFECTS + 1):
        raw[f"defect{i}_x"] = PLATE_LENGTH / 2
        raw[f"defect{i}_y"] = PLATE_WIDTH / 2
        raw[f"defect{i}_half_length"] = 5.0
        raw[f"defect{i}_width"] = 0.5
        raw[f"defect{i}_angle"] = 0.0
        raw[f"defect{i}_roughness"] = 0.5
    return raw


# ===========================================================================
# Model Loading Tests
# ===========================================================================


class TestModelLoading:
    def test_minimum_models_loaded(self, models):
        """At least 11 models should load (9 reg + 2 clf)."""
        assert len(models) >= 11

    def test_all_regression_targets(self, models):
        for target in REGRESSION_MODELS:
            assert target in models, f"Missing regression model: {target}"

    def test_all_classification_targets(self, models):
        for target in CLASSIFICATION_MODELS:
            assert target in models, f"Missing classification model: {target}"

    def test_per_defect_models(self, models):
        for i in range(1, MAX_DEFECTS + 1):
            key = f"max_mises_defect{i}"
            assert key in models, f"Missing per-defect model: {key}"

    def test_model_types(self, models):
        for target, (kind, _) in models.items():
            assert kind in ("npw", "nn", "xgb", "xgb_clf"), f"Unknown kind: {kind}"

    def test_scalers_match_models(self, models, scalers):
        for target in models:
            assert target in scalers, f"Missing scaler for {target}"

    def test_feature_names_count(self, feature_names):
        assert len(feature_names) == 98


# ===========================================================================
# Feature Vector Tests
# ===========================================================================


class TestFeatureVector:
    def test_shape(self, feature_names):
        raw = _default_raw()
        vec = build_feature_vector(raw, feature_names)
        assert vec.shape == (98,)

    def test_no_nan(self, feature_names):
        raw = _default_raw()
        vec = build_feature_vector(raw, feature_names)
        assert not np.any(np.isnan(vec))

    def test_no_inf(self, feature_names):
        raw = _default_raw()
        vec = build_feature_vector(raw, feature_names)
        assert not np.any(np.isinf(vec))

    def test_n_defects_in_vector(self, feature_names):
        raw = _default_raw(n_defects=4)
        vec = build_feature_vector(raw, feature_names)
        idx = feature_names.index("n_defects")
        assert vec[idx] == 4.0

    def test_zero_defects_beyond_n(self, feature_names):
        raw = _default_raw(n_defects=2)
        vec = build_feature_vector(raw, feature_names)
        # Defect 3 should be zeroed
        idx = feature_names.index("defect3_x")
        assert vec[idx] == 0.0

    def test_different_inputs_different_vectors(self, feature_names):
        raw1 = _default_raw(pressure_x=100.0)
        raw2 = _default_raw(pressure_x=200.0)
        v1 = build_feature_vector(raw1, feature_names)
        v2 = build_feature_vector(raw2, feature_names)
        assert not np.array_equal(v1, v2)

    # ------------------------------------------------------------------
    # BUG 1 — boundary_prox clamp (line 503)
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("x, y", [
        (PLATE_LENGTH + 50, PLATE_WIDTH / 2),    # x far right of plate
        (PLATE_LENGTH / 2, PLATE_WIDTH + 50),     # y far above plate
        (PLATE_LENGTH + 50, PLATE_WIDTH + 50),    # both out of bounds
        (-100, PLATE_WIDTH / 2),                   # x negative
        (PLATE_LENGTH / 2, -100),                  # y negative
        (-100, -100),                              # both negative
        (PLATE_LENGTH * 10, PLATE_WIDTH * 10),     # extreme overshoot
        (0, 0),                                    # edge corner
        (PLATE_LENGTH, PLATE_WIDTH),               # opposite corner
        (PLATE_LENGTH, 0),                         # bottom-right corner
    ])
    def test_boundary_prox_never_negative(self, feature_names, x, y):
        """boundary_prox must be >= 0 for any defect position."""
        raw = _default_raw()
        raw["defect1_x"] = x
        raw["defect1_y"] = y
        vec = build_feature_vector(raw, feature_names)
        idx = feature_names.index("defect1_boundary_prox")
        assert vec[idx] >= 0.0, f"boundary_prox={vec[idx]} for x={x}, y={y}"

    def test_boundary_prox_non_negative_all_defects(self, feature_names):
        """boundary_prox must be >= 0 for every defect slot when all out of bounds."""
        raw = _default_raw(n_defects=MAX_DEFECTS)
        for i in range(1, MAX_DEFECTS + 1):
            raw[f"defect{i}_x"] = PLATE_LENGTH + 100 * i
            raw[f"defect{i}_y"] = PLATE_WIDTH + 100 * i
        vec = build_feature_vector(raw, feature_names)
        for i in range(1, MAX_DEFECTS + 1):
            idx = feature_names.index(f"defect{i}_boundary_prox")
            assert vec[idx] >= 0.0, f"defect{i}_boundary_prox={vec[idx]}"

    def test_boundary_prox_zero_at_edge(self, feature_names):
        """Defect exactly on an edge should have boundary_prox == 0."""
        raw = _default_raw()
        raw["defect1_x"] = 0.0
        raw["defect1_y"] = PLATE_WIDTH / 2
        vec = build_feature_vector(raw, feature_names)
        idx = feature_names.index("defect1_boundary_prox")
        assert vec[idx] == pytest.approx(0.0, abs=1e-9)

    def test_boundary_prox_positive_interior(self, feature_names):
        """Defect at plate centre should have positive boundary_prox."""
        raw = _default_raw()
        raw["defect1_x"] = PLATE_LENGTH / 2
        raw["defect1_y"] = PLATE_WIDTH / 2
        vec = build_feature_vector(raw, feature_names)
        idx = feature_names.index("defect1_boundary_prox")
        assert vec[idx] > 0.0

    def test_boundary_prox_zero_for_unused_defects(self, feature_names):
        """Defects beyond n_defects should have boundary_prox == 0."""
        raw = _default_raw(n_defects=1)
        vec = build_feature_vector(raw, feature_names)
        for i in range(2, MAX_DEFECTS + 1):
            idx = feature_names.index(f"defect{i}_boundary_prox")
            assert vec[idx] == 0.0, f"defect{i}_boundary_prox should be 0"

    # ------------------------------------------------------------------
    # BUG 2 — load_ratio singularity (line 569)
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("px, py", [
        (-1e-6, 10.0),        # near-zero negative → old code singularity
        (-1e-6, 0.0),         # both near zero negative
        (-100.0, 50.0),       # moderate compression
        (-1000.0, 500.0),     # large compression
        (0.0, 100.0),         # zero px → should use epsilon
        (0.0, 0.0),           # both zero
        (1e-6, 1e-6),         # tiny positive
        (-1e-6, -1e-6),       # tiny negative both
        (100.0, 0.0),         # pure x-load
        (0.0, 100.0),         # pure y-load
        (-50.0, -50.0),       # biaxial compression
        (1e-12, 1e-12),       # extremely small
    ])
    def test_load_ratio_finite(self, feature_names, px, py):
        """load_ratio must always be finite, regardless of pressure sign."""
        raw = _default_raw(pressure_x=px, pressure_y=py)
        vec = build_feature_vector(raw, feature_names)
        idx = feature_names.index("load_ratio")
        assert np.isfinite(vec[idx]), f"load_ratio not finite for px={px}, py={py}: {vec[idx]}"

    @pytest.mark.parametrize("px, py", [
        (-1e-6, 10.0),
        (-1e-6, -10.0),
        (0.0, 100.0),
        (0.0, 0.0),
        (-100.0, 200.0),
    ])
    def test_load_ratio_bounded(self, feature_names, px, py):
        """load_ratio magnitude should stay reasonable (not explode to 1e+12)."""
        raw = _default_raw(pressure_x=px, pressure_y=py)
        vec = build_feature_vector(raw, feature_names)
        idx = feature_names.index("load_ratio")
        assert abs(vec[idx]) < 1e12, f"load_ratio exploded for px={px}, py={py}: {vec[idx]}"

    def test_load_ratio_symmetric_sign(self, feature_names):
        """load_ratio for px=+100 and px=-100 (same py) should have same magnitude."""
        raw_pos = _default_raw(pressure_x=100.0, pressure_y=50.0)
        raw_neg = _default_raw(pressure_x=-100.0, pressure_y=50.0)
        vec_pos = build_feature_vector(raw_pos, feature_names)
        vec_neg = build_feature_vector(raw_neg, feature_names)
        idx = feature_names.index("load_ratio")
        assert abs(vec_pos[idx]) == pytest.approx(abs(vec_neg[idx]), rel=1e-6)

    def test_load_ratio_correct_value(self, feature_names):
        """Verify load_ratio = py / (abs(px) + 1e-6) with known values."""
        raw = _default_raw(pressure_x=200.0, pressure_y=100.0)
        vec = build_feature_vector(raw, feature_names)
        idx = feature_names.index("load_ratio")
        expected = 100.0 / (200.0 + 1e-6)
        assert vec[idx] == pytest.approx(expected, rel=1e-9)

    # ------------------------------------------------------------------
    # Full vector sanity for edge-case inputs
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("px, py, x, y", [
        (-1e-6, 10.0, PLATE_LENGTH + 50, PLATE_WIDTH + 50),   # both bugs at once
        (-100.0, 0.0, -50, -50),                                # compression + OOB
        (0.0, 0.0, 0.0, 0.0),                                   # all zeros/edge
        (1000.0, 1000.0, PLATE_LENGTH / 2, PLATE_WIDTH / 2),    # large but in-bounds
    ])
    def test_no_nan_inf_edge_cases(self, feature_names, px, py, x, y):
        """Full feature vector must have no NaN/Inf even with extreme inputs."""
        raw = _default_raw(pressure_x=px, pressure_y=py)
        raw["defect1_x"] = x
        raw["defect1_y"] = y
        vec = build_feature_vector(raw, feature_names)
        assert not np.any(np.isnan(vec)), f"NaN in vector for px={px}, py={py}, x={x}, y={y}"
        assert not np.any(np.isinf(vec)), f"Inf in vector for px={px}, py={py}, x={x}, y={y}"

    def test_all_n_defects_extreme_positions(self, feature_names):
        """Every n_defects value (1-5) with OOB positions: no NaN/Inf."""
        for n in range(1, MAX_DEFECTS + 1):
            raw = _default_raw(n_defects=n, pressure_x=-50.0, pressure_y=30.0)
            for i in range(1, n + 1):
                raw[f"defect{i}_x"] = PLATE_LENGTH + 200
                raw[f"defect{i}_y"] = -200
            vec = build_feature_vector(raw, feature_names)
            assert not np.any(np.isnan(vec)), f"NaN with n_defects={n}"
            assert not np.any(np.isinf(vec)), f"Inf with n_defects={n}"

    # ------------------------------------------------------------------
    # BUG A — load_angle epsilon removed (line 585)
    # atan2 has no singularity; epsilon corrupted angle for small neg px
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("px, py, expected_load_angle_deg", [
        (100.0, 0.0, 0.0),          # pure X tension → 0°
        (0.0, 100.0, 90.0),          # pure Y tension → 90°
        (-100.0, 0.0, 180.0),        # pure X compression → 180°
        (0.0, -100.0, -90.0),        # pure Y compression → -90°
        (100.0, 100.0, 45.0),        # equal biaxial → 45°
        (-100.0, 100.0, 135.0),      # compression X + tension Y → 135°
        (-1e-6, 0.0, 180.0),         # tiny negative px → should be ~180°, NOT ~0°
        (-1e-6, 1e-6, 135.0),        # tiny negative both → ~135° quadrant
        (0.0, 0.0, 0.0),             # zero load → atan2(0,0)=0
    ])
    def test_load_angle_quadrant(self, feature_names, px, py, expected_load_angle_deg):
        """Verify load_angle is in the correct quadrant for various pressure combos."""
        import math as m
        actual_angle = m.degrees(m.atan2(py, px))
        assert actual_angle == pytest.approx(expected_load_angle_deg, abs=1.0), \
            f"atan2({py},{px}) = {actual_angle}°, expected ~{expected_load_angle_deg}°"
        # Also verify the feature vector uses the correct angle
        raw = _default_raw(pressure_x=px, pressure_y=py)
        raw["defect1_angle"] = 0.0
        vec = build_feature_vector(raw, feature_names)
        idx = feature_names.index("defect1_load_alignment")
        # load_alignment = min(diff, 180 - diff) / 90 where diff = |0 - load_angle| % 180
        diff = abs(0.0 - actual_angle) % 180
        expected_alignment = min(diff, 180 - diff) / 90.0
        assert vec[idx] == pytest.approx(expected_alignment, abs=0.01), \
            f"load_alignment wrong for px={px}, py={py}: got {vec[idx]}, expected {expected_alignment}"

    def test_load_alignment_negative_px_vs_positive(self, feature_names):
        """load_alignment for px=-100 and px=+100 should differ (opposite directions)."""
        raw_pos = _default_raw(pressure_x=100.0, pressure_y=50.0)
        raw_neg = _default_raw(pressure_x=-100.0, pressure_y=50.0)
        raw_pos["defect1_angle"] = 30.0
        raw_neg["defect1_angle"] = 30.0
        vec_pos = build_feature_vector(raw_pos, feature_names)
        vec_neg = build_feature_vector(raw_neg, feature_names)
        idx = feature_names.index("defect1_load_alignment")
        # These should give DIFFERENT alignment values since load comes from opposite sides
        # (if they were the same, the epsilon bug is still present)
        assert vec_pos[idx] != pytest.approx(vec_neg[idx], abs=0.01), \
            f"Alignment should differ: pos={vec_pos[idx]}, neg={vec_neg[idx]}"

    def test_load_alignment_all_defects_finite(self, feature_names):
        """load_alignment for all defects must be finite for px=0, py=0."""
        raw = _default_raw(pressure_x=0.0, pressure_y=0.0, n_defects=5)
        vec = build_feature_vector(raw, feature_names)
        for i in range(1, MAX_DEFECTS + 1):
            idx = feature_names.index(f"defect{i}_load_alignment")
            assert np.isfinite(vec[idx]), f"defect{i}_load_alignment not finite"
            assert 0.0 <= vec[idx] <= 1.0, f"defect{i}_load_alignment out of [0,1]: {vec[idx]}"


# ===========================================================================
# Prediction Tests
# ===========================================================================


class TestPredictions:
    def test_all_predictions_valid(self, models, scalers, feature_names):
        raw = _default_raw()
        vec = build_feature_vector(raw, feature_names)
        for target, model_entry in models.items():
            scaler = scalers[target]
            val = predict_single(model_entry, scaler, vec)
            assert val is not None, f"{target} returned None"
            assert not math.isnan(val), f"{target} returned NaN"
            assert not math.isinf(val), f"{target} returned Inf"

    def test_mises_positive(self, models, scalers, feature_names):
        raw = _default_raw(pressure_x=100.0)
        vec = build_feature_vector(raw, feature_names)
        val = predict_single(models["max_mises"], scalers["max_mises"], vec)
        assert val > 0, f"Mises should be positive, got {val}"

    def test_higher_pressure_higher_stress(self, models, scalers, feature_names):
        raw_lo = _default_raw(pressure_x=50.0)
        raw_hi = _default_raw(pressure_x=200.0)
        vec_lo = build_feature_vector(raw_lo, feature_names)
        vec_hi = build_feature_vector(raw_hi, feature_names)
        mises_lo = predict_single(models["max_mises"], scalers["max_mises"], vec_lo)
        mises_hi = predict_single(models["max_mises"], scalers["max_mises"], vec_hi)
        assert mises_hi > mises_lo, f"Higher pressure should -> higher stress: {mises_hi} vs {mises_lo}"

    def test_classification_binary(self, models, scalers, feature_names):
        raw = _default_raw()
        vec = build_feature_vector(raw, feature_names)
        for target in CLASSIFICATION_MODELS:
            val = predict_single(models[target], scalers[target], vec)
            assert val in (0, 1), f"{target} should be 0 or 1, got {val}"

    def test_predictions_vary_with_input(self, models, scalers, feature_names):
        """Changing inputs should change outputs."""
        raw1 = _default_raw(pressure_x=50.0, pressure_y=0.0, n_defects=1)
        raw2 = _default_raw(pressure_x=200.0, pressure_y=100.0, n_defects=5)
        vec1 = build_feature_vector(raw1, feature_names)
        vec2 = build_feature_vector(raw2, feature_names)
        changed = 0
        for target, model_entry in models.items():
            scaler = scalers[target]
            v1 = predict_single(model_entry, scaler, vec1)
            v2 = predict_single(model_entry, scaler, vec2)
            if v1 != v2:
                changed += 1
        assert changed > len(models) * 0.5, f"Only {changed}/{len(models)} outputs changed"

    def test_all_n_defects_values(self, models, scalers, feature_names):
        """Predictions should work for all n_defects 1-5."""
        for n in range(1, 6):
            raw = _default_raw(n_defects=n)
            vec = build_feature_vector(raw, feature_names)
            for target, model_entry in models.items():
                scaler = scalers[target]
                val = predict_single(model_entry, scaler, vec)
                assert val is not None


# ===========================================================================
# Edge-Case Prediction Tests (bugs 1+2 combined with model inference)
# ===========================================================================


class TestEdgeCasePredictions:
    """Ensure edge-case inputs (OOB positions, negative pressure) produce
    valid model predictions — not NaN, not Inf, not None."""

    @pytest.mark.parametrize("px, py, x, y", [
        (-1e-6, 10.0, PLATE_LENGTH + 50, PLATE_WIDTH + 50),
        (-100.0, 0.0, -50, -50),
        (0.0, 0.0, 0.0, 0.0),
        (1000.0, 1000.0, PLATE_LENGTH / 2, PLATE_WIDTH / 2),
        (-500.0, -500.0, PLATE_LENGTH * 2, -PLATE_WIDTH),
    ])
    def test_all_models_survive_edge_inputs(self, models, scalers, feature_names, px, py, x, y):
        """Every model must return a valid number for edge-case inputs."""
        raw = _default_raw(pressure_x=px, pressure_y=py)
        raw["defect1_x"] = x
        raw["defect1_y"] = y
        vec = build_feature_vector(raw, feature_names)
        for target, model_entry in models.items():
            scaler = scalers[target]
            val = predict_single(model_entry, scaler, vec)
            assert val is not None, f"{target} returned None for px={px}, py={py}, x={x}, y={y}"
            assert not math.isnan(val), f"{target} returned NaN for px={px}, py={py}, x={x}, y={y}"
            assert not math.isinf(val), f"{target} returned Inf for px={px}, py={py}, x={x}, y={y}"

    def test_negative_pressure_predictions_reasonable(self, models, scalers, feature_names):
        """Predictions with negative px should be in a similar range to positive px."""
        raw_pos = _default_raw(pressure_x=100.0, pressure_y=50.0)
        raw_neg = _default_raw(pressure_x=-100.0, pressure_y=50.0)
        vec_pos = build_feature_vector(raw_pos, feature_names)
        vec_neg = build_feature_vector(raw_neg, feature_names)
        for target, model_entry in models.items():
            scaler = scalers[target]
            v_pos = predict_single(model_entry, scaler, vec_pos)
            v_neg = predict_single(model_entry, scaler, vec_neg)
            # Both should be finite
            assert math.isfinite(v_pos), f"{target} pos not finite: {v_pos}"
            assert math.isfinite(v_neg), f"{target} neg not finite: {v_neg}"

    def test_oob_defect_predictions_no_crash(self, models, scalers, feature_names):
        """OOB defect positions should produce valid predictions for all n_defects."""
        for n in range(1, MAX_DEFECTS + 1):
            raw = _default_raw(n_defects=n, pressure_x=100.0)
            for i in range(1, n + 1):
                raw[f"defect{i}_x"] = PLATE_LENGTH + 500
                raw[f"defect{i}_y"] = -500
            vec = build_feature_vector(raw, feature_names)
            for target, model_entry in models.items():
                scaler = scalers[target]
                val = predict_single(model_entry, scaler, vec)
                assert val is not None, f"{target} None for n_def={n} OOB"
                assert math.isfinite(val), f"{target} not finite for n_def={n} OOB: {val}"


# ===========================================================================
# NumpyNet Tests
# ===========================================================================


class TestNumpyNet:
    def test_basic_inference(self):
        """NumpyNet should produce a float from random data."""
        data = {
            "layers": [
                {
                    "W": np.random.randn(32, 10),
                    "b": np.zeros(32),
                    "bn_weight": np.ones(32),
                    "bn_bias": np.zeros(32),
                    "bn_mean": np.zeros(32),
                    "bn_var": np.ones(32),
                }
            ],
            "output": {
                "W": np.random.randn(1, 32),
                "b": np.zeros(1),
            },
        }
        net = _NumpyNet(data)
        result = net(np.random.randn(10))
        assert isinstance(result, float)
        assert not math.isnan(result)


# ===========================================================================
# UI Tests (headless — just verify startup and basic interaction)
# ===========================================================================


class TestUI:
    @pytest.fixture(autouse=True)
    def _setup_teardown(self):
        """Create and destroy the app for each test."""
        surrogate_app._TEST_MODE = True
        self.app = surrogate_app.SurrogateApp()
        # Process events so the UI builds
        self.app.update_idletasks()
        yield
        try:
            self.app.destroy()
        except Exception:
            pass

    def test_startup(self):
        assert self.app.winfo_exists()

    def test_title(self):
        assert "RP3" in self.app.title()

    def test_n_defects_slider(self):
        self.app._n_defects.set(2)
        self.app._on_n_defects_changed(2)
        self.app.update_idletasks()
        # Defect 3 frame should be hidden
        assert not self.app._defect_frames[3].winfo_ismapped()
        # Defect 2 should be visible
        assert self.app._defect_frames[2].winfo_ismapped()

    def test_result_labels_exist(self):
        assert "max_mises" in self.app._result_labels
        assert "tsai_wu_index" in self.app._result_labels
        assert "failed_hashin" in self.app._result_labels

    def test_window_size_reasonable(self):
        self.app.update_idletasks()
        w = self.app.winfo_width()
        h = self.app.winfo_height()
        assert 400 <= w <= 4000, f"Width {w} out of range"
        assert 300 <= h <= 3000, f"Height {h} out of range"

    # ------------------------------------------------------------------
    # BUG 3 — Invalid input shows visible error (lines 1228-1232)
    # ------------------------------------------------------------------

    def _inject_models(self):
        """Load real models into the app so _on_predict gets past the guard."""
        m, s, fn, status = load_all_models()
        with _models_lock:
            self.app._models = m
            self.app._scalers = s
            self.app._feature_names = fn
            self.app._model_status = status

    def test_invalid_input_shows_status_error(self):
        """Typing 'abc' in pressure field then predicting should show error in status."""
        self._inject_models()
        self.app._pressure_x.delete(0, "end")
        self.app._pressure_x.insert(0, "abc")
        self.app.update_idletasks()
        self.app._on_predict()
        self.app.update_idletasks()
        label_text = self.app._status_label.cget("text")
        assert "Invalid input" in label_text, f"Expected 'Invalid input' in status, got: {label_text}"

    def test_invalid_input_shows_red_dot(self):
        """Invalid input should turn the status dot red (_COL_DANGER)."""
        self._inject_models()
        self.app._pressure_x.delete(0, "end")
        self.app._pressure_x.insert(0, "not_a_number")
        self.app.update_idletasks()
        self.app._on_predict()
        self.app.update_idletasks()
        dot_color = self.app._status_dot.cget("text_color")
        assert dot_color == "#f87171", f"Expected red dot, got: {dot_color}"

    def test_invalid_input_does_not_crash(self):
        """App should not crash or throw on invalid input."""
        self._inject_models()
        self.app._pressure_x.delete(0, "end")
        self.app._pressure_x.insert(0, "xyz")
        self.app.update_idletasks()
        # Should not raise
        self.app._on_predict()
        self.app.update_idletasks()
        assert self.app.winfo_exists()

    def test_invalid_input_button_stays_enabled(self):
        """After invalid input, predict button should still be clickable."""
        self._inject_models()
        self.app._pressure_x.delete(0, "end")
        self.app._pressure_x.insert(0, "bad")
        self.app.update_idletasks()
        self.app._on_predict()
        self.app.update_idletasks()
        state = self.app._predict_btn.cget("state")
        assert state == "normal", f"Button should be normal after invalid input, got: {state}"

    def test_invalid_defect_field_shows_error(self):
        """Invalid value in a defect field should also show status error."""
        self._inject_models()
        ws = self.app._defect_widgets[1]
        ws["x"].delete(0, "end")
        ws["x"].insert(0, "??")
        self.app.update_idletasks()
        self.app._on_predict()
        self.app.update_idletasks()
        label_text = self.app._status_label.cget("text")
        assert "Invalid input" in label_text, f"Expected error for bad defect field, got: {label_text}"

    def test_empty_field_gather_raw_succeeds(self):
        """Empty field should be treated as 0 (not error) via 'or 0' fallback."""
        self.app._pressure_x.delete(0, "end")
        # leave empty — _gather_raw uses `float(... or "0")`
        self.app.update_idletasks()
        # Call _gather_raw directly to avoid spawning prediction threads
        raw = self.app._gather_raw()
        assert raw["pressure_x"] == 0.0, f"Empty field should resolve to 0, got: {raw['pressure_x']}"

    def test_multiple_invalid_fields_shows_error(self):
        """Multiple bad fields should still show the error (first ValueError caught)."""
        self._inject_models()
        self.app._pressure_x.delete(0, "end")
        self.app._pressure_x.insert(0, "bad1")
        self.app._pressure_y.delete(0, "end")
        self.app._pressure_y.insert(0, "bad2")
        self.app.update_idletasks()
        self.app._on_predict()
        self.app.update_idletasks()
        label_text = self.app._status_label.cget("text")
        assert "Invalid input" in label_text

    def test_invalid_then_valid_gather_raw(self):
        """After fixing invalid input, _gather_raw should succeed."""
        # First: invalid
        self.app._pressure_x.delete(0, "end")
        self.app._pressure_x.insert(0, "abc")
        self.app.update_idletasks()
        with pytest.raises(ValueError):
            self.app._gather_raw()
        # Fix: valid value
        self.app._pressure_x.delete(0, "end")
        self.app._pressure_x.insert(0, "100")
        self.app.update_idletasks()
        raw = self.app._gather_raw()
        assert raw["pressure_x"] == 100.0

    # ------------------------------------------------------------------
    # BUG 4 — Prediction error shows visible feedback (lines 1283-1290)
    # ------------------------------------------------------------------

    def test_predict_error_shows_status_message(self):
        """_on_predict_error should set visible error text in status label."""
        self.app._on_predict_error(RuntimeError("test error"))
        self.app.update_idletasks()
        label_text = self.app._status_label.cget("text")
        assert "Prediction error" in label_text, f"Expected 'Prediction error' in status, got: {label_text}"

    def test_predict_error_shows_red_dot(self):
        """_on_predict_error should turn the status dot red."""
        self.app._on_predict_error(ValueError("boom"))
        self.app.update_idletasks()
        dot_color = self.app._status_dot.cget("text_color")
        assert dot_color == "#f87171", f"Expected red dot on predict error, got: {dot_color}"

    def test_predict_error_resets_button(self):
        """_on_predict_error should re-enable the predict button."""
        self.app._predict_btn.configure(state="disabled", text="Predicting...")
        self.app._on_predict_error(Exception("fail"))
        self.app.update_idletasks()
        state = self.app._predict_btn.cget("state")
        text = self.app._predict_btn.cget("text")
        assert state == "normal", f"Button should be re-enabled, got: {state}"
        assert text == "Run Prediction", f"Button text should reset, got: {text}"

    def test_predict_error_hides_progress(self):
        """_on_predict_error should hide the progress bar."""
        self.app._progress.pack(fill="x")
        self.app.update_idletasks()
        self.app._on_predict_error(Exception("fail"))
        self.app.update_idletasks()
        assert not self.app._progress.winfo_ismapped(), "Progress bar should be hidden after error"

    def test_status_label_exists(self):
        """Status label and dot should exist on app startup."""
        assert hasattr(self.app, "_status_label")
        assert hasattr(self.app, "_status_dot")
        assert self.app._status_label.winfo_exists()
        assert self.app._status_dot.winfo_exists()

    # ------------------------------------------------------------------
    # BUG B/C/D — Formatters must handle NaN/Inf safely
    # ------------------------------------------------------------------

    def test_fmt_stress_nan(self):
        """_fmt_stress(NaN) should return 'ERROR', not 'nan MPa'."""
        result = self.app._fmt_stress(float('nan'))
        assert result == "ERROR", f"Expected 'ERROR' for NaN stress, got: {result}"

    def test_fmt_stress_inf(self):
        """_fmt_stress(Inf) should return 'ERROR', not 'inf MPa'."""
        result = self.app._fmt_stress(float('inf'))
        assert result == "ERROR", f"Expected 'ERROR' for Inf stress, got: {result}"

    def test_fmt_stress_neg_inf(self):
        result = self.app._fmt_stress(float('-inf'))
        assert result == "ERROR"

    def test_fmt_stress_none(self):
        result = self.app._fmt_stress(None)
        assert result == "--"

    def test_fmt_stress_normal(self):
        result = self.app._fmt_stress(123.456)
        assert "123.46" in result
        assert "MPa" in result

    def test_fmt_index_nan_shows_danger(self):
        """_fmt_index(NaN) must NOT show green/success — must show ERROR + red."""
        text, colour = self.app._fmt_index(float('nan'))
        assert text == "ERROR", f"NaN index should show ERROR, got: {text}"
        assert colour == "#f87171", f"NaN index should be red, got: {colour}"

    def test_fmt_index_inf_shows_danger(self):
        text, colour = self.app._fmt_index(float('inf'))
        assert text == "ERROR"
        assert colour == "#f87171"

    def test_fmt_index_none(self):
        text, colour = self.app._fmt_index(None)
        assert text == "--"

    def test_fmt_index_below_threshold(self):
        text, colour = self.app._fmt_index(0.5, threshold=1.0)
        assert "0.5000" in text
        assert colour == "#34d399"  # success green

    def test_fmt_index_above_threshold(self):
        text, colour = self.app._fmt_index(1.5, threshold=1.0)
        assert "1.5000" in text
        assert colour == "#f87171"  # danger red

    def test_fmt_index_warning_zone(self):
        text, colour = self.app._fmt_index(0.85, threshold=1.0)
        assert colour == "#fbbf24"  # warning amber

    def test_fmt_bool_nan_no_crash(self):
        """_fmt_bool(NaN) must not crash (int(NaN) raises ValueError)."""
        text, colour = self.app._fmt_bool(float('nan'))
        assert text == "ERROR", f"NaN bool should show ERROR, got: {text}"
        assert colour == "#f87171"

    def test_fmt_bool_inf_no_crash(self):
        text, colour = self.app._fmt_bool(float('inf'))
        assert text == "ERROR"
        assert colour == "#f87171"

    def test_fmt_bool_none(self):
        text, colour = self.app._fmt_bool(None)
        assert text == "--"

    def test_fmt_bool_pass(self):
        text, colour = self.app._fmt_bool(0)
        assert text == "PASS"
        assert colour == "#34d399"

    def test_fmt_bool_fail(self):
        text, colour = self.app._fmt_bool(1)
        assert text == "FAIL"
        assert colour == "#f87171"

    def test_fmt_bool_float_one(self):
        """Model may return 1.0 as float — should still show FAIL."""
        text, colour = self.app._fmt_bool(1.0)
        assert text == "FAIL"

    # ------------------------------------------------------------------
    # BUG E — Re-entry guard: rapid Enter should not spawn duplicate workers
    # ------------------------------------------------------------------

    def test_predict_blocked_when_button_disabled(self):
        """_on_predict should return immediately if button is disabled."""
        self._inject_models()
        # Simulate an in-progress prediction by disabling button
        self.app._predict_btn.configure(state="disabled", text="Predicting...")
        self.app.update_idletasks()
        # This should be a no-op (re-entry blocked)
        self.app._on_predict()
        self.app.update_idletasks()
        # Button should still be disabled (not reset by error handler)
        state = self.app._predict_btn.cget("state")
        assert state == "disabled", f"Re-entry guard failed, button state: {state}"

    def test_predict_allowed_when_button_normal(self):
        """_on_predict should proceed when button is enabled."""
        self._inject_models()
        self.app._predict_btn.configure(state="normal")
        self.app.update_idletasks()
        # Should proceed — button gets disabled during prediction
        self.app._on_predict()
        self.app.update_idletasks()
        state = self.app._predict_btn.cget("state")
        assert state == "disabled", f"Prediction should have started, button state: {state}"
