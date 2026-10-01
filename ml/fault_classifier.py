import os
import sys
import json
import time
import hashlib
import numpy as np
import pandas as pd
import joblib
import matplotlib
matplotlib.use('Agg') # Non-interactive backend
import matplotlib.pyplot as plt
from typing import Dict, Any, Tuple, List, Optional

try:
    import streamlit as st
    HAS_STREAMLIT = True
except ImportError:
    HAS_STREAMLIT = False

from simulator.data_loader import load_and_preprocess_dataset

# Strict Feature Ordering
FEATURE_COLUMNS = [
    "type_code",
    "air_c",
    "proc_c",
    "temp_gap_c",
    "rpm",
    "torque",
    "wear",
    "power_w",
    "strain"
]

CLASS_LABELS = ["none", "TWF", "HDF", "PWF", "OSF"]

MODEL_DIR = "models"
MODEL_PATH = os.path.join(MODEL_DIR, "fault_rf.joblib")
META_PATH = os.path.join(MODEL_DIR, "fault_rf_meta.json")
FAULT_MODEL_PATH = MODEL_PATH
FAULT_META_PATH = META_PATH
REPORT_PATH = os.path.join("docs", "model_report.md")
CONF_MATRIX_PATH = os.path.join("docs", "confusion_matrix.png")
FEAT_IMPORT_PATH = os.path.join("docs", "feature_importance.png")



def compute_file_sha256(filepath: str) -> str:
    """Computes SHA-256 fingerprint of a binary file."""
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            sha.update(chunk)
    return sha.hexdigest()


def extract_features(df_or_dict: Any) -> np.ndarray:
    """
    Extracts features in exact strict order:
    ['type_code', 'air_c', 'proc_c', 'temp_gap_c', 'rpm', 'torque', 'wear', 'power_w', 'strain']
    """
    type_map = {"L": 0, "M": 1, "H": 2, 0: 0, 1: 1, 2: 2}

    if isinstance(df_or_dict, pd.DataFrame):
        df_copy = df_or_dict.copy()
        if "type_code" not in df_copy.columns:
            df_copy["type_code"] = df_copy["type"].map(type_map).fillna(1).astype(int)
        return df_copy[FEATURE_COLUMNS].to_numpy()

    elif isinstance(df_or_dict, dict):
        d = df_or_dict
        type_str = d.get("machine_type", d.get("type", "M"))
        type_code = type_map.get(type_str, 1)

        air_k = float(d.get("air_temperature_k", d.get("air_k", 300.0)))
        proc_k = float(d.get("process_temperature_k", d.get("proc_k", 310.0)))
        air_c = float(d.get("air_c", air_k - 273.15))
        proc_c = float(d.get("proc_c", proc_k - 273.15))
        temp_gap_c = float(d.get("temp_gap_c", proc_c - air_c))

        rpm = float(d.get("rotational_speed_rpm", d.get("rpm", 1500.0)))
        torque = float(d.get("torque_nm", d.get("torque", 40.0)))
        wear = float(d.get("tool_wear_min", d.get("wear", 0.0)))

        power_w = float(d.get("calculated_power_w", d.get("power_w", torque * rpm * (2 * np.pi / 60))))
        strain = float(d.get("strain", wear * torque))

        row = [type_code, air_c, proc_c, temp_gap_c, rpm, torque, wear, power_w, strain]
        return np.array([row])
    else:
        raise ValueError("Input must be a DataFrame or Dict")


