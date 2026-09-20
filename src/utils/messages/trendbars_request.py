"""ProtoOAGetTrendbarsReq (payload type 2114)."""

from __future__ import annotations

import uuid
from typing import Optional

from src.utils.open_api_message import OpenAPIMessage


class TrendbarsRequest(OpenAPIMessage):
    """Request historical trendbars for a symbol and period."""

    payloadType = 2114

    def __init__(
        self,
        ctidTraderAccountId: int,
        symbolId: int,
        period: int = 5,
        from_timestamp: Optional[int] = None,
        to_timestamp: Optional[int] = None,
        count: Optional[int] = None,
        clientMsgId: Optional[str] = None,
    ) -> None:
        self.ctid_trader_account_id = int(ctidTraderAccountId)
        self.symbol_id = int(symbolId)
        self.period = int(period)
        self.from_timestamp = from_timestamp
        self.to_timestamp = to_timestamp
        self.count = count
        self.clientMsgId = clientMsgId or str(uuid.uuid4())

    def client_msg_id(self) -> str:
        return self.clientMsgId

    def payload_type(self) -> int:
        return self.payloadType

    def payload(self) -> dict:
        payload = {
            "ctidTraderAccountId": self.ctid_trader_account_id,
            "symbolId": self.symbol_id,
            "period": self.period,
        }
        if self.from_timestamp is not None:
            payload["fromTimestamp"] = int(self.from_timestamp)
        if self.to_timestamp is not None:
            payload["toTimestamp"] = int(self.to_timestamp)
        if self.count is not None:
            payload["count"] = int(self.count)
        return payload

    def as_json_string(self) -> dict:
        return {
            "clientMsgId": self.clientMsgId,
            "payloadType": self.payloadType,
            "payload": self.payload(),
        }
