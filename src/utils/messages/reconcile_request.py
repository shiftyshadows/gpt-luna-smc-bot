#!/usr/bin/env python3
"""
   This module defines the class: ReconcileRequest
   that normalizes the json output for the ctrader json message request
   for for getting Trader's current open positions and pending orders data.
"""

import json
import uuid
from typing import List
from src.utils.open_api_message import OpenAPIMessage


class ReconcileRequest(OpenAPIMessage):
    """
       This class represents a current price for a given symbol.
    """
    def __init__(self, ctidTraderAccountId: int, returnProtectionOrders: bool = False, clientMsgId: str = str(uuid.uuid4())):
        """
           Initializes a `ReconcileRequest` instance.
        """

        self.payloadType = 2124
        self.ctid_trader_account_id = ctidTraderAccountId
        self.return_protection_orders = returnProtectionOrders
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
            "returnProtectionOrders": self.return_protection_orders
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
