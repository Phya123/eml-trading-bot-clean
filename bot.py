import os, time, logging, json
import pandas as pd

from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.requests import LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# =========================
# CONFIG
# =========================
MY_SYMBOLS = ["XLE", "SPCX", "QQQ", "SPY"]

MAX_CAPITAL_USAGE = 0.15
MIN_ORDER_VALUE = 5.00

STOP_LOSS_PCT = 0.02
TAKE_PROFIT_PCT = 0.05
TRAILING_STOP_PCT = 0.02

DAILY_LOSS_LIMIT = 0.03
MA_PERIOD = 200
COOLDOWN_SECONDS = 1800  # 30 min safer cooldown

STATE_FILE = "sentinel_state.json"

# =========================
# LOGGING
# =========================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
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
# STATE (PERSISTENT)
# =========================
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {
        "start_equity": None,
        "last_trade_time": {},
        "highs": {}
    }

def save_state():
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

state = load_state()
trading_enabled = True

# =========================
# HELPERS
# =========================
def get_bars(symbol, limit=200, timeframe=TimeFrame.Day):
    try:
        bars = data_api.get_stock_bars(
            StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=timeframe,
                limit=limit
            )
        ).df

        if bars is None or bars.empty:
            return None
        return bars

    except Exception as e:
        logger.error(f"Bars error {symbol}: {e}")
        return None


def market_trend_ok():
    bars = get_bars("SPY", MA_PERIOD, TimeFrame.Day)
    if bars is None:
        return False
    return bars["close"].iloc[-1] > bars["close"].mean()


def cooldown_ok(symbol):
    last = state["last_trade_time"].get(symbol, 0)
    return time.time() - last > COOLDOWN_SECONDS


# =========================
# RISK CHECK
# =========================
def check_circuit_breaker():
    global trading_enabled

    acc = api.get_account()

    if state["start_equity"] is None:
        state["start_equity"] = float(acc.equity)
        save_state()

    equity = float(acc.equity)
    start = float(state["start_equity"])

    if equity < start * (1 - DAILY_LOSS_LIMIT):
        logger.critical("🚨 CIRCUIT BREAKER TRIGGERED")
        trading_enabled = False


# =========================
# POSITION MANAGEMENT
# =========================
def manage_positions():
    positions = api.get_all_positions()

    for p in positions:
        sym = p.symbol
        entry = float(p.avg_entry_price)
        price = float(p.current_price)

        if sym not in state["highs"]:
            state["highs"][sym] = price

        state["highs"][sym] = max(state["highs"][sym], price)

        high = state["highs"][sym]

        # STOP LOSS
        if price <= entry * (1 - STOP_LOSS_PCT):
            logger.info(f"🛑 Stop loss {sym}")
            api.close_position(sym)
            continue

        # TAKE PROFIT
        if price >= entry * (1 + TAKE_PROFIT_PCT):
            logger.info(f"💰 Take profit {sym}")
            api.close_position(sym)
            continue

        # TRAILING STOP
        if price <= high * (1 - TRAILING_STOP_PCT):
            logger.info(f"📉 Trailing stop {sym}")
            api.close_position(sym)
            continue


# =========================
# ENTRY LOGIC
# =========================
def try_buy(symbol):
    if not cooldown_ok(symbol):
        return

    bars = get_bars(symbol, 200, TimeFrame.Day)
    if bars is None:
        return

    price = float(bars["close"].iloc[-1])

    if price <= 0:
        return

    ma = bars["close"].mean()

    # trend filter
    if price < ma:
        return

    acc = api.get_account()
    cash = float(acc.cash)

    invest = cash * MAX_CAPITAL_USAGE

    if invest < MIN_ORDER_VALUE:
        return

    qty = round(invest / price, 4)

    if qty <= 0:
        return

    try:
        order = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            type="limit",
            limit_price=price,
            time_in_force=TimeInForce.DAY
        )

        api.submit_order(order)

        state["last_trade_time"][symbol] = time.time()
        save_state()

        logger.info(f"✅ BUY {symbol} @ {price}")

    except Exception as e:
        logger.error(f"Buy error {symbol}: {e}")


# =========================
# MAIN LOOP
# =========================
logger.info("🚀 Sentinel v2 Running (Paper Safe Mode)")

while True:
    try:
        if api.get_clock().is_open and trading_enabled:

            check_circuit_breaker()

            if not market_trend_ok():
                time.sleep(60)
                continue

            manage_positions()

            for sym in MY_SYMBOLS:
                try_buy(sym)

        time.sleep(60)

    except Exception as e:
        logger.error(f"Loop crash: {e}")
        time.sleep(120)import os, time, logging, json
