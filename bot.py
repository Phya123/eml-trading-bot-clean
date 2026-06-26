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
MA200 = 200          # ✅ ADDED
ATR_PERIOD = 14

MAX_CAPITAL_USAGE = 0.05

STOP_LOSS_PCT = 0.02
TAKE_PROFIT_PCT = 0.04

COOLDOWN_SECONDS = 120
DAILY_LOSS_LIMIT = 0.03
MAX_TRADES_PER_DAY = 10

ENABLE_TRADING = True


# =========================
# LOGGING
# =========================
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger()


def log(msg):
    logger.info(msg)


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
    "trade_count": 0,
    "day": date.today(),
    "vol_history": {}
}

for s in SYMBOLS:
    state["vol_history"][s] = []


trade_stats = {
    "trades": 0,
    "wins": 0,
    "losses": 0,
    "pnl": 0.0
}


# =========================
# CIRCUIT BREAKER (ADDED)
# =========================
def check_circuit_breaker():
    try:
        acc = api.get_account()

        if state["start_equity"] is None:
            state["start_equity"] = float(acc.equity)

        equity = float(acc.equity)

        drawdown = (state["start_equity"] - equity) / state["start_equity"]

        if drawdown >= DAILY_LOSS_LIMIT:
            global ENABLE_TRADING
            ENABLE_TRADING = False
            log(f"🚨 CIRCUIT BREAKER TRIGGERED (DD={drawdown:.2%})")

    except Exception as e:
        log(f"CIRCUIT ERROR {e}")


# =========================
# DATA
# =========================
def get_data(symbol):
    try:
        req = StockBarsRequest(
            symbol_or_symbols=[symbol],
            timeframe=TIMEFRAME,
            limit=250   # enough for MA200
        )

        bars = data_api.get_stock_bars(req)

        if bars is None or bars.df is None or len(bars.df) == 0:
            log(f"{symbol} BAD_DATA")
            return None

        df = bars.df

        if isinstance(df.index, pd.MultiIndex):
            df = df.xs(symbol)

        df = df.dropna()

        if len(df) < 210:
            log(f"{symbol} NOT_ENOUGH_DATA")
            return None

        return df

    except Exception as e:
        log(f"{symbol} DATA_ERROR {e}")
        return None


# =========================
# ATR (STANDARDIZED)
# =========================
def atr(df):
    high = df["high"]
    low = df["low"]
    close = df["close"]

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)

    return tr.rolling(ATR_PERIOD).mean().iloc[-1]


# =========================
# ANALYZE (WITH MA200 ADDED)
# =========================
def analyze(symbol):
    log(f"{symbol} START ANALYSIS")

    df = get_data(symbol)
    if df is None:
        return 0.0, "BAD_DATA", "BAD_DATA"

    price = float(df["close"].iloc[-1])

    fast = df["close"].rolling(FAST_MA).mean().iloc[-1]
    slow = df["close"].rolling(SLOW_MA).mean().iloc[-1]
    ma200 = df["close"].rolling(MA200).mean().iloc[-1]   # ✅ ADDED
    vol = atr(df)

    if pd.isna(fast) or pd.isna(slow) or pd.isna(ma200) or pd.isna(vol):
        return price, "NO_SIGNAL", "INDICATOR_NA"

    trend = "BULLISH" if fast > slow else "BEARISH"

    # =========================
    # MA200 FILTER (ADDED)
    # =========================
    if price < ma200:
        log(f"{symbol} BELOW MA200 -> NO LONGS")
        return price, "BELOW_MA200", "TREND_FILTER"

    # volatility ratio
    vol_ratio = vol / price

    state["vol_history"][symbol].append(vol_ratio)
    if len(state["vol_history"][symbol]) > 20:
        state["vol_history"][symbol].pop(0)

    avg = sum(state["vol_history"][symbol]) / len(state["vol_history"][symbol])
    threshold = avg * 0.75 if avg > 0 else 0.0010

    if vol_ratio < threshold:
        log(f"{symbol} LOW_VOL_SKIP {vol_ratio:.5f}")
        return price, f"{trend}_LOW_VOL_SKIP", "LOW_VOL"

    log(f"{symbol} TREND={trend} MA200_OK")
    return price, trend, "OK"


# =========================
# BUY ENGINE
# =========================
def buy(symbol):

    try:
        if not api.get_clock().is_open:
            log(f"{symbol} MARKET_CLOSED")
            return
    except:
        return

    if not ENABLE_TRADING:
        log(f"{symbol} BLOCKED CIRCUIT BREAKER")
        return

    price, signal, reason = analyze(symbol)

    log(f"{symbol} SIGNAL={signal}")

    if signal != "BULLISH":
        log(f"{symbol} NOT TRADED ({reason})")
        return

    account = api.get_account()
    spend = float(account.buying_power) * MAX_CAPITAL_USAGE

    if spend < 5:
        log(f"{symbol} INSUFFICIENT FUNDS")
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

        trade_stats["trades"] += 1

        log(f"BUY CONFIRMED {symbol} ${spend:.2f}")

    except Exception as e:
        log(f"{symbol} BUY_ERROR {e}")


# =========================
# POSITION MANAGEMENT
# =========================
def manage_positions():
    try:
        positions = api.get_all_positions()

        for p in positions:
            entry = float(p.avg_entry_price)
            price = float(p.current_price)

            pnl_pct = (price - entry) / entry

            if pnl_pct >= TAKE_PROFIT_PCT:
                api.close_position(p.symbol)
                log(f"{p.symbol} EXIT TAKE_PROFIT")

            elif pnl_pct <= -STOP_LOSS_PCT:
                api.close_position(p.symbol)
                log(f"{p.symbol} EXIT STOP_LOSS")

    except Exception as e:
        log(f"POSITION ERROR {e}")


# =========================
# MAIN LOOP
# =========================
log("SENTINEL LIVE ENGINE STARTED")

while True:
    try:
        check_circuit_breaker()   # ✅ ADDED

        for sym in SYMBOLS:
            log(f"LOOP START -> {sym}")
            buy(sym)

        manage_positions()

    except Exception as e:
        log(f"LOOP ERROR {e}")

    time.sleep(60)
