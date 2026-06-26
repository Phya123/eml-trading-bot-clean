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
    "vol_history": {}
}

for sym in SYMBOLS:
    state["vol_history"][sym] = []


# =========================
# LOG HELPERS
# =========================
def log(symbol, msg):
    logger.info(f"{symbol} {msg}")


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

        if bars is None or bars.df is None or len(bars.df) == 0:
            log(symbol, "BAD_DATA")
            return None

        df = bars.df

        if isinstance(df.index, pd.MultiIndex):
            try:
                df = df.xs(symbol)
            except:
                log(symbol, "BAD_DATA")
                return None

        df = df.dropna()

        if len(df) < 60:
            log(symbol, "BAD_DATA")
            return None

        return df

    except Exception as e:
        log(symbol, f"data error: {e}")
        return None


# =========================
# ATR
# =========================
def atr(df, period=14):
    high = df["high"]
    low = df["low"]
    close = df["close"]

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)

    return tr.rolling(period).mean().iloc[-1]


# =========================
# ANALYZE (FIXED VISIBILITY)
# =========================
def analyze(symbol):
    log(symbol, "STARTING ANALYSIS")

    df = get_data(symbol)
    if df is None:
        return 0.0, "BAD_DATA"

    price = float(df["close"].iloc[-1])

    fast = df["close"].rolling(FAST_MA).mean().iloc[-1]
    slow = df["close"].rolling(SLOW_MA).mean().iloc[-1]
    vol = atr(df, ATR_PERIOD)

    trend = "BULLISH" if fast > slow else "BEARISH"

    log(symbol, f"TREND={trend}")

    # 🔥 FIX: LESS AGGRESSIVE FILTER (was blocking all trades)
    if pd.isna(fast) or pd.isna(slow) or pd.isna(vol):
        return price, "NO_SIGNAL"

    # relaxed volatility filter
    current_vol_ratio = vol / price

    state["vol_history"][symbol].append(current_vol_ratio)
    if len(state["vol_history"][symbol]) > 20:
        state["vol_history"][symbol].pop(0)

    avg = sum(state["vol_history"][symbol]) / len(state["vol_history"][symbol])

    # FIX: no hard max() blocking everything
    threshold = avg * 0.75 if avg > 0 else 0.0010

    if current_vol_ratio < threshold:
        log(symbol, f"LOW_VOL_SKIP ({current_vol_ratio:.5f})")
        return price, f"{trend}_LOW_VOL_SKIP"

    return price, trend


# =========================
# BUY ENGINE
# =========================
def buy(symbol):

    try:
        if not api.get_clock().is_open:
            log(symbol, "SKIP MARKET CLOSED")
            return
    except:
        return

    if state["trade_count"] >= MAX_TRADES_PER_DAY:
        return

    positions = api.get_all_positions()
    if any(p.symbol == symbol for p in positions):
        return

    price, signal = analyze(symbol)

    log(symbol, f"SIGNAL: {signal}")

    if signal != "BULLISH":
        return

    account = api.get_account()
    spend = float(account.buying_power) * MAX_CAPITAL_USAGE

    if spend < 5:
        return

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

        # CLEAN OUTPUT (your requested format)
        logger.info(f"BUY CONFIRMED {symbol} ${spend:.2f}")

    except Exception as e:
        log(symbol, f"buy error: {e}")


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
                log(symbol, f"EXIT {reason}")

    except Exception as e:
        logger.info(f"position error: {e}")


# =========================
# MAIN LOOP
# =========================
logger.info("SENTINEL LIVE ENGINE STARTED")

while True:
    try:
        for sym in SYMBOLS:
            log(sym, "LOOP START")
            buy(sym)

        manage_positions()

    except Exception as e:
        logger.info(f"loop error: {e}")

    time.sleep(60)
