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
