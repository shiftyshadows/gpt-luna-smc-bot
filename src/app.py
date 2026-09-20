#!/usr/bin/env python3
"""
   Flask Application Entry Point

   This module initializes the Flask application, database connection, and
   background tasks. Blueprint registration is handled in `src/__init__.py`.
"""

from dotenv import load_dotenv
from os import getenv, path
from flask import Flask, jsonify, send_from_directory, request
from src.database import init_db
from src.api.routes.Oauth import get_valid_token
from src.utils.jwt_utils import generate_jwt, decode_jwt
from src.utils.jwt_auth import token_required
import src  # ✅ Ensures `app_views` is registered

# ✅ Load environment variables
load_dotenv()

# ✅ Initialize Flask app
app = Flask(__name__)

# 🔐 Simulated credential store
MACHINE_CREDENTIALS = {"bot_1": getenv("BOT_PASSWORD")}

# ✅ Secure Flask session cookies
app.config["SESSION_COOKIE_HTTPONLY"] = True  # Prevent JavaScript access
app.config["SESSION_COOKIE_SECURE"] = True    # Only send over HTTPS
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"  # Prevent cross-site leaks

# ✅ Initialize MongoDB
init_db(app)

# ✅ Import `src` to ensure blueprints are registered
# import src  # ✅ Ensures `app_views` is registered

# ✅ Example Usage Inside Other Routes
# Issue a token


@app.route('/api/jwtauth', methods=['POST'])
def get_token():
    """
       This flask route authenticates a trading machine
       and issues a JWT.

       Expected JSON Body:
         {
             "machine_id": "string",
             "password": "string"
         }

       Returns:
         - JSON: { "jwt_access_token": "...", "expires_at": 177... }
         - Status Codes: 200 (Success), 401 (Unauthorized), 400 (Bad Request)
    """
    # 1. Ensure we actually got JSON
    data = request.get_json()
    if not data:
        return jsonify({"error": "Content-Type must be application/json"}), 415

    try:
        machine_id = str(data.get("machine_id", ""))
        mach_password = str(data.get("password", ""))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid data types"}), 400

    # 2. Check Credentials
    if machine_id in MACHINE_CREDENTIALS and MACHINE_CREDENTIALS[machine_id] == mach_password:
        token = generate_jwt(machine_id, 30)
        return jsonify({"jwt_access_token": token})
    return jsonify({"message": "Invalid credentials"}), 401


@app.route("/api/protected", methods=["GET"])
#@token_required
def protected_resource():
    """
    Example API endpoint that requires a valid access token.
    """

    # 1. Get the raw result (could be a Response object OR a tuple)
    access_result = get_valid_token()

    # 2. If result is a tuple (e.g., (Response, 401)), return it immediately to the client
    if isinstance(access_result, tuple):
        return access_result

    # 3. Now it's safe to call .get_json() because we know it's a single Response object
    token_data = access_result.get_json()

    # 4. Final safety check: if the JSON contains an error key
    if "error" in token_data:
        return jsonify(token_data), 401

    access_token = token_data["access_token"]
    return jsonify({"message": "Success", "token": access_token})


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(path.join(
        app.root_path, 'static'), 'favicon.ico', mimetype='image/vnd.microsoft.icon')


if __name__ == "__main__":
    """
    Runs the Flask application.

    - Starts the development server on port 8000.
    - Enables debugging for easier troubleshooting.
    - The application is accessible at http://127.0.0.1:8000.
    """
    logging.info("🚀 Starting Flask Application...")
    app.run(host='0.0.0.0', port=8000, debug=True)
