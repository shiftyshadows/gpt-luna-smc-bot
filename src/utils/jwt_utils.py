#!/usr/bin/env python3
"""
   This module defines functions: generate_jwt and decode_jwt
   relevant for JSON web token utility.
"""

import jwt
import secrets
from datetime import datetime, timedelta, timezone
from os import getenv
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = getenv("JWT_SECRET")
if not SECRET_KEY:
    raise RuntimeError("JWT_SECRET is not set in the environment variables.")

ALGORITHM = "HS256"


def generate_jwt(machine_id: str, exp_minutes=60):
    """
       Generates a signed JWT token for a given machine identity.

       Args:
           -machine_id (str): The identifier for the authenticating machine.
           -exp_minutes (int): Expiration time in minutes (default is 60).

       Returns:
           -str: A JWT as a string, signed with the configured secret key.
    """
    payload = {
        # "machine": machine_id,
        "sub": machine_id,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=exp_minutes)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_jwt(token: str):
    """
       Decodes a JWT and verifies its signature and expiration.

       Args:
           -token (str): The JWT string to decode and verify.

       Returns:
           -dict: The decoded payload if the token is valid.
           -None: If the token is expired or invalid.
    """
    try:
        decoded = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return decoded
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
