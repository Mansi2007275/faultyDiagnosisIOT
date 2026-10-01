import os
import numpy as np
import pandas as pd
import streamlit as st
from typing import Tuple, List, Dict, Any, Optional

REQUIRED_COLUMNS = [
    "UDI",
    "Product ID",
    "Type",
    "Air temperature [K]",
    "Process temperature [K]",
    "Rotational speed [rpm]",
    "Torque [Nm]",
    "Tool wear [min]",
    "Machine failure",
    "TWF",
    "HDF",
    "PWF",
    "OSF",
    "RNF"
]

COLUMN_MAPPING = {
    "UDI": "udi",
    "Product ID": "product_id",
    "Type": "type",
    "Air temperature [K]": "air_k",
    "Process temperature [K]": "proc_k",
    "Rotational speed [rpm]": "rpm",
    "Torque [Nm]": "torque",
    "Tool wear [min]": "wear",
    "Machine failure": "failure",
    "TWF": "twf",
    "HDF": "hdf",
    "PWF": "pwf",
    "OSF": "osf",
    "RNF": "rnf"
}

@st.cache_data
def load_and_preprocess_dataset(csv_path: str = os.path.join("data", "ai4i2020.csv")) -> Tuple[pd.DataFrame, str, List[str]]:
    """
    Cached data loading function.
    Reads dataset, validates column presence, renames columns, and adds derived physics features.
    Returns: (df, source_label, missing_columns_list)
    """
    if os.path.exists(csv_path):
        try:
            df_raw = pd.read_csv(csv_path)
            # Check for missing required columns
            missing_cols = [col for col in REQUIRED_COLUMNS if col not in df_raw.columns]
            
            if not missing_cols:
                # Select and rename required columns
                df = df_raw[REQUIRED_COLUMNS].copy()
                df = df.rename(columns=COLUMN_MAPPING)
                
                # Add derived physics columns
                df["air_c"] = np.round(df["air_k"] - 273.15, 2)
                df["proc_c"] = np.round(df["proc_k"] - 273.15, 2)
                df["temp_gap_c"] = np.round(df["proc_c"] - df["air_c"], 2)
                df["power_w"] = np.round(df["torque"] * df["rpm"] * (2 * np.pi / 60), 2)
                df["strain"] = np.round(df["wear"] * df["torque"], 2)
                
                return df, "AI4I 2020 dataset (UCI)", []
            else:
                print(f"[DataLoader] Warning: Missing columns in CSV: {missing_cols}")
                # If required columns are missing, fallback to synthetic
                df_synth = DataLoader.generate_synthetic_ai4i(n_samples=10000)
                return df_synth, "Demo data (Missing columns in file)", missing_cols
        except Exception as e:
            print(f"[DataLoader] Failed to read {csv_path}: {e}")
            df_synth = DataLoader.generate_synthetic_ai4i(n_samples=10000)
            return df_synth, "Demo data (Read Error)", []

    # Fallback to high-fidelity synthetic demo data
    df_synth = DataLoader.generate_synthetic_ai4i(n_samples=10000)
    return df_synth, "Demo data", []


