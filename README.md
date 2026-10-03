# Candle Trailing Bot

A Python trading bot built on the [Alpaca](https://alpaca.markets) API. It watches a list of stocks on 5-minute candles and buys when a candle closes. Each trade is protected by a stop-loss, and once a profit target is reached, a trailing stop follows the highest price and sells on a pullback.

It runs in **paper-trading mode by default**, so no real money is used.

> **Disclaimer:** This project is for educational purposes only and is not financial advice. Trading involves risk. Test on paper trading for several weeks before ever considering real money.

## Features

- Trades several stocks at once, each tracked independently
- Buys when a candle fully closes
- Stop-loss, profit target and trailing stop exits
- Limit on how many stocks are held at the same time
- Resumes any existing positions in your Alpaca account on restart
- Saves every message to `bot.log` and every finished trade to `trades.csv`
- API keys kept in a private `.env` file
- Paper trading by default

## How it works

For each stock in `SYMBOLS`:

1. **Entry:** when a new candle closes and you hold no position in that stock (and fewer than `MAX_POSITIONS` stocks are open), the bot buys at market.
2. **Stop-loss:** if the price falls `STOP_LOSS_PCT` below the entry price, the bot sells.
3. **Profit target:** once the price reaches `MIN_PROFIT_PCT` above entry, the trailing stop turns on.
4. **Trailing stop:** after the target is reached, the bot tracks the highest price and sells if the price drops `TRAIL_PCT` below it.
5. The bot then waits for the next closed candle and repeats.

**Example:** you buy at $100 with a 0.3% stop-loss, a 0.5% target and a 0.5% trail. The stop-loss sits at $99.70. If the price reaches $100.50, the trailing stop activates. If it climbs to $101 and then falls to $100.49, the bot sells for a small profit.

## Requirements

- Python 3.10 or newer
- A free Alpaca account with paper-trading API keys
- Libraries: `alpaca-py` and `python-dotenv`

## Setup

1. **Clone or download** this project and open the folder in VS Code.

2. **Create and activate a virtual environment** (Git Bash on Windows):
   ```bash
   python -m venv venv
   source venv/Scripts/activate
   ```
   On Mac/Linux, use `source venv/bin/activate`. You should see `(venv)` at the start of the terminal line.

3. **Install the libraries** (with `(venv)` showing):
   ```bash
   pip install alpaca-py python-dotenv
   ```

4. **Get your Alpaca keys:** sign up at alpaca.markets, choose the **Trading API**, switch the dashboard to **Paper Trading**, and generate API keys. The secret is shown only once, so copy it right away.

5. **Create a `.env` file** in the project folder (a file, not a folder), with no spaces or quotes:
   ```
   API_KEY=your_key_here
   SECRET_KEY=your_secret_here
   ```

6. **Run the bot:**
   ```bash
   python bot.py
   ```
   Stop it any time with `Ctrl+C`.

## Configuration

Edit the settings at the top of `bot.py`:

| Setting | Default | Meaning |
|---|---|---|
| `PAPER` | `True` | Keep `True` to use paper trading |
| `SYMBOLS` | `["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL"]` | Stocks to watch (valid US tickers) |
| `QTY` | `1` | Shares per trade, for each stock |
| `MAX_POSITIONS` | `3` | Maximum stocks held at the same time |
| `CANDLE_MINUTES` | `5` | Candle size in minutes |
| `STOP_LOSS_PCT` | `0.003` | Sell if price falls 0.3% below entry |
| `MIN_PROFIT_PCT` | `0.005` | Trailing stop activates 0.5% above entry |
| `TRAIL_PCT` | `0.005` | After the target, sell if price drops 0.5% from the high |
| `POLL_SECONDS` | `2` | How often held stocks are checked |
| `CANDLE_CHECK_SECONDS` | `5` | How often new candles are looked for |

## Output files

- **`bot.log`** has every message with date and time.
- **`trades.csv`** has one row per finished trade: time, symbol, quantity, entry, exit, profit/loss, profit %, and reason (`stop_loss` or `trailing_stop`). It opens in Excel.

## Market hours

US stocks trade Monday to Friday, 9:30 AM to 4:00 PM Eastern Time (about 7:00 PM to 1:30 AM India time). Outside these hours the bot prints "Market closed" and waits. Positions are held until the market reopens.

## Project structure

```
candle-bot/
├── bot.py          # the trading bot
├── .env            # your API keys (never share or upload)
├── bot.log         # created when the bot runs
├── trades.csv      # created after the first completed trade
└── venv/           # virtual environment (do not upload)
```

