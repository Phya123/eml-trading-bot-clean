import csv, os, time, datetime
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

# --- INITIALIZATION ---
api_key = os.environ.get("APCA_API_KEY_ID")
secret_key = os.environ.get("APCA_API_SECRET_KEY")

if not api_key or not secret_key:
    raise ValueError("API Keys are missing!")

data_api = StockHistoricalDataClient(api_key=api_key, secret_key=secret_key)
api = TradingClient(api_key=api_key, secret_key=secret_key, paper=False)

my_symbols = ["SPCX", "EXL", "QQQ", "SPY"]

# --- HELPER FUNCTIONS ---
def is_market_open():
    now = datetime.datetime.now().time()
    return datetime.time(9, 30) <= now <= datetime.time(16, 0)

def _get_bars_dataframe(symbol, limit):
    request = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Minute,
        limit=limit
    )
    return data_api.get_stock_bars(request).df

def force_buy(symbol):
    try:
        bars = _get_bars_dataframe(symbol, limit=60)
        # Your trading logic here
        print(f"✅ Checking {symbol}")
    except Exception as e:
        print(f"❌ Failed: {symbol} - {e}")

# --- MAIN LOOP ---
while True:
    if is_market_open():
        for symbol in my_symbols:
            force_buy(symbol)
    else:
        print("Market closed. Sentinel standby.")
    
    time.sleep(60)
