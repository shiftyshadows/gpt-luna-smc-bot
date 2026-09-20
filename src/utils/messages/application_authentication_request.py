#!/usr/bin/env python3
"""
   This module defines the class: Application Authentication Request
   that normalizes the json output for the ctrader json message request
   for application authentication.
"""

import json
import uuid
from typing import List
from src.utils.open_api_message import OpenAPIMessage
from os import getenv
from dotenv import load_dotenv

load_dotenv()

class ApplicationAuthRequest(OpenAPIMessage):
    """
       This class represents a current price for a given symbol.
    """
    def __init__(self, clientMsgId: str = str(uuid.uuid4())):
        """
           Initializes a `AssetClassList` instance.
        """

        self.payloadType = 2100
        self.client_id = str(getenv("CTRADER_CLIENT_ID"))
        self.client_secret = str(getenv("CTRADER_CLIENT_SECRET"))
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
            "clientId": self.client_id,
            "clientSecret": self.client_secret,
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
