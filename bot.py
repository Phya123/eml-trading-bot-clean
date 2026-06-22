import os, time, datetime
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.common.enums import BaseURL

# --- CONFIGURATION ---
MY_SYMBOLS = ["SPCX", "EXL", "QQQ", "SPY"]
MAX_CAPITAL_USAGE = 0.70
DAILY_PROFIT_TARGET = 3.00
daily_stats = {"total_profit": 0.0}

# --- INITIALIZATION ---
api = TradingClient(
    os.environ.get("APCA_API_KEY_ID"),
    os.environ.get("APCA_API_SECRET_KEY"),
    paper=False
)
data_api = StockHistoricalDataClient(os.environ.get("APCA_API_KEY_ID"), os.environ.get("APCA_API_SECRET_KEY"))

# --- HELPER FUNCTIONS ---
def is_market_open():
    clock = api.get_clock()
    return clock.is_open

def force_buy(symbol):
    try:
        # 1. Fetch data
        request = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Minute, limit=60)
        bars = data_api.get_stock_bars(request).df
        current_price = float(bars['close'].iloc[-1])
        
        # 2. Get Account Info
        available_cash = float(api.get_account().cash)
        
        # 3. Calculate and Check
        investment_amount = available_cash * MAX_CAPITAL_USAGE
        
        if investment_amount < 1.05:
            print(f"Skipping {symbol}: Investment (${investment_amount:.2f}) below $1.00 min.")
            return

        qty = investment_amount / current_price
        print(f"SENTINEL: Buying {qty:.4f} shares of {symbol} at ${current_price}")

        # 4. Submit Order
        order_data = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            type='market',
            time_in_force=TimeInForce.DAY
        )
        api.submit_order(order_data)
        print(f"✅ Order submitted for {symbol}")

    except Exception as e:
        print(f"❌ CRITICAL FAILURE: {e}")
