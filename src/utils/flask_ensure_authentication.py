#!/usr/bin/env python3
"""
   This module defines the function: ensure_authenticated.
"""
import time
import logging
from dotenv import load_dotenv
from os import getenv

load_dotenv()

def ensure_authenticated(ct_client, max_retries: int = 10, delay: int = 1):
    """
       This function defines the logic for application and
       account authorization.

       Args:
          -ct_client: class_instance of cTrader openAPI client.

       Return:
          -bool: Representing success or error.
          -str: Representing result
    """
    # 1. Connect + App Authentication
    app_success = False
    for attempt in range(max_retries):
        try:
            if not ct_client.is_connected():
                ct_client.close()        # ✅ clean up before reconnecting
                ct_client.connect()
            app_success = ct_client.authenticate()
            if app_success:
                break
        except Exception as e:
            logging.error(f"❌ App auth attempt {attempt + 1} failed: {e}")
        logging.info(f"⏳ Retrying in {delay}s... ({attempt + 1}/{max_retries})")
        time.sleep(delay)               # ✅ delay between retries

    if not app_success:
        ct_client.close()
        return False, "Application Authentication Failed, Max Retries."

    # 2. Get Account
    try:
        account = getenv("CTRADER_ACCOUNT_ID")
        account = int(account) if account else ct_client.get_accounts()
    except Exception as e:
        ct_client.close()
        return False, f"Failed to get account: {e}"

    # 3. Account Authorization
    account_success = False
    for attempt in range(max_retries):
        try:
            account_success = ct_client.account_authorization(account)
            if account_success:
                return True, account
        except Exception as e:
            logging.error(f"❌ Account auth attempt {attempt + 1} failed: {e}")
        logging.info(f"⏳ Retrying in {delay}s... ({attempt + 1}/{max_retries})")
        time.sleep(delay)               # ✅ delay between retries

    ct_client.close()
    return False, "Account Authorization Failed, Max Retries."
