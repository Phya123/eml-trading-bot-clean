import os, time
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.requests import MarketOrderRequest, OrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# --- CONFIGURATION ---
MY_SYMBOLS = ["XLE", "SPCX", "QQQ", "SPY"]
MAX_CAPITAL_USAGE = 0.50
MIN_ORDER_VALUE = 1.10
STOP_LOSS_PCT = 0.02  # 2% Risk Limit

# --- INITIALIZATION ---
api = TradingClient(os.environ.get("APCA_API_KEY_ID"), os.environ.get("APCA_API_SECRET_KEY"), paper=False)
data_api = StockHistoricalDataClient(os.environ.get("APCA_API_KEY_ID"), os.environ.get("APCA_API_SECRET_KEY"))

def manage_positions():
    """Checks open positions and sells if loss exceeds 2%."""
    positions = api.get_all_positions()
    for pos in positions:
        # unrealized_plpc is the percentage gain/loss (e.g., -0.02 for -2%)
        loss_pct = float(pos.unrealized_plpc)
        if loss_pct <= -STOP_LOSS_PCT:
            print(f"🚨 STOP LOSS TRIGGERED: Selling {pos.symbol} (Loss: {loss_pct:.2%})")
            api.close_position(pos.symbol)

def force_buy(symbol):
    print(f"🔍 Checking {symbol}...")
    try:
        request = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Minute, limit=1)
        bars_df = data_api.get_stock_bars(request).df
        if bars_df.empty: return
            
        current_price = float(bars_df['close'].iloc[-1])
        available_cash = float(api.get_account().cash)
        investment = available_cash * MAX_CAPITAL_USAGE
        
        if investment < MIN_ORDER_VALUE: return

        qty = round(investment / current_price, 4)
        order = MarketOrderRequest(symbol=symbol, qty=qty, side=OrderSide.BUY, type='market', time_in_force=TimeInForce.DAY)
        api.submit_order(order)
        print(f"✅ Executed Buy: {qty} shares of {symbol} at ${current_price}")
    except Exception as e:
        print(f"❌ Failed to trade {symbol}: {e}")

# --- INFINITE MAIN LOOP ---
print("🚀 Sentinel Bot Active. Monitoring Market...")
while True:
    if api.get_clock().is_open:
        manage_positions() # Check stops first
        for symbol in MY_SYMBOLS:
            force_buy(symbol)
            time.sleep(30)
    else:
        print("Market closed. Sentinel in standby.")
        time.sleep(300)
