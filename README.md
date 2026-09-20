# cTrader 5-minute SMC bot

Algorithmic trading bot for cTrader Open API JSON. Bot builds closed-bar Smart Money Concepts (SMC) zones on M5 charts, validates zone entries with a five-minute Lee-Ready directional score, then sends market orders with risk-based volume, stop-loss, and take-profit levels.

> **Risk warning:** This software can place live trades. Run demo or paper tests first. Validate broker symbol settings, volume limits, price precision, and risk sizing before enabling live execution.

## Features

- Closed M5 trendbar analysis with non-repainting pivots, BOS, and CHOCH.
- Active Fair Value Gap (FVG) tracking with mitigation handling.
- Order Block (OB) creation only after structure break and matching active FVG.
- Live spot interception for unmitigated zones.
- Five-minute tick retrieval through `ProtoOAGetTickDataReq`.
- Quote-based Lee-Ready classification with tick-rule fallback.
- Volume-weighted directional score in `[-1, 1]`.
- Threshold-gated market execution.
- Risk-percentage position sizing with ATR stop buffer and fixed R:R target.
- Tick request pagination, timeout handling, duplicate-order protection, and clean shutdown.

## Project layout

```text
run_bot                         Canonical trading bot entrypoint
run.py                           Flask API server entrypoint
config/smc_strategy.json         Strategy settings
docs/SMC_LEE_READY_STRATEGY.md   Detailed strategy and protocol guide
src/strategy/                    SMC analyzer and cTrader message handlers
src/utils/                       cTrader transport and JSON payload helpers
tests/                           Unit and integration-boundary tests
Dockerfile                       Container runtime definition
```

`run_bot` starts the trading strategy. `run.py` starts the Flask API server. Do not use `run.py` as the trading entrypoint.

## Requirements

- Python 3.10+
- cTrader Open API application credentials
- cTrader account ID
- MongoDB for OAuth token storage
- Network access to cTrader and MongoDB

Install dependencies:

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements.txt
```

## Configuration

Create `.env` in the repository root. Never commit credentials or tokens.

```dotenv
CTRADER_CLIENT_ID=your_client_id
CTRADER_CLIENT_SECRET=your_client_secret
CTRADER_REDIRECT_URI=https://your-callback-url
CTRADER_TOKEN_URI=https://connect-proto.ctrader.com/apps/token
CTRADER_ACCOUNT_ID=your_account_id
MONGO_URI=mongodb://localhost:27017

# Optional runtime settings
CTRADER_SYMBOL_ID=41
CTRADER_EQUITY=10000
SMC_CONFIG_PATH=config/smc_strategy.json
SMC_HISTORY_DAYS=30
LOG_LEVEL=INFO
```

`run_bot` loads OAuth credentials through the existing authentication flow, stores tokens in MongoDB, authenticates the cTrader application, then authorizes the account.

Edit `config/smc_strategy.json` for strategy behavior:

| Setting | Default | Purpose |
| --- | ---: | --- |
| `pivot_left`, `pivot_right` | `5`, `5` | Closed-bar pivot confirmation window |
| `atr_period` | `14` | ATR period |
| `ob_lookback` | `20` | Search window for opposite candle |
| `lee_ready_threshold` | `0.35` | Required directional score magnitude |
| `risk_percentage` | `1.0` | Equity risk per trade, in percent |
| `target_rr` | `2.5` | Fixed risk-to-reward target |
| `atr_buffer_multiplier` | `0.5` | ATR distance beyond zone |
| `max_setup_bars` | `3` | Setup timeout in bars |
| `tick_timeout_ms` | `5000` | Tick response timeout |
| `max_tick_pages` | `10` | Maximum tick response pages |
| `volume_step` | `1000` | Broker volume increment |
| `minimum_volume` | `1000` | Minimum order volume |
| `maximum_volume` | `100000000` | Maximum order volume |
| `value_per_price_unit` | `1.0` | Account-currency value per price unit |
| `require_ob_confluence` | `false` | Require both linked OB and FVG |

See [`docs/SMC_LEE_READY_STRATEGY.md`](docs/SMC_LEE_READY_STRATEGY.md) for signal flow, protocol payloads, and operational limits.

## Run bot

Use explicit values for live or demo deployment:

```bash
./run_bot 41 \
  --config config/smc_strategy.json \
  --equity 10000 \
  --history-days 30
```

Or use environment defaults:

```bash
CTRADER_SYMBOL_ID=41 CTRADER_EQUITY=10000 ./run_bot
```

Check CLI options without loading cTrader credentials:

```bash
./run_bot --help
```

The bot requests historical M5 bars, subscribes to closed-bar and spot events, and keeps one shared cTrader message dispatcher active. Stop with `Ctrl+C` or `SIGTERM`.

## Run Flask API

`run.py` serves the existing Flask API on port `8000`:

```bash
python3 run.py
```

Use `run_bot` for trading. Use `run.py` only for API and authentication routes.

## Docker

Build and run with environment variables from a protected file:

```bash
docker build -t ctrader-smc-bot .
docker run --rm --env-file .env ctrader-smc-bot
```

The container command is `./run_bot`.

## Tests and checks

Run the repository test suite:

```bash
python3 -W error::ResourceWarning -m unittest discover -s tests -q
python3 -m compileall -q src tests
python3 -m py_compile run_bot
```

Tests cover SMC calculations, Lee-Ready scoring, JSON dispatch, tick pagination, request timeout, order rejection cleanup, queue backpressure, and the canonical CLI entrypoint.

## Trading limitations

- Live broker execution requires valid cTrader credentials, account authorization, MongoDB, and network access.
- cTrader tick history may not contain centralized trade aggressor information. Lee-Ready classification is an order-flow proxy, not exchange-grade aggressor data.
- Position-close event behavior must be confirmed against the target broker account before relying on long-running position limits.
- Historical bars must exclude the currently forming candle.
- Confirm symbol price scale, volume step, minimum volume, and value-per-price-unit before live use.