import pandas as pd

from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.requests import LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# =========================
# CONFIG
# =========================
MY_SYMBOLS = ["XLE", "SPCX", "QQQ", "SPY"]

MAX_CAPITAL_USAGE = 0.15
MIN_ORDER_VALUE = 5.00

STOP_LOSS_PCT = 0.02
TAKE_PROFIT_PCT = 0.05
TRAILING_STOP_PCT = 0.02

DAILY_LOSS_LIMIT = 0.03
MA_PERIOD = 200
COOLDOWN_SECONDS = 1800  # 30 min safer cooldown

STATE_FILE = "sentinel_state.json"

# =========================
# LOGGING
# =========================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
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
# STATE (PERSISTENT)
# =========================
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {
        "start_equity": None,
        "last_trade_time": {},
        "highs": {}
    }

def save_state():
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

state = load_state()
trading_enabled = True

# =========================
# HELPERS
# =========================
def get_bars(symbol, limit=200, timeframe=TimeFrame.Day):
    try:
        bars = data_api.get_stock_bars(
            StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=timeframe,
                limit=limit
            )
        ).df

        if bars is None or bars.empty:
            return None
        return bars

    except Exception as e:
        logger.error(f"Bars error {symbol}: {e}")
        return None


def market_trend_ok():
    bars = get_bars("SPY", MA_PERIOD, TimeFrame.Day)
    if bars is None:
        return False
    return bars["close"].iloc[-1] > bars["close"].mean()


def cooldown_ok(symbol):
    last = state["last_trade_time"].get(symbol, 0)
    return time.time() - last > COOLDOWN_SECONDS


# =========================
# RISK CHECK
# =========================
def check_circuit_breaker():
    global trading_enabled

    acc = api.get_account()

    if state["start_equity"] is None:
        state["start_equity"] = float(acc.equity)
        save_state()

    equity = float(acc.equity)
    start = float(state["start_equity"])

    if equity < start * (1 - DAILY_LOSS_LIMIT):
        logger.critical("🚨 CIRCUIT BREAKER TRIGGERED")
        trading_enabled = False


# =========================
# POSITION MANAGEMENT
# =========================
def manage_positions():
    positions = api.get_all_positions()

    for p in positions:
        sym = p.symbol
        entry = float(p.avg_entry_price)
        price = float(p.current_price)

        if sym not in state["highs"]:
            state["highs"][sym] = price

        state["highs"][sym] = max(state["highs"][sym], price)

        high = state["highs"][sym]

        # STOP LOSS
        if price <= entry * (1 - STOP_LOSS_PCT):
            logger.info(f"🛑 Stop loss {sym}")
            api.close_position(sym)
            continue

        # TAKE PROFIT
        if price >= entry * (1 + TAKE_PROFIT_PCT):
            logger.info(f"💰 Take profit {sym}")
            api.close_position(sym)
            continue

        # TRAILING STOP
        if price <= high * (1 - TRAILING_STOP_PCT):
            logger.info(f"📉 Trailing stop {sym}")
            api.close_position(sym)
            continue


# =========================
# ENTRY LOGIC
# =========================
def try_buy(symbol):
    if not cooldown_ok(symbol):
        return

    bars = get_bars(symbol, 200, TimeFrame.Day)
    if bars is None:
        return

    price = float(bars["close"].iloc[-1])

    if price <= 0:
        return

    ma = bars["close"].mean()

    # trend filter
    if price < ma:
        return

    acc = api.get_account()
    cash = float(acc.cash)

    invest = cash * MAX_CAPITAL_USAGE

    if invest < MIN_ORDER_VALUE:
        return

    qty = round(invest / price, 4)

    if qty <= 0:
        return

    try:
        order = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            type="limit",
            limit_price=price,
            time_in_force=TimeInForce.DAY
        )

        api.submit_order(order)

        state["last_trade_time"][symbol] = time.time()
        save_state()

        logger.info(f"✅ BUY {symbol} @ {price}")

    except Exception as e:
        logger.error(f"Buy error {symbol}: {e}")


# =========================
# MAIN LOOP
# =========================
logger.info("🚀 Sentinel v2 Running (Paper Safe Mode)")

while True:
    try:
        if api.get_clock().is_open and trading_enabled:

            check_circuit_breaker()
import os, time, logging, json
import pandas as pd

from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.requests import LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# =========================
# CONFIG
# =========================
MY_SYMBOLS = ["XLE", "SPCX", "QQQ", "SPY"]

MAX_CAPITAL_USAGE = 0.15
MIN_ORDER_VALUE = 5.00

