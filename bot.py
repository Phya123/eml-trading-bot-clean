import os, time, logging, sys
import pandas as pd
from datetime import date

from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.client import TradingClient

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame


# =========================
# CONFIG
# =========================
SYMBOLS = ["XLE", "SPCX", "QQQ", "SPY"]

TIMEFRAME = TimeFrame.Minute

FAST_MA = 20
SLOW_MA = 50
ATR_PERIOD = 14

MAX_RISK_PER_TRADE = 0.01
MAX_CAPITAL_USAGE = 0.05

STOP_LOSS_PCT = 0.02
TAKE_PROFIT_PCT = 0.04
TRAILING_STOP_PCT = 0.015

COOLDOWN_SECONDS = 120
DAILY_LOSS_LIMIT = 0.03
MAX_TRADES_PER_DAY = 10

ENABLE_TRADING = True


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
    "day": date.today()
}


# =========================
# EMERGENCY STOP
# =========================
def emergency_stop(reason):
    global ENABLE_TRADING
    ENABLE_TRADING = False
    logger.critical(f"🚨 EMERGENCY STOP: {reason}")


# =========================
# DAILY RESET
# =========================
def reset_daily_state():
    if date.today() != state["day"]:
        state["day"] = date.today()
        state["trade_count"] = 0
        logger.info("🔄 Daily reset completed")


# =========================
# CIRCUIT BREAKER
# =========================
def check_circuit_breaker():
    try:
        acc = api.get_account()

        if state["start_equity"] is None:
            state["start_equity"] = float(acc.equity)

        equity = float(acc.equity)

        if equity < state["start_equity"] * (1 - DAILY_LOSS_LIMIT):
            emergency_stop("Daily loss limit hit")

    except Exception as e:
        logger.error(f"Risk error: {e}")


# =========================
# DATA SAFETY
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

        if isinstance(df.index, pd.MultiIndex):
            df = df.xs(symbol)

        df = df.dropna()

        # BAD DATA FILTER
        if df is None or len(df) < 60 or df["close"].isnull().any():
            return None

        return df

    except Exception as e:
        logger.error(f"{symbol} data error: {e}")
        return None


# =========================
# ATR (VOLATILITY FILTER)
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
# STRATEGY
# =========================
def analyze(symbol):
    df = get_data(symbol)

    if df is None:
        return None, "BAD_DATA"

    price = float(df["close"].iloc[-1])

    fast = df["close"].rolling(FAST_MA).mean().iloc[-1]
    slow = df["close"].rolling(SLOW_MA).mean().iloc[-1]
    vol = atr(df, ATR_PERIOD)

    if pd.isna(fast) or pd.isna(slow) or pd.isna(vol):
        return price, "NO_SIGNAL"

    trend = "BULLISH" if fast > slow else "BEARISH"

    logger.info(
        f"{symbol} TREND={trend} FastMA={fast:.2f} SlowMA={slow:.2f}"
    )

    logger.info(
        f"{symbol} Price={price:.2f} ATR={vol:.4f} VolRatio={(vol/price):.4f}"
    )

    if vol / price < 0.0025:
        return price, f"{trend}_LOW_VOL_SKIP"

    return price, trend


# =========================
# SAFETY CHECKS
# =========================
def cooldown_ok(symbol):
    last = state["last_trade_time"].get(symbol)
    if not last:
        return True
    return (time.time() - last) > COOLDOWN_SECONDS


def market_open_safety():
    clock = api.get_clock()

    # SKIP FIRST 30 MINUTES (VERY IMPORTANT)
    if clock.is_open:
        if clock.timestamp.hour == 9 and clock.timestamp.minute < 40:
            return False
    return clock.is_open


# =========================
# EXECUTION SAFETY
# =========================
def verify_order(symbol):
    time.sleep(2)
    positions = api.get_all_positions()
    return any(p.symbol == symbol for p in positions)


# =========================
# BUY ENGINE
# =========================
def buy(symbol):
    global ENABLE_TRADING

    if not ENABLE_TRADING:
        return

    if state["trade_count"] >= MAX_TRADES_PER_DAY:
        return

    if not cooldown_ok(symbol):
        return

    positions = api.get_all_positions()
    if any(p.symbol == symbol for p in positions):
        return

    price, signal = analyze(symbol)

    logger.info(f"{symbol} SIGNAL: {signal}")

    if signal == "BULLISH":
    direction = "BUY"

elif signal == "BEARISH":
    direction = "BUY_DIP"

else:
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

        if not verify_order(symbol):
            logger.warning(f"{symbol} ORDER NOT CONFIRMED")
            return

        state["last_trade_time"][symbol] = time.time()
        state["trade_count"] += 1

        logger.info(f"BUY CONFIRMED {symbol} ${spend:.2f}")

    except Exception as e:
        logger.error(f"{symbol} buy error: {e}")


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

            if symbol not in state["position_high"]:
                state["position_high"][symbol] = price

            state["position_high"][symbol] = max(
                state["position_high"][symbol],
                price
            )

            high = state["position_high"][symbol]

            pnl_pct = (price - entry) / entry

            reason = None

            if pnl_pct >= TAKE_PROFIT_PCT:
                reason = "TAKE_PROFIT"

            elif pnl_pct <= -STOP_LOSS_PCT:
                reason = "STOP_LOSS"

            elif price <= high * (1 - TRAILING_STOP_PCT):
                reason = "TRAIL_STOP"

            if reason:
                api.close_position(symbol)

                # SAFE RESET (YOUR REQUIRED FIX)
                state["position_high"].pop(symbol, None)
                state["last_trade_time"].pop(symbol, None)

                logger.info(f"{symbol} EXIT + STATE RESET ({reason})")

    except Exception as e:
        logger.error(f"position error: {e}")


# =========================
# MAIN LOOP
# =========================
logger.info("🚀 SENTINEL v8 SAFE LIVE ENGINE STARTED")

while True:
    try:
        reset_daily_state()
        check_circuit_breaker()

        if market_open_safety():
            for sym in SYMBOLS:
                buy(sym)

            manage_positions()
        else:
            logger.info(
    f"Market Open={api.get_clock().is_open} | Trades Today={state['trade_count']}"
            )
    except Exception as e:
        logger.error(f"loop error: {e}")

    time.sleep(60)
