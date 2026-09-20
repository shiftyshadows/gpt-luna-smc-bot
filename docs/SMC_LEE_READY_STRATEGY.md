# 5-minute SMC and Lee-Ready strategy

The strategy lives in `src/strategy/` and is intentionally split into a pure
closed-bar analyzer and a cTrader JSON message handler.

## Runtime wiring

```python
from src.strategy import CTraderSMCStrategy, SMCConfig
from src.api.routes.ctrader import ctrader_client

settings = SMCConfig.from_mapping({
    "pivot_left": 5,
    "pivot_right": 5,
    "lee_ready_threshold": 0.35,
    "risk_percentage": 1.0,
    "target_rr": 2.5,
    "atr_buffer_multiplier": 0.5,
})
strategy = CTraderSMCStrategy(
    ctrader_client,
    account_id=ctrader_client.acc_authorized_no,
    symbol_id=41,
    config=settings,
    equity=10000.0,
)
strategy.attach()  # one shared dispatcher, no competing socket reader
strategy.start()
```

The existing dispatcher calls `handle_message` for non-DOM packets. Historical
trendbars use payload type **2114**, live closed-bar events are accepted as
**2136**, spot events are **2131**, tick responses are **2146**, and orders use
**2106**. `TrendbarsRequest` and `TickDataRequest` preserve the client message
ID so a tick response cannot confirm a different zone setup.

## Signal flow

1. `SMCAnalyzer` consumes closed M5 bars only. Pivots become available only
   after `pivot_right` bars close. BOS and CHOCH update the structural bias.
2. A three-bar FVG is kept active until a later candle's wick completely fills
   it. A linked order block is created only when the same impulse breaks
   structure and has an active same-direction FVG. OBs are invalidated only by
   a close beyond their distal boundary.
3. A spot event entering an active zone starts exactly one five-minute
   `ProtoOATickDataReq` (**2145**) request. No market order is sent on a zone
   touch alone.
4. `calculate_lee_ready_score` classifies trades above/below the quote midpoint
   and falls back to the tick rule when quotes are absent. The score is
   volume-weighted and bounded to `[-1, 1]`.
5. A market order is sent only when the score agrees with bias and clears the
   threshold. Its volume uses equity risk, and its payload includes absolute
   stop-loss and take-profit prices.

A missing/empty tick response, a failed threshold test, a mitigated zone, or a
stale setup cancels the setup. The default limit is one active/in-flight trade.

## Settings

| Setting | Default | Meaning |
| --- | ---: | --- |
| `pivot_left`, `pivot_right` | `5`, `5` | Closed-bar pivot confirmation window |
| `atr_period` | `14` | ATR period for the distal-zone buffer |
| `ob_lookback` | `20` | Search window for the last opposite candle |
| `lee_ready_threshold` | `0.35` | Required absolute directional score |
| `risk_percentage` | `1.0` | Percent of equity risked per trade |
| `target_rr` | `2.5` | Fixed risk-to-reward target |
| `atr_buffer_multiplier` | `0.5` | ATR distance beyond the zone |
| `max_setup_bars` | `3` | Bars before an unanswered setup is invalidated |
| `volume_step` / `minimum_volume` | `1000` / `1000` | Broker unit normalization |
| `value_per_price_unit` | `1.0` | Account-currency value of one price unit per cTrader unit |
| `require_ob_confluence` | `false` | Require price to be in linked OB and FVG |

`SMCConfig.from_mapping()` accepts these keys from a JSON configuration and
ignores unrelated application settings.

## Operational cautions

- Confirm the broker's symbol price scale, volume step, minimum volume, and
  value-per-price-unit before enabling live execution.
- `equity` must come from a trusted account status event or an explicit value.
  The strategy blocks an order when equity is unavailable.
- Historical data must exclude a currently forming candle. Run the included
  unit tests and a demo/paper replay before enabling a live account.
- The Lee-Ready score is a quote/trade classification proxy. cTrader tick
  history may not contain centralized trade aggressor information, so the
  tick-rule fallback should not be interpreted as exchange-grade order flow.