def preprocess_dataset(df_raw: Optional[pd.DataFrame] = None) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Cleans raw dataset, resolves multi-failure priorities, drops pure RNF/unlabeled failure noise,
    and returns (clean_df, preprocessing_stats).
    If df_raw is None, loads from data.data_loader.load_dataset().
    """
    if df_raw is None:
        df_raw, _, _ = load_and_preprocess_dataset()
        
    df = df_raw.copy()

    
    # 1. Encode Type
    type_map = {"L": 0, "M": 1, "H": 2}
    df["type_code"] = df["type"].map(type_map).fillna(1).astype(int)
    
    # Priority order for multi-failure resolution: HDF > PWF > OSF > TWF
    multi_count = 0
    assigned_labels = []
    dropped_mask = np.zeros(len(df), dtype=bool)
    
    rnf_only_count = 0
    unlabeled_failure_count = 0

    for idx, row in df.iterrows():
        twf = bool(row["twf"] == 1)
        hdf = bool(row["hdf"] == 1)
        pwf = bool(row["pwf"] == 1)
        osf = bool(row["osf"] == 1)
        rnf = bool(row["rnf"] == 1)
        failure = bool(row["failure"] == 1)

        active_faults = []
        if hdf: active_faults.append("HDF")
        if pwf: active_faults.append("PWF")
        if osf: active_faults.append("OSF")
        if twf: active_faults.append("TWF")

        if len(active_faults) > 1:
            multi_count += 1

        if not failure:
            assigned_labels.append("none")
        elif len(active_faults) > 0:
            # Pick highest priority fault according to HDF > PWF > OSF > TWF
            assigned_labels.append(active_faults[0])
        else:
            # Failure == 1, but no TWF/HDF/PWF/OSF flag set
            if rnf:
                rnf_only_count += 1
            else:
                unlabeled_failure_count += 1
            dropped_mask[idx] = True
            assigned_labels.append("dropped")

    df["fault_type"] = assigned_labels
    clean_df = df[~dropped_mask].copy()

    stats = {
        "total_raw_rows": len(df_raw),
        "clean_rows": len(clean_df),
        "multi_failure_rows": multi_count,
        "dropped_rnf_only_rows": rnf_only_count,
        "dropped_unlabeled_failure_rows": unlabeled_failure_count,
        "total_dropped_rows": rnf_only_count + unlabeled_failure_count,
        "class_distribution": clean_df["fault_type"].value_counts().to_dict()
    }

    return clean_df, stats


def train_fault_classifier(data_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Trains Random Forest classifier, evaluates 5-fold CV & test set, 
    generates matplotlib plots, and persists models and reports.
    """
    from simulator.data_loader import DataLoader
    from sklearn.ensemble._forest import RandomForestClassifier
    from sklearn.model_selection import StratifiedKFold, train_test_split
    from sklearn.metrics import classification_report, confusion_matrix, f1_score, precision_recall_fscore_support

    print("--- Training SentinelTwin Fault Type Random Forest ---")
    os.makedirs(MODEL_DIR, exist_ok=True)
    os.makedirs("docs", exist_ok=True)

    loader = DataLoader(data_path=data_path)
    clean_df, stats = preprocess_dataset(loader.df)

    print(f"Dataset preprocessed: {stats['clean_rows']:,} clean rows (Dropped {stats['total_dropped_rows']} noise/RNF rows).")
    print(f"Multi-failure resolved rows: {stats['multi_failure_rows']}")
    print("Class Distribution:", stats["class_distribution"])

    X = clean_df[FEATURE_COLUMNS].to_numpy()
    y = clean_df["fault_type"].to_numpy()

    # 1. Stratified 80/20 Train/Test Split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )

    # 2. 5-Fold Stratified Cross-Validation on Training Set
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_scores = []

    for train_idx, val_idx in skf.split(X_train, y_train):
        rf_cv = RandomForestClassifier(n_estimators=100, class_weight="balanced_subsample", random_state=42, n_jobs=-1)
        rf_cv.fit(X_train[train_idx], y_train[train_idx])
        preds_val = rf_cv.predict(X_train[val_idx])
        score_val = f1_score(y_train[val_idx], preds_val, average="macro")
        cv_scores.append(score_val)

    cv_mean = float(np.mean(cv_scores))
    cv_std = float(np.std(cv_scores))
    print(f"5-Fold Cross-Validation Macro F1: {cv_mean:.4f} (+/- {cv_std:.4f})")

    # 3. Train Final Model on 80% Train Set
    clf = RandomForestClassifier(
        n_estimators=300,
        class_weight="balanced_subsample",
        random_state=42,
        n_jobs=-1
    )
    clf.fit(X_train, y_train)

    # 4. Evaluate on 20% Test Set
    y_pred = clf.predict(X_test)
    macro_f1 = float(f1_score(y_test, y_pred, average="macro"))
    weighted_f1 = float(f1_score(y_test, y_pred, average="weighted"))

    # Per-class metrics
    p_cls, r_cls, f1_cls, sup_cls = precision_recall_fscore_support(
        y_test, y_pred, labels=CLASS_LABELS, zero_division=0
    )

    per_class_metrics = {}
    for i, label in enumerate(CLASS_LABELS):
        per_class_metrics[label] = {
            "precision": round(float(p_cls[i]), 4),
            "recall": round(float(r_cls[i]), 4),
            "f1": round(float(f1_cls[i]), 4),
            "support": int(sup_cls[i])
        }

    # Confusion Matrix
    cm = confusion_matrix(y_test, y_pred, labels=CLASS_LABELS)

    # Feature Importance
    importances = clf.feature_importances_

    # 5. Generate Matplotlib Plots
    # Plot 1: Confusion Matrix
    fig, ax = plt.subplots(figsize=(6.5, 5.5))
    im = ax.imshow(cm, interpolation='nearest', cmap=plt.cm.Blues)
    ax.figure.colorbar(im, ax=ax)
    ax.set(
        xticks=np.arange(cm.shape[1]),
        yticks=np.arange(cm.shape[0]),
        xticklabels=CLASS_LABELS,
        yticklabels=CLASS_LABELS,
        title='Confusion Matrix - Fault Type Classifier',
        ylabel='True Label',
        xlabel='Predicted Label'
    )
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right", rotation_mode="anchor")

    fmt = 'd'
    thresh = cm.max() / 2.
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(j, i, format(cm[i, j], fmt),
                    ha="center", va="center",
                    color="white" if cm[i, j] > thresh else "black")
    fig.tight_layout()
    plt.savefig(CONF_MATRIX_PATH, dpi=150)
    plt.close(fig)

    # Plot 2: Feature Importance Bar Chart
    fig_feat, ax_feat = plt.subplots(figsize=(7, 4.5))
    sorted_idx = np.argsort(importances)
    pos = np.arange(sorted_idx.shape[0]) + .5
    ax_feat.barh(pos, importances[sorted_idx], align='center', color='#38BDF8')
    ax_feat.set_yticks(pos)
    ax_feat.set_yticklabels([FEATURE_COLUMNS[i] for i in sorted_idx])
    ax_feat.set_xlabel('Relative Feature Importance')
    ax_feat.set_title('Random Forest Feature Importance')
    fig_feat.tight_layout()
    plt.savefig(FEAT_IMPORT_PATH, dpi=150)
    plt.close(fig_feat)

    # 6. Save Model and Metadata
    joblib.dump(clf, MODEL_PATH)
    fingerprint = compute_file_sha256(MODEL_PATH)

    meta = {
        "model_name": "Random Forest Fault Type Classifier",
        "version": "rf-v1",
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "features": FEATURE_COLUMNS,
        "classes": CLASS_LABELS,
        "label_rules": {
            "priority": "HDF > PWF > OSF > TWF",
            "dropped_rnf_only": stats["dropped_rnf_only_rows"],
            "dropped_unlabeled_failure": stats["dropped_unlabeled_failure_rows"],
            "multi_failure_resolved": stats["multi_failure_rows"]
        },
        "training_rows": len(X_train),
        "test_rows": len(X_test),
        "sha256_fingerprint": fingerprint,
        "metrics": {
            "macro_f1": round(macro_f1, 4),
            "weighted_f1": round(weighted_f1, 4),
            "cv_macro_f1_mean": round(cv_mean, 4),
            "cv_macro_f1_std": round(cv_std, 4),
            "per_class": per_class_metrics,
            "confusion_matrix": cm.tolist(),
            "feature_importances": {col: round(float(imp), 4) for col, imp in zip(FEATURE_COLUMNS, importances)}
        }
    }

    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    # 7. Append to docs/model_report.md
    append_to_model_report(meta)

    print("\n=== Fault Classifier Training & Evaluation Summary ===")
    print(f"Macro F1 Score:        {macro_f1:.4f}")
    print(f"Weighted F1 Score:     {weighted_f1:.4f}")
    print(f"5-Fold CV Macro F1:    {cv_mean:.4f} (+/- {cv_std:.4f})")
    print(f"SHA-256 Fingerprint:   {fingerprint[:16]}...")
    print(f"Saved artifacts to {MODEL_PATH}, {META_PATH}, and docs/ plots.")

    return meta


