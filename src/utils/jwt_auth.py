#!/usr/bin/env python3
from functools import wraps
from flask import request, jsonify
from src.utils.jwt_utils import decode_jwt


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
        token = None
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"message": "Missing or invalid token"}), 401

        token = auth.split(" ")[1]
        payload = decode_jwt(token)
        if not payload:
            return jsonify({"message": "Invalid or expired token"}), 401

        request.machine = payload["sub"]
        return f(*args, **kwargs)
    return decorated
