import os, time, math
from datetime import datetime
from alpaca_trade_api.rest import REST, TimeFrame

API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")
BASE_URL = os.getenv("APCA_API_BASE_URL", "https://api.alpaca.markets")

if not API_KEY or not API_SECRET:
    raise RuntimeError("Missing APCA_API_KEY_ID or APCA_API_SECRET_KEY in Railway Variables.")

api = REST(API_KEY, API_SECRET, BASE_URL, api_version="v2")

# --- CONFIG ---
SYMBOLS = ["SPY", "AAPL", "MSFT", "TSLA", "NVDA"]  # change if you want
USE_EXTENDED_HOURS = True        # set False if you only want regular market hours
MIN_NOTIONAL = 10               # Alpaca usually requires >= $1, but $10 avoids tiny rejects
MAX_NOTIONAL = 25               # keep it small while testing
BUYING_POWER_FRACTION = 0.30    # use 30% of buying power per buy attempt (aggressive but not all-in)

def market_is_open_now():
    try:
        clock = api.get_clock()
        return clock.is_open
    except Exception:
        return False

def get_last_price(symbol: str) -> float:
    barset = api.get_bars(symbol, TimeFrame.Minute, limit=1)
    return float(barset[-1].c)

def safe_notional(buying_power: float) -> float:
    n = buying_power * BUYING_POWER_FRACTION
    n = max(n, MIN_NOTIONAL)
    n = min(n, MAX_NOTIONAL, buying_power * 0.95)
    return float(max(0.0, round(n, 2)))

def place_fractional_buy(symbol: str, notional: float):
    # If market closed but USE_EXTENDED_HOURS=True, we use LIMIT + extended_hours
    if market_is_open_now() or not USE_EXTENDED_HOURS:
        order = api.submit_order(
            symbol=symbol,
            side="buy",
            type="market",
            time_in_force="day",
            notional=notional
        )
        return order

    # extended hours: LIMIT order slightly above last to help fill
    last = get_last_price(symbol)
    limit_price = round(last * 1.003, 2)  # +0.3%
    order = api.submit_order(
        symbol=symbol,
        side="buy",
        type="limit",
        time_in_force="day",
        notional=notional,
        limit_price=limit_price,
        extended_hours=True
    )
    return order

def main_loop():
    acct = api.get_account()
    print(f"✅ Connected. BaseURL={BASE_URL}")
    print(f"💰 Buying Power: {acct.buying_power} | Cash: {acct.cash} | Equity: {acct.equity}")
    print(f"🧾 Account status: {acct.status} | trading_blocked={acct.trading_blocked}")

    if str(acct.trading_blocked).lower() == "true":
        raise RuntimeError("Account is trading_blocked=True. You must clear restrictions in Alpaca.")

    # Simple "ABC" behavior: cycle symbols and buy small notional
    while True:
        acct = api.get_account()
        bp = float(acct.buying_power)
        n = safe_notional(bp)

        if n < MIN_NOTIONAL:
            print("⚠️ Not enough buying power to place a safe notional order.")
            time.sleep(60)
            continue

        for sym in SYMBOLS:
            try:
                print(f"🚀 Trying BUY {sym} notional=${n} (extended_hours={USE_EXTENDED_HOURS})")
                o = place_fractional_buy(sym, n)
                print(f"✅ Order submitted: {o.id} {sym} ${n}")
                time.sleep(5)
            except Exception as e:
                print(f"❌ Order failed for {sym}: {e}")

        print("⏳ Bot heartbeat...")
        time.sleep(60)

if __name__ == "__main__":
    main_loop()
