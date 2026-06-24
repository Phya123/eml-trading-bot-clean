import os, time, logging, sys
import pandas as pd
from datetime import datetime, date

from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.client import TradingClient

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame


# ======================
# CONFIG
# ======================
MY_SYMBOLS = ["XLE", "SPCX", "QQQ", "SPY"]

MAX_CAPITAL_USAGE = 0.15
MIN_ORDER_VALUE = 5.00

STOP_LOSS_PCT = 0.02
TAKE_PROFIT_PCT = 0.05
TRAILING_STOP_PCT = 0.02

DAILY_LOSS_LIMIT = 0.03
COOLDOWN_SECONDS = 120
MA_PERIOD = 200


# ======================
# LOGGING
# ======================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger()


# ======================
# API
# ======================
api = TradingClient(
    os.environ.get("APCA_API_KEY_ID"),
    os.environ.get("APCA_API_SECRET_KEY"),
    paper=True
)

data_api = StockHistoricalDataClient(
    os.environ.get("APCA_API_KEY_ID"),
    os.environ.get("APCA_API_SECRET_KEY")
)


# ======================
# STATE
# ======================
state = {
    "start_equity": None,
    "daily_pnl": 0.0,
    "last_trade_time": {},
    "position_high": {}  # symbol -> highest price since entry
}

trading_enabled = True
current_day = date.today()


# ======================
# HELPERS
# ======================
def reset_daily_state():
    global current_day
    today = date.today()

    if today != current_day:
        current_day = today
        state["daily_pnl"] = 0.0
        logger.info("🔄 Daily state reset")


def check_circuit_breaker():
    global trading_enabled

    try:
        acc = api.get_account()

        if state["start_equity"] is None:
            state["start_equity"] = float(acc.equity)

        equity = float(acc.equity)

        if equity < state["start_equity"] * (1 - DAILY_LOSS_LIMIT):
            trading_enabled = False
            logger.critical("🚨 CIRCUIT BREAKER TRIGGERED")

    except Exception as e:
        logger.error(f"Circuit breaker error: {e}")


def get_bars(symbol):
    try:
        req = StockBarsRequest(
            symbol_or_symbols=[symbol],
            timeframe=TimeFrame.Day,
            limit=MA_PERIOD
        )

        bars = data_api.get_stock_bars(req)
        df = bars.df

        if isinstance(df.index, pd.MultiIndex):
            df = df.xs(symbol)

        return df.dropna()

    except Exception as e:
        logger.error(f"Data error {symbol}: {e}")
        return None


def market_trend_ok(symbol):
    df = get_bars(symbol)
    if df is None or len(df) < MA_PERIOD:
        return False

    price = float(df["close"].iloc[-1])
    ma200 = float(df["close"].rolling(MA_PERIOD).mean().iloc[-1])

    return price > ma200


def cooldown_ok(symbol):
    last = state["last_trade_time"].get(symbol)
    if not last:
        return True
    return (time.time() - last) > COOLDOWN_SECONDS


# ======================
# TRADING LOGIC
# ======================
def try_buy(symbol):
    try:
        if not cooldown_ok(symbol):
            return

        positions = api.get_all_positions()
        if any(p.symbol == symbol for p in positions):
            return

        if not market_trend_ok(symbol):
            return

        account = api.get_account()
        buy_power = float(account.buying_power)

        spend = buy_power * MAX_CAPITAL_USAGE
        if spend < MIN_ORDER_VALUE:
            return

        order = MarketOrderRequest(
            symbol=symbol,
            notional=round(spend, 2),
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY
        )

        api.submit_order(order_data=order)

        state["last_trade_time"][symbol] = time.time()

        logger.info(f"BUY: ${spend:.2f} {symbol}")

    except Exception as e:
        logger.error(f"Buy error {symbol}: {e}")


def manage_positions():
    try:
        positions = api.get_all_positions()

        for p in positions:
            symbol = p.symbol
            entry = float(p.avg_entry_price)
            price = float(p.current_price)
            qty = float(p.qty)

            # update trailing high
            if symbol not in state["position_high"]:
                state["position_high"][symbol] = price
            else:
                state["position_high"][symbol] = max(
                    state["position_high"][symbol],
                    price
                )

            high = state["position_high"][symbol]

            # TAKE PROFIT
            if price >= entry * (1 + TAKE_PROFIT_PCT):
                api.close_position(symbol)
                logger.info(f"TAKE PROFIT {symbol}")
                continue

            # STOP LOSS
            if price <= entry * (1 - STOP_LOSS_PCT):
                api.close_position(symbol)
                logger.info(f"STOP LOSS {symbol}")
                continue

            # TRAILING STOP
            if price <= high * (1 - TRAILING_STOP_PCT):
                api.close_position(symbol)
                logger.info(f"TRAIL STOP {symbol}")
                continue

    except Exception as e:
        logger.error(f"Position error: {e}")


# ======================
# MAIN LOOP
# ======================
logger.info("🚀 Sentinel v3 LIVE")

while True:
    try:
        reset_daily_state()

        clock = api.get_clock()

        if clock.is_open and trading_enabled:
            check_circuit_breaker()

            for sym in MY_SYMBOLS:
                try_buy(sym)

            manage_positions()

    except Exception as e:
        logger.error(f"Main loop error: {e}")

    time.sleep(60)
