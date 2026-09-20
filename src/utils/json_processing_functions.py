#!/usr/bin/env python3
import pandas as pd
from datetime import datetime, timezone
import re
import json


def split_concatenated_json(raw_data):
    """
    Splits a raw string of concatenated JSON objects into a list of parsed dicts.
    """
    # Match JSON object start using regex
    """
    Splits concatenated JSON objects based on `{"payloadType":` start pattern.
    """
    snapshots = []
    messages = raw_data.split('{"payloadType":')[1:]  # Skip leading blank
    for chunk in messages:
        json_str = '{"payloadType":' + chunk
        try:
            msg = json.loads(json_str)
            quotes = msg["payload"]["newQuotes"]
            bids = [(q["bid"], q["size"]) for q in quotes if "bid" in q]
            asks = [(q["ask"], q["size"]) for q in quotes if "ask" in q]

            best_bid = max(bids, key=lambda x: x[0])[0] if bids else None
            best_ask = min(asks, key=lambda x: x[0])[0] if asks else None
            spread = best_ask - best_bid if best_bid and best_ask else None
            imbalance = (
                (sum(size for _, size in bids) - sum(size for _, size in asks)) /
                (sum(size for _, size in bids + asks) + 1e-6)
            )

            snapshots.append({
                "symbolId": msg["payload"]["symbolId"],
                "best_bid": best_bid,
                "best_ask": best_ask,
                "spread": spread,
                "imbalance": imbalance,
                "bids": bids,
                "asks": asks,
                "deleted": msg["payload"].get("deletedQuotes", [])
            })

        except json.JSONDecodeError as e:
            print("❌ JSON Decode Error:", e)
            continue
    return snapshots

def process_fetchbar_response(bar_data):
    """
    Processes the fetch bar response and returns a structured pandas DataFrame.

    Args:
        bar_data (list of dict): A list of dictionaries containing bar data.
            Each dictionary includes the following keys:
            - "volume"
            - "period"
            - "low"
            - "deltaOpen"
            - "deltaClose"
            - "deltaHigh"
            - "utcTimestampInMinutes"

    Returns:
        pd.DataFrame: A DataFrame containing extracted and computed fields.
    """
    extracted_data = []

    for bar in bar_data:
        timestamp_ms = bar["utcTimestampInMinutes"] * 60 * 1000  # Convert to ms
        date_time = datetime.fromtimestamp(timestamp_ms/1000, timezone.utc)
        actual_low = bar["low"] / 100000
        open_price = (bar["low"] + bar["deltaOpen"]) / 100000
        close_price = (bar["low"] + bar["deltaClose"]) / 100000
        high_price = (bar["low"] + bar["deltaHigh"]) / 100000

        extracted_data.append([
            timestamp_ms, date_time, open_price, high_price,
            close_price, actual_low, bar["volume"]
        ])

    df = pd.DataFrame(
        extracted_data,
        columns=["timestamp_ms", "datetime", "open", "high", "close", "low", "volume"]
    )
    return df


def process_tick_data(tick_data):
    """
    Processes tick data by reconstructing absolute timestamps,
    computing raw tick values, and converting them to actual prices.

    Args:
        tick_data (list of dict): List of tick data with relative timestamps.

    Returns:
        pd.DataFrame: Processed DataFrame with absolute timestamps and prices.
    """
    if not tick_data:
        print("❌ No tick data provided!")
        return None

    # Step 1: Convert relative timestamps to absolute timestamps
    base_timestamp = tick_data[0]["timestamp"]

    for i in range(1, len(tick_data)):
        tick_data[i]["timestamp"] = tick_data[i - 1]["timestamp"] + tick_data[i]["timestamp"]

    # Step 2: Convert to human-readable datetime
    for tick in tick_data:
        tick["datetime"] = datetime.utcfromtimestamp(tick["timestamp"] / 1000)

    # Step 3: Compute raw tick values (keep original order)
    base_price = tick_data[0]["tick"]
    tick_data[0]["raw_tick_value"] = base_price  # First tick is unchanged

    for i in range(1, len(tick_data)):
        tick_data[i]["raw_tick_value"] = tick_data[i - 1]["raw_tick_value"] + tick_data[i]["tick"]

    # Step 4: Convert raw tick values to actual price (assuming 5 decimal places)
    for tick in tick_data:
        tick["actual_price"] = tick["raw_tick_value"] / 10**5  # Convert to float price


    # Step 5: Convert to DataFrame
    df = pd.DataFrame(tick_data)

    # Step 6: Remove the columns after the DataFrame is created
    df.drop(columns=['tick', 'raw_tick_value'], inplace=True)

    return df

