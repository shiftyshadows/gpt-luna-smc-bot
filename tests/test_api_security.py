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
from src.utils.ctrader_tcp_client import CTraderTCPClient


class ApiSecurityTest(unittest.TestCase):
    def test_token_endpoint_requires_machine_bearer_token(self):
        response = app.test_client().get("/api/protected")
        self.assertEqual(response.status_code, 401)

    def test_tcp_client_reads_token_from_oauth_manager(self):
        client = CTraderTCPClient()
        client.oauth_manager.get_access_token = lambda: "direct-token"
        self.assertEqual(client.get_access_token(), "direct-token")
        client.oauth_manager.mclient.close()


if __name__ == "__main__":
    unittest.main()
