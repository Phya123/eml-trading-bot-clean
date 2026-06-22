import os, time
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce


# --- CONFIGURATION ---
MY_SYMBOLS = ["SPCX", "EXL", "QQQ", "SPY"] # Valid tradeable tickers
MAX_CAPITAL_USAGE = 0.50
MIN_ORDER_VALUE = 1.10

# --- INITIALIZATION ---
api = TradingClient(os.environ.get("APCA_API_KEY_ID"), os.environ.get("APCA_API_SECRET_KEY"), paper=False)
data_api = StockHistoricalDataClient(os.environ.get("APCA_API_KEY_ID"), os.environ.get("APCA_API_SECRET_KEY"))

def force_buy(symbol):
    try:
        request = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Minute, limit=1)
        price = float(data_api.get_stock_bars(request).df['close'].iloc[-1])
        available_cash = float(api.get_account().cash)
        investment = available_cash * MAX_CAPITAL_USAGE
        
        if investment < MIN_ORDER_VALUE:
            return

        qty = round(investment / price, 4)
        order = MarketOrderRequest(symbol=symbol, qty=qty, side=OrderSide.BUY, type='market', time_in_force=TimeInForce.DAY)
        api.submit_order(order)
        print(f"✅ Executed Buy: {qty} shares of {symbol} at ${price}")
    except Exception as e:
        print(f"❌ Failed to trade {symbol}: {e}")

# --- MAIN LOOP ---
print("🚀 Sentinel Bot Active. Monitoring Market...")
while True:
    if api.get_clock().is_open:
        for symbol in MY_SYMBOLS:
            force_buy(symbol)
            time.sleep(30)
    else:
        print("Market closed. Sentinel in standby.")
        time.sleep(300)
