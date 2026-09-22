import unittest

from src.utils.jwt_auth import _extract_bearer_token


class JwtAuthHeaderTest(unittest.TestCase):
    def test_extracts_only_well_formed_bearer_headers(self):
        self.assertEqual(_extract_bearer_token("Bearer token-value"), "token-value")
        self.assertEqual(_extract_bearer_token("bearer token-value"), "token-value")

        for header in ("", "Bearer", "Bearer ", "Bearer one two", "Basic token"):
            with self.subTest(header=header):
                self.assertIsNone(_extract_bearer_token(header))


if __name__ == "__main__":
    unittest.main()