def append_to_model_report(meta: Dict[str, Any]):
    """Appends Fault Classifier section to docs/model_report.md preserving existing sections."""
    m = meta["metrics"]
    pc = m["per_class"]

    new_section = f"""

---

# 🌲 Fault Type Classifier (Random Forest)

**Model Name:** {meta['model_name']}  
**Version:** `{meta['version']}`  
**Trained At:** `{meta['trained_at']}`  
**SHA-256 Fingerprint:** `{meta['sha256_fingerprint']}`  
**Class Weighting:** `balanced_subsample`  
**5-Fold Cross-Validation Macro F1:** `{m['cv_macro_f1_mean']:.4f} (± {m['cv_macro_f1_std']:.4f})`  
**Test Set Macro F1:** `{m['macro_f1']:.4f}` | **Weighted F1:** `{m['weighted_f1']:.4f}`  

---

## 1. Per-Class Test Set Performance

| Class Label | Full Name | Precision | Recall | F1 Score | Test Support |
|---|---|---|---|---|---|
| **none** | Nominal (No Failure) | `{pc['none']['precision']:.4f}` | `{pc['none']['recall']:.4f}` | `{pc['none']['f1']:.4f}` | {pc['none']['support']:,} |
| **TWF** | Tool Wear Failure | `{pc['TWF']['precision']:.4f}` | `{pc['TWF']['recall']:.4f}` | `{pc['TWF']['f1']:.4f}` | {pc['TWF']['support']} |
| **HDF** | Heat Dissipation Failure | `{pc['HDF']['precision']:.4f}` | `{pc['HDF']['recall']:.4f}` | `{pc['HDF']['f1']:.4f}` | {pc['HDF']['support']} |
| **PWF** | Power Failure | `{pc['PWF']['precision']:.4f}` | `{pc['PWF']['recall']:.4f}` | `{pc['PWF']['f1']:.4f}` | {pc['PWF']['support']} |
| **OSF** | Overstrain Failure | `{pc['OSF']['precision']:.4f}` | `{pc['OSF']['recall']:.4f}` | `{pc['OSF']['f1']:.4f}` | {pc['OSF']['support']} |

---

## 2. Model Visualizations

### Confusion Matrix
![Confusion Matrix](confusion_matrix.png)

### Feature Importance
![Feature Importance](feature_importance.png)

---

## 3. Plain-English Explanation & Limitations

- **Multiclass Decision Boundaries:** The Random Forest builds 300 decision trees to classify physical failure signatures based on thermodynamic features (`temp_gap_c`, `proc_c`), mechanical torque/speed laws (`power_w`), and tool wear accumulation (`strain`).
- **Honest Limitations Note:**
  1. **Synthetic Rule Calibration:** In the AI4I dataset, failure labels (HDF, PWF, OSF) were originally generated from mathematical rules on these exact features (e.g. power threshold P < 3500 W, strain threshold wear * torque > 11000). Consequently, high precision/recall on this dataset is expected, but real-world operational accuracy may be lower due to noise and external unmodeled dynamics.
  2. **Tool Wear Randomness (TWF):** `TWF` is inherently the most difficult class to separate perfectly because tool wear failures occur stochastically inside a broad window ($200 - 240$ minutes).
"""

    existing_content = ""
    if os.path.exists(REPORT_PATH):
        with open(REPORT_PATH, "r", encoding="utf-8") as f:
            existing_content = f.read()

    # Avoid duplicate section appends if trained multiple times
    if "Fault Type Classifier (Random Forest)" in existing_content:
        base_part = existing_content.split("--- \n\n# 🌲 Fault Type Classifier")[0].strip()
        final_content = base_part + new_section
    else:
        final_content = existing_content.strip() + new_section

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(final_content)


