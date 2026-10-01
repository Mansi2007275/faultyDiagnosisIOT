"""
Unit and Integration Tests for SentinelTwin Fault Type Random Forest Classifier (Step 5).
"""
import os
import pytest
import numpy as np
import pandas as pd
from ml.fault_classifier import (
    preprocess_dataset,
    train_fault_classifier,
    predict_fault,
    load_model,
    FAULT_MODEL_PATH,
    FAULT_META_PATH
)


def test_preprocess_dataset_labels_and_noise_filtering():
    """
    Test dataset preprocessing logic:
    - fault_type column created
    - RNF-only rows dropped
    - Rows with no failure assigned 'none'
    """
    clean_df, stats = preprocess_dataset()
    assert "fault_type" in clean_df.columns
    assert stats["total_dropped_rows"] > 0
    
    # Check valid set of labels
    unique_labels = set(clean_df["fault_type"].unique())
    expected_labels = {"none", "TWF", "HDF", "PWF", "OSF"}
    assert unique_labels.issubset(expected_labels)
    assert "none" in unique_labels

def test_multi_failure_priority_resolution():
    """
    Test multi-failure priority resolution: HDF > PWF > OSF > TWF.
    """
    sample_df = pd.DataFrame([
        {"type": "M", "air_temperature_k": 300, "process_temperature_k": 310, "rotational_speed_rpm": 1400, "torque_nm": 40, "tool_wear_min": 200, "failure": 1, "twf": 1, "hdf": 1, "pwf": 0, "osf": 0, "rnf": 0},
        {"type": "L", "air_temperature_k": 300, "process_temperature_k": 310, "rotational_speed_rpm": 1400, "torque_nm": 40, "tool_wear_min": 200, "failure": 1, "twf": 1, "hdf": 0, "pwf": 1, "osf": 1, "rnf": 0},
        {"type": "H", "air_temperature_k": 300, "process_temperature_k": 310, "rotational_speed_rpm": 1400, "torque_nm": 40, "tool_wear_min": 200, "failure": 1, "twf": 1, "hdf": 0, "pwf": 0, "osf": 1, "rnf": 0},
        {"type": "M", "air_temperature_k": 300, "process_temperature_k": 310, "rotational_speed_rpm": 1400, "torque_nm": 40, "tool_wear_min": 10, "failure": 1, "twf": 0, "hdf": 0, "pwf": 0, "osf": 0, "rnf": 1}, # RNF only -> should drop
    ])
    
    clean_sample, stats = preprocess_dataset(df_raw=sample_df)
    
    # RNF only row should be dropped
    assert len(clean_sample) == 3
    assert stats["total_dropped_rows"] == 1

    
    # Priority HDF over TWF
    assert clean_sample.iloc[0]["fault_type"] == "HDF"
    # Priority PWF over OSF/TWF
    assert clean_sample.iloc[1]["fault_type"] == "PWF"
    # Priority OSF over TWF
    assert clean_sample.iloc[2]["fault_type"] == "OSF"


def test_fault_classifier_artifacts_exist():
    """
    Verify model binary, meta JSON, and plot PNG artifacts exist after training.
    """
    if not os.path.exists(FAULT_MODEL_PATH):
        train_fault_classifier()
        
    assert os.path.exists(FAULT_MODEL_PATH)
    assert os.path.exists(FAULT_META_PATH)
    assert os.path.exists("docs/confusion_matrix.png")
    assert os.path.exists("docs/feature_importance.png")

def test_predict_fault_contract_and_probability_sum():
    """
    Verify predict_fault returns (predicted_class, max_probability, class_probabilities_dict)
    and class probabilities sum to 1.0 +- 0.001 across all 5 canonical classes.
    """
    sample_reading = {
        "type": "M",
        "air_temperature_k": 300.0,
        "process_temperature_k": 310.0,
        "rotational_speed_rpm": 1500.0,
        "torque_nm": 40.0,
        "tool_wear_min": 100.0
    }
    
    pred_class, conf, probs = predict_fault(sample_reading)
    
    assert isinstance(pred_class, str)
    assert pred_class in {"none", "TWF", "HDF", "PWF", "OSF"}
    assert 0.0 <= conf <= 1.0
    assert isinstance(probs, dict)
    
    expected_classes = {"none", "TWF", "HDF", "PWF", "OSF"}
    assert set(probs.keys()) == expected_classes
    
    prob_sum = sum(probs.values())
    assert pytest.approx(prob_sum, abs=0.001) == 1.0

def test_high_overstrain_reading_predicts_fault():
    """
    Verify extreme torque + wear overstrain reading produces an OSF or non-nominal fault prediction with high confidence.
    """
    extreme_reading = {
        "type": "L",
        "air_temperature_k": 298.0,
        "process_temperature_k": 308.0,
        "rotational_speed_rpm": 1200.0,
        "torque_nm": 75.0, # High torque
        "tool_wear_min": 240.0 # Extreme wear -> high strain wear * torque
    }
    
    pred_class, conf, probs = predict_fault(extreme_reading)
    assert pred_class in {"OSF", "PWF", "TWF", "HDF"}
    assert conf > 0.50
