import os, time, logging
import pandas as pd
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.requests import LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# --- 1. CONFIGURATION ---
MY_SYMBOLS = ["XLE", "SPCX", "QQQ", "SPY"]
MAX_CAPITAL_USAGE = 0.50
MIN_ORDER_VALUE = 1.10
STOP_LOSS_PCT = 0.02
DAILY_LOSS_LIMIT = 0.03 # 3% daily loss limit
MOVING_AVG_PERIOD = 20

# --- 2. LOGGING SETUP ---
logging.basicConfig(
    filename='trading.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger()

# --- 3. INITIALIZATION ---
api = TradingClient(os.environ.get("APCA_API_KEY_ID"), os.environ.get("APCA_API_SECRET_KEY"), paper=False)
data_api = StockHistoricalDataClient(os.environ.get("APCA_API_KEY_ID"), os.environ.get("APCA_API_SECRET_KEY"))
trading_enabled = True

# --- 4. SAFETY FUNCTIONS ---
def check_daily_loss():
    global trading_enabled
    account = api.get_account()
    daily_change = float(account.equity) - float(account.last_equity)
    if daily_change <= -(float(account.last_equity) * DAILY_LOSS_LIMIT):
        logger.critical("🚨 DAILY LOSS LIMIT REACHED. DISABLING TRADING.")
        trading_enabled = False

def manage_positions():
    try:
        for pos in api.get_all_positions():
            if float(pos.unrealized_plpc) <= -STOP_LOSS_PCT:
                logger.warning(f"🚨 STOP LOSS: Selling {pos.symbol}")
                api.close_position(pos.symbol)
    except Exception as e:
        logger.error(f"Error managing positions: {e}")

# --- 5. TRADING LOGIC ---
def force_buy(symbol):
    try:
        request = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Minute, limit=MOVING_AVG_PERIOD)
        bars_df = data_api.get_stock_bars(request).df
        if bars_df.empty: return
        
        current_price = float(bars_df['close'].iloc[-1])
        ma_price = bars_df['close'].mean()
        
        # Sanity & Trend Check
        if current_price <= 0 or current_price > 10000 or current_price < ma_price:
            return

        investment = float(api.get_account().cash) * MAX_CAPITAL_USAGE
        if investment < MIN_ORDER_VALUE: return

        qty = round(investment / current_price, 4)
        # Limit Order: Buy at current price or better
        order = LimitOrderRequest(symbol=symbol, qty=qty, side=OrderSide.BUY, 
                                  type='limit', limit_price=current_price, 
                                  time_in_force=TimeInForce.DAY)
        api.submit_order(order)
        logger.info(f"✅ Executed Limit Buy: {qty} shares of {symbol} at ${current_price}")
    except Exception as e:
        logger.error(f"Failed to trade {symbol}: {e}")

# --- 6. MAIN LOOP ---
logger.info("🚀 Sentinel Bot Active.")
while True:
    if api.get_clock().is_open and trading_enabled:
        check_daily_loss()
        manage_positions()
        for symbol in MY_SYMBOLS:
            force_buy(symbol)
            time.sleep(30)
    else:
        time.sleep(300)
