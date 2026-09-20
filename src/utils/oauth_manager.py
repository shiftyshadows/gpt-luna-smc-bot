#!/usr/bin/env python3
"""
   This module defines the class: OAuthManager.
"""
import logging
import requests
from os import getenv
from time import time
from pymongo import MongoClient
from dotenv import load_dotenv
from ctrader_open_api import Auth

# ✅ Load environment variables
load_dotenv()

# ✅ Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class OAuthManager:
    """
       This class defines OAuth 2.0 Manager for cTrader API.

       Features:
       - Handles OAuth2 authorization flow.
       - Stores access & refresh tokens in MongoDB.
       - Automatically refreshes access tokens when needed.
    """

    def __init__(self):
        """
           This class method initializes OAuthManager by loading credentials
           and connecting to MongoDB.
        """
        # ✅ Load API credentials
        self.client_id = getenv("CTRADER_CLIENT_ID")
        self.client_secret = getenv("CTRADER_CLIENT_SECRET")
        self.redirect_uri = getenv("CTRADER_REDIRECT_URI")
        self.token_uri = getenv("CTRADER_TOKEN_URI")
        self.mongo_uri = getenv("MONGO_URI")
        self.auth_uri = Auth(self.client_id, self.client_secret, self.redirect_uri).getAuthUri()

        # ✅ Validate credentials
        if not all([self.client_id, self.client_secret, self.redirect_uri, self.token_uri, self.mongo_uri]):
            raise ValueError("❌ Missing environment variables. Check `.env` file.")

        # ✅ Connect to MongoDB
        self.mclient = MongoClient(self.mongo_uri)
        self.db = self.mclient["ctrader_db"]
        self.tokens_collection = self.db["tokens"]

    def get_auth_url(self):
        """
           This class method generates the OAuth2 authorization URL.

           Returns:
             -str: The URL for user authorization.
        """
        return self.auth_uri

    def exchange_code_for_token(self, auth_code):
        """
           This class method exchanges an authorization code for an access token.

           Args:
             -auth_code (str): The authorization code received from cTrader.

           Returns:
             -dict: Response containing tokens or error message.
        """
        try:
            token_data = {
                "grant_type": "authorization_code",
                "code": auth_code,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": self.redirect_uri,
            }
            response = requests.post(self.token_uri, data=token_data)
            response.raise_for_status()

            token_response = response.json()
            # logging.info(f"tok_response : {token_response}")

            self.save_tokens(
                token_response.get("access_token"),
                token_response.get("refresh_token"),
                token_response.get("expires_in", 3600)
                # token_response.get("expires_ins", 10)
            )
            logging.info("🔄 Token Exchange Successful. ")
            return {"message": "OAuth tokens stored successfully."}

        except requests.exceptions.RequestException as e:
            logging.error(f"❌ OAuth token exchange failed: {e}")
            return {"error": f"OAuth token exchange failed: {str(e)}"}

    def get_access_token(self):
        """
           This class method retrieves a valid access token from MongoDB.
           If the token is expired or close to expiration (5 min left),
           it refreshes it.

           Args:
             -None.

           Returns:
             -str: The valid access token.
        """
        token_data = self.tokens_collection.find_one()

        if not token_data:
            logging.error("❌ No token found. User must log into ctrader.")
            raise ValueError("No access token found. Please authenticate application first.")

        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_at = token_data.get("expires_at", 0)

        # ✅ Refresh if token expires within 5 minutes
        if time() >= (expires_at - 300):
            logging.info("🔄 Access token expires soon. Refreshing now...")
            return self.refresh_access_token(refresh_token)

        logging.info("✅ Access token fetched successfully.")
        return access_token

    def refresh_access_token(self, refresh_token):
        """
           This class method refreshes an expired or near-expired access token.

           Args:
             -refresh_token (str): The refresh token.

           Returns:
             -str: The new access token.
        """
        try:
            refresh_data = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }
            response = requests.post(self.token_uri, data=refresh_data)
            response.raise_for_status()

            new_token_response = response.json()
            # logging.info(f"new_tok_response : {new_token_response}")

            new_access_token = new_token_response.get("access_token")
            new_refresh_token = new_token_response.get("refresh_token", refresh_token)
            new_expires_at = time() + new_token_response.get("expires_in", 3600)
            # new_expires_at = time() + new_token_response.get("expires_ins", 10)

            # ✅ Update token in MongoDB
            self.tokens_collection.update_one({}, {"$set": {
                "access_token": new_access_token,
                "refresh_token": new_refresh_token,
                "expires_at": new_expires_at
            }})

            logging.info("✅ Access token refreshed successfully.")
            return new_access_token

        except requests.exceptions.RequestException as e:
            logging.error(f"❌ Failed to refresh access token: {e}")
            raise ValueError(f"Failed to refresh token: {str(e)}")

    def save_tokens(self, access_token, refresh_token, expires_in):
        """
           This class method saves access & refresh tokens in MongoDB.

           Args:
             -access_token (str): The OAuth access token.
             -refresh_token (str): The OAuth refresh token.
             -expires_in (int): Token expiration time in seconds.

           Returns:
             -None.
        """
        expires_at = time() + expires_in
        self.tokens_collection.update_one({}, {"$set": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at
        }}, upsert=True)

        logging.info("✅ Tokens stored successfully.")

    def clear_tokens(self):
        """
           This class method clears all stored tokens.
           (for logout or reauthentication).

           Args:
             -None.

           Returns:
             -None.
        """
        self.tokens_collection.delete_many({})
        logging.info("✅ Tokens cleared successfully.")
