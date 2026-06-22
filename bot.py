import os, time, logging, json
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.requests import LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# =========================
# CONFIG & STATE
# =========================
MY_SYMBOLS = ["XLE", "SPCX", "QQQ", "SPY"]
MAX_CAPITAL_USAGE, MIN_ORDER_VALUE = 0.15, 5.00
STOP_LOSS_PCT, TAKE_PROFIT_PCT, TRAILING_STOP_PCT = 0.02, 0.05, 0.02
DAILY_LOSS_LIMIT, MA_PERIOD, COOLDOWN_SECONDS = 0.03, 200, 1800
STATE_FILE = "sentinel_state.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger()

api = TradingClient(os.environ.get("APCA_API_KEY_ID"), os.environ.get("APCA_API_SECRET_KEY"), paper=True)
data_api = StockHistoricalDataClient(os.environ.get("APCA_API_KEY_ID"), os.environ.get("APCA_API_SECRET_KEY"))

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f: return json.load(f)
    return {"start_equity": None, "last_trade_time": {}, "highs": {}}

state = load_state()
trading_enabled = True

def save_state():
    with open(STATE_FILE, "w") as f: json.dump(state, f)

def initialize_state_from_positions():
    """Ensure we track highs of existing positions after a restart."""
    for p in api.get_all_positions():
        if p.symbol not in state["highs"]:
            state["highs"][p.symbol] = float(p.current_price)
    save_state()

initialize_state_from_positions()

# =========================
# CORE LOGIC
# =========================
def market_trend_ok():
    try:
        bars = data_api.get_stock_bars(StockBarsRequest(symbol_or_symbols="SPY", timeframe=TimeFrame.Day, limit=MA_PERIOD)).df
        return bars["close"].iloc[-1] > bars["close"].mean()
    except: return False

def manage_positions():
    for p in api.get_all_positions():
        sym, entry, price = p.symbol, float(p.avg_entry_price), float(p.current_price)
        state["highs"][sym] = max(state["highs"].get(sym, price), price)
        
        if price <= entry * (1 - STOP_LOSS_PCT) or price >= entry * (1 + TAKE_PROFIT_PCT) or price <= state["highs"][sym] * (1 - TRAILING_STOP_PCT):
            logger.info(f"📢 EXITING {sym} @ {price}")
            api.close_position(sym)
    save_state()

def try_buy(symbol):
    if time.time() - state["last_trade_time"].get(symbol, 0) < COOLDOWN_SECONDS: return
    
    try:
        bars = data_api.get_stock_bars(StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Day, limit=200)).df
        price = float(bars["close"].iloc[-1])
        if price < bars["close"].mean(): return

        invest = float(api.get_account().cash) * MAX_CAPITAL_USAGE
        if invest < MIN_ORDER_VALUE: return

        api.submit_order(LimitOrderRequest(symbol=symbol, qty=round(invest/price, 4), side=OrderSide.BUY, 
                                           type="limit", limit_price=price, time_in_force=TimeInForce.DAY))
        state["last_trade_time"][symbol] = time.time()
        state["highs"][symbol] = price
        save_state()
        logger.info(f"✅ BUY {symbol} @ {price}")
    except Exception as e: logger.error(f"Buy error {symbol}: {e}")

# =========================
# MAIN LOOP
# =========================
logger.info("🚀 Sentinel v2.1 Online")
while True:
    if api.get_clock().is_open and trading_enabled:
        try:
            acc = api.get_account()
            if state["start_equity"] is None: state["start_equity"] = float(acc.equity); save_state()
            if float(acc.equity) < float(state["start_equity"]) * (1 - DAILY_LOSS_LIMIT): trading_enabled = False
            
            manage_positions()
            if market_trend_ok():
                for sym in MY_SYMBOLS: try_buy(sym)
        except Exception as e: logger.error(f"Loop error: {e}")
    time.sleep(60)
