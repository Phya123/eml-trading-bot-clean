import os
import time
import json
from datetime import datetime, timezone, date

import pandas as pd
from alpaca_trade_api import REST
from alpaca_trade_api.rest import TimeFrame

# -----------------------------
# CONFIG (edit here or use env vars)
# -----------------------------
APCA_API_KEY_ID = os.getenv("APCA_API_KEY_ID", "").strip()
APCA_API_SECRET_KEY = os.getenv("APCA_API_SECRET_KEY", "").strip()
APCA_API_BASE_URL = os.getenv("APCA_API_BASE_URL", "https://api.alpaca.markets").strip()

SYMBOLS = os.getenv("SYMBOLS", "SPY,QQQ,XLE").split(",")  # stocks only (focused portfolio)
SYMBOLS = [s.strip().upper() for s in SYMBOLS if s.strip()]
MAX_TRADES_PER_SYMBOL = int(os.getenv("MAX_TRADES_PER_SYMBOL", "2"))  # up to 2 trades per symbol per day

# ===== AUTO MODE RISK CONTROLS =====
USE_EQUITY_PCT = float(os.getenv("USE_EQUITY_PCT", "0.80"))         # only use 80% of total equity (20% cash reserve)
TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", "1.5"))        # +1.5%
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", "-1.0"))           # -1.0%

DAILY_PROFIT_GOAL = float(os.getenv("DAILY_PROFIT_GOAL", "4.0"))    # stop after +$4/day (NO re-entry same day)
DAILY_MAX_LOSS = float(os.getenv("DAILY_MAX_LOSS", "6.0"))          # stop after -$6/day (resume next day only)
MAX_DAILY_SPEND = float(os.getenv("MAX_DAILY_SPEND", "90.0"))       # max buys per day
DAILY_LOSS_STOP_PCT = float(os.getenv("DAILY_LOSS_STOP_PCT", "4.0")) # stop after -4% day

MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "3"))
ORDER_NOTIONAL = float(os.getenv("ORDER_NOTIONAL", "32.50"))        # $32.50 per trade (fractional)

COOLDOWN_MINUTES = int(os.getenv("COOLDOWN_MINUTES", "15"))

# Trading behavior
RUN_EVERY_SECONDS = int(os.getenv("RUN_EVERY_SECONDS", "120"))      # 2 min default
CASH_BUFFER = float(os.getenv("CASH_BUFFER", "2.00"))               # keep $2 buffer to avoid rejections

# Signals (stronger)
EMA_FAST = int(os.getenv("EMA_FAST", "9"))
EMA_SLOW = int(os.getenv("EMA_SLOW", "21"))
RSI_LEN = int(os.getenv("RSI_LEN", "14"))
RSI_BUY_MIN = float(os.getenv("RSI_BUY_MIN", "52"))                 # stronger than random
VOLUME_SPIKE = float(os.getenv("VOLUME_SPIKE", "1.10"))             # vol > 110% of vol avg

# After-hours behavior
ALLOW_EXTENDED_HOURS = os.getenv("ALLOW_EXTENDED_HOURS", "false").lower() == "true"

# State file (persists daily spend + start-of-day equity)
STATE_PATH = os.getenv("STATE_PATH", "state.json")

# -----------------------------
# HELPERS
# -----------------------------
def load_state():
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_state(state):
    try:
        with open(STATE_PATH, "w") as f:
            json.dump(state, f)
    except Exception:
        pass

def today_key():
    # Use UTC date to avoid timezone weirdness on servers
    return str(date.today())

def get_day_start_equity(api):
    """Get the equity at the start of the trading day (yesterday's close)"""
    acct = api.get_account()
    return float(acct.last_equity)

def get_current_equity(api):
    """Get the current account equity"""
    acct = api.get_account()
    return float(acct.equity)

def daily_pnl(api):
    """Calculate daily profit/loss vs yesterday's close"""
    acct = api.get_account()
    return float(acct.equity) - float(acct.last_equity)

