#!/usr/bin/env python3
from functools import wraps
from flask import request, jsonify
from src.utils.jwt_utils import decode_jwt


def _extract_bearer_token(authorization: str) -> str | None:
    """Return the token from a valid two-part Bearer header."""
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1]


def token_required(f):
    """
       This decorator to protect Flask routes using JWT Bearer authentication.

       Expects:
         - An 'Authorization' header in the format: 'Bearer <JWT_TOKEN>'

       Modifies:
         - Attaches the 'sub' (machine_id) from the token payload to
           'request.machine'.

       Raises:
         - 401 Unauthorized: If the token is missing, invalid, or expired.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        token = _extract_bearer_token(auth)
        if token is None:
            return jsonify({"message": "Missing or invalid token"}), 401

        payload = decode_jwt(token)
        if not payload:
            return jsonify({"message": "Invalid or expired token"}), 401

        request.machine = payload["sub"]
        return f(*args, **kwargs)
    return decorated
