#!/usr/bin/env python3
"""
This module defines the `TickDataRequest` class, which represents a message
containing a list of trading symbols in an OpenAPI-based system.

`TickDataRequest` is a subclass of `OpenAPIMessage` and implements all abstract
methods required for handling message payloads related to tick data retrieval.
"""

import uuid
from src.utils.open_api_message import OpenAPIMessage
from dotenv import load_dotenv
from os import getenv

load_dotenv()


class HistoricalDataRequest(OpenAPIMessage):
    """
    Represents a request for tick data.

    Mandatory payload fields:
      - ctidTraderAccountId
      - symbolId
      - type=1

    Optional payload fields:
      - fromTimestamp (milliseconds)
      - toTimestamp (milliseconds)
    """

    def __init__(
        self,
        ctidTraderAccountId: int = None,
        from_timeStamp: int = None,
        to_timeStamp: int = None,
        barPeriod: int = 1,
        symbolId: int = 1,
        clientMsgId: str = None,
    ):
        """
        Initializes a `HistoricalDataRequest` instance.

        Args:
            ctidTraderAccountId (int): The cTrader trader account ID.
            symbolId (int): The symbol ID for which tick data is requested.
            from_timestamp (int, optional): The earliest timestamp (ms) to fetch from.
            to_timestamp (int, optional): The latest timestamp (ms) to fetch until.
            clientMsgId (str, optional): A unique client message ID (default: generated UUID).
        """
        self.payloadType = 2137
        if ctidTraderAccountId:
            self.ctid_trader_account_id = ctidTraderAccountId
        else:
            self.ctid_trader_account_id = getenv("CTRADER_ACCOUNT_ID")
        self.from_timestamp = from_timeStamp
        self.to_timestamp = to_timeStamp
        self.period = barPeriod
        self.symbol_id = symbolId
        self.clientmsg_id = clientMsgId if clientMsgId else str(uuid.uuid4())


    def client_msg_id(self) -> str:
        """
        Returns the client message ID.
        """
        return self.clientmsg_id

    def payload_type(self) -> int:
        """
        Returns the type of the payload (ProtoOATickDataReq).

        Returns:
            int: The integer indicating the payload type.
        """
        return self.payloadType

    def payload(self) -> dict:
        """
        Returns the actual payload of the request message.

        Returns:
            dict: A dictionary with mandatory and optional fields for tick data requests.
        """
        pl = {
            "ctidTraderAccountId": self.ctid_trader_account_id,
            "period": self.period,
            "symbolId": self.symbol_id,
        }

        if self.from_timestamp is not None:
            pl["fromTimestamp"] = int(self.from_timestamp)

        if self.to_timestamp is not None:
            pl["toTimestamp"] = int(self.to_timestamp)

        return pl

    def as_json_string(self) -> dict:
        """
        Returns the message as a Python dict or JSON-like structure.

        (If needed as actual JSON, you can serialize with `json.dumps` yourself.)

        Returns:
            dict: The complete request payload, including clientMsgId and payloadType.
        """
        request_payload = {
            "payloadType": self.payloadType,
            "payload": self.payload(),
            "clientMsgId": self.clientmsg_id,
      }
        return request_payload
