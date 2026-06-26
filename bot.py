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
    "last_order_id": {}
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
            logger.warning(f"{symbol} BAD_DATA: empty bars response")
            return None

        df = bars.df

        if isinstance(df.index, pd.MultiIndex):
            try:
                df = df.xs(symbol)
            except Exception:
                logger.warning(f"{symbol} BAD_DATA: cannot extract symbol from MultiIndex")
                return None

        df = df.dropna()

        if df is None or len(df) < 60:
            logger.warning(f"{symbol} BAD_DATA: insufficient rows {len(df) if df is not None else 0}")
            return None

        return df

    except Exception as e:
        logger.error(f"{symbol} data error: {e}")
        return None


# =========================
# BUY ENGINE (PATCHED ONLY)
# =========================
def buy(symbol):
    global ENABLE_TRADING

    try:
        clock = api.get_clock()
        if not clock.is_open:
            logger.info(f"SKIP {symbol} - MARKET CLOSED")
            return
    except:
        return

    if not ENABLE_TRADING:
        return

    if state["trade_count"] >= MAX_TRADES_PER_DAY:
        return

    positions = api.get_all_positions()
    if any(p.symbol == symbol for p in positions):
        return

    df = get_data(symbol)
    if df is None:
        return

    price = float(df["close"].iloc[-1])
    fast = df["close"].rolling(FAST_MA).mean().iloc[-1]
    slow = df["close"].rolling(SLOW_MA).mean().iloc[-1]

    trend = "BULLISH" if fast > slow else "BEARISH"

    logger.info(f"{symbol} SIGNAL RAW -> {trend}")

    if trend != "BULLISH":
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

        # 🔥 SUBMIT ORDER
        response = api.submit_order(order_data=order)

        # 🔥 FIX: LOG EVERYTHING (THIS WAS YOUR MAIN ISSUE)
        logger.info(f"""
========================
ORDER PLACED
Symbol: {symbol}
Order ID: {response.id}
Status: {response.status}
Notional: {spend}
Trend: {trend}
========================
""")

        state["last_order_id"][symbol] = response.id
        state["last_trade_time"][symbol] = time.time()
        state["trade_count"] += 1

    except Exception as e:
        logger.error(f"{symbol} buy error: {e}")


# =========================
# POSITION MANAGEMENT (UNCHANGED)
# =========================
def manage_positions():
    try:
        positions = api.get_all_positions()

        for p in positions:
            symbol = p.symbol
            entry = float(p.avg_entry_price)
            price = float(p.current_price)

            if symbol not in state["position_high"]:
                state["position_high"][symbol] = price

            state["position_high"][symbol] = max(
                state["position_high"][symbol],
                price
            )

            pnl_pct = (price - entry) / entry

            reason = None

            if pnl_pct >= TAKE_PROFIT_PCT:
                reason = "TAKE_PROFIT"
            elif pnl_pct <= -STOP_LOSS_PCT:
                reason = "STOP_LOSS"
            elif price <= state["position_high"][symbol] * (1 - TRAILING_STOP_PCT):
                reason = "TRAIL_STOP"

            if reason:
                api.close_position(symbol)
                logger.info(f"{symbol} EXIT ({reason})")

    except Exception as e:
        logger.error(f"position error: {e}")


# =========================
# MAIN LOOP
# =========================
logger.info("🚀 SENTINEL LIVE ENGINE STARTED")

while True:
    try:
        if api.get_clock().is_open:
            for sym in SYMBOLS:
                logger.info(f"LOOP START -> {sym}")
                buy(sym)

            manage_positions()

        else:
            logger.info("Market closed")

    except Exception as e:
        logger.error(f"loop error: {e}")

    time.sleep(60) look at my code does it fix the issue that my bot bought xle and lmt but my logs don't show 
