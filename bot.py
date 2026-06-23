import os, time, logging, json, sys
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
COOLDOWN_SECONDS = 1800
STATE_FILE = "sentinel_state.json"

# =========================
# LOGGING
# =========================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", stream=sys.stdout)
logger = logging.getLogger()

# =========================
# API INITIALIZATION
# =========================
api = TradingClient(os.environ.get("APCA_API_KEY_ID"), os.environ.get("APCA_API_SECRET_KEY"), paper=True)
data_api = StockHistoricalDataClient(os.environ.get("APCA_API_KEY_ID"), os.environ.get("APCA_API_SECRET_KEY"))

# =========================
# STATE MANAGEMENT
# =========================
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f: return json.load(f)
    return {"start_equity": None, "last_trade_time": {}, "highs": {}}

state = load_state()
trading_enabled = True

def save_state():
    with open(STATE_FILE, "w") as f: json.dump(state, f)

# =========================
# HELPERS & DIAGNOSTICS
# =========================
def get_bars(symbol, limit=200, timeframe=TimeFrame.Day):
    try:
        return data_api.get_stock_bars(StockBarsRequest(symbol_or_symbols=symbol, timeframe=timeframe, limit=limit)).df
    except Exception as e:
        logger.error(f"Bars error {symbol}: {e}")
        return None

def log_diagnostics():
    logger.info("--- DIAGNOSTIC SIGNAL SCAN START ---")
    for sym in MY_SYMBOLS:
        bars = get_bars(sym, limit=200)
        if bars is None: continue
        price, ma = float(bars["close"].iloc[-1]), float(bars["close"].mean())
        if price > ma:
            logger.info(f"{sym} Decision: YES | Reason: Bullish (Price {price:.2f} > MA {ma:.2f})")
        else:
            logger.info(f"{sym} Decision: NO | Reason: Trend not bullish (Price {price:.2f} < MA {ma:.2f})")
    logger.info("--- DIAGNOSTIC SIGNAL SCAN END ---")

def market_trend_ok():
    bars = get_bars("SPY", MA_PERIOD)
    return bars["close"].iloc[-1] > bars["close"].mean() if bars is not None else False

def check_circuit_breaker():
    global trading_enabled
    acc = api.get_account()
    if state["start_equity"] is None:
        state["start_equity"] = float(acc.equity); save_state()
    if float(acc.equity) < float(state["start_equity"]) * (1 - DAILY_LOSS_LIMIT):
        trading_enabled = False
        logger.critical("🚨 CIRCUIT BREAKER TRIGGERED")

def manage_positions():
    for p in api.get_all_positions():
        sym, entry, price = p.symbol, float(p.avg_entry_price), float(p.current_price)
        state["highs"][sym] = max(state["highs"].get(sym, price), price)
        if price <= entry * (1 - STOP_LOSS_PCT) or price >= entry * (1 + TAKE_PROFIT_PCT) or price <= state["highs"][sym] * (1 - TRAILING_STOP_PCT):
            api.close_position(sym)
            logger.info(f"🛑/💰/📉 Position {sym} closed")

def try_buy(symbol):
    if time.time() - state["last_trade_time"].get(symbol, 0) < COOLDOWN_SECONDS: return
    bars = get_bars(symbol, 200)
    if bars is None or bars["close"].iloc[-1] < bars["close"].mean(): return
    invest = float(api.get_account().cash) * MAX_CAPITAL_USAGE
    if invest < MIN_ORDER_VALUE: return
    try:
        api.submit_order(LimitOrderRequest(symbol=symbol, qty=round(invest / float(bars["close"].iloc[-1]), 4), side=OrderSide.BUY, type="limit", limit_price=float(bars["close"].iloc[-1]), time_in_force=TimeInForce.DAY))
        state["last_trade_time"][symbol] = time.time(); save_state()
        logger.info(f"✅ BUY {symbol}")
    except Exception as e: logger.error(f"Buy error {symbol}: {e}")

# =========================
# MAIN LOOP
# =========================
logger.info("🚀 Sentinel v2 Running")
while True:
    try:
        # Diagnostic Scan every 30 minutes
        if int(time.time()) % 1800 < 60: log_diagnostics()
        
        # Main Trading Flow
        if api.get_clock().is_open and trading_enabled:
            check_circuit_breaker()
            if market_trend_ok():
                manage_positions()
                for sym in MY_SYMBOLS: try_buy(sym)
        
        time.sleep(60)
    except Exception as e:
        logger.error(f"Loop crash: {e}")
        time.sleep(120)