STOP_LOSS_PCT = 0.02
TAKE_PROFIT_PCT = 0.05
TRAILING_STOP_PCT = 0.02

DAILY_LOSS_LIMIT = 0.03
MA_PERIOD = 200
COOLDOWN_SECONDS = 1800  # 30 min safer cooldown

STATE_FILE = "sentinel_state.json"

# =========================
# LOGGING
# =========================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
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
# STATE (PERSISTENT)
# =========================
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {
        "start_equity": None,
        "last_trade_time": {},
        "highs": {}
    }

def save_state():
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

state = load_state()
trading_enabled = True

# =========================
# HELPERS
# =========================
def get_bars(symbol, limit=200, timeframe=TimeFrame.Day):
    try:
        bars = data_api.get_stock_bars(
            StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=timeframe,
                limit=limit
            )
        ).df

        if bars is None or bars.empty:
            return None
        return bars

    except Exception as e:
        logger.error(f"Bars error {symbol}: {e}")
        return None


def market_trend_ok():
    bars = get_bars("SPY", MA_PERIOD, TimeFrame.Day)
    if bars is None:
        return False
    return bars["close"].iloc[-1] > bars["close"].mean()


def cooldown_ok(symbol):
    last = state["last_trade_time"].get(symbol, 0)
    return time.time() - last > COOLDOWN_SECONDS


# =========================
# RISK CHECK
# =========================
def check_circuit_breaker():
    global trading_enabled

    acc = api.get_account()

    if state["start_equity"] is None:
        state["start_equity"] = float(acc.equity)
        save_state()

    equity = float(acc.equity)
    start = float(state["start_equity"])

    if equity < start * (1 - DAILY_LOSS_LIMIT):
        logger.critical("🚨 CIRCUIT BREAKER TRIGGERED")
        trading_enabled = False


# =========================
# POSITION MANAGEMENT
# =========================
def manage_positions():
    positions = api.get_all_positions()

    for p in positions:
        sym = p.symbol
        entry = float(p.avg_entry_price)
        price = float(p.current_price)

        if sym not in state["highs"]:
            state["highs"][sym] = price

        state["highs"][sym] = max(state["highs"][sym], price)

        high = state["highs"][sym]

        # STOP LOSS
        if price <= entry * (1 - STOP_LOSS_PCT):
            logger.info(f"🛑 Stop loss {sym}")
            api.close_position(sym)
            continue

        # TAKE PROFIT
        if price >= entry * (1 + TAKE_PROFIT_PCT):
            logger.info(f"💰 Take profit {sym}")
            api.close_position(sym)
            continue

        # TRAILING STOP
        if price <= high * (1 - TRAILING_STOP_PCT):
            logger.info(f"📉 Trailing stop {sym}")
            api.close_position(sym)
            continue


# =========================
# ENTRY LOGIC
# =========================
def try_buy(symbol):
    if not cooldown_ok(symbol):
        return

    bars = get_bars(symbol, 200, TimeFrame.Day)
    if bars is None:
        return

    price = float(bars["close"].iloc[-1])

    if price <= 0:
        return

    ma = bars["close"].mean()

    # trend filter
    if price < ma:
        return

    acc = api.get_account()
    cash = float(acc.cash)

    invest = cash * MAX_CAPITAL_USAGE

    if invest < MIN_ORDER_VALUE:
        return

    qty = round(invest / price, 4)

    if qty <= 0:
        return

    try:
        order = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            type="limit",
            limit_price=price,
            time_in_force=TimeInForce.DAY
        )

        api.submit_order(order)

        state["last_trade_time"][symbol] = time.time()
        save_state()

        logger.info(f"✅ BUY {symbol} @ {price}")

    except Exception as e:
        logger.error(f"Buy error {symbol}: {e}")


# =========================
# MAIN LOOP
# =========================
logger.info("🚀 Sentinel v2 Running (Paper Safe Mode)")

while True:
    try:
        if api.get_clock().is_open and trading_enabled:

            check_circuit_breaker()

            if not market_trend_ok():
                time.sleep(60)
                continue

            manage_positions()

            for sym in MY_SYMBOLS:
                try_buy(sym)

        time.sleep(60)

    except Exception as e:
        logger.error(f"Loop crash: {e}")
        time.sleep(120)
            if not market_trend_ok():
                time.sleep(60)
                continue

            manage_positions()

            for sym in MY_SYMBOLS:
                try_buy(sym)

        time.sleep(60)

    except Exception as e:
        logger.error(f"Loop crash: {e}")
        time.sleep(120)