def process_symbol_info(response_json):
    """
    Extracts a concise DataFrame with symbolId, symbolName, and enabled status
    from the full symbol list response JSON.

    Args:
        response_json (dict): The full API response with nested symbol metadata.

    Returns:
        pd.DataFrame: DataFrame with columns: symbolId, symbolName, enabled
    """
    try:
        symbol_dict = response_json["payload"]["symbol"]
    except KeyError:
        raise ValueError("Invalid symbol list structure.")

    # Extract each symbol entry and build a simplified list
    simplified = [
        {
            "symbolId": sym["symbolId"],
            "symbolName": sym["symbolName"],
            "symbolCategoryId": sym["symbolCategoryId"],
            "enabled": sym["enabled"],
        }
        for sym in symbol_dict
    ]

    return pd.DataFrame(simplified).sort_values(by="symbolId", ascending=True)

def process_acl_info(response_json):
    """
    Extracts a concise DataFrame with symbolId, symbolName, and enabled status
    from the full symbol list response JSON.

    Args:
        response_json (dict): The full API response with nested symbol metadata.

    Returns:
        pd.DataFrame: DataFrame with columns: symbolId, symbolName, enabled
    """
    try:
        acl_dict = response_json["payload"]["assetClass"]
    except KeyError:
        raise ValueError("Invalid symbol list structure.")

    # Extract each symbol entry and build a simplified list
    simplified = [
        {
            "id": sym["id"],
            "name": sym["name"],
        }
        for sym in acl_dict
    ]

    return pd.DataFrame(simplified).sort_values(by="id", ascending=True)

def process_al_info(response_json):
    """
    Extracts a concise DataFrame with symbolId, symbolName, and enabled status
    from the full symbol list response JSON.

    Args:
        response_json (dict): The full API response with nested symbol metadata.

    Returns:
        pd.DataFrame: DataFrame with columns: symbolId, symbolName, enabled
    """
    try:
        al_dict = response_json["payload"]["asset"]
    except KeyError:
        raise ValueError("Invalid symbol list structure.")

    # Extract each symbol entry and build a simplified list
    simplified = [
        {
            "assetId": sym["assetId"],
            "name": sym["name"],
            "digits": sym["digits"],
        }
        for sym in al_dict
    ]

    return pd.DataFrame(simplified).sort_values(by="assetId", ascending=True)

def process_trader_info(response_json):
    """
    Extracts trader account information from a trader API response.

    Args:
        response_json (dict): Raw JSON from cTrader API.

    Returns:
        pd.DataFrame: DataFrame with trader account information.
    """
    try:
        trader_info = response_json["payload"]["trader"]
    except KeyError:
        raise ValueError("Invalid trader info structure.")

    # You can customize which fields to include
    fields_to_extract = [
        "ctidTraderAccountId",
        "balance",
        "balanceVersion",
        "nonWithdrawableBonus",
        "accessRights",
        "depositAssetId",
        "swapFree",
        "leverageInCents",
        "totalMarginCalculationType",
        "frenchRisk",
        "traderLogin",
        "accountType",
        "brokerName",
        "registrationTimestamp",
        "isLimitedRisk",
        "moneyDigits",
    ]

    extracted = {key: trader_info.get(key) for key in fields_to_extract}
    return pd.DataFrame([extracted])

