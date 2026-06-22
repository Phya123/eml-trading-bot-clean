import os, time
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# --- CONFIGURATION (RISK MANAGEMENT) ---
MY_SYMBOLS = ["QQQ", "SPY"] # Added only stable symbols
MAX_CAPITAL_USAGE = 0.50     # Use 50% of available cash per symbol
MIN_ORDER_VALUE = 1.10       # Ensure order is above $1.00 min

# --- INITIALIZATION ---
api = TradingClient(os.environ.get("APCA_API_KEY_ID"), os.environ.get("APCA_API_SECRET_KEY"), paper=False)
data_api = StockHistoricalDataClient(os.environ.get("APCA_API_KEY_ID"), os.environ.get("APCA_API_SECRET_KEY"))

def force_buy(symbol):
    try:
        # 1. Fetch current price
        request = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Minute, limit=1)
        price = float(data_api.get_stock_bars(request).df['close'].iloc[-1])
        def force_buy(symbol):
    try:
        # AFTER: price = float(...)
        print(f"DEBUG: {symbol} current price is ${price}") 
        
        # AFTER: investment = available_cash * MAX_CAPITAL_USAGE
        print(f"DEBUG: Considering {symbol}. Cash available: ${available_cash:.2f}. Target investment: ${investment:.2f}")

        # AFTER: if investment < MIN_ORDER_VALUE:
        # Change this specific line to:
        if investment < MIN_ORDER_VALUE:
            print(f"DEBUG: Skipping {symbol}. Investment too low.")
            return
            
        # ... rest of your code
        # 2. Get Cash and Calculate Position
        available_cash = float(api.get_account().cash)
        investment = available_cash * MAX_CAPITAL_USAGE
        
        # 3. Risk Management: Sanity Check
        if investment < MIN_ORDER_VALUE:
            return # Skip if below minimum requirements

        # 4. Submit Order
        qty = round(investment / price, 4)
        order = MarketOrderRequest(symbol=symbol, qty=qty, side=OrderSide.BUY, type='market', time_in_force=TimeInForce.DAY)
        api.submit_order(order)
        print(f"✅ Executed Buy: {qty} shares of {symbol} at ${price}")
        
    except Exception as e:
        print(f"❌ Failed to trade {symbol}: {e}")

# --- INFINITE MAIN LOOP ---
print("🚀 Sentinel Bot Active. Monitoring Market...")
while True:
    if api.get_clock().is_open:
        for symbol in MY_SYMBOLS:
            force_buy(symbol)
            time.sleep(30) # Wait 30 seconds between orders to respect API limits
    else:
        print("Market closed. Sentinel in standby.")
        time.sleep(300) # Wait 5 minutes before re-checking