def rsi(series: pd.Series, length: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(length).mean()
    loss = (-delta.clip(upper=0)).rolling(length).mean()
    rs = gain / (loss.replace(0, 1e-9))
    return 100 - (100 / (1 + rs))

def market_is_open(api: REST):
    clock = api.get_clock()
    return clock.is_open

def can_trade_now(api: REST) -> bool:
    if market_is_open(api):
        return True
    return ALLOW_EXTENDED_HOURS

def get_bars_df(api: REST, symbol: str, limit: int = 120) -> pd.DataFrame:
    bars = api.get_bars(symbol, TimeFrame.Minute, limit=limit).df
    # alpaca returns multi-index if multiple symbols; guard:
    if isinstance(bars.index, pd.MultiIndex):
        bars = bars.xs(symbol, level=0)
    bars = bars.reset_index()
    return bars

def strong_buy_signal(df: pd.DataFrame) -> bool:
    """Check for strong buy signal with trend, RSI, and volume confirmation"""
    # Indicators already computed: ema9, ema21, rsi, volume, vol_avg
    last = df.iloc[-1]

    trend_ok = last["ema9"] > last["ema21"]
    rsi_ok = 52 <= last["rsi"] <= 68
    volume_ok = last["volume"] > last["vol_avg"] * 1.2

    return trend_ok and rsi_ok and volume_ok

def position_exists(api: REST, symbol: str) -> bool:
    try:
        api.get_position(symbol)
        return True
    except Exception:
        return False

def list_open_positions(api: REST):
    try:
        return api.list_positions()
    except Exception:
        return []

def compute_daily_controls(api: REST, state: dict):
    """Compute daily spend and P&L tracking"""
    tk = today_key()
    if tk not in state:
        # Initialize today's tracking
        state[tk] = {
            "spent": 0.0,
            "last_trade_ts": 0,
            "symbol_trades": {}  # track trades per symbol
        }
        save_state(state)

    # Use Alpaca's last_equity for accurate day-start equity
    start_eq = get_day_start_equity(api)
    cur_eq = get_current_equity(api)
    daily_pl = daily_pnl(api)

    down_pct = 0.0
    if start_eq > 0:
        down_pct = abs((cur_eq - start_eq) / start_eq * 100.0) if cur_eq < start_eq else 0.0

    spent = float(state[tk].get("spent", 0.0))
    return spent, down_pct, start_eq, cur_eq, daily_pl

def register_spend(state: dict, amount: float, symbol: str = None):
    tk = today_key()
    state.setdefault(tk, {})
    state[tk]["spent"] = float(state[tk].get("spent", 0.0)) + float(amount)
    state[tk]["last_trade_ts"] = int(time.time())
    
    # Track per-symbol trades
    if symbol:
        state[tk].setdefault("symbol_trades", {})
        state[tk]["symbol_trades"][symbol] = state[tk]["symbol_trades"].get(symbol, 0) + 1
    
    save_state(state)

def submit_buy_notional(api: REST, symbol: str, notional: float):
    # If extended hours, safest is LIMIT order.
    # During regular hours, MARKET is fine.
    is_open = market_is_open(api)

    if is_open:
        order = api.submit_order(
            symbol=symbol,
            notional=round(notional, 2),
            side="buy",
            type="market",
            time_in_force="day"
        )
        return order

    # Extended hours: limit order (small cushion above last close)
    # NOTE: extended hours typically requires limit orders.
    df = get_bars_df(api, symbol, limit=5)
    last_price = float(df["close"].iloc[-1])
    limit_price = round(last_price * 1.002, 2)

    order = api.submit_order(
        symbol=symbol,
        notional=round(notional, 2),
        side="buy",
        type="limit",
        limit_price=limit_price,
        time_in_force="day",
        extended_hours=True
    )
    return order

def should_cooldown(state: dict, cooldown_sec: int = 90) -> bool:
    tk = today_key()
    last_ts = int(state.get(tk, {}).get("last_trade_ts", 0))
    return (time.time() - last_ts) < cooldown_sec

def manage_positions(api):
    """Check all open positions and exit on stop loss or take profit"""
    positions = api.list_positions()

    for p in positions:
        entry = float(p.avg_entry_price)
        last = float(p.current_price)
        qty = float(p.qty)

        pnl_pct = (last - entry) / entry * 100

        # Stop loss
        if pnl_pct <= STOP_LOSS_PCT:
            print(f"🛑 STOP LOSS {p.symbol} {pnl_pct:.2f}%")
            api.submit_order(
                symbol=p.symbol,
                qty=qty,
                side="sell",
                type="market",
                time_in_force="day"
            )

        # Take profit
        elif pnl_pct >= TAKE_PROFIT_PCT:
            print(f"💰 TAKE PROFIT {p.symbol} {pnl_pct:.2f}%")
            api.submit_order(
                symbol=p.symbol,
                qty=qty,
                side="sell",
                type="market",
                time_in_force="day"
            )

# -----------------------------
# MAIN LOOP
# -----------------------------
def main():
    if not APCA_API_KEY_ID or not APCA_API_SECRET_KEY:
        print("❌ Missing APCA_API_KEY_ID / APCA_API_SECRET_KEY env vars")
        return

    api = REST(APCA_API_KEY_ID, APCA_API_SECRET_KEY, APCA_API_BASE_URL, api_version="v2")
    state = load_state()

    print(f"✅ Connected. BaseURL={APCA_API_BASE_URL}")

    while True:
        try:
            # ========================================
            # 1️⃣ PROTECT CAPITAL - manage exits first
            # ========================================
            manage_positions(api)

            # Get account state
            acct = api.get_account()
            equity = float(acct.equity)
            usable_equity = equity * USE_EQUITY_PCT
            buying_power = min(float(acct.buying_power), usable_equity)
            cash = float(acct.cash)

            spent, down_pct, start_eq, cur_eq, daily_pl = compute_daily_controls(api, state)

            print(f"💰 Buying Power: {buying_power:.2f} | Cash: {cash:.2f} | Equity: {equity:.2f} (using {USE_EQUITY_PCT*100:.0f}%)")
            print(f"📊 Daily spent: {spent:.2f}/{MAX_DAILY_SPEND:.2f} | Down today: {down_pct:.2f}% (start {start_eq:.2f} → now {cur_eq:.2f})")
            
            pnl_today = daily_pnl(api)
            print(f"📊 Daily P&L: ${pnl_today:.2f}")

            # ========================================
            # 2️⃣ DAILY STOP CHECKS - goal/loss limits
            # ========================================
            # Stop after profit goal
            if pnl_today >= DAILY_PROFIT_GOAL:
                print("🎯 Daily profit goal reached. Stopping trading for today.")
                time.sleep(600)
                continue

            # Stop after max dollar loss
            if pnl_today <= -DAILY_MAX_LOSS:
                print(f"🛑 Daily max loss (-${DAILY_MAX_LOSS}) hit. Stopping trading for today.")
                time.sleep(600)
                continue

            # Stop after percentage loss limit
            if pnl_today <= -(equity * DAILY_LOSS_STOP_PCT / 100):
                print("🛑 Daily loss % limit hit. Stopping trading for today.")
                time.sleep(600)
                continue

            if spent >= MAX_DAILY_SPEND:
                print("🛑 Stop: reached MAX_DAILY_SPEND. No more buys today.")
                time.sleep(RUN_EVERY_SECONDS)
                continue

            # ========================================
            # 3️⃣ TRY ENTRIES - new buys only if safe
            # ========================================
            if not can_trade_now(api):
                print("⏳ Market closed. Sleeping.")
                time.sleep(RUN_EVERY_SECONDS)
                continue

            if should_cooldown(state, cooldown_sec=COOLDOWN_MINUTES * 60):
                print(f"⏳ Cooldown active ({COOLDOWN_MINUTES} min). Waiting.")
                time.sleep(RUN_EVERY_SECONDS)
                continue

            # Respect max open positions
            positions = list_open_positions(api)
            open_syms = {p.symbol for p in positions}
            if len(open_syms) >= MAX_OPEN_POSITIONS:
                print(f"✅ Max positions reached ({len(open_syms)}/{MAX_OPEN_POSITIONS}). Holding.")
                time.sleep(RUN_EVERY_SECONDS)
                continue

            # Remaining daily budget and usable equity (70% of total equity)
            remaining_budget = max(0.0, MAX_DAILY_SPEND - spent)
            available = max(0.0, buying_power - CASH_BUFFER)
            
            if available < ORDER_NOTIONAL or remaining_budget < ORDER_NOTIONAL:
                print(f"⚠️ Not enough buying power or daily budget left for ORDER_NOTIONAL (${ORDER_NOTIONAL}).")
                time.sleep(RUN_EVERY_SECONDS)
                continue

            # Use fixed ORDER_NOTIONAL capped by available budget
            notional = min(ORDER_NOTIONAL, remaining_budget, available)

            # Scan symbols for strongest signal; buy first match not already owned
            bought_any = False
            for sym in SYMBOLS:
                if sym in open_syms:
                    continue
                if position_exists(api, sym):
                    continue
                
                # Check symbol daily trade limit (2 trades per symbol per day)
                if not can_trade_symbol(state, sym, MAX_TRADES_PER_SYMBOL):
                    continue

                df = get_bars_df(api, sym, limit=120)
                if df.empty or len(df) < 50:
                    continue

                # Compute indicators
                close = df["close"]
                vol = df["volume"]
                df["ema9"] = close.ewm(span=9, adjust=False).mean()
                df["ema21"] = close.ewm(span=21, adjust=False).mean()
                df["rsi"] = rsi(close, 14)
                df["vol_avg"] = vol.rolling(20).mean()

                if strong_buy_signal(df):
                    print(f"🚀 Signal OK: {sym} | Trying BUY notional=${notional:.2f} (extended_hours={not market_is_open(api)})")
                    order = submit_buy_notional(api, sym, notional)
                    print(f"✅ Order submitted: {order.id} {sym} ${notional:.2f}")

                    register_spend(state, notional, symbol=sym)
                    bought_any = True
                    break

            if not bought_any:
                print("🔎 No strong signals right now. Waiting...")

        except Exception as e:
            print(f"❌ Loop error: {e}")

        print("🫀 Bot heartbeat...")
        time.sleep(60)

if __name__ == "__main__":
    main()
