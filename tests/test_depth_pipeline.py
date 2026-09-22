import unittest
from queue import Queue

from src.utils.ctrader_tcp_client import CTraderTCPClient
from src.utils.dom_listener import DepthLogLimiter, _depth_signature, dom_stream_worker
from src.utils.full_depth_order_book import FullDepthOrderBook


class DepthPipelineTest(unittest.TestCase):
    def test_dom_worker_suppresses_immediate_duplicate_packets(self):
        class FakeClient:
            def __init__(self):
                self.depth_queue = Queue()
                self.is_listening_dom = True
                self.depth_worker_thread = None

            def is_connected(self):
                return self.is_listening_dom

            def dispatch_messages(self):
                self.is_listening_dom = False

        class RecordingBook:
            def __init__(self):
                self.updates = []

            def apply_update(self, new_quotes, deleted_quotes):
                self.updates.append((new_quotes, deleted_quotes))

            def get_top_of_book(self):
                return 1.0, 1.01, 1

            def snapshot_metrics(self):
                return {"best_bid": 1.0, "best_ask": 1.01, "spread": 0.01}

        client = FakeClient()
        book = RecordingBook()
        event = {"payload": {"newQuotes": [{"id": 1}], "deletedQuotes": []}}
        client.depth_queue.put(event)
        client.depth_queue.put(event.copy())

        dom_stream_worker(client, book)

        self.assertEqual(len(book.updates), 1)

    def test_depth_log_limiter_requires_top_change_and_throttles(self):
        now = [0.0]
        limiter = DepthLogLimiter(interval_seconds=1.0, clock=lambda: now[0])

        self.assertTrue(limiter.allow((1.0, 1.1, 2)))
        now[0] = 0.2
        self.assertFalse(limiter.allow((1.0, 1.1, 3)))
        now[0] = 1.1
        self.assertFalse(limiter.allow((1.0, 1.1, 3)))
        self.assertTrue(limiter.allow((1.01, 1.1, 3)))

    def test_depth_status_limiter_repeats_without_top_change(self):
        now = [0.0]
        limiter = DepthLogLimiter(
            interval_seconds=1.0,
            clock=lambda: now[0],
            only_on_change=False,
        )

        self.assertTrue(limiter.allow((1.0, 1.1, 2)))
        now[0] = 0.5
        self.assertFalse(limiter.allow((1.0, 1.1, 2)))
        now[0] = 1.0
        self.assertTrue(limiter.is_due())
        self.assertTrue(limiter.allow((1.0, 1.1, 2)))

    def test_order_book_exposes_structured_top_of_book(self):
        book = FullDepthOrderBook()
        book.apply_update(
            [
                {"id": 1, "bid": 100000, "size": 10},
                {"id": 2, "bid": 99000, "size": 20},
                {"id": 3, "ask": 101000, "size": 15},
            ],
            [],
        )

        self.assertEqual(book.get_top_of_book(), (1.0, 1.01, 3))
        self.assertEqual(book.snapshot_metrics()["depth_levels"], 3)

    def test_duplicate_handler_registration_is_idempotent(self):
        client = CTraderTCPClient()
        try:
            handler = lambda _message: None
            client.add_message_handler(handler)
            client.add_message_handler(handler)
            self.assertEqual(client.message_handlers, [handler])
        finally:
            client.oauth_manager.mclient.close()

    def test_depth_signature_is_stable_for_same_event(self):
        event = ([{"id": 1, "bid": 100000, "size": 10}], [2])
        self.assertEqual(_depth_signature(*event), _depth_signature(*event))


if __name__ == "__main__":
    unittest.main()
