import os
import time
from alpaca_trade_api import REST

# =====================
# CONFIG (LIVE + FRACTIONAL)
# =====================
API_KEY = os.getenv("APCA_API_KEY_ID")
SECRET_KEY = os.getenv("APCA_API_SECRET_KEY")
BASE_URL = "https://api.alpaca.markets"  # LIVE ONLY

USE_FRACTIONAL = True
TRADE_ALLOCATION_PCT = 0.25     # 25% per trade
MIN_NOTIONAL = 5.00             # Alpaca minimum
SYMBOLS = ["SPY", "AAPL", "MSFT"]

api = REST(API_KEY, SECRET_KEY, BASE_URL, api_version="v2")

# =====================
# UTILS
# =====================
def get_trade_amount():
    account = api.get_account()
    buying_power = float(account.buying_power)
    trade_amt = round(buying_power * TRADE_ALLOCATION_PCT, 2)
    return max(trade_amt, MIN_NOTIONAL)

# =====================
# TRADE LOGIC (SIMPLE + AGGRESSIVE)
# =====================
def trade():
    print("🤖 Bot heartbeat...")
    account = api.get_account()
    print(f"💰 Buying Power: ${account.buying_power}")

    clock = api.get_clock()
    if not clock.is_open:
        print("⏰ Market closed. Sleeping.")
        return

    trade_amount = get_trade_amount()

    for symbol in SYMBOLS:
        try:
            print(f"🟢 BUY {symbol} | ${trade_amount}")
            api.submit_order(
                symbol=symbol,
                notional=trade_amount,   # 🔥 FRACTIONAL FIX
                side="buy",
                type="market",
                time_in_force="day"
            )
            time.sleep(2)
        except Exception as e:
            print(f"❌ Trade error {symbol}: {e}")

# =====================
# MAIN LOOP
# =====================
if __name__ == "__main__":
    print("🚀 LIVE FRACTIONAL BOT STARTED")
    while True:
        trade()
        time.sleep(300)  # run every 5 minutes
