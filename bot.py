"""
Multi-stock candle-close BUY bot with stop-loss, profit target and trailing stop
(Alpaca, paper trading by default).

Install:  pip install alpaca-py python-dotenv
Run:      python bot.py

Logic (applied to EACH stock in SYMBOLS independently):
  1. A candle closes and you hold no position in that stock -> BUY at market.
  2. STOP-LOSS: sell if price falls STOP_LOSS_PCT below your entry.
  3. After price reaches MIN_PROFIT_PCT above entry, a trailing stop turns on:
     sell if price falls TRAIL_PCT below the highest price since entry.
  4. MAX_POSITIONS limits how many stocks are held at the same time.

Files created next to this script:
  bot.log     every message, with date and time
  trades.csv  one row per finished trade

EDUCATIONAL ONLY. Test on paper trading first. Not financial advice.
"""

import csv
import os
import time
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestTradeRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

# ---------------- CONFIG ----------------
load_dotenv()
API_KEY = os.getenv("API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY")
PAPER = True                 # keep True until you fully trust the bot

SYMBOLS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL"]   # add or remove tickers here
QTY = 1                      # shares per trade, for each stock
MAX_POSITIONS = 3            # max stocks held at the same time
CANDLE_MINUTES = 5
MIN_PROFIT_PCT = 0.10      # trailing stop activates once price is 0.10% above entry
STOP_LOSS_PCT = 0.000        # sell if price falls 0% below entry
TRAIL_PCT = 0.005            # after target is hit, sell if price drops 0.5% from high
POLL_SECONDS = 2             # how often to check prices of held stocks
CANDLE_CHECK_SECONDS = 3     # how often to look for newly closed candles
# ----------------------------------------

LOG_FILE = "bot.log"
TRADES_FILE = "trades.csv"

trading = TradingClient(API_KEY, SECRET_KEY, paper=PAPER)
data = StockHistoricalDataClient(API_KEY, SECRET_KEY)
TIMEFRAME = TimeFrame(CANDLE_MINUTES, TimeFrameUnit.Minute)

# symbol -> {"qty", "entry", "highest", "target", "stop_loss", "armed"}
positions = {}


# ---------------- logging ----------------
def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def log_trade(symbol, qty, entry, exit_price, reason):
    new_file = not os.path.exists(TRADES_FILE)
    pnl = (exit_price - entry) * qty
    pnl_pct = (exit_price / entry - 1) * 100
    with open(TRADES_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["time", "symbol", "qty", "entry", "exit", "pnl", "pnl_pct", "reason"])
        w.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            symbol, qty, f"{entry:.2f}", f"{exit_price:.2f}",
            f"{pnl:.2f}", f"{pnl_pct:.2f}", reason,
        ])


# ---------------- market data ----------------
def market_open():
    return trading.get_clock().is_open


def last_closed_candle_times():
    """{symbol: timestamp of its most recent fully closed candle}"""
    now = datetime.now(timezone.utc)
    req = StockBarsRequest(
        symbol_or_symbols=SYMBOLS,
        timeframe=TIMEFRAME,
        start=now - timedelta(hours=2),
        feed=DataFeed.IEX,  # free real-time feed
    )
    bars = data.get_stock_bars(req).data
    result = {}
    for sym in SYMBOLS:
        closed = [
            b for b in bars.get(sym, [])
            if b.timestamp + timedelta(minutes=CANDLE_MINUTES) <= now
        ]
        if closed:
            result[sym] = closed[-1].timestamp
    return result


def latest_prices(symbols):
    """{symbol: latest trade price} for the given symbols"""
    req = StockLatestTradeRequest(symbol_or_symbols=list(symbols), feed=DataFeed.IEX)
    trades = data.get_stock_latest_trade(req)
    return {sym: float(t.price) for sym, t in trades.items()}


# ---------------- orders ----------------
def place_order(symbol, side, qty):
    order = trading.submit_order(
        MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=side,
            time_in_force=TimeInForce.DAY,
        )
    )
    # wait for the fill so we know the real price
    for _ in range(30):
        o = trading.get_order_by_id(order.id)
        if o.filled_avg_price:
            return float(o.filled_avg_price)
        time.sleep(1)
    raise RuntimeError(f"{symbol} order not filled in time")