def process_version_info(response_json):
    """
    Parses a version update or account version response into a DataFrame.

    Args:
        response_json (dict): The JSON payload from the API.

    Returns:
        pd.DataFrame: One-row DataFrame with clientMsgId and version.
    """
    try:
        version = response_json["payload"]["version"]
        client_id = response_json["clientMsgId"]
    except KeyError:
        raise ValueError("Invalid version message structure.")

    return pd.DataFrame([{
        "clientMsgId": client_id,
        "version": version
    }])

def process_scl_info(response_json):
    """
    Converts symbolCategory data from cTrader API response into a DataFrame.

    Args:
        response_json (dict): The full JSON object containing symbolCategory.

    Returns:
        pd.DataFrame: DataFrame with id, assetClassId, name, sortingNumber
    """
    try:
        categories = response_json["payload"]["symbolCategory"]
    except KeyError:
        raise ValueError("Invalid JSON structure for symbol categories.")

    df = pd.DataFrame(categories)
    df.sort_values(by=["id"], inplace=True)
    df.reset_index(drop=True, inplace=True)

    return df

def process_sid_info(response_json):
    """
    Parses trading symbol settings from a cTrader API response.

    Args:
        response_json (dict): Full JSON response from the API.

    Returns:
        pd.DataFrame: A flattened DataFrame with key symbol settings.
    """
    try:
        symbol_data = response_json["payload"]["symbol"]
    except KeyError:
        raise ValueError("Invalid symbol structure.")

    # Flatten only the core fields from each symbol
    simplified = []
    for s in symbol_data:
        simplified.append({
            "symbolId": s.get("symbolId"),
            "digits": s.get("digits"),
            "pipPosition": s.get("pipPosition"),
            "enableShortSelling": s.get("enableShortSelling"),
            "swapLong": s.get("swapLong"),
            "swapShort": s.get("swapShort"),
            "lotSize": s.get("lotSize"),
            "slDistance": s.get("slDistance"),
            "tpDistance": s.get("tpDistance"),
            "minVolume": s.get("minVolume"),
            "maxVolume": s.get("maxVolume"),
            "commission": s.get("commission"),
            "preciseMinCommission": s.get("preciseMinCommission"),
            "commissionType": s.get("commissionType"),
            "measurementUnits": s.get("measurementUnits")
        })

    return pd.DataFrame(simplified)

def process_spot_event_data(json_message: dict) -> pd.DataFrame:
    """
    Converts a cTrader spot event (payloadType=2131) into a pandas DataFrame.

    Parameters:
        json_message (dict): The full JSON message received from the socket.

    Returns:
        pd.DataFrame: A flattened DataFrame containing trendbar and price data.
    """
    if json_message.get("payloadType") != 2131:
        raise ValueError("❌ Not a valid spot event (payloadType 2131)")

    payload = json_message["payload"]
    # Scale raw prices (cTrader uses 5-digit pip precision)
    bid = payload.get("bid")
    ask = payload.get("ask")
    session_close = payload.get("sessionClose")
    timestamp = payload.get("timestamp")

    bid_price = bid / 100000 if bid is not None else None
    ask_price = ask / 100000 if ask is not None else None
    close_price = session_close / 100000 if session_close is not None else None

    # Calculate spread in pips (1 pip = 0.0001)
    spread_pips = None
    if bid_price is not None and ask_price is not None:
        spread_pips = round((ask_price - bid_price) / 0.0001, 2)
    # Base fields that are always included
    base_data = {
        "symbolId": payload.get("symbolId"),
        "bid": bid_price,
        "ask": ask_price,
        "spread_pips": spread_pips,
        "sessionClose": close_price,
        "timestamp_ms": pd.to_datetime(timestamp, unit="ms")
    }

    return pd.DataFrame([base_data])
