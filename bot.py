import os, time, math, json
from datetime import datetime, date
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

# ===== SAFETY CONTROLS =====
MAX_DAILY_SPEND = 60.0        # max dollars the bot can BUY per day
MAX_DAILY_DRAWDOWN_PCT = -5.0 # stop buying if down -5% today

STATE_FILE = "bot_state.json"

def load_state():
    if not os.path.exists(STATE_FILE):
        return {"date": "", "daily_spend": 0.0, "start_equity": 0.0}
    with open(STATE_FILE, "r") as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

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

    # Load or initialize state
    state = load_state()
    today = str(date.today())
    
    if state.get("date") != today:
        # New day - reset counters
        state = {"date": today, "daily_spend": 0.0, "start_equity": float(acct.equity)}
        save_state(state)
        print(f"🆕 New day started. Start equity: ${state['start_equity']:.2f}")

    # Simple "ABC" behavior: cycle symbols and buy small notional
    while True:
        # Reload state each loop
        state = load_state()
        today = str(date.today())
        
        # Check if new day
        if state.get("date") != today:
            acct = api.get_account()
            state = {"date": today, "daily_spend": 0.0, "start_equity": float(acct.equity)}
            save_state(state)
            print(f"🆕 New day started. Start equity: ${state['start_equity']:.2f}")
        
        acct = api.get_account()
        current_equity = float(acct.equity)
        bp = float(acct.buying_power)
        
        # Check daily spend limit
        if state["daily_spend"] >= MAX_DAILY_SPEND:
            print(f"🛑 Daily spend limit reached: ${state['daily_spend']:.2f} >= ${MAX_DAILY_SPEND}")
            print("⏳ Waiting for next day...")
            time.sleep(300)
            continue
        
        # Check daily drawdown
        start_equity = state.get("start_equity", current_equity)
        if start_equity > 0:
            drawdown_pct = ((current_equity - start_equity) / start_equity) * 100
            print(f"📊 Daily P&L: {drawdown_pct:+.2f}% | Spend: ${state['daily_spend']:.2f}/${MAX_DAILY_SPEND}")
            
            if drawdown_pct <= MAX_DAILY_DRAWDOWN_PCT:
                print(f"🚨 Daily drawdown limit hit: {drawdown_pct:.2f}% <= {MAX_DAILY_DRAWDOWN_PCT}%")
                print("⏳ Waiting for next day...")
                time.sleep(300)
                continue
        
        n = safe_notional(bp)

        if n < MIN_NOTIONAL:
            print("⚠️ Not enough buying power to place a safe notional order.")
            time.sleep(60)
            continue
        
        # Check if we have enough room in daily spend
        remaining = MAX_DAILY_SPEND - state["daily_spend"]
        if remaining < MIN_NOTIONAL:
            print(f"🛑 Daily spend limit almost reached. Remaining: ${remaining:.2f}")
            time.sleep(60)
            continue
        
        # Adjust notional to not exceed daily limit
        n = min(n, remaining)

        for sym in SYMBOLS:
            try:
                print(f"🚀 Trying BUY {sym} notional=${n} (extended_hours={USE_EXTENDED_HOURS})")
                o = place_fractional_buy(sym, n)
                print(f"✅ Order submitted: {o.id} {sym} ${n}")
                
                # Update daily spend
                state["daily_spend"] = round(state["daily_spend"] + n, 2)
                save_state(state)
                
                time.sleep(5)
            except Exception as e:
                print(f"❌ Order failed for {sym}: {e}")

        print("⏳ Bot heartbeat...")
        time.sleep(60)

if __name__ == "__main__":
    main_loop()
