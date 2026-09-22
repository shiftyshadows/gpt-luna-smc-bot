import unittest
import socket
import runpy

from src.strategy.ctrader_smc_strategy import CTraderSMCStrategy
from src.strategy.smc_lee_ready import (
    Bar,
    FairValueGap,
    SMCAnalyzer,
    SMCConfig,
    calculate_lee_ready_score,
)
from src.utils.messages.new_order_request import NewOrderRequest
from src.utils.ctrader_tcp_client import CTraderTCPClient


class FakeClient:
    def __init__(self):
        self.sent = []

    def send_json(self, payload):
        self.sent.append(payload)


class LeeReadyAndSMCTest(unittest.TestCase):
    def test_config_rejects_non_positive_limits(self):
        for field in ("max_zones", "max_setup_bars", "max_tick_pages", "max_active_trades"):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    SMCConfig(**{field: 0})
                with self.assertRaises(ValueError):
                    SMCConfig(**{field: -1})

    def test_config_rejects_invalid_volume_and_price_settings(self):
        invalid_settings = (
            {"volume_step": 0},
            {"minimum_volume": 0},
            {"maximum_volume": -1},
            {"minimum_volume": 2000, "maximum_volume": 1000},
            {"price_scale": 0},
            {"value_per_price_unit": 0},
        )
        for settings in invalid_settings:
            with self.subTest(settings=settings):
                with self.assertRaises(ValueError):
                    SMCConfig(**settings)

    def test_lee_ready_is_volume_weighted_and_uses_quote_midpoint(self):
        result = calculate_lee_ready_score([
            {"price": 101.0, "bid": 100.0, "ask": 100.5, "volume": 3},
            {"price": 99.0, "bid": 99.5, "ask": 100.0, "volume": 1},
        ])
        self.assertEqual(result.tick_count, 2)
        self.assertEqual(result.total_volume, 4)
        self.assertAlmostEqual(result.score, 0.5)

    def test_pivot_is_not_available_until_right_bar_closes(self):
        analyzer = SMCAnalyzer(SMCConfig(pivot_left=1, pivot_right=1))
        analyzer.process_closed_bar(Bar(1, 1.0, 2.0, 0.9, 1.5))
        analyzer.process_closed_bar(Bar(2, 1.5, 3.0, 1.4, 2.5))
        self.assertEqual(analyzer.swings, [])
        analyzer.process_closed_bar(Bar(3, 2.5, 2.7, 1.8, 2.0))
        self.assertEqual([(i, side) for i, side, _ in analyzer.swings], [(1, "high")])

    def test_fvg_stays_active_on_retrace_and_is_removed_on_full_fill(self):
        analyzer = SMCAnalyzer(SMCConfig(pivot_left=1, pivot_right=1))
        analyzer.process_closed_bar(Bar(1, 10, 11, 9.5, 10.5))
        analyzer.process_closed_bar(Bar(2, 10.6, 11.5, 10.5, 11.2))
        analyzer.process_closed_bar(Bar(3, 11.6, 12.5, 11.6, 12.2))
        self.assertEqual(len(analyzer.active_fvgs("bullish")), 1)
        analyzer.process_closed_bar(Bar(4, 11.6, 12.1, 11.4, 11.5))
        self.assertEqual(len(analyzer.active_fvgs("bullish")), 1)
        analyzer.process_closed_bar(Bar(5, 11.8, 12.0, 10.9, 11.0))
        self.assertEqual(len(analyzer.active_fvgs("bullish")), 0)

    def test_market_order_keeps_protective_prices(self):
        payload = NewOrderRequest(
            42, symbolId=7, tradeSide=1, orderType=1,
            stopLoss=1.1, takeProfit=1.3,
        ).as_json_string()
        self.assertEqual(payload["payload"]["orderType"], 1)
        self.assertEqual(payload["payload"]["stopLoss"], 1.1)
        self.assertEqual(payload["payload"]["takeProfit"], 1.3)

    def test_zone_touch_requests_ticks_then_executes_after_threshold(self):
        client = FakeClient()
        strategy = CTraderSMCStrategy(client, 42, 7, SMCConfig(
            atr_buffer_multiplier=0, minimum_volume=1000, volume_step=1000,
            value_per_price_unit=1, lee_ready_threshold=0.35,
        ), equity=10000, now_ms=lambda: 1_000_000)
        strategy.analyzer.bias = "bullish"
        zone = FairValueGap("fvg-test", "bullish", 1.0, 1.1, 1)
        strategy.analyzer.fvgs.append(zone)
        strategy.analyzer.atr = 0.01
        request = strategy.on_spot(1.04, 1.05)
        self.assertEqual(request["payloadType"], 2145)
        strategy.handle_message({
            "payloadType": 2146,
            "clientMsgId": request["clientMsgId"],
            "payload": {"tickData": [
                {"price": 1.05, "bid": 1.04, "ask": 1.045, "volume": 10},
                {"price": 1.06, "bid": 1.04, "ask": 1.045, "volume": 10},
            ]},
        })
        order = client.sent[-1]
        self.assertEqual(order["payloadType"], 2106)
        self.assertEqual(order["payload"]["tradeSide"], 1)
        self.assertIsNotNone(order["payload"]["stopLoss"])
        self.assertIsNotNone(order["payload"]["takeProfit"])

    def test_dispatcher_handles_complete_json_without_newline_and_expires_setup(self):
        client = CTraderTCPClient()
        strategy = CTraderSMCStrategy(
            client, 42, 7, SMCConfig(max_setup_bars=1), equity=10000,
            now_ms=lambda: 1_000_000,
        )
        strategy.analyzer.bias = "bullish"
        strategy.analyzer.fvgs.append(FairValueGap("dispatch-zone", "bullish", 1, 2, 1))
        strategy.attach()
        left, right = socket.socketpair()
        try:
            client.client = left
            right.sendall(b'{"payloadType":2131,"payload":{"bid":1.4,"ask":1.5}}')
            client.dispatch_messages(timeout=0.2)
            self.assertIsNotNone(strategy.pending)
            strategy.on_closed_bar({
                "timestamp": 1, "open": 1.0, "high": 1.1,
                "low": 0.9, "close": 1.0,
            })
            self.assertIsNone(strategy.pending)
        finally:
            strategy.detach()
            right.close()
            left.close()
            client.oauth_manager.mclient.close()

    def test_spot_reader_handles_unframed_json_and_full_main_queue(self):
        client = CTraderTCPClient()
        left, right = socket.socketpair()
        try:
            client.client = left
            right.sendall(b'{"payloadType":2131,"payload":{"bid":1.4,"ask":1.5}}')
            event = client.recv_spot_events(2131, timeout=0.2)
            self.assertEqual(event["payloadType"], 2131)

            for index in range(client.main_queue.maxsize):
                client.main_queue.put_nowait({"payloadType": index})
            right.sendall(b'{"payloadType":2131,"payload":{"bid":1.4,"ask":1.5}}')
            client.dispatch_messages(timeout=0.2)
            self.assertEqual(client.main_queue.qsize(), client.main_queue.maxsize)
        finally:
            right.close()
            left.close()
            client.oauth_manager.mclient.close()

    def test_order_rejection_releases_in_flight_slot(self):
        client = FakeClient()
        strategy = CTraderSMCStrategy(client, 42, 7, SMCConfig(
            minimum_volume=1000, volume_step=1000, atr_buffer_multiplier=0,
        ), equity=10000, now_ms=lambda: 1_000_000)
        strategy.analyzer.bias = "bullish"
        strategy.analyzer.fvgs.append(FairValueGap("reject-zone", "bullish", 1, 1.1, 1))
        request = strategy.on_spot(1.04, 1.05)
        strategy.handle_message({
            "payloadType": 2146,
            "clientMsgId": request["clientMsgId"],
            "payload": {"tickData": [
                {"price": 1.06, "volume": 10},
                {"price": 1.07, "volume": 10},
            ]},
        })
        order = client.sent[-1]
        label = order["payload"]["label"]
        self.assertEqual(strategy.open_trade_count, 0)
        self.assertEqual(len(strategy.orders_in_flight), 1)
        strategy.handle_message({
            "payloadType": 2132,
            "payload": {"label": label, "errorCode": "REJECTED"},
        })
        self.assertEqual(strategy.orders_in_flight, {})

    def test_tick_pages_accumulate_before_scoring(self):
        client = FakeClient()
        strategy = CTraderSMCStrategy(client, 42, 7, SMCConfig(
            minimum_volume=1000, volume_step=1000, atr_buffer_multiplier=0,
        ), equity=10000, now_ms=lambda: 1_000_000)
        strategy.analyzer.bias = "bullish"
        strategy.analyzer.fvgs.append(FairValueGap("page-zone", "bullish", 1, 1.1, 1))
        request = strategy.on_spot(1.04, 1.05)
        strategy.handle_message({
            "payloadType": 2146,
            "clientMsgId": request["clientMsgId"],
            "payload": {"hasMore": True, "tickData": [
                {"timestamp": 900000, "price": 1.06, "volume": 10},
            ]},
        })
        self.assertIsNotNone(strategy.pending)
        self.assertEqual(client.sent[-1]["payload"]["toTimestamp"], 899999)
        strategy.handle_message({
            "payloadType": 2146,
            "clientMsgId": request["clientMsgId"],
            "payload": {"hasMore": False, "tickData": [
                {"timestamp": 899000, "price": 1.07, "volume": 10},
            ]},
        })
        self.assertEqual(client.sent[-1]["payloadType"], 2106)

    def test_run_bot_parser_rejects_invalid_history_days(self):
        module = runpy.run_path("run_bot")
        with self.assertRaises(SystemExit):
            module["parse_args"](["--history-days", "0"])


if __name__ == "__main__":
    unittest.main()
