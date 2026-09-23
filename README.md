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

## Recommended deployment topology

Run the trading bot as a systemd service on the host and run MongoDB in Docker
Compose. This keeps the cTrader socket in one long-lived bot process while
keeping MongoDB restartable and private to the host. The Compose API service is
optional and is intended only for OAuth and administrative routes.

```text
systemd ctrader-smc-bot  ── localhost:27017 ──>  Compose MongoDB
        │
        └── outbound TLS:5036 ──> demo.ctraderapi.com

optional Compose API  ── internal network ──> MongoDB
       localhost:8000 only
```

The cTrader client is part of `run_bot`, not a separate container. Do not run
the bot both from systemd and Compose because that would create competing
strategy processes and account connections.

### Install the systemd topology

The deployment units assume the repository is installed at
`/opt/ctrader-smc-bot` and that a `ctrader-bot` user exists:

```bash
sudo chown -R ctrader-bot:ctrader-bot /opt/ctrader-smc-bot
sudo -u ctrader-bot python3 -m venv /opt/ctrader-smc-bot/.venv
sudo -u ctrader-bot /opt/ctrader-smc-bot/.venv/bin/pip install -r /opt/ctrader-smc-bot/requirements.txt
sudo install -d -m 0750 /etc/ctrader-smc-bot
sudo install -m 0600 deploy/bot.env.example /etc/ctrader-smc-bot/bot.env
# Edit /etc/ctrader-smc-bot/bot.env with real credentials. Never commit it.
sudo install -m 0644 deploy/ctrader-mongo.service /etc/systemd/system/
sudo install -m 0644 deploy/ctrader-smc-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ctrader-mongo.service
sudo systemctl enable --now ctrader-smc-bot.service
```

The Mongo service publishes `127.0.0.1:27017` only. The bot environment must
therefore use `mongodb://127.0.0.1:27017/ctrader_db`. The Mongo unit waits for
the container health check before the bot starts.

### Optional API and OAuth service

The API is disabled by default. Start it only when the OAuth callback or API is
needed, using the same protected environment file:

```bash
sudo CTRADER_ENV_FILE=/etc/ctrader-smc-bot/bot.env \
  docker compose --profile api up -d --build
```

It binds to `127.0.0.1:8000` and uses the Compose Mongo hostname internally.
Use a private reverse proxy or an SSH tunnel if remote OAuth access is needed.

### Compose-only development commands

```bash
docker compose up -d mongo
docker compose --profile api up -d --build
docker compose logs -f mongo api
```

The repository `.dockerignore` excludes credentials, virtual environments,
local databases, logs, and generated market data from image builds.

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
