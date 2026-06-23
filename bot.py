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
# 1. Imports and Setup (Lines 1-31)

# 2. DEFINITIONS (Paste these code blocks individually into their respective spots)

def check_circuit_breaker():
    global trading_enabled
    try:
        acc = api.get_account()
        if state["start_equity"] is None:
            state["start_equity"] = float(acc.equity)
        if float(acc.equity) < float(state["start_equity"]) * (1 - DAILY_LOSS_LIMIT):
            logger.critical("🚨 CIRCUIT BREAKER TRIGGERED")
            trading_enabled = False
    except Exception as e:
        logger.error(f"Circuit breaker failed: {e}")

def market_trend_ok(symbol):
    try:
        bars = data_api.get_bars(StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Day, limit=MA_PERIOD))
        
        # Calculate price and MA200
        price = float(bars["close"].iloc[-1])
        ma200 = float(bars["close"].mean())
        
        # Log the diagnostic data
        logger.info(f"{symbol} Price: {price:.2f} MA200={ma200:.2f}")
        
        # Trend filter logic
        if price < ma200:
            logger.info(f"Skipping {symbol}: Price {price:.2f} below MA200 {ma200:.2f}")
            return False
            
        return True
    except Exception as e:
        logger.error(f"Trend check error: {e}")
        return False

def try_buy(symbol):
    try:
        positions = api.get_all_positions()
        if not any(p.symbol == symbol for p in positions):
            if float(api.get_account().buying_power) > MIN_ORDER_VALUE:
                api.submit_order(symbol=symbol, qty=1, side=OrderSide.BUY, type="market", time_in_force="day")
                logger.info(f"Bought {symbol}")
    except Exception as e:
        logger.error(f"Buy failed for {symbol}: {e}")

def manage_positions():
    try:
        for p in api.get_all_positions():
            if float(p.current_price) >= float(p.avg_entry_price) * (1 + TAKE_PROFIT_PCT):
                api.close_position(p.symbol)
                logger.info(f"Take profit hit for {p.symbol}")
    except Exception as e:
        logger.error(f"Position management failed: {e}")

# 3. MAIN LOOP (Starts at the bottom)


# =========================
# MAIN LOOP
# =========================
logger.info("🚀 Sentinel v2.1 Online")

while True:
        if api.get_clock().is_open and trading_enabled:
            try:
                # 1. Log Account Status
                acc = api.get_account()
                logger.info(f"Account Balance: ${acc.cash} | Equity: ${acc.equity}")
                
                # 2. Global Checks
                check_circuit_breaker()
                
                # 3. Check each symbol independently
                for sym in MY_SYMBOLS:
                    if market_trend_ok(sym):
                        try_buy(sym)
                    else:
                        logger.info(f"Skipping {sym}: Market trend filter not met.")
                
                # 4. Manage existing positions
                manage_positions()
                
            except Exception as e:
                logger.error(f"Loop error: {e}")
        
        time.sleep(60)
