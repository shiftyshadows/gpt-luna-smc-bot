import os
import unittest


for name, value in {
    "JWT_SECRET": "test-secret",
    "MONGO_URI": "mongodb://localhost:27017",
    "CTRADER_CLIENT_ID": "test-client",
    "CTRADER_CLIENT_SECRET": "test-secret",
    "CTRADER_REDIRECT_URI": "http://localhost/callback",
    "CTRADER_TOKEN_URI": "https://example.invalid/token",
    "CTRADER_LIVE_STATUS": "false",
    "BOT_PORT": "8000",
}.items():
    os.environ.setdefault(name, value)

from src.app import app
from src.api.routes.ctrader import ctrader_client
from src.utils.ctrader_tcp_client import CTraderTCPClient
from src.utils.jwt_utils import generate_jwt


class ApiSecurityTest(unittest.TestCase):
    def test_token_endpoint_requires_machine_bearer_token(self):
        response = app.test_client().get("/api/protected")
        self.assertEqual(response.status_code, 401)

    def test_tcp_client_reads_token_from_oauth_manager(self):
        client = CTraderTCPClient()
        client.oauth_manager.get_access_token = lambda: "direct-token"
        self.assertEqual(client.get_access_token(), "direct-token")
        client.oauth_manager.mclient.close()

    def test_trading_routes_reject_non_object_json_bodies(self):
        ctrader_client.acc_authorized = True
        ctrader_client.acc_authorized_no = 1
        headers = {"Authorization": f"Bearer {generate_jwt('bot_1')}"}
        for route in (
            "/api/ctrader/new_order",
            "/api/ctrader/cancel_order",
            "/api/ctrader/amend_position",
            "/api/ctrader/close_position",
        ):
            with self.subTest(route=route):
                response = app.test_client().post(route, json=[], headers=headers)
                self.assertEqual(response.status_code, 400)

    def test_new_order_rejects_unknown_direction(self):
        ctrader_client.acc_authorized = True
        headers = {"Authorization": f"Bearer {generate_jwt('bot_1')}"}
        response = app.test_client().post(
            "/api/ctrader/new_order",
            json={"direction": "HOLD"},
            headers=headers,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "direction must be BUY or SELL")


if __name__ == "__main__":
    unittest.main()
