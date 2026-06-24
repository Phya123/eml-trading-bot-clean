import os, time, logging, sys
import pandas as pd
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

# CONFIG
MY_SYMBOLS = ["XLE", "SPCX", "QQQ", "SPY"]
MAX_CAPITAL_USAGE = 0.15
MIN_ORDER_VALUE = 5.00
STOP_LOSS_PCT = 0.02
TAKE_PROFIT_PCT = 0.05
TRAILING_STOP_PCT = 0.02
DAILY_LOSS_LIMIT = 0.03
MA_PERIOD = 200

# LOGGING
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", stream=sys.stdout)
logger = logging.getLogger()

# API
api = TradingClient(
    os.environ.get("APCA_API_KEY_ID"),
    os.environ.get("APCA_API_SECRET_KEY"),
    paper=True
)

data_api = StockHistoricalDataClient(
    os.environ.get("APCA_API_KEY_ID"),
    os.environ.get("APCA_API_SECRET_KEY")
)

# STATE
state = {"start_equity": None}
trading_enabled = True


def check_circuit_breaker():
    global trading_enabled

    try:
        acc = api.get_account()

        if state["start_equity"] is None:
            state["start_equity"] = float(acc.equity)

        current_equity = float(acc.equity)

        if current_equity < state["start_equity"] * (1 - DAILY_LOSS_LIMIT):
            logger.critical("🚨 CIRCUIT BREAKER TRIGGERED - STOPPING TRADING")
            trading_enabled = False

    except Exception as e:
        logger.error(f"Circuit breaker failed: {e}")


def get_price_data(symbol):
    try:
        req = StockBarsRequest(
            symbol_or_symbols=[symbol],
            timeframe=TimeFrame.Day,
            limit=MA_PERIOD
        )

        bars = data_api.get_stock_bars(req)

        df = bars.df

        # handle multi-index safely
        if isinstance(df.index, pd.MultiIndex):
            df = df.xs(symbol)

        df = df.dropna()

        return df

    except Exception as e:
        logger.error(f"Data fetch error for {symbol}: {e}")
        return None


def market_trend_ok(symbol):
    df = get_price_data(symbol)
    if df is None or len(df) < MA_PERIOD:
        return False

    price = float(df["close"].iloc[-1])
    ma200 = float(df["close"].rolling(window=MA_PERIOD).mean().iloc[-1])

    if price < ma200:
        logger.info(f"Skipping {symbol}: price {price:.2f} below MA200 {ma200:.2f}")
        return False

    return True


def try_buy(symbol):
    try:
        positions = api.get_all_positions()

        if any(p.symbol == symbol for p in positions):
            return

        account = api.get_account()
        buying_power = float(account.buying_power)

        spend_amount = buying_power * MAX_CAPITAL_USAGE

        if spend_amount < MIN_ORDER_VALUE:
            return

        order = MarketOrderRequest(
            symbol=symbol,
            notional=round(spend_amount, 2),
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY
        )

        api.submit_order(order_data=order)
        logger.info(f"Bought ${spend_amount:.2f} of {symbol}")

    except Exception as e:
        logger.error(f"Buy failed for {symbol}: {e}")


def manage_positions():
    try:
        for p in api.get_all_positions():

            entry_price = float(p.avg_entry_price)
            current_price = float(p.current_price)

            pnl_up = entry_price * (1 + TAKE_PROFIT_PCT)
            pnl_down = entry_price * (1 - STOP_LOSS_PCT)

            # TAKE PROFIT
            if current_price >= pnl_up:
                api.close_position(p.symbol)
                logger.info(f"Take profit hit: {p.symbol}")
                continue

            # STOP LOSS
            if current_price <= pnl_down:
                api.close_position(p.symbol)
                logger.info(f"Stop loss hit: {p.symbol}")
                continue

    except Exception as e:
        logger.error(f"Position management failed: {e}")


# MAIN LOOP
logger.info("🚀 Sentinel v2.1 FIXED ONLINE")

while True:
    try:
        clock = api.get_clock()

        if clock.is_open and trading_enabled:
            check_circuit_breaker()

            for sym in MY_SYMBOLS:
                if market_trend_ok(sym):
                    try_buy(sym)

            manage_positions()

    except Exception as e:
        logger.error(f"Main loop error: {e}")

    time.sleep(60)
