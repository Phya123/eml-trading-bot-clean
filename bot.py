import os, time
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# --- 1. CONFIGURATION ---
MY_SYMBOLS = ["XLE", "SPCX", "QQQ", "SPY"]
MAX_CAPITAL_USAGE = 0.50
MIN_ORDER_VALUE = 1.10
STOP_LOSS_PCT = 0.02  # 2% Risk Limit

# --- 2. INITIALIZATION ---
api = TradingClient(os.environ.get("APCA_API_KEY_ID"), os.environ.get("APCA_API_SECRET_KEY"), paper=False)
data_api = StockHistoricalDataClient(os.environ.get("APCA_API_KEY_ID"), os.environ.get("APCA_API_SECRET_KEY"))

# --- 3. RISK MANAGEMENT (STOP LOSS) ---
def manage_positions():
    """Checks open positions and sells if loss exceeds 2%."""
    try:
        positions = api.get_all_positions()
        for pos in positions:
            loss_pct = float(pos.unrealized_plpc)
            if loss_pct <= -STOP_LOSS_PCT:
                print(f"🚨 STOP LOSS TRIGGERED: Selling {pos.symbol} (Loss: {loss_pct:.2%})")
                api.close_position(pos.symbol)
    except Exception as e:
        print(f"⚠️ Could not manage positions: {e}")

# --- 4. TRADING LOGIC ---
def force_buy(symbol):
    print(f"🔍 Checking {symbol}...")
    try:
        request = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Minute, limit=1)
        bars_df = data_api.get_stock_bars(request).df
        
        if bars_df.empty:
            print(f"⚠️ Skipping {symbol}: No data.")
            return
            
        current_price = float(bars_df['close'].iloc[-1])
        available_cash = float(api.get_account().cash)
        investment = available_cash * MAX_CAPITAL_USAGE
        
        if investment < MIN_ORDER_VALUE:
            print(f"⚠️ Skipping {symbol}: Investment too low (${investment:.2f})")
            return

        qty = round(investment / current_price, 4)
        order = MarketOrderRequest(symbol=symbol, qty=qty, side=OrderSide.BUY, type='market', time_in_force=TimeInForce.DAY)
        api.submit_order(order)
        print(f"✅ Executed Buy: {qty} shares of {symbol} at ${current_price}")
    except Exception as e:
        print(f"❌ Failed to trade {symbol}: {e}")

# --- 5. MAIN LOOP ---
print("🚀 Sentinel Bot Active. Monitoring Market...")
while True:
    if api.get_clock().is_open:
        manage_positions() # Safety check first
        for symbol in MY_SYMBOLS:
            force_buy(symbol)
            time.sleep(30) # Prevent rate limiting
    else:
        print("Market closed. Sentinel in standby.")
        time.sleep(300)
