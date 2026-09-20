"""Non-repainting 5-minute SMC and Lee-Ready primitives.

The analyzer only consumes closed bars. A pivot is not available until its
right-hand confirmation bars have closed, which keeps historical structure
signals causal and suitable for live use.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import floor, isfinite
from typing import Any, Iterable, Literal, Optional

Direction = Literal["bullish", "bearish"]


@dataclass(frozen=True)
class Bar:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    def __post_init__(self) -> None:
        values = (self.open, self.high, self.low, self.close)
        if not all(isfinite(float(value)) for value in values):
            raise ValueError("bar OHLC values must be finite")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("bar high/low does not contain open/close")
        if self.high < self.low:
            raise ValueError("bar high must be greater than or equal to low")

    @classmethod
    def from_mapping(cls, raw: dict[str, Any], price_scale: float = 100000.0) -> "Bar":
        """Convert explicit OHLC or cTrader delta-encoded trendbar JSON."""
        def first(*keys: str, default: Any = None) -> Any:
            for key in keys:
                if key in raw and raw[key] is not None:
                    return raw[key]
            return default

        raw_low = first("low", "lowPrice")
        explicit = all(first(name) is not None for name in ("open", "high", "low", "close"))
        if explicit:
            open_price = float(first("open"))
            high_price = float(first("high"))
            low_price = float(first("low"))
            close_price = float(first("close"))
        else:
            if raw_low is None or price_scale <= 0:
                raise ValueError("trendbar needs explicit OHLC or low plus deltas")
            low_price = float(raw_low) / price_scale
            open_price = (float(raw_low) + float(first("deltaOpen", default=0))) / price_scale
            close_price = (float(raw_low) + float(first("deltaClose", default=0))) / price_scale
            high_price = (float(raw_low) + float(first("deltaHigh", default=0))) / price_scale

        timestamp = first("timestamp", "timestampMs", "utcTimestampInMinutes", "time")
        if timestamp is None:
            raise ValueError("trendbar has no timestamp")
        timestamp = int(timestamp)
        # cTrader's utcTimestampInMinutes is deliberately retained as a stable
        # identifier. Millisecond/second timestamps are also accepted.
        return cls(
            timestamp=timestamp,
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=float(first("volume", "tickVolume", default=0) or 0),
        )


@dataclass
class FairValueGap:
    id: str
    direction: Direction
    lower: float
    upper: float
    created_timestamp: int
    active: bool = True
    touched: bool = False

    def contains(self, price: float) -> bool:
        return self.active and self.lower <= price <= self.upper


@dataclass
class OrderBlock:
    id: str
    direction: Direction
    lower: float
    upper: float
    created_timestamp: int
    source_fvg_id: str
    active: bool = True
    touched: bool = False

    def contains(self, price: float) -> bool:
        return self.active and self.lower <= price <= self.upper


@dataclass(frozen=True)
class StructureEvent:
    kind: Literal["BOS", "CHOCH"]
    direction: Direction
    timestamp: int
    broken_price: float


@dataclass
class SMCConfig:
    pivot_left: int = 5
    pivot_right: int = 5
    atr_period: int = 14
    ob_lookback: int = 20
    max_zones: int = 200
    price_scale: float = 100000.0
    lee_ready_threshold: float = 0.35
    risk_percentage: float = 1.0
    target_rr: float = 2.5
    atr_buffer_multiplier: float = 0.5
    max_setup_bars: int = 3
    tick_timeout_ms: int = 5000
    max_tick_pages: int = 10
    max_active_trades: int = 1
    volume_step: int = 1000
    minimum_volume: int = 1000
    maximum_volume: int = 100000000
    value_per_price_unit: float = 1.0
    require_ob_confluence: bool = False

    @classmethod
    def from_mapping(cls, values: dict[str, Any]) -> "SMCConfig":
        """Build settings from JSON while ignoring unrelated application keys."""
        allowed = set(cls.__dataclass_fields__)
        return cls(**{key: value for key, value in values.items() if key in allowed})

    def to_mapping(self) -> dict[str, Any]:
        return {key: getattr(self, key) for key in self.__dataclass_fields__}

    def __post_init__(self) -> None:
        if self.pivot_left < 1 or self.pivot_right < 1:
            raise ValueError("pivot_left and pivot_right must be positive")
        if self.atr_period < 1 or self.ob_lookback < 1:
            raise ValueError("atr_period and ob_lookback must be positive")
        if not 0 < self.lee_ready_threshold <= 1:
            raise ValueError("lee_ready_threshold must be in (0, 1]")
        if self.risk_percentage <= 0 or self.target_rr <= 0:
            raise ValueError("risk_percentage and target_rr must be positive")
        if self.tick_timeout_ms < 1 or self.max_tick_pages < 1:
            raise ValueError("tick timeout and page limit must be positive")
        if self.atr_buffer_multiplier < 0 or self.value_per_price_unit <= 0:
            raise ValueError("ATR buffer and value_per_price_unit are invalid")


@dataclass(frozen=True)
class TickScore:
    score: float
    total_volume: float
    tick_count: int
    classified_buys: int
    classified_sells: int


def _tick_value(tick: dict[str, Any], *keys: str) -> Optional[float]:
    for key in keys:
        value = tick.get(key)
        if value is not None:
            try:
                number = float(value)
                if isfinite(number):
                    return number
            except (TypeError, ValueError):
                pass
    return None


def _normalise_ticks(ticks: Iterable[dict[str, Any]], price_scale: float) -> list[dict[str, Any]]:
    """Normalize explicit prices and cTrader's cumulative encoded tick field."""
    normalized: list[dict[str, Any]] = []
    encoded_price: Optional[float] = None
    for raw in ticks:
        tick = dict(raw)
        price = _tick_value(tick, "price", "tradePrice", "actual_price", "last")
        if price is None and "tick" in tick:
            encoded = _tick_value(tick, "tick")
            if encoded is None:
                continue
            encoded_price = encoded if encoded_price is None else encoded_price + encoded
            price = encoded_price / price_scale
        if price is None:
            # A quote-only tick can still participate if its midpoint exists.
            bid = _tick_value(tick, "bid")
            ask = _tick_value(tick, "ask")
            price = (bid + ask) / 2 if bid is not None and ask is not None else None
        if price is None or not isfinite(price):
            continue
        tick["_price"] = price
        raw_volume = _tick_value(tick, "volume", "tickVolume", "size")
        tick["_volume"] = max(0.0, raw_volume) if raw_volume is not None else 1.0
        normalized.append(tick)
    return normalized


