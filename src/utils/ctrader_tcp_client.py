#!/usr/bin/env python3
"""
   This module defines the class: CTraderTCPClient.
"""
import uuid
import socket
import ssl
import json
import time
import logging
import requests
import struct
from os import getenv
from time import sleep, time
from queue import Full, Queue
from threading import Thread, Event, RLock
from src.utils.oauth_manager import OAuthManager
from src.utils.messages.application_authentication_request import ApplicationAuthRequest
from src.utils.messages.account_authentication_request import AccountAuthRequest
from src.utils.messages.account_list_request import AccountListRequest
from src.utils.messages.heartbeat_event  import HeartBeatEventRequest

# ✅ Configure Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class CTraderTCPClient:
    """
       This class is the cTrader TCP Client for Real-time Communication.

       Features:
         - Establishes a secure SSL TCP connection.
         - Authenticates using OAuth2 access token.
         - Sends and receives JSON messages.
         - Maintains connection with heartbeat.
    """

    def __init__(self, port: int = 5036, live_account: bool = False):
        """
           This class method initializes the cTrader TCP client.

           Args:
             -port (int): The cTrader TCP port for JSON over TCP.
             -live_account (boolean): Denotes whether to use live/demo server.
        """
        self.host = "live.ctraderapi.com" if live_account else "demo.ctraderapi.com"
        self.port = port
        self.is_account_live = live_account
        self.oauth_manager = OAuthManager()
        self.raw_socket = None
        self.ssl_context = ssl.create_default_context()
        self.client = None
        self.is_authorized = False
        self.acc_authorized = False
        self.is_listening_dom = False
        self.debug_account = 42542468
        self.acc_authorized_no = None
        self.heartbeat_thread = None
        self._heartbeat_stop = Event()
        self.socket_lock = RLock() # 🔒 The "Talking Stick"
        self.main_queue = Queue(maxsize=100)
        self.depth_queue = Queue(maxsize=2000)
        # Consumers such as the SMC strategy can observe packets without
        # opening a second competing socket reader. The main queue remains
        # populated for existing route consumers.
        self.message_handlers = []

        self.access_token = None
        self._recv_buffer = b""
        self._dispatch_buffer = ""

    def connect(self):
        """
           This class method establishes a secure SSL TCP connection to cTrader.

           Args:
             -None

           Returns:
             -None
        """
        try:
            # 1. Create a raw TCP socket
            self.raw_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

            # 2. Enable TCP Keep-Alive
            self.raw_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

            # 3. Connect the raw socket to the server
            self.raw_socket.connect((self.host, self.port))

            # 4. Wrap the socket with SSL
            self.client = self.ssl_context.wrap_socket(
                self.raw_socket,
                server_hostname=self.host
            )

            # 5. Set a reasonable timeout for socket operations
            self.client.settimeout(30)

            logging.info(f"✅ Successfully connected via SSL/TLS: {self.host}.")

        except Exception as e:
            logging.error(f"❌ Connection error: {e}")
            self.close()
            raise

    def is_connected(self) -> bool:
        try:
            if self.client is None:
                return False
            self.client.getpeername()
            return True
        except OSError:
            return False

    def send_json(self, message: dict):
        """
           This class method sends a JSON-formatted message
           over the TCP connection. Thread safety enforced
           Args:
             - message (dict): The JSON request.

           Returns:
             - None.
        """
        if not self.client:
            logging.error("⚠️  No active connection. Please connect first.")
            return

        try:
            json_text = json.dumps(message, separators=(",", ":"))
            data = json_text.encode("utf-8") + b"\n"

            with self.socket_lock:
                self.client.sendall(data)
                logging.debug(f"📤 Sending message: {message}")
                #logging.info(f"📤 Sending message: {message}")

        except Exception as e:
            logging.error(f"❌ Send error: {e}")
            self.close()

    def receive_json(self):
        """
           This class method receives a JSON response from cTrader API.

           Args:
             - None.

           Returns:
             - dict: The decoded JSON response.
        """
        if not self.client:
            logging.error("⚠️  No active connection. Please connect first.")
            return None

        decoder = json.JSONDecoder()

        try:
            while True:
                with self.socket_lock: # Protect the buffer access
                    if self._recv_buffer:
                        try:
                            text = self._recv_buffer.decode("utf-8")
                            obj, idx = decoder.raw_decode(text)

                            remaining = text[idx:].lstrip()
                            self._recv_buffer = remaining.encode("utf-8")

                            logging.debug(f"📥 Received: {obj}")
                            #logging.info(f"📥 Received: {obj}")
                            return obj

                        except json.JSONDecodeError:
                            pass

                with self.socket_lock: # Protect the buffer access
                    chunk = self.client.recv(8192)

                if not chunk:
                    logging.error("🔌 Connection closed by server.")
                    self.close()
                    return None

                with self.socket_lock:
                    logging.debug(f"📥 Raw chunk: {chunk!r}")
                    self._recv_buffer += chunk

        except Exception as e:
            logging.error(f"❌ Receive error: {e}")
            self.close()
            return None

    def authenticate(self):
        """
           This class method authenticates the client using the access token retrieved
           from `/api/protected`.

           Args:
             - None

           Returns:
             - boolean: True if authenticated, otherwise false
        """
        if not self.client:
            logging.error("⚠️  No active connection. Connect first.")
            return False

        try:
            if self.is_authorized:
                return True
            app_auth = ApplicationAuthRequest()
            app_auth_json = app_auth.as_json_string()
            self.send_json(app_auth_json)
            # Wait for response
            for _ in range(10):
                response = self.receive_json()
                if response.get("payloadType") == int(2101):
                    self.is_authorized = True
                    logging.info("✅ Successfully authenticated with cTrader Open API.")
                    self._start_heartbeat()
                    return True
                elif response.get("payloadType") == int(2142):
                    desc = response.get("payload", {}).get("description", "")
                    #logging.error(f"❌ {response.get('payload', {})}")
                    logging.error(f"❌ Authentication failed: {desc}")
                    return False
            logging.error(f"❌ Authentication failed: Max Retries")
            self.close()

        except Exception as e:
            logging.error(f"❌ Authentication error: {e}")
            self.close()
            return False

    def get_access_token(self):
        """
        Retrieves the access token from `/api/protected`.

        Returns:
            str: The valid access token, or None if retrieval fails.
        """
        try:
            response = requests.get("http://localhost:8000/api/protected", timeout=10)
            response_data = response.json()

            if "error" in response_data:
                return None

            return response_data["token"]

        except requests.exceptions.RequestException as e:
            logging.error(f"❌ Error retrieving access token: {e}")
            return None

    def get_accounts(self):
        """
           This class method
        """
        if not self.client:
            logging.error("⚠️ No active connection. Connect first.")
            return
        if self.is_authorized:
            self.access_token = self.get_access_token()  # ✅ Fetch token from API
            if not self.access_token:
                logging.error("❌ Fetching accounts failed: Could not retrieve access token.")
                return
        else:
            logging.error("❌ Fetching accounts failed: Application not authorized.")
            return
        try:
            acc_request = AccountListRequest(self.access_token)
            acc_request_json = acc_request.as_json_string()
            self.send_json(acc_request_json)
            # ✅ Wait for response with payloadType 2150
            response = self.receive_json()
            # logging.info(f"Accounts: {response}")
            if response and response.get("payloadType") == int(2150):
                # Extract all accounts from response
                accounts = response.get("payload", {}).get("ctidTraderAccount", [])

                # ✅ Extract the `ctidTraderAccountId` where `isLive` is False
                for account in accounts:
                    ac_no = account.get("ctidTraderAccountId")
                    if account.get("isLive", False):
                        if self.is_account_live:
                            self.acc_authorized_no = ac_no
                            logging.info(f"✅ Live account fetched successfully: {ac_no}")
                            return ac_no
                        else:
                            continue
                    else:
                        if not self.is_account_live:
                            self.acc_authorized_no = ac_no
                            logging.info(f"✅ Demo account fetched successfully: {ac_no}")
                            return ac_no
                        else:
                            continue
                return None
            else:
                logging.error("❌ No response received for account request.")
                return None
        except Exception as e:
            logging.error(f"❌ Error while fetching accounts: {e}")
            return None

    def account_authorization(self, ctid_trader_account_id: int = None):
        """
           This class method initiates an account authorization request to cTrader API.

           Args:
             - ctid_trader_account_id (int): The trading account ID to authorize.

           Returns:
             - boolean: True if account authorization successfull else False.
        """
        if not self.client:
            logging.error("⚠️ No active connection. Connect first.")
            return self.acc_authorized

        try:
            target_account = ctid_trader_account_id or self.acc_authorized_no

            if not target_account:
                logging.error("❌ No account ID provided for authorization.")
                return self.acc_authorized

            if not self.access_token:
                self.access_token = self.get_access_token()
                if not self.access_token:
                    return self.acc_authorized

            acc_auth_request = AccountAuthRequest(target_account, self.access_token)
            acc_auth_json = acc_auth_request.as_json_string()
            self.send_json(acc_auth_json)

            # Wait for response with payloadType 51 (Authorization Result)
            response = self.receive_json()

            if response and response.get("payloadType") == int(2103):
                self.acc_authorized = True
                self.acc_authorized_no = target_account
                ac_status = "Live" if self.is_account_live else "Demo"
                logging.info(f"✅ {ac_status} account authorized successfully: {target_account}")
                return self.acc_authorized

            elif response and response.get("payloadType") == int(2142):
                err_des = response.get("payload", {}).get("description", "")
                logging.error(f"❌ OpenAPI Error: {err_des}")
                return self.acc_authorized

            else:
                logging.error("❌ No response received for authorization request.")
                return self.acc_authorized

        except Exception as e:
            logging.error(f"❌ Error initiating authorization: {e}")
            return self.acc_authorized

    def _start_heartbeat(self):
        """
           This class method starts sending a heartbeat event every 10 seconds to keep the connection alive.
        """
        self._heartbeat_stop.clear()
        def heartbeat_loop():
            while not self._heartbeat_stop.is_set() and self.is_authorized:
                try:
                    hbr = HeartBeatEventRequest()
                    self.send_json(hbr.as_json_string())
                    logging.debug("💓 Heartbeat sent.")
                    # logging.info("💓 Heartbeat sent.")
                except Exception as e:
                    logging.error(f"❌ Heartbeat failed: {e}")
                    self.close()
                    break
                self._heartbeat_stop.wait(20)
            logging.info("🧵 Standalone Heartbeat thread has exited safely.")

        self.heartbeat_thread = Thread(target=heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()
        logging.info("💓 Heartbeat process started (sending every 10s).")

    def close(self, reconnect: bool = False):
        """
           This class method closes the TCP connection to cTrader API.

           Args:
             -None

           Returns:
             -None
        """
        # 1. Reset Authorization States immediately to stop outgoing traffic
        self.is_authorized = False
        self.acc_authorized = False
        self.acc_authorized_no = None
        self._heartbeat_stop.set()

        # 2. Attempt a clean SSL shutdown.
        try:
            if self.client:
                self.client.shutdown(socket.SHUT_RDWR)
                self.client.close()
                logging.info("🔌 SSL Connection closed gracefully.")
        except Exception as e:
            logging.warning(f"⚠️ Error during SSL shutdown: {e}")
        finally:
            self.client = None

        # 3. Ensure the raw socket is also cleared
        try:
            if self.raw_socket:
                self.raw_socket.close()
                logging.info("🔌 Raw TCP Socket closed.")
        except Exception as e:
            logging.warning(f"⚠️ Error closing raw socket: {e}")
        finally:
            self.raw_socket = None
            self._recv_buffer = b""
            self._dispatch_buffer = ""

        # 5. ✅ Reconnect if requested
        if reconnect:
            logging.info("🔄 Reconnecting...")
            self.connect()
            self.authenticate()
            #self.account_authorization()

    def recv_spot_events(self, payload_type: int, timeout: int = 5):
        """
           Return first packet matching payload_type before timeout.
           Return None when no matching packet arrives.
        """
        if not self.client:
            return None
        deadline = time() + timeout
        while time() < deadline:
            packets = self.recv_depth_events(timeout=max(0.001, deadline - time()))
            for packet in packets:
                if packet.get("payloadType") == payload_type:
                    return packet
        return None

    def recv_depth_events(self, payload_type: int = 2155, timeout: int = 5):
        """
           Reads from the socket line by line, returning a list
           of all JSON objects that arrived. If no data arrives for
           `timeout` seconds, it returns any parsed messages so far
            (or an empty list if none).
        """
        start = time()
        json_objects = []
        buffer = self._dispatch_buffer

        def decode_complete_objects(text):
            decoder = json.JSONDecoder()
            objects = []
            while text.lstrip():
                stripped = text.lstrip()
                try:
                    obj, index = decoder.raw_decode(stripped)
                except json.JSONDecodeError:
                    break
                objects.append(obj)
                text = stripped[index:]
            return objects, text


        with self.socket_lock: # <--- Start Lock
            previous_timeout = self.client.gettimeout()
            try:
                while time() - start < timeout:
                    remaining = max(0.001, timeout - (time() - start))
                    self.client.settimeout(min(remaining, previous_timeout) if previous_timeout else remaining)
                    try:
                        chunk = self.client.recv(4096).decode("utf-8")
                    except socket.timeout:
                        break
                    if not chunk:
                        break
                    buffer += chunk
                    decoded, remainder = decode_complete_objects(buffer)
                    if decoded:
                        json_objects.extend(decoded)
                        buffer = remainder
                        break
            finally:
                self.client.settimeout(previous_timeout)
            self._dispatch_buffer = buffer
            if not json_objects:
                return []
            logging.info("✅ Returning depth events:")
            return json_objects

    def dispatch_messages(self, timeout=0.2):
        """The 'Pump': Reads the socket and sorts the mail."""
        with self.socket_lock:
            # Reusing your high-performance burst parser
            packets = self.recv_depth_events(timeout=timeout)

            for packet in packets:
                p_type = packet.get("payloadType")

                if p_type == 2155:
                    # Non-blocking put to avoid slowing down the pump if depth lags
                    try:
                        self.depth_queue.put_nowait(packet)
                    except: pass
                else:
                    # Everything else goes to Main (2157, 2158, 2142, etc.)
                    for handler in tuple(self.message_handlers):
                        try:
                            handler(packet)
                        except Exception:
                            logging.exception("Message handler failed")
                    try:
                        self.main_queue.put_nowait(packet)
                    except Full:
                        logging.warning("Main message queue full; dropping payload type %s", p_type)

    def add_message_handler(self, handler):
        """Register a callable for packets received by ``dispatch_messages``."""
        if not callable(handler):
            raise TypeError("handler must be callable")
        with self.socket_lock:
            if handler not in self.message_handlers:
                self.message_handlers.append(handler)

    def remove_message_handler(self, handler):
        """Unregister a previously attached packet handler."""
        with self.socket_lock:
            if handler in self.message_handlers:
                self.message_handlers.remove(handler)