class DataLoader:
    """
    Data Loader manager providing access to the processed AI4I dataframe,
    statistical metrics, and real/synthetic fallback states.
    """
    DATA_PATH = os.path.join("data", "ai4i2020.csv")
    UCI_LINK = "https://archive.ics.uci.edu/dataset/601"

    def __init__(self, data_path: Optional[str] = None):
        self.data_path = data_path or self.DATA_PATH
        self.df, self.source_label, self.missing_columns = load_and_preprocess_dataset(self.data_path)
        self.is_real_data = "UCI" in self.source_label

    def reload(self):
        """Forces reloading the dataset cache."""
        self.df, self.source_label, self.missing_columns = load_and_preprocess_dataset(self.data_path)
        self.is_real_data = "UCI" in self.source_label

    @staticmethod
    def generate_synthetic_ai4i(n_samples: int = 10000, random_seed: int = 42) -> pd.DataFrame:
        """
        Generates synthetic fallback dataset calibrated to AI4I 2020 statistics.
        """
        rng = np.random.default_rng(random_seed)
        
        # Product types: L (60%), M (30%), H (10%)
        types = rng.choice(['L', 'M', 'H'], size=n_samples, p=[0.60, 0.2997, 0.1003])
        
        # Air temperature [K]: ~ 298.15 to 304.5 K
        air_k = np.round(rng.normal(300.0, 2.0, n_samples), 2)
        proc_k = np.round(air_k + 10.0 + rng.normal(0.0, 0.9, n_samples), 2)
        
        # Rotational speed [rpm]
        rpm = np.round(np.clip(rng.normal(1538.0, 179.0, n_samples), 1100, 2900), 1)
        
        # Torque [Nm]
        base_power = 6500.0
        torque = np.round(np.clip((base_power / (2 * np.pi * rpm / 60)) + rng.normal(0, 3.5, n_samples), 5.0, 80.0), 2)
        
        # Tool wear [min]
        wear = np.round(rng.uniform(0, 250, n_samples), 1)
        
        # Failures
        twf = (wear >= 200) & (rng.random(n_samples) < 0.25)
        dt = proc_k - air_k
        hdf = (dt < 8.6) & (rpm < 1380)
        power_w = torque * rpm * (2 * np.pi / 60)
        pwf = (power_w < 3500) | (power_w > 9000)
        osf_thresh = np.where(types == 'L', 11000, np.where(types == 'M', 12000, 13000))
        osf = (wear * torque) > osf_thresh
        rnf = (rng.random(n_samples) < 0.002)
        
        failure = (twf | hdf | pwf | osf | rnf).astype(int)
        
        air_c = np.round(air_k - 273.15, 2)
        proc_c = np.round(proc_k - 273.15, 2)
        temp_gap_c = np.round(proc_c - air_c, 2)
        power_w = np.round(power_w, 2)
        strain = np.round(wear * torque, 2)
        
        df = pd.DataFrame({
            'udi': np.arange(1, n_samples + 1),
            'product_id': [f"{t}{10000 + i}" for i, t in enumerate(types)],
            'type': types,
            'air_k': air_k,
            'proc_k': proc_k,
            'rpm': rpm,
            'torque': torque,
            'wear': wear,
            'failure': failure,
            'twf': twf.astype(int),
            'hdf': hdf.astype(int),
            'pwf': pwf.astype(int),
            'osf': osf.astype(int),
            'rnf': rnf.astype(int),
            'air_c': air_c,
            'proc_c': proc_c,
            'temp_gap_c': temp_gap_c,
            'power_w': power_w,
            'strain': strain
        })
        return df

    def get_summary_statistics(self) -> Dict[str, Any]:
        """Returns statistics for display across the application."""
        total_rows = len(self.df)
        total_failures = int(self.df["failure"].sum())
        failure_rate = float((total_failures / total_rows) * 100) if total_rows > 0 else 0.0
        
        type_counts = self.df["type"].value_counts().to_dict()
        
        return {
            "total_rows": total_rows,
            "is_real": self.is_real_data,
            "source_label": self.source_label,
            "missing_columns": self.missing_columns,
            "total_failures": total_failures,
            "failure_rate": failure_rate,
            "type_counts": {
                "L": type_counts.get("L", 0),
                "M": type_counts.get("M", 0),
                "H": type_counts.get("H", 0)
            },
            "failure_counts": {
                "TWF (Tool wear failure)": int(self.df["twf"].sum()),
                "HDF (Heat dissipation failure)": int(self.df["hdf"].sum()),
                "PWF (Power failure)": int(self.df["pwf"].sum()),
                "OSF (Overstrain failure)": int(self.df["osf"].sum()),
                "RNF (Random failure)": int(self.df["rnf"].sum())
            }
        }