def calculate_lee_ready_score(
    ticks: Iterable[dict[str, Any]],
    *,
    price_scale: float = 100000.0,
) -> TickScore:
    """Return volume-weighted Lee-Ready direction in the closed interval [-1, 1].

    cTrader frequently supplies bid/ask quotes separately from trade prices. If
    quotes are absent, the standard tick rule is used. Equal-price or equal-mid
    ticks retain the previous classification, with a neutral first tick.
    """
    normalized = _normalise_ticks(ticks, price_scale)
    if not normalized:
        return TickScore(0.0, 0.0, 0, 0, 0)

    signed_volume = 0.0
    total_volume = 0.0
    previous_price: Optional[float] = None
    previous_direction = 0
    buys = sells = 0
    for tick in normalized:
        price = float(tick["_price"])
        bid = _tick_value(tick, "bid")
        ask = _tick_value(tick, "ask")
        direction = 0
        if bid is not None and ask is not None and ask >= bid:
            midpoint = (bid + ask) / 2
            if price > midpoint:
                direction = 1
            elif price < midpoint:
                direction = -1
        if direction == 0 and previous_price is not None:
            if price > previous_price:
                direction = 1
            elif price < previous_price:
                direction = -1
        if direction == 0:
            direction = previous_direction
        volume = float(tick["_volume"])
        signed_volume += volume * direction
        total_volume += volume
        if direction > 0:
            buys += 1
        elif direction < 0:
            sells += 1
        previous_direction = direction
        previous_price = price

    score = signed_volume / total_volume if total_volume else 0.0
    return TickScore(max(-1.0, min(1.0, score)), total_volume, len(normalized), buys, sells)


def calculate_volume(
    equity: float,
    entry: float,
    stop: float,
    *,
    risk_percentage: float,
    value_per_price_unit: float,
    volume_step: int,
    minimum_volume: int,
    maximum_volume: int,
) -> int:
    """Calculate cTrader units from equity risk and normalize to volume step."""
    distance = abs(float(entry) - float(stop))
    if equity <= 0 or distance <= 0 or value_per_price_unit <= 0:
        return 0
    risk_cash = float(equity) * float(risk_percentage) / 100.0
    raw = risk_cash / (distance * value_per_price_unit)
    if raw < minimum_volume:
        return 0
    step = max(1, int(volume_step))
    volume = int(floor(raw / step) * step)
    return max(minimum_volume, min(maximum_volume, volume))


