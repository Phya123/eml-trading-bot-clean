import os
from alpaca_trade_api import REST
import time

API_KEY = os.getenv("APCA_API_KEY_ID")
SECRET_KEY = os.getenv("APCA_API_SECRET_KEY")
BASE_URL = os.getenv("APCA_API_BASE_URL", "https://paper-api.alpaca.markets")

try:
    api = REST(API_KEY, SECRET_KEY, BASE_URL, api_version="v2")
    print("✅ Bot started")
    account = api.get_account()
    print(f"💰 Account: ${account.equity}")
    print(f"📊 Buying Power: ${account.buying_power}")
except Exception as e:
    print(f"❌ Error connecting to Alpaca: {e}")
    exit(1)

while True:
    print("⏳ Bot heartbeat...")
    time.sleep(60)
