"""
Unit and Integration Tests for CWRU Bearing Fault Classifier (Step 6).
"""
import os
import pytest
import numpy as np

from ml.cwru_bearing import (
    generate_synthetic_cwru_data,
    window_signal,
    extract_window_features,
    build_feature_matrix,
    train_cwru_classifier,
    predict_cwru_window,
    CWRU_MODEL_PATH,
    CWRU_META_PATH,
    CWRU_CM_PATH,
    CWRU_FI_PATH,
    FEATURE_NAMES,
    CLASS_LABELS,
    WINDOW_SIZE
)


def test_synthetic_data_generation():
    """
    Test generate_synthetic_cwru_data produces 16 recordings (4 classes x 4 loads)
    with 12,000 samples each.
    """
    records = generate_synthetic_cwru_data(n_samples_per_record=12000)
    assert len(records) == 16

    labels = set(r["label"] for r in records)
    assert labels == set(CLASS_LABELS)

    loads = set(r["load_hp"] for r in records)
    assert loads == {0, 1, 2, 3}

    for r in records:
        assert len(r["signal"]) == 12000
        assert r["label"] in CLASS_LABELS


def test_window_signal_and_feature_extraction():
    """
    Test windowing logic and feature extraction shape (15 features).
    """
    dummy_signal = np.random.randn(12000)
    windows = window_signal(dummy_signal, window_size=2048, overlap=0.5)

    # With window_size=2048 and step=1024, 12000 samples yield 10 windows
    assert len(windows) == 10
    assert len(windows[0]) == 2048

    features = extract_window_features(windows[0])
    assert isinstance(features, np.ndarray)
    assert features.shape == (15,)
    assert not np.isnan(features).any()


def test_build_feature_matrix():
    """
    Test building feature matrix from synthetic records.
    """
    records = generate_synthetic_cwru_data()
    X, y, loads, file_nums = build_feature_matrix(records)

    assert X.shape[1] == 15
    assert len(y) == X.shape[0]
    assert len(loads) == X.shape[0]
    assert len(file_nums) == X.shape[0]
    assert set(np.unique(y)) == set(CLASS_LABELS)


def test_train_cwru_classifier_artifacts():
    """
    Verify training generates model binary, metadata JSON, and plot PNG files.
    """
    meta = train_cwru_classifier()

    assert meta is not None
    assert os.path.exists(CWRU_MODEL_PATH)
    assert os.path.exists(CWRU_META_PATH)
    assert os.path.exists(CWRU_CM_PATH)
    assert os.path.exists(CWRU_FI_PATH)

    assert meta["model_name"] == "CWRU Bearing Fault Classifier"
    assert "macro_f1" in meta["metrics"]
    assert meta["metrics"]["macro_f1"] >= 0.0


def test_predict_cwru_window_contract():
    """
    Verify predict_cwru_window returns (predicted_class, max_probability, class_probabilities_dict)
    and probabilities sum to 1.0.
    """
    # Ensure model exists
    if not os.path.exists(CWRU_MODEL_PATH):
        train_cwru_classifier()

    sample_window = np.random.randn(WINDOW_SIZE)
    pred_class, conf, probs = predict_cwru_window(sample_window)

    assert pred_class in CLASS_LABELS
    assert 0.0 <= conf <= 1.0
    assert isinstance(probs, dict)
    assert set(probs.keys()) == set(CLASS_LABELS)

    prob_sum = sum(probs.values())
    assert pytest.approx(prob_sum, abs=0.001) == 1.0
