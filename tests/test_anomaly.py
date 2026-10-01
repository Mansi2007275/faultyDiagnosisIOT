import os
import pytest
from ml.anomaly import (
    score_reading,
    load_model,
    train_anomaly_model,
    extract_features,
    FEATURE_COLUMNS,
    MODEL_PATH,
    META_PATH
)

@pytest.fixture(scope="module", autouse=True)
def ensure_model_trained():
    """Ensures model artifacts exist for testing."""
    if not os.path.exists(MODEL_PATH) or not os.path.exists(META_PATH):
        train_anomaly_model()

def test_feature_extraction_order():
    """Validates strict feature ordering."""
    sample = {
        "air_c": 25.0,
        "proc_c": 35.0,
        "temp_gap_c": 10.0,
        "rpm": 1500.0,
        "torque": 40.0,
        "wear": 10.0,
        "power_w": 6283.18
    }
    arr = extract_features(sample)
    assert arr.shape == (1, 7)
    assert arr[0][0] == 25.0
    assert arr[0][3] == 1500.0

def test_healthy_reading_below_threshold():
    """A typical healthy reading gets an anomaly score below the decision threshold."""
    loaded = load_model()
    assert loaded is not None, "Model should be loaded"
    _, meta = loaded
    threshold = meta["threshold"]

    healthy_reading = {
        "air_temperature_k": 300.0,
        "process_temperature_k": 310.0,
        "rotational_speed_rpm": 1538.0,
        "torque_nm": 39.5,
        "tool_wear_min": 25.0,
        "calculated_power_w": 6360.0
    }
    score, is_unusual, explanation = score_reading(healthy_reading)
    
    assert score is not None
    assert score >= 0.0 and score <= 1.0
    assert score < threshold, f"Healthy score ({score}) should be below threshold ({threshold})"
    assert is_unusual is False
    assert "Nominal" in explanation or "normal" in explanation

def test_extreme_reading_above_threshold():
    """An extreme reading (torque 76, rpm 1170, tool wear 250) gets a score above the threshold."""
    loaded = load_model()
    assert loaded is not None
    _, meta = loaded
    threshold = meta["threshold"]

    extreme_reading = {
        "air_temperature_k": 304.0,
        "process_temperature_k": 318.0,
        "rotational_speed_rpm": 1170.0,
        "torque_nm": 76.0,
        "tool_wear_min": 250.0,
        "calculated_power_w": 9310.0
    }
    score, is_unusual, explanation = score_reading(extreme_reading)
    
    assert score is not None
    assert score >= threshold, f"Extreme score ({score}) should be >= threshold ({threshold})"
    assert is_unusual is True
    assert "Unusual" in explanation

def test_score_bounded_zero_to_one():
    """Scores are strictly bounded within [0, 1]."""
    test_cases = [
        {"air_c": 10.0, "proc_c": 15.0, "temp_gap_c": 5.0, "rpm": 800.0, "torque": 10.0, "wear": 0.0, "power_w": 800.0},
        {"air_c": 50.0, "proc_c": 90.0, "temp_gap_c": 40.0, "rpm": 3200.0, "torque": 90.0, "wear": 300.0, "power_w": 25000.0},
        {"air_c": 25.0, "proc_c": 35.0, "temp_gap_c": 10.0, "rpm": 1500.0, "torque": 40.0, "wear": 50.0, "power_w": 6280.0}
    ]
    for case in test_cases:
        score, _, _ = score_reading(case)
        assert score is not None
        assert 0.0 <= score <= 1.0, f"Score {score} out of bounds [0, 1]"

def test_missing_model_files_graceful(monkeypatch):
    """Missing model files return None without crashing."""
    import ml.anomaly as anomaly_mod
    
    # Mock load_model returning None (simulating missing files)
    monkeypatch.setattr(anomaly_mod, "load_model", lambda: None)
    
    score, is_unusual, exp = anomaly_mod.score_reading({"rpm": 1500.0})
    assert score is None
    assert is_unusual is None
    assert "not trained yet" in exp or "Run: python -m ml.anomaly train" in exp
