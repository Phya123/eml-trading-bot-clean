import os, time, logging, sys
import pandas as pd
from datetime import date
from csv import writer

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
COOLDOWN_SECONDS = 120

STOP_LOSS_PCT = 0.02
TAKE_PROFIT_PCT = 0.04
TRAILING_STOP_PCT = 0.015

DAILY_LOSS_LIMIT = 0.03

LOG_FILE = "trade_journal.csv"


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
    paper=True
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
}


# =========================
# JOURNAL
# =========================
def log_trade(data):
    file_exists = os.path.isfile(LOG_FILE)

    with open(LOG_FILE, "a", newline="") as f:
        w = writer(f)

        if not file_exists:
            w.writerow(["time", "symbol", "side", "entry", "exit", "pnl_pct", "reason"])

        w.writerow([
            data["time"],
            data["symbol"],
            data["side"],
            data["entry"],
            data["exit"],
            data["pnl_pct"],
            data["reason"]
        ])


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

        if isinstance(df.index, pd.MultiIndex):
            df = df.xs(symbol)

        return df.dropna()

    except Exception as e:
        logger.error(f"{symbol} data error: {e}")
        return None


# =========================
# INDICATORS
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


def analyze(symbol):
    df = get_data(symbol)

    if df is None or len(df) < 60:
        return None, "NO_DATA"

    price = float(df["close"].iloc[-1])

    fast = df["close"].rolling(FAST_MA).mean().iloc[-1]
    slow = df["close"].rolling(SLOW_MA).mean().iloc[-1]

    vol = atr(df, ATR_PERIOD)

    if pd.isna(fast) or pd.isna(slow) or pd.isna(vol):
        return price, "NO_SIGNAL"

    # regime filter
    if vol / price < 0.003:
        return price, "LOW_VOL_SKIP"

    if fast > slow:
        return price, "BULLISH"

    return price, "BEARISH"


# =========================
# RISK
# =========================
def cooldown_ok(symbol):
    last = state["last_trade_time"].get(symbol)
    if not last:
        return True
    return (time.time() - last) > COOLDOWN_SECONDS


# =========================
# BUY ENGINE
# =========================
def buy(symbol):
    try:
        if not cooldown_ok(symbol):
            return

        positions = api.get_all_positions()
        if any(p.symbol == symbol for p in positions):
            return

        price, signal = analyze(symbol)

        logger.info(f"{symbol} SIGNAL = {signal}")

        if signal != "BULLISH":
            return

        account = api.get_account()
        spend = float(account.buying_power) * 0.10

        if spend < 5:
            return

        order = MarketOrderRequest(
            symbol=symbol,
            notional=round(spend, 2),
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY
        )

        api.submit_order(order_data=order)

        state["last_trade_time"][symbol] = time.time()

        logger.info(f"BUY {symbol} ${spend:.2f}")

    except Exception as e:
        logger.error(f"{symbol} buy error: {e}")


# =========================
# POSITION MANAGEMENT (FIXED RESET LOGIC)
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

                # 🔥 FIX YOU REQUESTED (APPLIED CORRECTLY)
                state["position_high"].pop(symbol, None)
                state["last_trade_time"].pop(symbol, None)

                logger.info(f"{symbol} EXIT + STATE RESET")

                log_trade({
                    "time": str(date.today()),
                    "symbol": symbol,
                    "side": "SELL",
                    "entry": entry,
                    "exit": price,
                    "pnl_pct": pnl_pct,
                    "reason": reason
                })

    except Exception as e:
        logger.error(f"position error: {e}")


# =========================
# MAIN LOOP
# =========================
logger.info("🚀 SENTINEL v7 HEDGE FUND ENGINE LIVE")

while True:
    try:
        clock = api.get_clock()

        if clock.is_open:
            for sym in SYMBOLS:
                buy(sym)

            manage_positions()

        else:
            logger.info("Market closed")

    except Exception as e:
        logger.error(f"loop error: {e}")

    time.sleep(60)
