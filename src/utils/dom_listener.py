import logging
import threading
from time import sleep
from src.utils.messages.heartbeat_event  import HeartBeatEventRequest

def dom_stream_worker(client, book):
    """
       Listens to the 2155 stream and updates the book.
    """
    logging.info("🚀 Background DOM Listener started.")
    while client.is_connected() and getattr(client, 'is_listening_dom', False):
        try:
            # 1. THE PUMP: This fills both depth_queue and main_queue
            data = client.dispatch_messages()


            # 2. PROCESS DEPTH: Drain the depth_queue
            processed_count = 0
            while not client.depth_queue.empty():
                try:
                    event = client.depth_queue.get_nowait()
                    payload = event.get("payload", {})

                    new_quotes = payload.get("newQuotes", [])
                    del_ids = payload.get("deletedQuotes", [])

                    book.apply_update(new_quotes, del_ids)
                    processed_count += 1
                except Exception:
                    break

            # 3. LOGGING: Only log if we actually moved the needle
            if processed_count > 0:
                metrics = book.snapshot_metrics()
                logging.info(f"DOM Updated: {processed_count} packets | Metrics: {metrics}")

            # 4. THROTTLE: Tiny sleep to prevent 100% CPU usage
            sleep(0.001)


        except Exception as e:
            logging.error(f"💥 DOM Worker Crash: {e}")
            client.is_listening_dom = False
            break
