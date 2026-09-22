#!/usr/bin/env python3
"""
   This module defines routes relevant to management of the ctrader
   TCP connection
"""
import logging
import requests
import pytz
from flask import jsonify, request
from src.utils.json_processing_functions import *
from src.utils.ctrader_tcp_client import CTraderTCPClient
from src.utils.messages.version_request import VersionRequest
from src.utils.messages.asset_list_request import AssetListRequest
from src.utils.messages.asset_class_list_request import AssetClassListRequest
from src.utils.messages.symbol_category_list_request import SymbolCategoryListRequest
from src.utils.messages.symbol_by_id_request import SymbolByIdRequest
from src.utils.messages.symbol_list_request import SymbolListRequest
from src.utils.messages.tick_data_request import TickDataRequest
from src.utils.messages.h_data_request import HistoricalDataRequest
from src.utils.flask_ensure_authentication import ensure_authenticated
from src.utils.full_depth_order_book import FullDepthOrderBook
from src.utils.jwt_auth import token_required
from src.views import app_views
from dotenv import load_dotenv
from os import getenv, makedirs
from datetime import datetime, timedelta, timezone
from time import time


#load_dotenv()
ct_client_live = getenv("CTRADER_LIVE_STATUS", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

ctrader_client = CTraderTCPClient(live_account = ct_client_live)
depth_client = CTraderTCPClient(live_account = ct_client_live)
order_book = FullDepthOrderBook()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def _env_int(name, default):
    """Read an integer environment setting without breaking module import."""
    raw_value = getenv(name)
    if raw_value in (None, ""):
        return default
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        logging.warning("Invalid %s=%r; using %s", name, raw_value, default)
        return default


# Directory to save CSV files
CSV_DIR_TICK = "src/data/raw/tick_data"
CSV_DIR_BAR = "src/data/raw/bar_data" if _env_int("BOT_PORT", 8000) == 8000 else "src/data_2/raw/bar_data"
CSV_DIR_SYMBOLS = "src/data/raw/broker_data"
CSV_DIR_SYMBOL_INFO = "src/data/raw/broker_data/symbols_data"
CSV_DIR_SPOT_EVENTS = "src/data/raw/spot_events"
timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
makedirs(CSV_DIR_TICK, exist_ok=True)
makedirs(CSV_DIR_BAR, exist_ok=True)
makedirs(CSV_DIR_SYMBOLS, exist_ok=True)
makedirs(CSV_DIR_SYMBOL_INFO, exist_ok=True)
makedirs(CSV_DIR_SPOT_EVENTS, exist_ok=True)
GMT_PLUS_2 = pytz.timezone("Etc/GMT-2")
#N_DAYS = 90


#@app_views.route("/ctrader/authenticate", methods=["POST"])
def authenticate():
    """
       This function authenticates the client with cTrader API
       using OAuth2 access token.
    """
    success, result = ensure_authenticated(ctrader_client)
    if success:
        return jsonify({"message": "Account Authorized", "demo_account": result})
    return jsonify({"error": result}), 401


@app_views.route("/ctrader/fetchsymbols", methods=["GET"])
def fetch_symbol_list():

    # 1) Ensure we're authenticated
    if not ctrader_client.acc_authorized:
        success, result = ensure_authenticated(ctrader_client)
        if not success:
            return jsonify({"error": result}), 401

    try:
        # sl = SymbolListRequest(ctrader_client.debug_account)
        sl = SymbolListRequest(ctrader_client.acc_authorized_no)
        sl_json = sl.as_json_string()
        ctrader_client.send_json(sl_json)

        for _ in range(10):
            sl_response = ctrader_client.receive_json()
            if not sl_response:
                continue

            payload_type = sl_response.get("payloadType")
            if payload_type == 2115:
                return jsonify({
                    "message": "Symbol List data retrieved successfully.",
                    "data": sl_response})
            elif payload_type == 2142:
                desc = sl_response.get("payload", {}).get("description", "Unknown error")
                return jsonify({"status": "error", "details": desc}), 400

        return jsonify({"status": "error", "details": "Timeout waiting for cTrader response"}), 504

    except Exception as e:
            logging.error(f"❌ TCP Request failed: {e}")
            return {"status": "error", "details": str(e)}, 500


@app_views.route("/ctrader/fetchsymbol/<int:symbol_id>", methods=["GET"])
def fetch_symbol_data(symbol_id):

    # 1) Ensure we're authenticated
    if not ctrader_client.acc_authorized:
        success, result = ensure_authenticated(ctrader_client)
        if not success:
            return jsonify({"error": result}), 401


    try:
        #symbol = SymbolByIdRequest(ctrader_client.debug_account, int(symbol_id))
        symbol = SymbolByIdRequest(ctrader_client.acc_authorized_no, int(symbol_id))
        symbol_json = symbol.as_json_string()
        ctrader_client.send_json(symbol_json)

        for _ in range(10):
            symbol_response = ctrader_client.receive_json()
            if not symbol_response:
                continue

            payload_type = symbol_response.get("payloadType")
            if payload_type == 2117:
                return jsonify({
                    "message": f"Symbol {symbol_id} data retrieved successfully.",
                    "data": symbol_response})
            elif payload_type == 2142:
                desc = symbol_response.get("payload", {}).get("description", "Unknown error")
                return jsonify({"status": "error", "details": desc}), 400

        return jsonify({"status": "error", "details": "Timeout waiting for cTrader response"}), 504

    except Exception as e:
            logging.error(f"❌ TCP Request failed: {e}")
            return {"status": "error", "details": str(e)}, 500


@app_views.route("/ctrader/fetchsymbolcategory", methods=["GET"])
def fetch_sc_list():

    # 1) Ensure we're authenticated
    if not ctrader_client.acc_authorized:
        success, result = ensure_authenticated(ctrader_client)
        if not success:
            return jsonify({"error": result}), 401

    try:
        #scl = SymbolCategoryListRequest(ctrader_client.debug_account)
        scl = SymbolCategoryListRequest(ctrader_client.acc_authorized_no)
        scl_json = scl.as_json_string()
        ctrader_client.send_json(scl_json)

        for _ in range(10):
            scl_response = ctrader_client.receive_json()
            if not scl_response:
                continue

            payload_type = scl_response.get("payloadType")
            if payload_type == 2161:
                return jsonify({
                    "message": "Symbol Category data retrieved successfully.",
                    "data": scl_response})
            elif payload_type == 2142:
                desc = scl_response.get("payload", {}).get("description", "Unknown error")
                return jsonify({"status": "error", "details": desc}), 400

        return jsonify({"status": "error", "details": "Timeout waiting for cTrader response"}), 504

    except Exception as e:
            logging.error(f"❌ TCP Request failed: {e}")
            return {"status": "error", "details": str(e)}, 500


@app_views.route("/ctrader/fetchassetclass", methods=["GET"])
def fetch_ac_list():

    # 1) Ensure we're authenticated
    if not ctrader_client.acc_authorized:
        success, result = ensure_authenticated(ctrader_client)
        if not success:
            return jsonify({"error": result}), 401

    try:
        #acl = AssetClassListRequest(ctrader_client.debug_account)
        acl = AssetClassListRequest(ctrader_client.acc_authorized_no)
        acl_json = acl.as_json_string()
        ctrader_client.send_json(acl_json)

        for _ in range(10):
            acl_response = ctrader_client.receive_json()
            if not acl_response:
                continue

            payload_type = acl_response.get("payloadType")
            if payload_type == 2154:
                return jsonify({
                    "message": "Asset class data retrieved successfully.",
                    "data": acl_response})
            elif payload_type == 2142:
                desc = acl_response.get("payload", {}).get("description", "Unknown error")
                return jsonify({"status": "error", "details": desc}), 400

        return jsonify({"status": "error", "details": "Timeout waiting for cTrader response"}), 504

    except Exception as e:
            logging.error(f"❌ TCP Request failed: {e}")
            return {"status": "error", "details": str(e)}, 500


@app_views.route("/ctrader/fetchassets", methods=["GET"])
def fetch_assets():

    # 1) Ensure we're authenticated
    if not ctrader_client.acc_authorized:
        success, result = ensure_authenticated(ctrader_client)
        if not success:
            return jsonify({"error": result}), 401

    try:
        #acl = AssetClassListRequest(ctrader_client.debug_account)
        al = AssetListRequest(ctrader_client.acc_authorized_no)
        al_json = al.as_json_string()
        ctrader_client.send_json(al_json)

        for _ in range(10):
            al_response = ctrader_client.receive_json()
            if not al_response:
                continue

            payload_type = al_response.get("payloadType")
            if payload_type == 2113:
                return jsonify({
                    "message": "Asset List data retrieved successfully.",
                    "data": al_response})
            elif payload_type == 2142:
                desc = al_response.get("payload", {}).get("description", "Unknown error")
                return jsonify({"status": "error", "details": desc}), 400

        return jsonify({"status": "error", "details": "Timeout waiting for cTrader response"}), 504

    except Exception as e:
            logging.error(f"❌ TCP Request failed: {e}")
            return {"status": "error", "details": str(e)}, 500


@app_views.route("/ctrader/fetchversion", methods=["GET"])
def fetch_version():

    # 1) Ensure we're authenticated
    if not ctrader_client.acc_authorized:
        success, result = ensure_authenticated(ctrader_client)
        if not success:
            return jsonify({"error": result}), 401

    try:
        #acl = AssetClassListRequest(ctrader_client.debug_account)
        version = VersionRequest(ctrader_client.acc_authorized_no)
        version_json = version.as_json_string()
        ctrader_client.send_json(version_json)

        for _ in range(10):
            version_response = ctrader_client.receive_json()
            if not version_response:
                continue

            payload_type = version_response.get("payloadType")
            if payload_type == 2105:
                return jsonify({
                    "message": "Version data retrieved successfully.",
                    "data": version_response})
            elif payload_type == 2142:
                desc = version_response.get("payload", {}).get("description", "Unknown error")
                return jsonify({"status": "error", "details": desc}), 400

        return jsonify({"status": "error", "details": "Timeout waiting for cTrader response"}), 504

    except Exception as e:
            logging.error(f"❌ TCP Request failed: {e}")
            return {"status": "error", "details": str(e)}, 500


@app_views.route("/ctrader/fetchticks", methods=["POST"])
#@token_required
def fetch_tick_data():
    """
       Fetches historical tick data, handling pagination with `hasMore`.
       Saves everything to a CSV when done.

       Args:
         -symbol_id (int): The symbol ID for which tick data is being retrieved.

       Returns:
         -dict: A response indicating success or failure.
    """

    # 1) Ensure we're authenticated
    if not ctrader_client.acc_authorized:
        success, result = ensure_authenticated(ctrader_client)
        if not success:
            return jsonify({"error": result}), 401

    # 2) Parse request data
    data = request.get_json()
    symbol_id = data.get("symbolId")
    n_mins = data.get("lookback_window")


    logging.info(f"📅 Fetching tick data for symbol {symbol_id}")
    try:
        # 3) Define the window
        now_ms = int(datetime.now().timestamp() * 1000)
        time_window_ms = n_mins * 60 * 1000

        from_timestamp = now_ms - time_window_ms
        to_timestamp = now_ms

        all_tick_data = []
        has_more = True

        # 4) Build your tick data request
        tick_request = TickDataRequest(
            ctrader_client.acc_authorized_no,
            int(symbol_id),
            2, #Ask
            from_timestamp,
            to_timestamp
        )

        tick_json = tick_request.as_json_string()
        logging.debug(f"🚀 Sending request: {tick_json}")

        # 5) Send the request
        ctrader_client.send_json(tick_json)

        while has_more:
            # 6) Receive response (adjust timeout as needed)
            tick_response = ctrader_client.receive_json()
            logging.debug(f"🚀 Received: {tick_response}")

            if not tick_response:
                logging.error("❌ Incomplete JSON received from OpenAPI!")
                return {"error": "Incomplete JSON data from backend"}, 500

            # 7) Extract data and check pagination
            tick_data = tick_response.get("payload", {}).get("tickData", [])
            has_more = tick_response.get("payload", {}).get("hasMore", False)
            py_type = tick_response.get("payloadType")

            if py_type == 2146:
                # 8) Process the chunk
                if tick_data:
                    df_processed = process_tick_data(tick_data)
                    if not df_processed.empty:
                        all_tick_data.extend(df_processed.to_dict(orient="records"))
                        earliest_ts_in_chunk = df_processed["timestamp"].min()
                        to_timestamp = earliest_ts_in_chunk - 1  # fetch older data next
                        logging.info(
                            f"✅ Fetched chunk. Updating to_timestamp to {to_timestamp}"
                        )
            elif py_type == 2142:
                desc = tick_response.get("payload", {}).get("description", "Unknown error")
                return jsonify({"status": "error", "details": desc}), 400
            elif py_type == 51:
                has_more = True
                continue
            elif py_type == 2155:
                dep_pl = tick_response.get("payload", {})
                order_book.apply_update(
                    dep_pl.get("newQuotes", []),
                    dep_pl.get("deletedQuotes", [])
                )


        # 6) Convert all collected data into a DataFrame and save
        df_final = pd.DataFrame(all_tick_data)
        if df_final.empty:
            return {"message": "No tick data available."}, 404
        df_final = df_final.sort_values(by="timestamp", ascending=True)
        filename = f"{CSV_DIR_TICK}/tick_data_{symbol_id}_{timestamp_str}.csv"
        df_final.to_csv(filename, index=False)

        logging.info(f"✅ Tick data saved to CSV: {filename}")
        return {
            "message": "Tick data saved successfully.",
            "file_path": filename
        }

    except Exception as e:
        logging.error(f"❌ Failed to fetch tick data: {e}")
        return {"error": "Failed to fetch tick data"}, 500


@app_views.route("/ctrader/fetchbars", methods=["POST"])
#@token_required
def fetch_bar_data():
    """
    Fetches up to 1 year worth of historical bar data,
    handling pagination with `hasMore`.
    Saves everything to a CSV when done.

    Args:
        symbol_id (int): The symbol ID for which bar data is being retrieved.

    Returns:
        dict: A response indicating success or failure.
    """
    logging.info(f"📊 Fetching bar data for symbol.")

    # 1) Ensure we're authenticated
    if not ctrader_client.acc_authorized:
        success, result = ensure_authenticated(ctrader_client)
        if not success:
            return jsonify({"error": result}), 401

    # 2) Parse request data
    data = request.get_json()
    symbol_id = data.get("symbolId")
    timeframe_id = int(data.get("period"))
    n_days = data.get("lookback_window")
    if timeframe_id not in range(0, 16):
        logging.error(f"❌ Incompatible Timeframe Id.")
        return jsonify({"error": "Input valid Timeframe Id"}), 500

    try:
        # 3) Define the window in ms
        now_ms = int(datetime.now().timestamp() * 1000)
        #now_ms = int((datetime.now() - timedelta(days=180)).timestamp() * 1000)
        time_window_ms = (n_days * 24 * 60 * 60 * 1000)
        from_timestamp = now_ms - int(time_window_ms)
        to_timestamp = now_ms

        all_bar_data = []
        has_more = True

        # 4) Build the bar data request
        bar_request = HistoricalDataRequest(
            ctrader_client.acc_authorized_no,
            from_timestamp,
            to_timestamp,
            timeframe_id,
            symbol_id
        )
        bar_json = bar_request.as_json_string()
        ctrader_client.send_json(bar_json)


        while has_more:
            bar_response = ctrader_client.receive_json()

            if not bar_response:
                logging.error("❌ Incomplete JSON received from OpenAPI!")
                return jsonify({"status": "error", "details": "Incomplete JSON data from backend"}), 500

            # 4) Extract data and check pagination
            bar_data = bar_response.get("payload", {}).get("trendbar", [])
            py_type = bar_response.get("payloadType")

            if py_type == 2138:
                # 5) Process the chunk
                has_more = bar_response.get("payload", {}).get("hasMore", False)
                df_processed = process_fetchbar_response(bar_data)
                if not df_processed.empty:
                    all_bar_data.extend(df_processed.to_dict(orient="records"))
            elif py_type == 2142:
                desc = bar_response.get("payload", {}).get("description", "Unknown error")
                return jsonify({"status": "error", "details": desc}), 400
            elif py_type == 51:
                continue
            elif py_type == 2155:
                dep_pl = bar_response.get("payload", {})
                order_book.apply_update(
                    dep_pl.get("newQuotes", []),
                    dep_pl.get("deletedQuotes", [])
                )


        # 6) Convert all collected data into a DataFrame and save
        df_final = pd.DataFrame(all_bar_data)
        if df_final.empty:
            return {"message": "No bar data available."}, 404
        df_final = df_final.sort_values(by="timestamp_ms", ascending=True)
        filename = f"{CSV_DIR_BAR}/bar_data_{timeframe_id}m_{symbol_id}_{timestamp_str}.csv"
        df_final.to_csv(filename, index=False)
        logging.info(f"✅ Bar data saved to CSV: {filename}")
        return jsonify({
            "message": "Bar data saved successfully.",
            "file_path": filename
        })

    except Exception as e:
        logging.error(f"❌ Failed to fetch bar data: {e}")
        ctrader_client.close()
        return {"error": "Failed to fetch bar data"}, 500

    #finally:
        #ctrader_client.close()
