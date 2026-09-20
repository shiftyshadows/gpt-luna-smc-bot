#!/usr/bin/env python3
"""
   This module defines OAuth2 Authentication Flask Routes for cTrader API.
"""
from flask import request, jsonify, redirect
from src.utils.oauth_manager import OAuthManager
from src.views import app_views

# ✅ Initialize OAuth Manager
oauth_manager = OAuthManager()


@app_views.route("/oauth", strict_slashes=False)
def start_oauth():
    """
       This flask route redirects the user to cTrader's OAuth2 authorization
       page.

       Returns:
         -Response: Redirects to cTrader OAuth2 login page.
    """
    return redirect(oauth_manager.get_auth_url())


@app_views.route("/callback", strict_slashes=False)
def oauth_callback():
    """
       This flask route handles OAuth2 callback after user authorization. After
       successful login, cTrader redirects the user back to this endpoint with
       an authorization code if authorized. This function:
         - Extracts the authorization code from the request.
         - Exchanges the code for access and refresh tokens.
         - Stores tokens securely in MongoDB.

       Returns:
         - JSON: Success message if token exchange succeeds.
         - JSON: Error message if authorization code is missing.
    """
    auth_code = request.args.get("code")
    if not auth_code:
        return jsonify({"error": "Authorization code missing."}), 400

    return jsonify(oauth_manager.exchange_code_for_token(auth_code))


def get_valid_token():
    """
       This function retrieves a valid access token from MongoDB and
       refreshes it if necessary.

       Returns:
         -JSON: A valid access token.
         -JSON: Error message if token retrieval or refresh fails.
    """
    try:
        access_token = oauth_manager.get_access_token()
        if not access_token:
            return jsonify({"error": "No token found in database"}), 404
        return jsonify({"access_token": access_token})

    except ValueError as e:
        return jsonify({"error": f"Invalid token data: {str(e)}"}), 401

    except ConnectionError as e:
        return jsonify({"error": f"Database Error: {str(e)}"}), 503

    except Exception as e:
        return jsonify({f"error": f"Unexpected Error: {str(e)}"}), 500
