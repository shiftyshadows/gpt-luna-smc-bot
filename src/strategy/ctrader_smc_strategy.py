"""cTrader JSON orchestration for the closed-bar SMC strategy.

This class is deliberately a message handler rather than a socket reader. The
existing client's dispatcher can pass each JSON packet to ``handle_message``
from one central receive loop, avoiding concurrent reads from the TCP socket.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from src.utils.messages.new_order_request import NewOrderRequest
from src.utils.messages.subscribe_live_trendbars import SubscribeLiveTrendbarsRequest
from src.utils.messages.subscribe_spot_request import SubscribeSpotRequest
from src.utils.messages.tick_data_request import TickDataRequest
from src.utils.messages.trendbars_request import TrendbarsRequest

from .smc_lee_ready import (
    Bar,
    Direction,
    FairValueGap,
    OrderBlock,
    SMCAnalyzer,
    SMCConfig,
    calculate_lee_ready_score,
    calculate_volume,
    extract_equity,
)

LOG = logging.getLogger(__name__)


@dataclass
class PendingZoneSetup:
    zone_id: str
    direction: Direction
    intercepted_at_ms: int
    bar_count: int
    request_id: str


class CTraderSMCStrategy:
    """Stateful SMC strategy wired to cTrader Open API JSON messages."""

    TREND_BAR_RESPONSE = 2115
    LEGACY_TREND_BAR_RESPONSE = 2138
    LIVE_TRENDBAR_EVENT = 2136
    SPOT_EVENT = 2131
    TICK_DATA_RESPONSE = 2146
    ERROR_RESPONSE = 2142
    EXECUTION_EVENT = 2126

    def __init__(
        self,
        client: Any,
        account_id: int,
        symbol_id: int,
        config: Optional[SMCConfig] = None,
        *,
        equity: Optional[float] = None,
        now_ms: Optional[callable] = None,
    ) -> None:
        self.client = client
        self.account_id = int(account_id)
        self.symbol_id = int(symbol_id)
        self.config = config or SMCConfig()
        self.analyzer = SMCAnalyzer(self.config)
        self.equity = equity
        self.open_trade_count = 0
        self.pending: Optional[PendingZoneSetup] = None
        self.invalidated_setups: set[str] = set()
        self.last_quote: dict[str, float] = {}
        self.sent_order_ids: set[str] = set()
        self._now_ms = now_ms or (lambda: int(time.time() * 1000))

    def attach(self) -> None:
        """Attach this handler to the repository's shared JSON dispatcher."""
        add_handler = getattr(self.client, "add_message_handler", None)
        if not callable(add_handler):
            raise TypeError("client does not support shared message handlers")
        add_handler(self.handle_message)

    def detach(self) -> None:
        """Stop receiving packets from the shared dispatcher."""
        remove_handler = getattr(self.client, "remove_message_handler", None)
        if callable(remove_handler):
            remove_handler(self.handle_message)

    def start(self, *, from_timestamp: Optional[int] = None, to_timestamp: Optional[int] = None) -> None:
        """Subscribe to 5m closed-bar events and spot events, then request history."""
        now = int(self._now_ms())
        to_timestamp = to_timestamp or now
        from_timestamp = from_timestamp or now - 30 * 24 * 60 * 60 * 1000
        self._send(SubscribeSpotRequest(self.account_id, self.symbol_id).as_json_string())
        self._send(SubscribeLiveTrendbarsRequest(self.account_id, self.symbol_id, period=5).as_json_string())
        self._send(
            TrendbarsRequest(
                self.account_id,
                self.symbol_id,
                period=5,
                from_timestamp=from_timestamp,
                to_timestamp=to_timestamp,
            ).as_json_string()
        )

    def seed_history(self, bars: list[Bar | dict[str, Any]]) -> None:
        """Seed only closed bars. Callers should omit the currently forming bar."""
        self.analyzer.seed(bars)

    def handle_message(self, message: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Route one decoded JSON packet from the central client dispatcher."""
        if not isinstance(message, dict):
            return None
        try:
            payload_type = int(message.get("payloadType", -1))
        except (TypeError, ValueError):
            return None
        if payload_type in (self.TREND_BAR_RESPONSE, self.LEGACY_TREND_BAR_RESPONSE, self.LIVE_TRENDBAR_EVENT):
            return self._handle_trendbars(message)
        if payload_type == self.SPOT_EVENT:
            self._handle_spot(message)
            return None
        if payload_type == self.TICK_DATA_RESPONSE:
            return self._handle_tick_response(message)
        if payload_type == self.ERROR_RESPONSE:
            self._handle_error(message)
            return None
        if payload_type == self.EXECUTION_EVENT:
            self._handle_execution(message)
            return None
        account_equity = extract_equity(message)
        if account_equity is not None:
            self.equity = account_equity
        return None

    def on_closed_bar(self, raw_bar: Bar | dict[str, Any]) -> list[Any]:
        """Process a confirmed closed M5 bar and expire stale pending setups."""
        bar = raw_bar if isinstance(raw_bar, Bar) else Bar.from_mapping(raw_bar, self.config.price_scale)
        events = self.analyzer.process_closed_bar(bar)
        if self.pending is not None:
            self.pending.bar_count += 1
            if self.pending.bar_count > self.config.max_setup_bars:
                self.invalidated_setups.add(self.pending.zone_id)
                self.pending = None
        return events

    def on_spot(self, bid: float, ask: float, timestamp_ms: Optional[int] = None) -> Optional[dict[str, Any]]:
        """Intercept an active zone and asynchronously request the last five minutes."""
        if bid <= 0 or ask <= 0 or ask < bid:
            return None
        self.last_quote = {"bid": float(bid), "ask": float(ask)}
        if self.pending is not None or self.open_trade_count >= self.config.max_active_trades:
            return None
        now = int(timestamp_ms or self._now_ms())
        # Use executable-side prices for zone tests, not an untradeable midpoint.
        for direction, price in (("bullish", ask), ("bearish", bid)):
            if self.analyzer.bias != direction:
                continue
            zone = self.analyzer.find_trigger_zone(price, direction)
            if zone is None or zone.id in self.invalidated_setups or not zone.active:
                continue
            request_id = str(uuid.uuid4())
            self.pending = PendingZoneSetup(zone.id, direction, now, 0, request_id)
            request = TickDataRequest(
                self.account_id,
                self.symbol_id,
                tickType=1,
                from_timestamp=now - 5 * 60 * 1000,
                to_timestamp=now,
                clientMsgId=request_id,
            )
            payload = request.as_json_string()
            self._send(payload)
            return payload
        return None

    def _handle_spot(self, message: dict[str, Any]) -> None:
        payload = message.get("payload", {})
        bid = self._decode_price(payload.get("bid"))
        ask = self._decode_price(payload.get("ask"))
        if bid is None and ask is None:
            return
        if bid is None:
            bid = ask
        if ask is None:
            ask = bid
        timestamp = payload.get("spotTimestamp") or payload.get("timestamp")
        self.on_spot(float(bid), float(ask), int(timestamp) if timestamp else None)

    def _handle_trendbars(self, message: dict[str, Any]) -> Optional[dict[str, Any]]:
        payload = message.get("payload", {})
        bars = payload.get("trendbar") or payload.get("trendbars") or []
        if isinstance(bars, dict):
            bars = [bars]
        for raw_bar in bars:
            try:
                # A live event denotes a completed bar. A response can include
                # an explicit closed flag, and open bars are never consumed.
                if raw_bar.get("closed") is False:
                    continue
                self.on_closed_bar(raw_bar)
            except (TypeError, ValueError) as exc:
                LOG.warning("Ignoring malformed trendbar: %s", exc)
        return None

    def _handle_tick_response(self, message: dict[str, Any]) -> Optional[dict[str, Any]]:
        if self.pending is None:
            return None
        response_id = message.get("clientMsgId") or message.get("payload", {}).get("clientMsgId")
        if response_id and response_id != self.pending.request_id:
            return None
        payload = message.get("payload", {})
        ticks = payload.get("tickData") or payload.get("ticks") or []
        if not ticks:
            LOG.warning("Tick response for %s contained no data; setup cancelled", self.pending.zone_id)
            self.invalidated_setups.add(self.pending.zone_id)
            self.pending = None
            return None
        score = calculate_lee_ready_score(ticks, price_scale=self.config.price_scale)
        direction = self.pending.direction
        threshold_passed = score.score >= self.config.lee_ready_threshold if direction == "bullish" else score.score <= -self.config.lee_ready_threshold
        zone = self._find_zone(self.pending.zone_id)
        request_direction = direction
        self.pending = None
        if not threshold_passed or zone is None or not zone.active:
            self.invalidated_setups.add(zone.id if zone is not None else request_direction)
            return None
        return self._execute_market(zone, direction, score.score)

    def _execute_market(self, zone: FairValueGap | OrderBlock, direction: Direction, score: float) -> Optional[dict[str, Any]]:
        if self.open_trade_count >= self.config.max_active_trades or self.equity is None:
            LOG.warning("Trade blocked: missing equity or active-trade limit reached")
            return None
        quote = self.last_quote
        entry = quote.get("ask" if direction == "bullish" else "bid")
        if entry is None:
            return None
        buffer = self.analyzer.atr * self.config.atr_buffer_multiplier
        if direction == "bullish":
            stop = zone.lower - buffer
            risk = entry - stop
            take_profit = entry + risk * self.config.target_rr
            trade_side = 1
        else:
            stop = zone.upper + buffer
            risk = stop - entry
            take_profit = entry - risk * self.config.target_rr
            trade_side = 2
        if risk <= 0:
            return None
        volume = calculate_volume(
            self.equity,
            entry,
            stop,
            risk_percentage=self.config.risk_percentage,
            value_per_price_unit=self.config.value_per_price_unit,
            volume_step=self.config.volume_step,
            minimum_volume=self.config.minimum_volume,
            maximum_volume=self.config.maximum_volume,
        )
        if volume <= 0:
            LOG.warning("Trade blocked: calculated volume is below broker minimum")
            return None
        label = f"smc5m-{uuid.uuid4().hex[:12]}"
        order = NewOrderRequest(
            self.account_id,
            symbolId=self.symbol_id,
            tradeSide=trade_side,
            volume=volume,
            orderType=1,
            stopLoss=stop,
            takeProfit=take_profit,
            orderComment=f"SMC5M LR={score:.3f}",
            label=label,
        )
        payload = order.as_json_string()
        self._send(payload)
        self.sent_order_ids.add(label)
        self.open_trade_count += 1
        return payload

    def _handle_error(self, message: dict[str, Any]) -> None:
        if self.pending is not None:
            LOG.error("cTrader error while waiting for Lee-Ready data: %s", message.get("payload", {}))
            self.invalidated_setups.add(self.pending.zone_id)
            self.pending = None

    def _handle_execution(self, message: dict[str, Any]) -> None:
        payload = message.get("payload", {})
        if payload.get("executionType") == 3:
            self.open_trade_count = max(1, self.open_trade_count)
        account_equity = extract_equity(message)
        if account_equity is not None:
            self.equity = account_equity

    def _find_zone(self, zone_id: str) -> Optional[FairValueGap | OrderBlock]:
        for zone in [*self.analyzer.fvgs, *self.analyzer.order_blocks]:
            if zone.id == zone_id:
                return zone
        return None

    def _send(self, message: dict[str, Any]) -> None:
        self.client.send_json(message)

    def _decode_price(self, value: Any) -> Optional[float]:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if number <= 0:
            return None
        return number / self.config.price_scale if number > 1000 else number
