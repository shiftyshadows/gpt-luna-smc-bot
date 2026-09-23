#!/usr/bin/env python3
"""
   This module defines routes relevant to management of the ctrader
   TCP connection
"""
import logging
import requests
import pytz
import threading
import uuid
from flask import jsonify, request
from src.utils.json_processing_functions import *
from src.utils.dom_listener import dom_stream_worker
from src.utils.messages.new_order_request import NewOrderRequest
from src.utils.messages.cancel_order_request import CancelOrderRequest
from src.utils.messages.trader_request import TraderRequest
from src.utils.messages.reconcile_request import ReconcileRequest
from src.utils.messages.unrealized_pnl_request import GetPositionUnrealizedPnLRequest
from src.utils.messages.close_position_request import ClosePositionRequest
from src.utils.messages.amend_position_sltp_request import AmendPositionSLTPRequest
from src.utils.messages.subscribe_spot_request import SubscribeSpotRequest
from src.utils.messages.subscribe_depth_request import SubscribeDepthRequest
from src.utils.messages.unsubscribe_depth_request import UnSubscribeDepthRequest
from src.utils.messages.subscribe_live_trendbars import SubscribeLiveTrendbarsRequest
from src.utils.flask_ensure_authentication import ensure_authenticated
from src.utils.jwt_auth import token_required
from src.views import app_views
from dotenv import load_dotenv
from os import getenv, makedirs
from datetime import datetime, timedelta, timezone
from time import time, sleep
from src.api.routes.ctrader import ctrader_client
from src.api.routes.ctrader import depth_client
from src.api.routes.ctrader import order_book

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def _json_object():
    """Parse a request body and require a JSON object for trading routes."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, (jsonify({"error": "Request body must be a JSON object"}), 400)
    return data, None


def _request_reply(client, message, payload_types, matcher=None, timeout=30):
    """Send a request and accept only its correlated response."""
    request_id = message.get("clientMsgId")
    expected_types = set(
        payload_types if isinstance(payload_types, (tuple, list, set)) else (payload_types,)
    )

    def matches(response):
        response_id = response.get("clientMsgId")
        if response_id is not None:
            return response_id == request_id
        if matcher is not None and matcher(response):
            return True
        return response.get("payloadType") in expected_types | {2132, 2142}

    return client.request_reply(message, matcher=matches, timeout=timeout)


def _wait_reply(client, matcher, timeout=30):
    """Wait for a correlated follow-up without sending the request again."""
    return client.wait_for_reply(matcher, timeout=timeout)


GMT_PLUS_2 = pytz.timezone("Etc/GMT-2")
N_DAYS = 90


@app_views.route("/ctrader/new_order", methods=["POST"])
@token_required
def new_order():
    """
    Places a new order and handles the complete order lifecycle including:
    - Order placement (executionType: 2)
    - Order execution (executionType: 3)
    - Position updates
    All potentially received in a single accumulated JSON response.
    """
    # 1) Ensure we're authenticated
    if not ctrader_client.acc_authorized:
        success, result = ensure_authenticated(ctrader_client)
        if not success:
            return jsonify({"error": result}), 401

    # Parse request data
    data, error = _json_object()
    if error is not None:
        return error
    symbol_id = data.get("symbolId")
    direction = data.get("direction", "BUY")
    if not isinstance(direction, str) or direction.upper() not in {"BUY", "SELL"}:
        return jsonify({"error": "direction must be BUY or SELL"}), 400
    direction = direction.upper()
    trade_side = 1 if direction == "BUY" else 2
    order_volume = int(data.get("volume", 100000))
    od_type = str(data.get("od_type", ""))
    order_type = 2 if od_type == "limit" else 1
    limit_price = data.get("order_price", 0.0)
    stop_loss = data.get("stop_loss", 0.0)
    take_profit = data.get("take_profit", 0.0)
    client_order_id = data.get("c_order_id") or f"api-{uuid.uuid4().hex}"
    order_comment = str(data.get("od_comment", {})) if od_type == "market" and len(str(data.get("od_comment", {}))) < 100 else ""
    t_frame = int(data.get("order_timeframe")) if od_type == "limit" else 1

    # Calculation order expiration
    # Logic: (Minutes per bar) * 24
    expiration_lookup = {
        1: 24,       # M1: 1 * 24
        2: 48,       # M2: 2 * 24
        3: 72,       # M3: 3 * 24
        4: 96,       # M4: 4 * 24
        5: 120,      # M5: 5 * 24
        6: 240,      # M10: 10 * 24
        7: 360,      # M15: 15 * 24
        8: 720,      # M30: 30 * 24
        9: 1440,     # H1: 60 * 24
        10: 5760,    # H4: 240 * 24
        11: 17280,   # H12: 720 * 24
        12: 34560,   # D1: 1440 * 24
        13: 241920,  # W1: 10080 * 24
        14: 1036800  # MN1: 43200 * 24
    }

    # Assign the expiration based on t_frame
    exp_min = expiration_lookup.get(t_frame, 0)


    # State tracking
    result = {
        "order_placed": False,
        "order_executed": False,
        "order_id": None,
        "position_id": None,
        "execution_price": None,
        "error": None,
        "timestamp_utc": datetime.utcnow().isoformat() + "Z",
        "local_timestamp": datetime.now(GMT_PLUS_2).isoformat()
    }

    try:
        # Send order request
        new_order = NewOrderRequest(
            ctrader_client.acc_authorized_no,
            symbolId = symbol_id,
            tradeSide = trade_side,
            volume = order_volume,
            orderType = order_type,
            limitPrice = limit_price,
            expirationTimestamp = exp_min,
            stopLoss = stop_loss,
            takeProfit = take_profit,
            orderComment = order_comment,
            label = client_order_id
        )
        order_request = new_order.as_json_string()
        placement = _request_reply(
            ctrader_client,
            order_request,
            2126,
            matcher=lambda packet: packet.get("payload", {}).get("executionType") == 2,
        )
        if not placement:
            return jsonify({"status": "error", "details": "Timeout waiting for order placement"}), 504
        if placement.get("payloadType") == 2132:
            e_payload = placement.get("payload", {})
            return jsonify({
                "status": "error",
                "error code": e_payload.get("errorCode", "UNKNOWN ERROR"),
                "details": e_payload.get("description"),
            }), 500

        placement_payload = placement.get("payload", {})
        placement_order = placement_payload.get("order", {}) or {}
        result.update({
            "order_placed": placement_payload.get("executionType") == 2,
            "order_id": placement_order.get("orderId"),
        })
        logging.info(f"✅ Order placed - ID: {result['order_id']}")
        if order_type == 2:
            result["execution_price"] = limit_price
            return jsonify({"status": "success", "details": result}), 200

        def execution_matches(packet):
            payload = packet.get("payload", {})
            order = payload.get("order", {}) or {}
            return (
                payload.get("executionType") in {3, 7}
                and (order.get("orderId") == result["order_id"] or order.get("label") == client_order_id)
            )

        response = _wait_reply(ctrader_client, execution_matches)
        if not response:
            return jsonify({"status": "error", "details": "Timeout waiting for order execution"}), 504
        payload = response.get("payload", {})
        if payload.get("executionType") == 3 and (payload.get("order", {}) or {}).get("orderStatus") == 2:
            order_data = payload.get("order", {}) or {}
            position_data = payload.get("position", {}) or {}
            result.update({
                "order_executed": True,
                "execution_price": order_data.get("executionPrice"),
                "position_id": position_data.get("positionId"),
            })
            logging.info(f"⚡ Order executed at {result['execution_price']}")
            return jsonify({"status": "success", "details": result}), 200

        er_code = payload.get("errorCode", "UNKNOWN ERROR")
        return jsonify({"status": "error", "order_id": result["order_id"], "error code": er_code}), 500


    except Exception as e:
        error_msg = f"Order processing failed: {str(e)}"
        logging.error(f"❌ {error_msg}")
        result["error"] = error_msg
        return jsonify({"status": "error", "details": result}), 500


@app_views.route("/ctrader/cancel_order", methods=["POST"])
@token_required
def cancel_order():
    """
       Cancels a pending order and handles the complete order lifecycle including:
       - Order placement (executionType: 2)
       - Order execution (executionType: 3)
       - Position updates
       All potentially received in a single accumulated JSON response.
    """
    # 1) Ensure we're authenticated
    if not ctrader_client.acc_authorized:
        success, result = ensure_authenticated(ctrader_client)
        if not success:
            return jsonify({"error": result}), 401

    # 2) Parse request data
    data, error = _json_object()
    if error is not None:
        return error
    order_id = data.get("orderId")

    # 3) Send TCP Request
    try:
        cancel_order_req = CancelOrderRequest(ctrader_client.acc_authorized_no, order_id)
        cancel_order_req = cancel_order_req.as_json_string()

        cancel_response = _request_reply(
            ctrader_client,
            cancel_order_req,
            2126,
            matcher=lambda packet: (packet.get("payload", {}).get("order", {}) or {}).get("orderId") == order_id,
        )
        if cancel_response:
            payload_type = cancel_response.get("payloadType")
            if payload_type == 2126:
                return jsonify({"status": "success", "data": cancel_response})
            if payload_type == 2132:
                desc = cancel_response.get("payload", {}).get("description", "Unknown error")
                return jsonify({"status": "error", "details": desc}), 400

        return jsonify({"status": "error", "details": "Timeout waiting for cTrader response"}), 504


    except Exception as e:
            logging.error(f"❌ TCP Request failed: {e}")
            return jsonify({"status": "error", "details": str(e)}, 500)



@app_views.route("/ctrader/subscribedepth/<int:symbol_id>", methods=["GET"])
#@token_required
def subscribe_depth(symbol_id):
    """
       This route subscribes to depth events.
    """
    # 1) Ensure we're authenticated
    if not depth_client.acc_authorized:
        success, result = ensure_authenticated(depth_client)
        if not success:
            return jsonify({"error": result}), 401


    with depth_client.depth_subscription_lock:
        # cTrader subscriptions are idempotent, but repeated requests still
        # create needless traffic and can start overlapping readers.
        if depth_client.is_depth_subscribed(symbol_id):
            _start_depth_listener(symbol_id)
            return {"status": "success", "message": f"Depth Subscription Confirmed for Symbol {symbol_id}"}

        if not depth_client.is_connected():
            return jsonify({"status": "error", "details": "Depth client is not connected"}), 503

        sd = SubscribeDepthRequest(depth_client.acc_authorized_no, symbol_id)
        sd_request = sd.as_json_string()
        sd_response = _request_reply(depth_client, sd_request, (2157, 2142))
        if sd_response and sd_response.get("payloadType") == int(2157):
            depth_client.mark_depth_subscribed(symbol_id)
            logging.info("Depth subscription confirmed for symbol %s", symbol_id)
            _start_depth_listener(symbol_id)
            return {"status": "success", "message": f"Depth Subscription Confirmed for Symbol {symbol_id}"}
        if sd_response and sd_response.get("payloadType") == int(2142):  # ProtoOAErrorRes
            desc = sd_response.get("payload", {}).get("description", "Unknown error")
            return jsonify({"status": "error", "details": desc}), 400

        return jsonify({"status": "error", "details": "Timeout waiting for depth subscription"}), 504


def _start_depth_listener(symbol_id):
    """Start one queue consumer for depth events. Caller holds subscription lock."""
    worker = getattr(depth_client, "depth_worker_thread", None)
    if worker is not None and worker.is_alive():
        return

    depth_client.is_listening_dom = True
    worker = threading.Thread(
        target=dom_stream_worker,
        args=(depth_client, order_book, symbol_id),
        daemon=True,
        name=f"ctrader-depth-{symbol_id}",
    )
    depth_client.depth_worker_thread = worker
    worker.start()


@app_views.route("/ctrader/reconcile", methods=["GET"])
@token_required
def reconcile_position():
    """
       This route fetches data on open positions and pending orders from
       ctrader open API and makes it available.
    """
    # 1) Ensure we're authenticated
    if not ctrader_client.acc_authorized:
        success, result = ensure_authenticated(ctrader_client)
        if not success:
            return jsonify({"error": result}), 401

    try:
        reconcile_req = ReconcileRequest(ctrader_client.acc_authorized_no)
        reconcile_req = reconcile_req.as_json_string()
        reconcile_response = _request_reply(ctrader_client, reconcile_req, (2125, 2155, 51))
        if reconcile_response and reconcile_response.get("payloadType") == 2125:
            return jsonify({"status": "success", "data": reconcile_response})
        if reconcile_response and reconcile_response.get("payloadType") == 2142:
            desc = reconcile_response.get("payload", {}).get("description", "Unknown error")
            return jsonify({"status": "error", "details": desc}), 400

        return jsonify({"status": "error", "details": "Timeout waiting for cTrader response"}), 504

    except Exception as e:
            logging.error(f"❌ Reconcile TCP Request failed: {e}")
            return {"status": "error", "details": str(e)}, 500



@app_views.route("/ctrader/amend_position", methods=["POST"])
@token_required
def amend_position():
    """
       This route sends a TCP request to OpenAPI backend defining the moditication
       of an existing position's stop loss and take profit.
    """
    # 1) Ensure we're authenticated
    if not ctrader_client.acc_authorized:
        success, result = ensure_authenticated(ctrader_client)
        if not success:
            return jsonify({"error": result}), 401

    # 2) Parse request data
    data, error = _json_object()
    if error is not None:
        return error
    position_id = data.get("positionId")
    stop_loss = data.get("stopLoss")
    take_profit = data.get("takeProfit")

    # 3) Send TCP Request
    try:
        amend_position_req = AmendPositionSLTPRequest(ctrader_client.acc_authorized_no, position_id, stop_loss, take_profit)
        amend_position_req = amend_position_req.as_json_string()
        amend_response = _request_reply(
            ctrader_client,
            amend_position_req,
            2126,
            matcher=lambda packet: (packet.get("payload", {}).get("position", {}) or {}).get("positionId") == position_id,
        )
        if amend_response:
            payload_type = amend_response.get("payloadType")
            if payload_type == 2126:
                return jsonify({"status": "success", "data": amend_response})
            if payload_type == 2132:
                desc = amend_response.get("payload", {}).get("description", "Unknown error")
                return jsonify({"status": "error", "details": desc})

        return jsonify({"status": "error", "details": "Timeout waiting for cTrader response"}), 504

    except Exception as e:
            logging.error(f"❌ TCP Request failed: {e}")
            return jsonify({"status": "error", "details": str(e)}), 500




@app_views.route("/ctrader/close_position", methods=["POST"])
@token_required
def close_position():
    """
       This route sends a TCP request to cTrader backend requesting the partial
       or full close of an open position.
    """
    # 1) Ensure we're authenticated
    if not ctrader_client.acc_authorized:
        success, result = ensure_authenticated(ctrader_client)
        if not success:
            return jsonify({"error": result}), 401

    # State tracking
    result = {
        "close_order_placed": False,
        "close_order_executed": False,
        "close_order_id": None,
        "position_id": None,
        "execution_price": None,
        "error": None,
        "timestamp_utc": datetime.utcnow().isoformat() + "Z",
        "local_timestamp": datetime.now(GMT_PLUS_2).isoformat()
    }

    # 2) Parse request data
    data, error = _json_object()
    if error is not None:
        return error
    try:
        position_id = int(data["positionId"])
        volume = int(data["volume"])
    except (KeyError, ValueError, TypeError):
        return jsonify({"error": "Invalid input"}), 400

    # 3) Send TCP Request
    try:
        close_position_req = ClosePositionRequest(ctrader_client.acc_authorized_no, position_id, volume)
        close_position_req = close_position_req.as_json_string()
        placement = _request_reply(
            ctrader_client,
            close_position_req,
            2126,
            matcher=lambda packet: packet.get("payload", {}).get("executionType") == 2,
        )
        if not placement:
            return {"status": "error", "details": "Timeout waiting for close placement"}, 504
        if placement.get("payloadType") == 2132:
            e_payload = placement.get("payload", {})
            return {
                "status": "error",
                "error code": e_payload.get("errorCode", "UNKNOWN ERROR"),
                "details": e_payload.get("description"),
            }, 500

        placement_payload = placement.get("payload", {})
        placement_order = placement_payload.get("order", {}) or {}
        result.update({
            "close_order_placed": placement_payload.get("executionType") == 2,
            "close_order_id": placement_order.get("orderId"),
        })
        logging.info(f"✅ Close Order placed - ID: {result['close_order_id']}")

        def close_execution_matches(packet):
            payload = packet.get("payload", {})
            order = payload.get("order", {}) or {}
            return (
                payload.get("executionType") in {3, 7}
                and (
                    order.get("orderId") == result["close_order_id"]
                    or order.get("positionId") == position_id
                    or (payload.get("position", {}) or {}).get("positionId") == position_id
                )
            )

        response = _wait_reply(ctrader_client, close_execution_matches)
        if not response:
            return {"status": "error", "details": "Timeout waiting for close execution"}, 504
        payload = response.get("payload", {})
        if payload.get("executionType") == 3 and (payload.get("order", {}) or {}).get("orderStatus") == 2:
            order_data = payload.get("order", {}) or {}
            position_data = payload.get("position", {}) or {}
            result.update({
                "close_order_executed": True,
                "execution_price": order_data.get("executionPrice"),
                "position_id": position_data.get("positionId", position_id),
            })
            logging.info(f"⚡ Order executed at {result['execution_price']}")
        else:
            er_code = payload.get("errorCode", "UNKNOWN ERROR")
            return {"status": "error", "order_id": result["close_order_id"], "error code": er_code}, 500

    except Exception as e:
        error_msg = f"Close Order processing failed: {str(e)}"
        logging.error(f"❌ {error_msg}")
        result["error"] = error_msg
        return {"status": "error", "details": result}, 500


    return {
        "status": "success",
        "details": result
    }, 200


@app_views.route("/ctrader/trader", methods=["GET"])
@token_required
def trader_account():
    """
       This route sends aa standard TCP request for
       Trader's Account data.
    """
    # 1) Ensure we're authenticated
    if not ctrader_client.acc_authorized:
        success, result = ensure_authenticated(ctrader_client)
        if not success:
            return jsonify({"error": result}), 401

    try:
        trader_req = TraderRequest(ctrader_client.acc_authorized_no)
        trader_req = trader_req.as_json_string()
        trader_response = _request_reply(ctrader_client, trader_req, (2122, 2142))
        if trader_response:
            payload_type = trader_response.get("payloadType")
            if payload_type == 2122:
                return jsonify({"status": "success", "data": trader_response})
            if payload_type == 2142:
                desc = trader_response.get("payload", {}).get("description", "Unknown error")
                return jsonify({"status": "error", "details": desc}), 400

        return jsonify({"status": "error", "details": "Timeout waiting for cTrader response"}), 504

    except Exception as e:
            logging.error(f"❌ TCP Request failed: {e}")
            return {"status": "error", "details": str(e)}, 500




@app_views.route("/ctrader/pnl", methods=["GET"])
@token_required
def unrealized_pnl():
    """
       This method fetches current price data from cTraderApi
    """
    # 1) Ensure we're authenticated
    if not ctrader_client.acc_authorized:
        success, result = ensure_authenticated(ctrader_client)
        if not success:
            return jsonify({"error": result}), 401

    try:
        #pnl_req = GetPositionUnrealizedPnLRequest(ctrader_client.debug_account)
        pnl_req = GetPositionUnrealizedPnLRequest(ctrader_client.acc_authorized_no)
        pnl_req = pnl_req.as_json_string()
        pnl_response = _request_reply(ctrader_client, pnl_req, (2188, 2142))
        if pnl_response:
            payload_type = pnl_response.get("payloadType")
            if payload_type == 2188:
                return jsonify({"status": "success", "data": pnl_response})
            if payload_type == 2142:
                desc = pnl_response.get("payload", {}).get("description", "Unknown error")
                return jsonify({"status": "error", "details": desc}), 400

        return jsonify({"status": "error", "details": "Timeout waiting for cTrader response"}), 504

    except Exception as e:
            logging.error(f"❌ TCP Request failed: {e}")
            return {"status": "error", "details": str(e)}, 500



@app_views.route("/ctrader/unsubscribedepth/<int:symbol_id>", methods=["GET"])
#@token_required
def unsubscribe_depth(symbol_id):
    """
       This route cleans up the DOM worker and tells cTrader to stop the stream.
    """
    # 1) Ensure we're authenticated
    if not depth_client.acc_authorized:
        success, result = ensure_authenticated(depth_client)
        if not success:
            return jsonify({"error": result}), 401

    try:
        usd = UnSubscribeDepthRequest(depth_client.acc_authorized_no, symbol_id)
        usd_json = usd.as_json_string()

        # Stop and join current worker before this route reads unsubscribe reply.
        with depth_client.depth_subscription_lock:
            depth_client.is_listening_dom = False
            worker = getattr(depth_client, "depth_worker_thread", None)
            if worker is not None and worker.is_alive() and worker is not threading.current_thread():
                worker.join(timeout=1.0)
            depth_client.depth_worker_thread = None

        with order_book.lock:
            order_book.bids.clear()
            order_book.asks.clear()

        usd_response = _request_reply(depth_client, usd_json, (2159, 2142))
        if usd_response:
            payload_type = usd_response.get("payloadType")
            if payload_type == 2159:
                depth_client.clear_depth_subscription(symbol_id)
                logging.info(f"🛑 Unsubscribed from symbol {symbol_id} and cleaned up worker.")
                return jsonify({"status": "success", "message": "Unsubscribed and worker stopped"}), 200
            if payload_type == 2142:
                desc = usd_response.get("payload", {}).get("description", "Unknown error")
                return jsonify({"status": "error", "details": desc}), 400


    except Exception as e:
        logging.error(f"❌ Unsubscribe failed: {e}")
        return jsonify({"status": "error", "details": str(e)}), 500

@app_views.route("/ctrader/snapshot", methods=["GET"])
def get_snapshot():
    """
    The 'Ferry' route. Returns the processed SMC metrics to the Main Bot.
    """
    # Use a depth of 5 (Standard for SMC) and your 10k unit threshold
    metrics = order_book.snapshot_metrics(depth=5, min_depth_threshold=10000)
    if not metrics:
        return jsonify({
            "status": "error",
            "message": "Order book is empty or not yet synchronized"
        }), 503

    # If the metrics logic caught a negative spread, it will return NO_TRADE
    return jsonify({"status": "success", "metrics": metrics}), 200

@app_views.route("/ctrader/current_price/<int:symbol_id>", methods=["GET"])
def fetch_current_price(symbol_id):
    """
       This method fetches current price data from cTraderApi
    """
    # 1) Ensure we're authenticated
    if not ctrader_client.acc_authorized:
        success, result = ensure_authenticated(ctrader_client)
        if not success:
            return jsonify({"error": result}), 401

    sub_spot = SubscribeSpotRequest(ctrader_client.acc_authorized_no, symbol_id)
    sub_spot = sub_spot.as_json_string()
    #sub_live_tb = SubscribeLiveTrendbarsRequest(ctrader_client.acc_authorized_no, symbol_id, 1)
    #sub_live_tb = sub_live_tb.as_json_string()
    spot_response = _request_reply(ctrader_client, sub_spot, 2131)
    if spot_response and spot_response.get("payloadType") == 2131:
        spot_df = process_spot_event_data(spot_response)
        if spot_df.empty:
            return {"message": "No spot event available."}, 404
        filename = f"{CSV_DIR_SPOT_EVENTS}/spot_price_{symbol_id}_{timestamp_str}.csv"
        spot_df.to_csv(filename, index=False)
        logging.info(f"✅ Spot event saved to CSV: {filename}")
        # 6) Return response with bid and spread
        bid_price = float(spot_df.iloc[0]["bid"])
        spread_pips = int(spot_df.iloc[0]["spread_pips"])
        ctrader_client.close()
        return jsonify({
            "message": "Spot data saved successfully.",
            "symbol_id": symbol_id,
            "bid_price": bid_price,
            "spread_pips": spread_pips
        })

    return {"error": "No valid spot response received."}, 500
