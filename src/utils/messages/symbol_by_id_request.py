#!/usr/bin/env python3
"""
   This module defines the class: SymbolByIdRequest that normalizes
   the json output for the ctrader json message request for details
   for a specified symbol.
"""

import json
import uuid
from typing import List
from src.utils.open_api_message import OpenAPIMessage

class SymbolByIdRequest(OpenAPIMessage):
    """
       This class represents a current price for a given symbol.
    """
    def __init__(self, ctidTraderAccountId: int, symbolId: int, clientMsgId: str = str(uuid.uuid4())):
        """
           Initializes a `AssetClassList` instance.
        """

        self.payloadType = 2116
        self.ctid_trader_account_id = ctidTraderAccountId
        self.symbol_id = symbolId
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
            dict: A dictionary containing the trader account ID
            and the archive filter flag.
        """
        return {
            "ctidTraderAccountId": self.ctid_trader_account_id,
            "symbolId": self.symbol_id
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
