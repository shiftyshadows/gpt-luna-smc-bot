#!/usr/bin/env python3
"""
   This module defines the class: NewOrderRequest that normalizes
   the json output for the ctrader json message request for making
   new orders.
"""

import json
import uuid
from typing import List
from src.utils.open_api_message import OpenAPIMessage
from datetime import datetime, timedelta


class NewOrderRequest(OpenAPIMessage):
    """
       This class defines the message structure for making API
       calls to the cTrader OpenAPI backend that post new orders
       for a given symbol.
    """
    def __init__(self,
                 ctidTraderAccountId: int,
                 symbolId: int,
                 tradeSide: int,
                 volume: int = 100000,
                 orderType: int = 1,
                 positionId: int = None,
                 limitPrice: int = None,
                 stopPrice: int = None,
                 timeInForce: int = 2,
                 expirationTimestamp: int = 120,
                 stopLoss: float = 0.1,
                 takeProfit: float = 1.0,
                 orderComment: str = None,
                 label: str = None,
                 clientOrderId: str = None,
                 relativeStopLoss: int = None,
                 relativeTakeProfit: int = None,
                 trailingStopLoss: bool = None,
                 guaranteedStopLoss: bool = False,
                 stopTriggerMethod: int = None,
                 clientMsgId: str = str(uuid.uuid4())
                 ):
        """
           This method initializes a `NeworderRequest` instance.

           Args:
               - None

           Returns:
               - (class object): Class object representing Instance.
        """

        self.payloadType = 2106
        self.ctid_trader_account_id = ctidTraderAccountId
        self.symbol_id = symbolId
        self.order_type = orderType
        self.trade_side = tradeSide
        self.order_volume = volume

        self.time_in_force = 1 if orderType == 2 else timeInForce
        self.limit_price = limitPrice if orderType == 2 else None
        self.stop_price = stopPrice if orderType == 3 else None

        self.expiration_timestamp = int(
            (datetime.now() + timedelta(
                minutes=expirationTimestamp)).timestamp() * 1000
        ) if self.time_in_force == 1 else None

        self.stop_loss = stopLoss if orderType != 1 else None
        self.take_profit = takeProfit if orderType != 1 else None

        self.order_comment = orderComment
        self.base_slippage_price = None
        self.slippage_in_points = None
        self.order_label = label
        self.client_order_id = clientOrderId
        self.relative_stop_loss = relativeStopLoss
        self.relative_take_profit = relativeTakeProfit
        self.guaranteed_stop_loss = guaranteedStopLoss
        self.trailing_stop_loss = trailingStopLoss if orderType == 1 else None
        self.stop_trigger_method = stopTriggerMethod
        self.clientMsgId = clientMsgId

    def client_msg_id(self) -> str:
        """
           This method returns the client message id.

           Args:
               - None

           Returns:
               - (str): String representing client message id.
        """
        return self.clientMsgId

    def payload_type(self) -> int:
        """
           This method returns an integer representing the payload type.

           Args:
               - None

           Returns:
               - (int): Integer representing cTrader OpenAPI payload code.
        """
        return self.payloadType

    def payload(self) -> dict:
        """
           This method returns a dictionary containing items relevant to the
           of the request message.

           Args:
               - None

           Returns:
               - (dict): A dictionary containing message items.
        """
        return {
            "ctidTraderAccountId": self.ctid_trader_account_id,
            "symbolId": self.symbol_id,
            "orderType": self.order_type,
            "tradeSide": self.trade_side,
            "volume": self.order_volume,
            "limitPrice": self.limit_price,
            "stopPrice": self.stop_price,
            "timeInForce": self.time_in_force,
            "expirationTimestamp": self.expiration_timestamp,
            "stopLoss": self.stop_loss,
            "takeProfit":  self.take_profit,
            "comment": self.order_comment,
            "baseSlippagePrice": self.base_slippage_price,
            "slippageInPoints": self.slippage_in_points,
            "label": self.order_label,
            "clientOrderId": self.client_order_id,
            "relativeStopLoss": self.relative_stop_loss,
            "relativeTakeProfit": self.relative_take_profit,
            "guaranteedStopLoss": self.guaranteed_stop_loss,
            "trailingStopLoss": self.trailing_stop_loss,
            "stopTriggerMethod": self.stop_trigger_method
        }

    def as_json_string(self) -> str:
        """
           This method returns a dictionary that can be encoded
           as a JSON string.

           Args:
               - None

           Returns:
               - sl_payload (dict): Dictionary encoding the entire
                 message structure that can be encoded into a JSON string.
        """
        sl_payload = {
            "clientMsgId": self.clientMsgId,
            "payloadType": self.payloadType,
            "payload": self.payload()
        }
        return sl_payload
