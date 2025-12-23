import os, time, datetime as dt
from alpaca_trade_api import REST, TimeFrame
import pandas as pd
import json

# ===== ENV =====
KEY     = os.getenv("APCA_API_KEY_ID")
SECRET  = os.getenv("APCA_API_SECRET_KEY")
BASEURL = os.getenv("APCA_API_BASE_URL", "https://api.alpaca.markets")

if not KEY or not SECRET:
    raise ValueError("Missing APCA_API_KEY_ID or APCA_API_SECRET_KEY in Railway Variables.")

api = REST(KEY, SECRET, BASEURL, api_version="v2")

# ===== SETTINGS (SAFE DEFAULTS) =====
SYMBOLS = ["SPY", "QQQ"]
TIMEFRAME = TimeFrame.Minute
BARS = 120  # last 120 minutes

MAX_TRADES_PER_DAY = 6
MAX_OPEN_POSITIONS = 2
TRADE_ALLOCATION_PCT = 0.25  # 25% of account per trade
MIN_NOTIONAL = 5.00          # Alpaca minimum
DAILY_LOSS_LIMIT = 0.05      # 5% account kill switch
STOP_LOSS_PCT = 0.004        # 0.4% stop
TAKE_PROFIT_PCT = 0.008      # 0.8% take profit
TRAILING_STOP = True
COOLDOWN_MINUTES = 30        # don't re-enter too fast

STATE_FILE = "bot_state.json"

# ===== SIMPLE STATE (file-based) =====
def load_state():
    if not os.path.exists(STATE_FILE):
        return {"date": "", "trades_today": 0, "last_trade_ts": {}, "start_equity": 0.0}
    with open(STATE_FILE, "r") as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def est_now():
    # Railway runs UTC; convert logic using market clock below
    return dt.datetime.utcnow()

def market_open(api):
    clock = api.get_clock()
    return clock.is_open

def get_minutes_since(ts_iso):
    if not ts_iso:
        return 10**9
    ts = dt.datetime.fromisoformat(ts_iso)
    return (dt.datetime.utcnow() - ts).total_seconds() / 60.0

def get_bars(symbol):
    bars = api.get_bars(symbol, TIMEFRAME, limit=BARS).df
    if bars.empty:
        return None
    # alpaca returns multi-index sometimes; normalize
    if isinstance(bars.index, pd.MultiIndex):
        bars = bars.reset_index().set_index("timestamp")
    return bars

def ema(series, span):
    return series.ewm(span=span, adjust=False).mean()

def get_position_qty(symbol):
    try:
        pos = api.get_position(symbol)
        return float(pos.qty)
    except Exception:
        return 0.0

def count_open_positions():
    try:
        positions = api.list_positions()
        return len(positions)
    except Exception:
        return 0

def cancel_open_orders(symbol):
    try:
        orders = api.list_orders(status="open", symbols=[symbol], limit=50)
        for o in orders:
            api.cancel_order(o.id)
    except Exception:
        pass

def place_bracket_buy(symbol, notional):
    last = api.get_latest_trade(symbol).price
    
    if notional < MIN_NOTIONAL:
        print(f"⚠️ {symbol}: notional ${notional:.2f} below minimum ${MIN_NOTIONAL}.")
        return False
    
    trade_amount = round(notional, 2)
    print(f"🟢 BUY {symbol} ${trade_amount} entry≈{last:.2f}")
    
    api.submit_order(
        symbol=symbol,
        notional=trade_amount,
        side="buy",
        type="market",
        time_in_force="day"
    )
    
    return True

def should_buy(symbol, bars):
    close = bars["close"]
    e9 = ema(close, 9)
    e20 = ema(close, 20)

    # crossover confirmation: e9 crosses above e20 on last bar
    if len(close) < 25:
        return False

    cross_up = (e9.iloc[-2] <= e20.iloc[-2]) and (e9.iloc[-1] > e20.iloc[-1])

    # basic trend filter: price above EMA20
    trend_ok = close.iloc[-1] > e20.iloc[-1]

    # avoid super low volatility chop: last 20 bars range threshold
    rng = (bars["high"].tail(20).max() - bars["low"].tail(20).min()) / close.iloc[-1]
    vol_ok = rng > 0.003  # 0.3%

    return cross_up and trend_ok and vol_ok

def main_loop():
    state = load_state()
    today = dt.datetime.utcnow().date().isoformat()
    
    acct = api.get_account()
    current_equity = float(acct.equity)
    buying_power = float(acct.buying_power)
    
    if state.get("date") != today:
        state = {"date": today, "trades_today": 0, "last_trade_ts": {}, "start_equity": current_equity}
        save_state(state)
    
    # Check daily loss limit
    start_equity = state.get("start_equity", current_equity)
    if start_equity > 0:
        daily_pnl_pct = (current_equity - start_equity) / start_equity
        print(f"💰 Equity: ${current_equity:.2f} | Daily P&L: {daily_pnl_pct*100:.2f}%")
        
        if daily_pnl_pct <= -DAILY_LOSS_LIMIT:
            print(f"🚨 DAILY LOSS LIMIT HIT: {daily_pnl_pct*100:.2f}% <= -{DAILY_LOSS_LIMIT*100}%")
            return
    else:
        print(f"💰 Equity: ${current_equity:.2f} | Buying Power: ${buying_power:.2f}")

    if not market_open(api):
        print("⏳ Market closed. Sleeping.")
        return

    if state["trades_today"] >= MAX_TRADES_PER_DAY:
        print("🛑 Max trades reached for today.")
        return
    
    # Check max open positions
    open_positions = count_open_positions()
    if open_positions >= MAX_OPEN_POSITIONS:
        print(f"🛑 Max open positions reached: {open_positions}/{MAX_OPEN_POSITIONS}")
        return

    for sym in SYMBOLS:
        # cooldown
        last_ts = state["last_trade_ts"].get(sym, "")
        mins = get_minutes_since(last_ts)
        if mins < COOLDOWN_MINUTES:
            print(f"⏱️ {sym}: cooldown {mins:.1f}/{COOLDOWN_MINUTES} min")
            continue

        qty = get_position_qty(sym)
        if qty > 0:
            print(f"📌 {sym}: already holding qty={qty}.")
            continue

        bars = get_bars(sym)
        if bars is None:
            print(f"⚠️ {sym}: no bars returned.")
            continue

        if should_buy(sym, bars):
            # allocate notional based on equity
            notional = current_equity * TRADE_ALLOCATION_PCT
            cancel_open_orders(sym)
            ok = place_bracket_buy(sym, notional)
            if ok:
                state["trades_today"] += 1
                state["last_trade_ts"][sym] = dt.datetime.utcnow().isoformat()
                save_state(state)
        else:
            print(f"🔎 {sym}: no signal.")

if __name__ == "__main__":
    print("✅ Bot started (Trend Rider B)")
    while True:
        try:
            main_loop()
            print("⏳ Bot heartbeat...")
        except Exception as e:
            print(f"❌ Error: {e}")
        time.sleep(300)  # 5 minutes