def new_position(entry, qty):
    return {
        "qty": qty,
        "entry": entry,
        "highest": entry,
        "target": entry * (1 + MIN_PROFIT_PCT),
        "stop_loss": entry * (1 - STOP_LOSS_PCT),
        "armed": False,  # becomes True once price reaches the profit target
    }


def buy(symbol):
    log(f"{symbol}: candle closed, buying {QTY}")
    entry = place_order(symbol, OrderSide.BUY, QTY)
    pos = new_position(entry, QTY)
    positions[symbol] = pos
    log(f"{symbol}: bought at {entry:.2f} | target {pos['target']:.2f} | stop-loss {pos['stop_loss']:.2f}")


def sell(symbol, reason):
    pos = positions[symbol]
    exit_price = place_order(symbol, OrderSide.SELL, pos["qty"])
    pnl = (exit_price - pos["entry"]) * pos["qty"]
    log(f"{symbol}: {reason.upper()} sold at {exit_price:.2f} | P/L: {pnl:+.2f}")
    log_trade(symbol, pos["qty"], pos["entry"], exit_price, reason)
    del positions[symbol]


def check_exit(symbol, price):
    pos = positions[symbol]

    if price > pos["highest"]:
        pos["highest"] = price

    # 1) stop-loss
    if price <= pos["stop_loss"]:
        sell(symbol, "stop_loss")
        return

    # 2) profit target reached -> start trailing the high
    if not pos["armed"] and price >= pos["target"]:
        pos["armed"] = True
        log(f"{symbol}: profit target reached at {price:.2f}, trailing stop is now active")

    # 3) trailing stop (only after target is reached)
    if pos["armed"] and price <= pos["highest"] * (1 - TRAIL_PCT):
        sell(symbol, "trailing_stop")


def adopt_existing_positions():
    """Resume managing shares already held in your Alpaca account."""
    for p in trading.get_all_positions():
        if p.symbol in SYMBOLS:
            entry = float(p.avg_entry_price)
            positions[p.symbol] = new_position(entry, float(p.qty))
            log(f"Resuming existing position: {p.symbol} {p.qty} @ {entry:.2f}")


# ---------------- main loop ----------------
def run():
    log(f"Started. Watching {', '.join(SYMBOLS)} on {CANDLE_MINUTES}m candles "
        f"(paper={PAPER}, max positions={MAX_POSITIONS})")
    adopt_existing_positions()
    last_seen = last_closed_candle_times()  # ignore candles that closed before start
    last_candle_check = 0.0
    last_status = 0.0

    while True:
        try:
            if not market_open():
                log("Market closed, sleeping 60s")
                time.sleep(60)
                continue

            now = time.time()

            # 1) manage stocks we hold
            if positions:
                prices = latest_prices(list(positions))
                for sym in list(positions):
                    if sym in prices:
                        try:
                            check_exit(sym, prices[sym])
                        except Exception as e:
                            log(f"{sym}: error while managing trade: {e}")

                if positions and now - last_status >= 60:
                    last_status = now
                    parts = [
                        f"{s} {prices.get(s, 0):.2f} (entry {p['entry']:.2f}, stop {p['stop_loss']:.2f})"
                        for s, p in positions.items()
                    ]
                    log("Holding: " + " | ".join(parts))

            # 2) look for newly closed candles -> buy
            if now - last_candle_check >= CANDLE_CHECK_SECONDS:
                last_candle_check = now
                for sym, ts in last_closed_candle_times().items():
                    if ts == last_seen.get(sym):
                        continue
                    last_seen[sym] = ts
                    if sym in positions or len(positions) >= MAX_POSITIONS:
                        continue
                    try:
                        buy(sym)
                    except Exception as e:
                        log(f"{sym}: buy failed: {e}")

        except KeyboardInterrupt:
            log("Stopped by user")
            break
        except Exception as e:
            log(f"Error: {e}. Retrying in 10s")
            time.sleep(10)
            continue

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    run()
    