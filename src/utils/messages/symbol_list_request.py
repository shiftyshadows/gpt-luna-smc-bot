#!/usr/bin/env python3
"""
This module defines the `SymbolList` class, which represents a message
containing a list of trading symbols in an OpenAPI-based system.

`SymbolList` is a subclass of `OpenAPIMessage` and implements all abstract
methods required for handling message payloads related to trading symbols.
"""

import json
import uuid
from typing import List
from src.utils.open_api_message import OpenAPIMessage


class SymbolListRequest(OpenAPIMessage):
    """
    Represents a message containing a list of trading symbols.

    This class provides functionality to store and retrieve a list of symbols
    within an OpenAPI-based system.
    """

    def __init__(self, ctidTraderAccountId: int, includeArchivedSymbol: bool = False, clientMsgId: str = str(uuid.uuid4())):
        """
        Initializes a `SymbolList` instance.

        Args:
            symbols (List[str]): A list of trading symbols.
            msg_id (str): A unique client message ID.
        """
        self.ctid_trader_account_id = ctidTraderAccountId
        self.include_archived_symbols = includeArchivedSymbol
        self.clientMsgId = clientMsgId
        self.payloadType = 2114

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
            "includeArchivedSymbols": self.include_archived_symbols
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