class SMCAnalyzer:
    """Causal 5m market-structure and active-zone state machine."""

    def __init__(self, config: Optional[SMCConfig] = None):
        self.config = config or SMCConfig()
        self.bars: list[Bar] = []
        self.swings: list[tuple[int, Literal["high", "low"], float]] = []
        self.fvgs: list[FairValueGap] = []
        self.order_blocks: list[OrderBlock] = []
        self.bias: Optional[Direction] = None
        self.last_structure_event: Optional[StructureEvent] = None
        self.atr: float = 0.0
        self._broken_swings: set[tuple[int, str]] = set()
        self._last_timestamp: Optional[int] = None
        self._bar_offset = 0

    def reset(self) -> None:
        self.__init__(self.config)

    def seed(self, bars: Iterable[Bar | dict[str, Any]]) -> list[StructureEvent]:
        events: list[StructureEvent] = []
        for raw in bars:
            bar = raw if isinstance(raw, Bar) else Bar.from_mapping(raw, self.config.price_scale)
            events.extend(self.process_closed_bar(bar))
        return events

    def active_fvgs(self, direction: Optional[Direction] = None) -> list[FairValueGap]:
        return [f for f in self.fvgs if f.active and (direction is None or f.direction == direction)]

    def active_order_blocks(self, direction: Optional[Direction] = None) -> list[OrderBlock]:
        return [o for o in self.order_blocks if o.active and (direction is None or o.direction == direction)]

    def zone_is_active(self, zone: FairValueGap | OrderBlock) -> bool:
        return zone.active

    def process_closed_bar(self, bar: Bar) -> list[StructureEvent]:
        if self._last_timestamp is not None and bar.timestamp <= self._last_timestamp:
            return []
        self._last_timestamp = bar.timestamp
        self.bars.append(bar)
        if len(self.bars) > self.config.max_zones * 4:
            self.bars.pop(0)
            self._bar_offset += 1
            self.swings = [(index - 1, kind, price) for index, kind, price in self.swings if index > 0]
            self._broken_swings = {(index - 1, kind) for index, kind in self._broken_swings if index > 0}
        index = len(self.bars) - 1
        self.atr = self._atr()

        # Existing zones are invalidated only by a complete fill or distal close.
        for fvg in self.fvgs:
            if fvg.active:
                if fvg.direction == "bullish" and bar.low <= fvg.lower:
                    fvg.active = False
                elif fvg.direction == "bearish" and bar.high >= fvg.upper:
                    fvg.active = False
                elif fvg.contains(bar.close) or (bar.low <= fvg.upper and bar.high >= fvg.lower):
                    fvg.touched = True
        for ob in self.order_blocks:
            if ob.active:
                if ob.direction == "bullish" and bar.close < ob.lower:
                    ob.active = False
                elif ob.direction == "bearish" and bar.close > ob.upper:
                    ob.active = False
                elif ob.contains(bar.close) or (bar.low <= ob.upper and bar.high >= ob.lower):
                    ob.touched = True

        self._confirm_pivot(index)
        new_fvg = self._detect_fvg(index)
        if new_fvg is not None:
            self.fvgs.append(new_fvg)

        event = self._detect_structure_break(bar)
        events = [event] if event else []
        if event:
            self.last_structure_event = event
            self.bias = event.direction
            # An OB is created only when the same impulse also creates an active FVG.
            if new_fvg is not None and new_fvg.direction == event.direction:
                ob = self._make_order_block(index, event.direction, new_fvg.id)
                if ob:
                    self.order_blocks.append(ob)

        if len(self.fvgs) > self.config.max_zones:
            self.fvgs = [f for f in self.fvgs if f.active][-self.config.max_zones :]
        if len(self.order_blocks) > self.config.max_zones:
            self.order_blocks = [o for o in self.order_blocks if o.active][-self.config.max_zones :]
        return events

    def _atr(self) -> float:
        if not self.bars:
            return 0.0
        trs: list[float] = []
        for i, bar in enumerate(self.bars):
            previous_close = self.bars[i - 1].close if i else bar.close
            trs.append(max(bar.high - bar.low, abs(bar.high - previous_close), abs(bar.low - previous_close)))
        values = trs[-self.config.atr_period :]
        return sum(values) / len(values) if values else 0.0

    def _confirm_pivot(self, index: int) -> None:
        candidate_index = index - self.config.pivot_right
        left = self.config.pivot_left
        right = self.config.pivot_right
        if candidate_index < left or candidate_index + right >= len(self.bars):
            return
        candidate = self.bars[candidate_index]
        neighbors = self.bars[candidate_index - left : candidate_index + right + 1]
        if candidate.high > max(b.high for b in neighbors if b is not candidate):
            item = (candidate_index, "high", candidate.high)
            if item not in self.swings:
                self.swings.append(item)
        if candidate.low < min(b.low for b in neighbors if b is not candidate):
            item = (candidate_index, "low", candidate.low)
            if item not in self.swings:
                self.swings.append(item)

    def _detect_fvg(self, index: int) -> Optional[FairValueGap]:
        if index < 2:
            return None
        first, _, third = self.bars[index - 2], self.bars[index - 1], self.bars[index]
        if third.low > first.high:
            return FairValueGap(f"fvg-{third.timestamp}-bullish", "bullish", first.high, third.low, third.timestamp)
        if third.high < first.low:
            return FairValueGap(f"fvg-{third.timestamp}-bearish", "bearish", third.high, first.low, third.timestamp)
        return None

    def _detect_structure_break(self, bar: Bar) -> Optional[StructureEvent]:
        highs = [s for s in self.swings if s[1] == "high" and (s[0], s[1]) not in self._broken_swings]
        lows = [s for s in self.swings if s[1] == "low" and (s[0], s[1]) not in self._broken_swings]
        candidate: Optional[tuple[str, Direction, tuple[int, str, float]]] = None
        if highs and bar.close > max(highs, key=lambda s: s[0])[2]:
            swing = max(highs, key=lambda s: s[0])
            candidate = ("high", "bullish", swing)
        elif lows and bar.close < max(lows, key=lambda s: s[0])[2]:
            swing = max(lows, key=lambda s: s[0])
            candidate = ("low", "bearish", swing)
        if candidate is None:
            return None
        side, direction, swing = candidate
        self._broken_swings.add((swing[0], side))
        kind: Literal["BOS", "CHOCH"] = "CHOCH" if self.bias and self.bias != direction else "BOS"
        return StructureEvent(kind, direction, bar.timestamp, swing[2])

    def _make_order_block(self, index: int, direction: Direction, fvg_id: str) -> Optional[OrderBlock]:
        start = max(0, index - self.config.ob_lookback)
        opposite_bearish = direction == "bullish"
        for candidate in reversed(self.bars[start:index]):
            is_opposite = candidate.close < candidate.open if opposite_bearish else candidate.close > candidate.open
            if not is_opposite:
                continue
            if direction == "bullish":
                lower, upper = candidate.low, candidate.open
            else:
                lower, upper = candidate.open, candidate.high
            if upper <= lower:
                lower, upper = candidate.low, candidate.high
            return OrderBlock(
                id=f"ob-{candidate.timestamp}-{direction}",
                direction=direction,
                lower=lower,
                upper=upper,
                created_timestamp=self.bars[index].timestamp,
                source_fvg_id=fvg_id,
            )
        return None

    def find_trigger_zone(self, price: float, direction: Direction) -> Optional[FairValueGap | OrderBlock]:
        obs = [o for o in self.active_order_blocks(direction) if o.contains(price)]
        fvgs = [f for f in self.active_fvgs(direction) if f.contains(price)]
        if self.config.require_ob_confluence:
            for ob in obs:
                if any(f.id == ob.source_fvg_id and f.contains(price) for f in fvgs):
                    return ob
            return None
        # The OB is the more specific zone. FVG is the fallback trigger.
        return max(obs, key=lambda z: z.created_timestamp) if obs else (
            max(fvgs, key=lambda z: z.created_timestamp) if fvgs else None
        )


def extract_equity(message: dict[str, Any]) -> Optional[float]:
    """Find account equity in account/trader JSON without depending on one event shape."""
    def walk(value: Any) -> Optional[float]:
        if isinstance(value, dict):
            for key, item in value.items():
                if key.lower() in {"equity", "balanceequity", "equityvalue"}:
                    try:
                        number = float(item)
                        if isfinite(number) and number > 0:
                            return number
                    except (TypeError, ValueError):
                        pass
                found = walk(item)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for item in value:
                found = walk(item)
                if found is not None:
                    return found
        return None
    return walk(message)
