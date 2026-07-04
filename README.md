# 🤖 GMGN Ahong Bot — Solana Meme Coin Sniper

Multi-filter sniper bot for **Solana Pump.fun** tokens using [GMGN OpenAPI CLI](https://gmgn.ai).

Scans from **3 sources** (Sniper/Trenches, Trending, Smart Money), scores with a multi-factor algorithm, and auto-buys with TP/SL strategy.

---

## ✨ Features

- 🔫 **Sniper** — New token creation on Pump.fun
- 📈 **Trending** — Momentum-based tokens with volume & price change filters
- 🐳 **Smart Money** — Tokens with KOL/smart money activity
- 🧠 **Scoring** — Rug ratio, bundler rate, holder count, smart degen, market cap
- 🛡️ **Filters** — Max rug ratio, dev hold rate, min holders, MC range
- 🎯 **TP/SL** — Trailing take-profit + stop-loss via GMGN conditional orders
- 📱 **Telegram** — Real-time notifications for BUY, SELL, errors
- 📊 **PnL Tracking** — Local trade log + position tracking
- 🧠 **Auto-Learning** — Adjusts parameters based on trade history

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- [GMGN CLI](https://gmgn.ai) installed & authenticated
- Solana wallet with SOL balance
- Telegram bot token (optional, for notifications)

### Installation

```bash
# Clone repo
git clone https://github.com/YOUR_USERNAME/gmgn-ahong-bot.git
cd gmgn-ahong-bot

# Copy config
cp config.example.json ~/.gmgn_sniper/config.json
cp .env.example ~/.gmgn_sniper/.env

# Edit config with your wallet & settings
nano ~/.gmgn_sniper/config.json
nano ~/.gmgn_sniper/.env

# Run
python3 sniper_bot.py
```

### PM2 Setup (Recommended)

```bash
pm2 start sniper_bot.py --name gmgn-sniper --update-env --interpreter python3
pm2 save
```

---

## ⚙️ Configuration

### `config.json`

| Parameter | Description | Default |
|---|---|---|
| `wallet_address` | Your Solana wallet address | — |
| `max_sol_per_trade` | SOL amount per trade | 0.05 |
| `max_positions` | Max concurrent open positions | 2 |
| `slippage` | Slippage tolerance % | 4 |
| `priority_fee` | Priority fee in SOL | 0.00005 |
| `tip_fee` | Jito tip fee in SOL | 0.0001 |
| `loop_interval_seconds` | Scan interval | 30 |

### Filters

| Filter | Description | Default |
|---|---|---|
| `max_rug_ratio` | Max rug score (0-1) | 0.15 |
| `max_dev_hold_rate` | Max dev holding % | 6% |
| `min_market_cap` | Min MC in USD | $200 |
| `max_market_cap` | Max MC in USD | $100K |
| `min_holders` | Min holder count | 50 |

### TP/SL Strategy

| Level | Type | Trigger | Sell | Drawdown |
|---|---|---|---|---|
| 🟢 **TP1** | `profit_stop` | **+30%** | **70%** | Fixed |
| 🟣 **TP2** | `profit_stop_trace` | **+100%** | **100%** | 30% trailing |
| 🔴 **SL** | `loss_stop` | **-20%** | **100%** | Fixed |

**Strategy Logic:**
- **+30% gain** → sell 70% to secure profit + capital
- Continues to **+100%** → trailing stop activates on remaining 30%
- If price drops 30% from peak → trailing sells remaining position
- **-20% loss** → full stop loss cut

---

## 📊 Data & Analytics

The `trade_data/` directory contains comprehensive trade history:

| File | Source | Rows | Description |
|---|---|---|---|
| `gmgn_trade_history_full.csv` | **All sources merged** | 226 | Unified trade data from 5 sources |
| — GMGN API | `gmgn-cli` activities | 20 | On-chain buy/sell records |
| — Bot Local | `trade_log.json` | 102 | Local PnL tracking |
| — Bot Positions | `positions.json` | 102 | Detailed position data |
| — GMGN Stats | Portfolio stats | 1 | Aggregate performance metrics |
| — Solscan RPC | Solana RPC | 1 | Current wallet holdings |

### CSV Columns (47 fields)

```
source, trade_id, timestamp, event_type, token_symbol, token_address,
token_amount, quote_amount_sol, buy_cost_usd, sold_usd, pnl_usd, pnl_pct,
pnl_sol, is_win, score_at_buy, rug_ratio, source_strat, timestamp_open,
timestamp_close, entry_price, smart_degen, bundler_rate, holder_count,
price_usd, launchpad, tx_hash, gas_usd, dex_usd, priority_fee_sol, tip_fee_sol,
+ aggregate stats fields
```

---

## 🧪 Scoring Algorithm

Base score: **30** (max 100)

| Factor | Bonus/Penalty |
|---|---|
| Rug ratio < 5% | +20 |
| Rug ratio 5-10% | +10 |
| Rug ratio > 25% | **-30** |
| Smart degen ≥ 5 | +15 |
| Bundler rate > 50% | **-30** |
| Holders > 500 | +15 |
| Holders < 10 | -10 |
| MC > $50K | +10 |
| Renounced mint | +5 |
| Creator still holding | -10 |

**Min score threshold: 50** — tokens below this are skipped.

---

## 🛠️ Troubleshooting

### `NODE_CHANNEL_FD` Crash (SIGABRT)
When running under PM2, gmgn-cli can crash. The bot automatically strips this env var in `rg()`.

### 0 SOL Balance
GMGN API sometimes returns 0 SOL balance. The bot has a Solana RPC fallback.

### `stop_loss` Not Supported
GMGN only supports: `buy_low`, `profit_stop`, `loss_stop`, `profit_stop_trace`.

---

## 📝 License

MIT — use at your own risk! Trading meme coins is highly speculative. 🚀

---

## 🙋‍♂️ About

Built for personal use on Solana Pump.fun ecosystem. Not financial advice.