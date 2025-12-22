import os
from alpaca_trade_api import REST
import time

API_KEY = os.getenv("APCA_API_KEY_ID")
SECRET_KEY = os.getenv("APCA_API_SECRET_KEY")
BASE_URL = os.getenv("APCA_API_BASE_URL")

api = REST(API_KEY, SECRET_KEY, BASE_URL)

print("✅ Bot started")
print("💰 Account:", api.get_account().equity)

while True:
    print("⏳ Bot heartbeat...")
    time.sleep(60)
