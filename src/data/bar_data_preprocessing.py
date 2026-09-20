#!/usr/bin/env python3
import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler
from pymongo import MongoClient

# Define file paths (Modify these as needed)
INPUT_CSV = "src/data/raw/bar/bar_data_1_20250305_220554.csv"   # Path to input CSV
OUTPUT_CSV = "src/data/processed/bar/processed_bar_data.csv" # Path to output CSV
# Define MongoDB connection settings
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "ctrader_db"
COLLECTION_NAME = "bar_processed_data"

def calculate_features(df):
    """
    Processes the raw OHLCV dataset and adds useful features for trading analysis.
    """

    # Convert timestamp to datetime and extract useful time features
    df['Timestamp'] = pd.to_datetime(df['timestamp_ms'], unit = 'ms')
    df['DayOfWeek'] = df['Timestamp'].dt.dayofweek  # Monday=0, Sunday=6
    df['HourOfDay'] = df['Timestamp'].dt.hour

    # Calculate Typical Price
    df['Typical_Price'] = (df['high'] + df['low'] + df['close']) / 3

    # Calculate VWAP (Cumulative)
    df['Cumulative_TP_Volume'] = (df['Typical_Price'] * df['volume']).cumsum()
    df['Cumulative_Volume'] = df['volume'].cumsum()
    df['VWAP'] = df['Cumulative_TP_Volume'] / df['Cumulative_Volume']

    # Calculate SMA (Simple Moving Averages)
    df['SMA_15'] = df['close'].rolling(window=15).mean()
    df['SMA_60'] = df['close'].rolling(window=60).mean()

    # Calculate RSI (Relative Strength Index - 14 Period)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI_14'] = 100 - (100 / (1 + rs))

    # Calculate Volatility (Rolling Standard Deviation of Returns)
    df['Returns'] = df['close'].pct_change()
    df['Volatility'] = df['Returns'].rolling(window=15).std()

    # Drop intermediate columns
    df.drop(columns=['Cumulative_TP_Volume', 'Cumulative_Volume', 'Returns'], inplace=True)

    return df


def preprocess_csv(input_file, output_file):
    """
    Reads a CSV file, processes time-series data, and saves the transformed dataset.
    """

    # Load dataset
    df = pd.read_csv(input_file)

    # Ensure column names are correct
    required_columns = {'timestamp_ms', 'open', 'high', 'low', 'close', 'volume'}
    if not required_columns.issubset(df.columns):
        raise ValueError(f"Missing columns in input CSV. Required columns: {required_columns}")

    # Process the dataset
    df = calculate_features(df)

    # Drop NaN values created during feature calculations
    df.dropna(inplace=True)

    # Normalize numerical features (except timestamp-related features)
    feature_cols = ['open', 'high', 'low', 'close', 'volume', 'RSI_14', 'VWAP',
                    'SMA_15', 'SMA_60', 'Volatility']

    scaler = MinMaxScaler(feature_range=(0, 1))
    df[feature_cols] = scaler.fit_transform(df[feature_cols])

    # Connect to MongoDB
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]

    # Convert DataFrame to list of dictionaries
    data = df.to_dict(orient="records")

    # Insert data into MongoDB
    collection.insert_many(data)
    print(f"Processed data saved to MongoDB in '{DB_NAME}.{COLLECTION_NAME}'")


if __name__ == "__main__":
    preprocess_csv(INPUT_CSV, OUTPUT_CSV)

