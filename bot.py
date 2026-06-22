# --- IMPORTS AND INITIALIZATION ---
import csv, os, time
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestTradeRequest
from alpaca.data.timeframe import TimeFrame

        

  # --- HELPER FUNCTIONS ---
def _get_bars_dataframe(symbol, limit):
    global data_api
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    request = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Minute,
        limit=limit
    )
    bars = data_api.get_stock_bars(request)
    return bars.df

# --- TRADING LOGIC ---
def force_buy(symbol, amount=None):
    try:
        bars = _get_bars_dataframe(symbol, limit=60)
        current_price = float(bars['close'].iloc[-1])
        order = api.submit_order(
            symbol=symbol,
            qty=1,
            side='buy',
            type='market',
            time_in_force='day'
        )
        print(f"✅ FORCED BUY: {symbol}")
        return True
    except Exception as e:
        print(f"❌ FORCED BUY FAILED: {symbol} - {e}")
        return False                      
print("DEBUG: Script reached the end of the file", flush=True)
# If you have a loop, put the next line right INSIDE the loop:
print("DEBUG: Inside main trading loop", flush=True)
# ... (all your existing imports, helper functions, and force_buy logic) ...

# --- MAIN LOOP ---
while True:
    print(f"DEBUG: Still running. Current loop status: OK", flush=True)
    
    # Place your existing trading strategy calls here
    # Example:
    # manage_positions()
    # check_signals()
    
    time.sleep(60) # This pauses the bot for 60 seconds to prevent API rate limiting
# --- MAIN LOOP ---
while True:
    print(f"DEBUG: Still running. Current loop status: OK", flush=True)
    
    # ADD YOUR TEST LINE HERE:
    print(f"TEST: Checking symbol: AAPL - Calculated Score: 0.85", flush=True)
    
    # Your strategy logic follows...
    # manage_positions()
    # time.sleep(60)
