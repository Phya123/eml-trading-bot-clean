import os, time, logging, json, sys, traceback
import pandas as pd

from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.requests import LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# CONFIG
MY_SYMBOLS = ["XLE", "SPCX", "QQQ", "SPY"]
MAX_CAPITAL_USAGE = 0.15
MIN_ORDER_VALUE = 5.00
STOP_LOSS_PCT = 0.02
TAKE_PROFIT_PCT = 0.05
TRAILING_STOP_PCT = 0.02
DAILY_LOSS_LIMIT = 0.03
MA_PERIOD = 200
COOLDOWN_SECONDS = 1800
STATE_FILE = "sentinel_state.json"

# LOGGING
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", stream=sys.stdout)
logger = logging.getLogger()

# API
api = TradingClient(os.environ.get("APCA_API_KEY_ID"), os.environ.get("APCA_API_SECRET_KEY"), paper=False)
data_api = StockHistoricalDataClient(os.environ.get("APCA_API_KEY_ID"), os.environ.get("APCA_API_SECRET_KEY"))

# STATE
state = {"start_equity": None, "last_trade_time": {}, "highs": {}}
trading_enabled = True

def get_market_trend():
    bars = data_api.get_stock_bars(StockBarsRequest(symbol_or_symbols="SPY", timeframe=TimeFrame.Day, limit=MA_PERIOD)).df
    return bars["close"].iloc[-1] > bars["close"].mean() if not bars.empty else False

def run_sentinel():
    global trading_enabled
    logger.info("Running sentinel cycle")
    
    acc = api.get_account()
    logger.info(f"Cash: ${acc.cash} | Equity: ${acc.equity}")
    
    trend = get_market_trend()
    logger.info(f"Market trend check: {trend}")
    
    positions = api.get_all_positions()
    logger.info(f"Current positions: {[p.symbol for p in positions]}")
    
    if not trend:
        logger.info("Market trend filter blocked all new buys.")
        return

    for sym in MY_SYMBOLS:
        logger.info(f"Checking symbol: {sym}")
        # Add your buy logic here...

# MAIN LOOP
logger.info("Sentinel started")
while True:
    try:
        if api.get_clock().is_open and trading_enabled:
            run_sentinel()
        time.sleep(60)
    except Exception as e:
        logger.error(f"Loop Error: {e}")
        logger.error(traceback.format_exc())
        time.sleep(120)
