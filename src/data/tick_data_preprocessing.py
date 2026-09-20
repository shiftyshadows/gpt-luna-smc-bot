#!/usr/bin/env python3
import os
import numpy as np
import pandas as pd
import joblib
from sklearn.preprocessing import StandardScaler

# ------------------------------------------------------------
# 1. Load Data
# ------------------------------------------------------------
def load_data(csv_path: str):
    print("[INFO] Loading raw data...")
    df = pd.read_csv(csv_path)

    if 'datetime' in df.columns:
        df['datetime'] = pd.to_datetime(df['datetime'])
        df.sort_values(by='datetime', inplace=True)
    else:
        print("⚠️ Warning: 'datetime' column not found. Ensure data is pre-sorted.")

    return df

# ------------------------------------------------------------
# 2. Generate Features
# ------------------------------------------------------------
def generate_features(df: pd.DataFrame):
    print("[INFO] Generating features...")

    if 'actual_price' not in df.columns:
        raise ValueError("❌ Column 'actual_price' is missing from the dataset.")

    df['time_diff'] = df['datetime'].diff().dt.total_seconds().fillna(0)
    df['price_change'] = df['actual_price'].diff().fillna(0)

    if 'tick' in df.columns:
        df['synthetic_volume'] = df['tick'].rolling(window=5).sum().bfill()
    else:
        df['synthetic_volume'] = 0  

    df['price_movement_intensity'] = (
        df['price_change'].abs() / (df['time_diff'] + 1e-9)
    ).fillna(0)

    df['tick_imbalance'] = (df['price_change'] > 0).cumsum() - (df['price_change'] < 0).cumsum()

    return df

# ------------------------------------------------------------
# 3. Generate Target Variable
# ------------------------------------------------------------
def generate_target(df: pd.DataFrame, future_target: int):
    print("[INFO] Generating target variable...")
    df['future_price'] = df['actual_price'].shift(-future_target)
    df.dropna(subset=['future_price'], inplace=True)
    return df

# ------------------------------------------------------------
# 4. Normalize Data (Fixed: Save Feature Names with Scaler)
# ------------------------------------------------------------
def normalize_data(df: pd.DataFrame, feature_cols: list, scaler_path: str):
    print("[INFO] Normalizing data...")

    missing_cols = [c for c in feature_cols if c not in df.columns]
    if missing_cols:
        raise ValueError(f"❌ Missing feature columns: {missing_cols}")

    features_raw = df[feature_cols].values
    labels_raw = df['future_price'].values

    scaler = StandardScaler()
    features_scaled = scaler.fit_transform(features_raw)

    # ✅ Ensure the scaler directory exists
    scaler_dir = os.path.dirname(scaler_path)
    if scaler_dir:
        os.makedirs(scaler_dir, exist_ok=True)

    # ✅ Fix: Save scaler as a dictionary (scaler + feature names)
    scaler_data = {"scaler": scaler, "feature_names": feature_cols}
    joblib.dump(scaler_data, scaler_path)
    
    print(f"[INFO] ✅ Scaler and feature names saved at {scaler_path}")

    return features_scaled, labels_raw, scaler

# ------------------------------------------------------------
# 5. Create LSTM Sequences
# ------------------------------------------------------------
def create_sequences(data, labels, seq_length):
    print("[INFO] Creating LSTM sequences...")
    X, y = [], []
    for i in range(len(data) - seq_length):
        X.append(data[i:i+seq_length])
        y.append(labels[i + seq_length])
    return np.array(X), np.array(y)

# ------------------------------------------------------------
# 6. Split Data
# ------------------------------------------------------------
def split_data(X, y, val_split_ratio):
    print("[INFO] Splitting into training and validation sets...")
    split_idx = int(len(X) * (1 - val_split_ratio))
    return X[:split_idx], X[split_idx:], y[:split_idx], y[split_idx:]

# ------------------------------------------------------------
# 7. Save Preprocessed Data
# ------------------------------------------------------------
def save_preprocessed_data(df: pd.DataFrame, output_csv_path: str):
    os.makedirs(os.path.dirname(output_csv_path), exist_ok=True)
    df.to_csv(output_csv_path, index=False)
    print(f"[INFO] ✅ Preprocessed data saved at {output_csv_path}")

# ------------------------------------------------------------
# 8. Full Preprocessing Pipeline
# ------------------------------------------------------------
def preprocess_data(
    raw_csv_path: str,
    output_csv_path: str,
    feature_cols: list,
    seq_length: int,
    future_target: int,
    val_split_ratio: float = 0.2,
    scaler_path: str = "src/data/preprocessed/scaler.pkl"
):
    """
    Runs the full preprocessing pipeline.

    :return: X_train, X_val, y_train, y_val, scaler.
    """
    df = load_data(raw_csv_path)
    df = generate_features(df)
    df = generate_target(df, future_target)
    features_scaled, labels_raw, scaler = normalize_data(df, feature_cols, scaler_path)
    X, y = create_sequences(features_scaled, labels_raw, seq_length)
    X_train, X_val, y_train, y_val = split_data(X, y, val_split_ratio)
    save_preprocessed_data(df, output_csv_path)

    return X_train, X_val, y_train, y_val, scaler

# ------------------------------------------------------------
# Main Execution
# ------------------------------------------------------------
if __name__ == "__main__":
    RAW_CSV_PATH = "src/data/raw/tick/tick_data_1_20250305_215020.csv"
    PROCESSED_CSV_PATH = "src/data/processed/preprocessed_tick_data.csv"
    FEATURE_COLS = [
        'actual_price', 'time_diff', 'price_change', 'synthetic_volume',
        'price_movement_intensity', 'tick_imbalance'
    ]
    SEQ_LENGTH = 20
    FUTURE_TARGET = 1
    SCALER_PATH = "src/data/processed/scaler.pkl"  # ✅ Default path for the scaler

    X_train, X_val, y_train, y_val, scaler = preprocess_data(
        raw_csv_path=RAW_CSV_PATH,
        output_csv_path=PROCESSED_CSV_PATH,
        feature_cols=FEATURE_COLS,
        seq_length=SEQ_LENGTH,
        future_target=FUTURE_TARGET,
        scaler_path=SCALER_PATH
    )
