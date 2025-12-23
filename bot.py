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

MAX_TRADES_PER_DAY = 4
MAX_POSITION_PCT = 0.10      # 10% of buying power per symbol
STOP_LOSS_PCT = 0.02         # 2% stop
TAKE_PROFIT_PCT = 0.03       # 3% take profit
COOLDOWN_MINUTES = 30        # don't re-enter too fast

STATE_FILE = "bot_state.json"

# ===== SIMPLE STATE (file-based) =====
def load_state():
    if not os.path.exists(STATE_FILE):
        return {"date": "", "trades_today": 0, "last_trade_ts": {}}
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

def cancel_open_orders(symbol):
    try:
        orders = api.list_orders(status="open", symbols=[symbol], limit=50)
        for o in orders:
            api.cancel_order(o.id)
    except Exception:
        pass

def place_bracket_buy(symbol, notional):
    # bracket requires qty; we'll convert notional -> qty using last price
    last = api.get_latest_trade(symbol).price
    qty = max(int(notional / last), 0)
    if qty <= 0:
        print(f"⚠️ {symbol}: not enough buying power for qty.")
        return False

    # bracket prices
    entry = last
    tp = round(entry * (1 + TAKE_PROFIT_PCT), 2)
    sl = round(entry * (1 - STOP_LOSS_PCT), 2)

    print(f"🟢 BUY {symbol} qty={qty} entry≈{entry:.2f} TP={tp} SL={sl}")
    api.submit_order(
        symbol=symbol,
        qty=qty,
        side="buy",
        type="market",
        time_in_force="day",
        order_class="bracket",
        take_profit={"limit_price": tp},
        stop_loss={"stop_price": sl},
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
    if state.get("date") != today:
        state = {"date": today, "trades_today": 0, "last_trade_ts": {}}
        save_state(state)

    acct = api.get_account()
    buying_power = float(acct.buying_power)
    print(f"💰 Buying Power: ${buying_power:.2f}")

    if not market_open(api):
        print("⏳ Market closed. Sleeping.")
        return

    if state["trades_today"] >= MAX_TRADES_PER_DAY:
        print("🛑 Max trades reached for today.")
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
            # allocate notional
            notional = buying_power * MAX_POSITION_PCT
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
