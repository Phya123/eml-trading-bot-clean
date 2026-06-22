import os, time, datetime
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

# --- CONFIGURATION ---
MY_SYMBOLS = ["SPCX", "EXL", "QQQ", "SPY"]
MAX_CAPITAL_USAGE = 0.70
DAILY_PROFIT_TARGET = 3.00
daily_stats = {"total_profit": 0.0}

# --- INITIALIZATION ---
api = TradingClient(os.environ.get("APCA_API_KEY_ID"), os.environ.get("APCA_API_SECRET_KEY"), paper=False)
data_api = StockHistoricalDataClient(os.environ.get("APCA_API_KEY_ID"), os.environ.get("APCA_API_SECRET_KEY"))

# --- HELPER FUNCTIONS ---
def is_market_open():
    now = datetime.datetime.now().time()
    return datetime.time(9, 30) <= now <= datetime.time(16, 0)

def force_buy(symbol):
    try:
        # Data fetch logic
        request = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Minute, limit=60)
        bars = data_api.get_stock_bars(request).df
        current_price = float(bars['close'].iloc[-1])
        
        # Position sizing logic
        available_cash = float(api.get_account().cash)
        qty = (available_cash * MAX_CAPITAL_USAGE) / current_price
        
        print(f"SENTINEL: Live Trade - Buying {qty:.4f} shares of {symbol} at ${current_price}")
       from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# ... inside your force_buy(symbol) function ...

# Create the request object properly
order_data = MarketOrderRequest(
    symbol=symbol,
    qty=qty,
    side=OrderSide.BUY,
    type='market',
    time_in_force=TimeInForce.GTC
)

# Submit the order using the request object
api.submit_order(order_data)
        # LINE 34 IS NOW ACTIVE:
        api.submit_order(symbol=symbol, qty=qty, side='buy', type='market', time_in_force='gtc')
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
        print("Market closed. Sentinel standby.")
    
    time.sleep(60)
        
