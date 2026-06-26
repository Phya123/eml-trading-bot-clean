import os, time, logging, sys, csv
import pandas as pd
from datetime import date, datetime

from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.client import TradingClient

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame


# =========================
# CONFIG
# =========================
SYMBOLS = ["SPY", "QQQ", "AAPL", "LMT", "XLE"]

TIMEFRAME = TimeFrame.Minute

FAST_MA = 20
SLOW_MA = 50
ATR_PERIOD = 14

MAX_CAPITAL_USAGE = 0.05

STOP_LOSS_PCT = 0.02
TAKE_PROFIT_PCT = 0.04
TRAILING_STOP_PCT = 0.015

COOLDOWN_SECONDS = 120
DAILY_LOSS_LIMIT = 0.03
MAX_TRADES_PER_DAY = 10

ENABLE_TRADING = True

TRADE_LOG_FILE = "trade_journal.csv"


# =========================
# STRATEGY MODES
# =========================
STRATEGY_MODE = {
    "AAPL": "FAST",
    "LMT": "SLOW",
    "SPY": "DEFAULT",
    "QQQ": "DEFAULT",
    "XLE": "DEFAULT"
}


# =========================
# LOGGING
# =========================
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger()


# =========================
# API
# =========================
api = TradingClient(
    os.environ.get("APCA_API_KEY_ID"),
    os.environ.get("APCA_API_SECRET_KEY"),
    paper=False
)

data_api = StockHistoricalDataClient(
    os.environ.get("APCA_API_KEY_ID"),
    os.environ.get("APCA_API_SECRET_KEY")
)


# =========================
# STATE
# =========================
state = {
    "start_equity": None,
    "last_trade_time": {},
    "position_high": {},
    "trade_count": 0,
    "day": date.today(),
    "vol_history": {},
    "skip_reasons": {s: {} for s in SYMBOLS}
}

for sym in SYMBOLS:
    state["vol_history"][sym] = []


# =========================
# DASHBOARD
# =========================
trade_stats = {
    "trades": 0,
    "wins": 0,
    "losses": 0,
    "pnl": 0.0
}


# =========================
# EMERGENCY STOP
# =========================
def emergency_stop(reason):
    global ENABLE_TRADING
    ENABLE_TRADING = False
    logger.critical(f"🚨 EMERGENCY STOP: {reason}")


# =========================
# DASHBOARD OUTPUT
# =========================
def print_dashboard():
    trades = trade_stats["trades"]
    wins = trade_stats["wins"]
    losses = trade_stats["losses"]
    pnl = trade_stats["pnl"]

    win_rate = (wins / trades * 100) if trades > 0 else 0

    logger.info("===================================")
    logger.info("📊 LIVE DASHBOARD")
    logger.info(f"Trades: {trades}")
    logger.info(f"Wins: {wins} | Losses: {losses}")
    logger.info(f"Win Rate: {win_rate:.2f}%")
    logger.info(f"PnL: {pnl:.4f}")
    logger.info("===================================")


# =========================
# DATA
# =========================
def get_data(symbol):
    try:
        req = StockBarsRequest(
            symbol_or_symbols=[symbol],
            timeframe=TIMEFRAME,
            limit=200
        )

        bars = data_api.get_stock_bars(req)
        df = bars.df

        if df is None or len(df) == 0:
            return None

        if isinstance(df.index, pd.MultiIndex):
            df = df.xs(symbol)

        df = df.dropna()

        if len(df) < 60:
            return None

        return df

    except Exception:
        return None


# =========================
# ANALYZE (WITH REASON TRACKING)
# =========================
def analyze(symbol):
    logger.info(f"STARTING ANALYSIS FOR {symbol}")

    df = get_data(symbol)
    if df is None:
        return 0.0, "BAD_DATA", "BAD_DATA"

    price = float(df["close"].iloc[-1])

    fast = df["close"].rolling(FAST_MA).mean().iloc[-1]
    slow = df["close"].rolling(SLOW_MA).mean().iloc[-1]
    vol = (df["high"] - df["low"]).rolling(ATR_PERIOD).mean().iloc[-1]

    if pd.isna(fast) or pd.isna(slow) or pd.isna(vol):
        return price, "NO_SIGNAL", "INDICATOR_NA"

    trend = "BULLISH" if fast > slow else "BEARISH"

    current_vol_ratio = vol / price
    state["vol_history"][symbol].append(current_vol_ratio)

    if len(state["vol_history"][symbol]) > 20:
        state["vol_history"][symbol].pop(0)

    avg = sum(state["vol_history"][symbol]) / len(state["vol_history"][symbol])
    threshold = avg * 0.75 if avg > 0 else 0.0010

    if current_vol_ratio < threshold:
        return price, f"{trend}_LOW_VOL_SKIP", "LOW_VOL"

    return price, trend, "OK"


# =========================
# BUY ENGINE
# =========================
def buy(symbol):

    try:
        if not api.get_clock().is_open:
            logger.info(f"SKIP {symbol} MARKET_CLOSED")
            return "MARKET_CLOSED"

    except:
        return "MARKET_ERROR"

    if state["trade_count"] >= MAX_TRADES_PER_DAY:
        logger.info(f"{symbol} SKIP MAX_TRADES")
        return "MAX_TRADES"

    positions = api.get_all_positions()
    if any(p.symbol == symbol for p in positions):
        logger.info(f"{symbol} SKIP POSITION_EXISTS")
        return "POSITION_EXISTS"

    price, signal, reason = analyze(symbol)

    logger.info(f"{symbol} SIGNAL: {signal}")

    if signal != "BULLISH":
        logger.info(f"{symbol} NOT TRADED ({reason})")
        return reason

    account = api.get_account()
    spend = float(account.buying_power) * MAX_CAPITAL_USAGE

    if spend < 5:
        return "INSUFFICIENT_FUNDS"

    try:
        order = MarketOrderRequest(
            symbol=symbol,
            notional=round(spend, 2),
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY
        )

        api.submit_order(order_data=order)

        state["trade_count"] += 1
        state["last_trade_time"][symbol] = time.time()

        trade_stats["trades"] += 1

        logger.info(f"BUY CONFIRMED {symbol} ${spend:.2f}")

        return "TRADED"

    except Exception as e:
        logger.info(f"{symbol} BUY ERROR {e}")
        return "ERROR"


# =========================
# POSITION MANAGEMENT
# =========================
def manage_positions():
    try:
        positions = api.get_all_positions()

        for p in positions:
            symbol = p.symbol
            entry = float(p.avg_entry_price)
            price = float(p.current_price)

            pnl_pct = (price - entry) / entry

            reason = None

            if pnl_pct >= TAKE_PROFIT_PCT:
                reason = "TAKE_PROFIT"
            elif pnl_pct <= -STOP_LOSS_PCT:
                reason = "STOP_LOSS"

            if reason:
                api.close_position(symbol)
                logger.info(f"{symbol} EXIT {reason}")

    except Exception as e:
        logger.info(f"POSITION ERROR {e}")


# =========================
# MAIN LOOP
# =========================
logger.info("SENTINEL LIVE ENGINE STARTED")

while True:
    try:
        for sym in SYMBOLS:
            logger.info(f"LOOP START -> {sym}")
            buy(sym)

        manage_positions()
        print_dashboard()

    except Exception as e:
        logger.info(f"LOOP ERROR {e}")

    time.sleep(60)
