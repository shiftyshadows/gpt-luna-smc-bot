#!/usr/bin/env python3
"""
   This module defines the class: AmendPositionSLTPRequest
   that normalizes the json output for the ctrader json message request
   for amending StopLoss and TakeProfit of existing position..
"""

import json
import uuid
from typing import List
from src.utils.open_api_message import OpenAPIMessage


class AmendPositionSLTPRequest(OpenAPIMessage):
    """
       This class represents a current price for a given symbol.
    """
    def __init__(self,
        ctidTraderAccountId: int,
        positionId: int,
        stopLoss: float,
        takeProfit: float,
        guaranteedStopLoss: bool = False,
        trailingStopLoss: bool = False,
        stopLossTriggerMethod: int = 1,
        clientMsgId: str = str(uuid.uuid4())):
        """
           Initializes a `AssetClassList` instance.
        """

        self.payloadType = 2110
        self.ctid_trader_account_id = ctidTraderAccountId
        self.position_id = positionId
        self.stop_loss = stopLoss
        self.take_profit = takeProfit
        self.guaranteed_stop_loss = guaranteedStopLoss
        self.trailing_stop_loss = trailingStopLoss
        self.stop_loss_trigger_method =stopLossTriggerMethod
        self.clientMsgId = clientMsgId

    def client_msg_id(self) -> str:
        """
           Returns the client message id.
        """
        return self.clientMsgId

    def payload_type(self) -> int:
        """
        Returns the type of the payload.

        Returns:
            int: Predetermined integer
        """
        return self.payloadType

    def payload(self) -> dict:
        """
        Returns the actual payload of the request message.

        Returns:
            dict: A dictionary containing the required parameters.
        """
        return {
            "ctidTraderAccountId": self.ctid_trader_account_id,
            "positionId": self.position_id,
            "stopLoss": self.stop_loss,
            "takeProfit": self.take_profit,
            "guaranteedStopLoss": self.guaranteed_stop_loss,
            "trailingStopLoss": self.trailing_stop_loss,
            "stopLossTriggerMethod": self.stop_loss_trigger_method
        }

    def as_json_string(self) -> str:
        """
        Returns the message as a JSON string.
        Returns:
            str: A JSON-encoded string representation of the message.
        """
        sl_payload = {
            "clientMsgId": self.clientMsgId,
            "payloadType": self.payloadType,
            "payload": self.payload()
        }
        return sl_payload
