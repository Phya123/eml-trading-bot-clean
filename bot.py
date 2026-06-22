import os, time, datetime
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# --- CONFIGURATION ---
MY_SYMBOLS = ["SPCX", "EXL", "QQQ", "SPY"]
MAX_CAPITAL_USAGE = 0.70
DAILY_PROFIT_TARGET = 3.00
daily_stats = {"total_profit": 0.0}
# ERASE your old line 14 and ADD this:
api = TradingClient(
    os.environ.get("APCA_API_KEY_ID"), 
    os.environ.get("APCA_API_SECRET_KEY"), 
    paper=False
)

# --- INITIALIZATION ---
api = TradingClient(os.environ.get("APCA_API_KEY_ID"), os.environ.get("APCA_API_SECRET_KEY"), paper=True)
data_api = StockHistoricalDataClient(os.environ.get("APCA_API_KEY_ID"), os.environ.get("APCA_API_SECRET_KEY"))

# --- HELPER FUNCTIONS ---
def is_market_open():
    clock = api.get_clock()
    return clock.is_open

def force_buy(symbol):
    try:
        request = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Minute, limit=60)
        bars = data_api.get_stock_bars(request).df
        current_price = float(bars['close'].iloc[-1])
        
        available_cash = float(api.get_account().cash)
        qty = (available_cash * MAX_CAPITAL_USAGE) / current_price
        
        print(f"SENTINEL: Live Trade - Buying {qty:.4f} shares of {symbol} at ${current_price}")
        
        # CORRECT ORDER SUBMISSION
        order_data = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            type='market',
            time_in_force=TimeInForce.GTC
        )
        api.submit_order(order_data)
        print(f"✅ Order submitted for {symbol}")
        
    except Exception as e:
        print(f"❌ Failed: {symbol} - {e}")

# --- MAIN LOOP ---
while True:
    if is_market_open():
        if daily_stats["total_profit"] >= DAILY_PROFIT_TARGET:
            print("Daily profit target reached. Sleeping.")
        else:
            for symbol in MY_SYMBOLS:
                if symbol == "SPCX":
                    print("Skipping SPCX (Validation pending)")
                    continue
                force_buy(symbol)
    else:
        print("Market is closed. Sentinel is in standby mode.")
    time.sleep(60)
