import json

from src.utils.ctrader_tcp_client import CTraderTCPClient


class ReplyClient(CTraderTCPClient):
    def __init__(self, packets):
        super().__init__()
        self.client = object()
        self.sent = []
        self.packets = iter(packets)

    def send_json(self, message):
        self.sent.append(message)

    def receive_json(self):
        return next(self.packets, None)


def test_request_reply_skips_unrelated_reply_and_preserves_dispatcher_packet():
    seen = []
    request_id = "request-2"
    client = ReplyClient([
        {"payloadType": 2157, "clientMsgId": "strategy-event"},
        {"payloadType": 2115, "clientMsgId": request_id},
    ])
    client.add_message_handler(seen.append)

    response = client.request_reply(
        {"payloadType": 2114, "clientMsgId": request_id},
        timeout=1,
    )

    assert response["payloadType"] == 2115
    assert seen == [{"payloadType": 2157, "clientMsgId": "strategy-event"}]
    assert client.main_queue.get_nowait()["clientMsgId"] == "strategy-event"


def test_request_reply_adds_unique_correlation_id_to_requests_without_one():
    client = ReplyClient([{"payloadType": 2105, "clientMsgId": "generated"}])

    response = client.request_reply(
        json.dumps({"payloadType": 2104}),
        matcher=lambda packet: packet.get("payloadType") == 2105,
        timeout=1,
    )

    assert response["payloadType"] == 2105
    sent = client.sent[0]
    assert sent["payloadType"] == 2104
    assert sent["clientMsgId"]