def _load_model_internal() -> Optional[Tuple[Any, Dict[str, Any]]]:
    """Loads classifier model and metadata."""
    if not os.path.exists(MODEL_PATH) or not os.path.exists(META_PATH):
        return None
    try:
        clf = joblib.load(MODEL_PATH)
        with open(META_PATH, "r", encoding="utf-8") as f:
            meta = json.load(f)
        return clf, meta
    except Exception as e:
        print(f"[FaultClassifier] Error loading model: {e}")
        return None


if HAS_STREAMLIT:
    @st.cache_resource
    def load_model() -> Optional[Tuple[Any, Dict[str, Any]]]:
        return _load_model_internal()
else:
    def load_model() -> Optional[Tuple[Any, Dict[str, Any]]]:
        return _load_model_internal()


def predict_fault(reading: Dict[str, Any]) -> Tuple[Optional[str], Optional[float], Optional[Dict[str, float]]]:
    """
    Predicts fault type for an incoming telemetry reading.
    Returns: (predicted_class, max_probability, class_probabilities_dict)
    where max_probability and probabilities in dict are floats between 0.0 and 1.0.
    If model is missing, returns (None, None, None) without crashing.
    """
    loaded = load_model()
    if loaded is None:
        return None, None, None

    clf, meta = loaded
    # IMPORTANT: use clf.classes_ (sklearn's internal alphabetical order),
    # NOT the meta's class list, to correctly map predict_proba outputs.
    classes = list(clf.classes_)

    try:
        X = extract_features(reading)
        probs = clf.predict_proba(X)[0]

        prob_dict = {cls_name: round(float(prob), 4) for cls_name, prob in zip(classes, probs)}
        best_idx = int(np.argmax(probs))
        predicted_class = classes[best_idx]
        max_probability = round(float(probs[best_idx]), 4)

        return predicted_class, max_probability, prob_dict


    except Exception as e:
        print(f"[FaultClassifier] Prediction error: {e}")
        return None, None, None



if __name__ == "__main__":
    train_fault_classifier()
