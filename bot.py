import os, time, logging, sys, csv
import pandas as pd
from datetime import date, datetime

from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.client import TradingClient

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame


# =========================
# CONFIG
# =========================
SYMBOLS = ["SPY", "QQQ", "AAPL", "LMT", "XLE"]

TIMEFRAME = TimeFrame.Minute

FAST_MA = 20
SLOW_MA = 50
ATR_PERIOD = 14

MAX_CAPITAL_USAGE = 0.05

STOP_LOSS_PCT = 0.02
TAKE_PROFIT_PCT = 0.04
TRAILING_STOP_PCT = 0.015

COOLDOWN_SECONDS = 120
DAILY_LOSS_LIMIT = 0.03
MAX_TRADES_PER_DAY = 10

ENABLE_TRADING = True

TRADE_LOG_FILE = "trade_journal.csv"


# =========================
# STRATEGY MODES
# =========================
STRATEGY_MODE = {
    "AAPL": "FAST",
    "LMT": "SLOW",
    "SPY": "DEFAULT",
    "QQQ": "DEFAULT",
    "XLE": "DEFAULT"
}


# =========================
# LOGGING
# =========================
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger()


# =========================
# API
# =========================
api = TradingClient(
    os.environ.get("APCA_API_KEY_ID"),
    os.environ.get("APCA_API_SECRET_KEY"),
    paper=False
)

data_api = StockHistoricalDataClient(
    os.environ.get("APCA_API_KEY_ID"),
    os.environ.get("APCA_API_SECRET_KEY")
)


# =========================
# STATE
# =========================
state = {
    "start_equity": None,
    "last_trade_time": {},
    "position_high": {},
    "trade_count": 0,
    "day": date.today(),
    "vol_history": {}
}

for sym in SYMBOLS:
    state["vol_history"][sym] = []


# =========================
# DASHBOARD STATE
# =========================
trade_stats = {
    "trades": 0,
    "wins": 0,
    "losses": 0,
    "pnl": 0.0
}


# =========================
# EMERGENCY STOP
# =========================
def emergency_stop(reason):
    global ENABLE_TRADING
    ENABLE_TRADING = False
    logger.critical(f"🚨 EMERGENCY STOP: {reason}")


# =========================
# JOURNAL
# =========================
def log_trade(symbol, side, price, qty, pnl, reason):
    file_exists = os.path.isfile(TRADE_LOG_FILE)

    with open(TRADE_LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)

        if not file_exists:
            writer.writerow(["time", "symbol", "side", "price", "qty", "pnl", "reason"])

        writer.writerow([
            datetime.utcnow(),
            symbol,
            side,
            price,
            qty,
            pnl,
            reason
        ])


# =========================
# DASHBOARD
# =========================
def print_dashboard():
    trades = trade_stats["trades"]
    wins = trade_stats["wins"]
    losses = trade_stats["losses"]
    pnl = trade_stats["pnl"]

    win_rate = (wins / trades * 100) if trades > 0 else 0

    logger.info("===================================")
    logger.info("📊 LIVE DASHBOARD")
    logger.info(f"Trades: {trades}")
    logger.info(f"Wins: {wins} | Losses: {losses}")
    logger.info(f"Win Rate: {win_rate:.2f}%")
    logger.info(f"PnL: {pnl:.4f}")
    logger.info("===================================")


# =========================
# DATA
# =========================
def get_data(symbol):
    try:
        req = StockBarsRequest(
            symbol_or_symbols=[symbol],
            timeframe=TIMEFRAME,
            limit=200
        )

        bars = data_api.get_stock_bars(req)
        df = bars.df

        if isinstance(df.index, pd.MultiIndex):
            df = df.xs(symbol)

        df = df.dropna()

        if df is None or len(df) < 10:
            return None

        return df

    except Exception as e:
        logger.error(f"{symbol} data error: {e}")
        return None


# =========================
# ATR
# =========================
def atr(df, period=14):
    high = df["high"]
    low = df["low"]
    close = df["close"]

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)

    return tr.rolling(period).mean().iloc[-1]


# =========================
# THRESHOLD
# =========================
def get_threshold(symbol):
    mode = STRATEGY_MODE.get(symbol, "DEFAULT")

    if mode == "FAST":
        return 0.0007
    if mode == "SLOW":
        return 0.0013
    return 0.0010


# =========================
# ANALYZE (FIXED + MORE TRADABLE)
# =========================
def analyze(symbol):
    logger.info(f"STARTING ANALYSIS FOR {symbol}")

    df = get_data(symbol)

    if df is None or len(df) < 60:
        return 0.0, "BAD_DATA"

    price = float(df["close"].iloc[-1])

    fast = df["close"].rolling(FAST_MA).mean().iloc[-1]
    slow = df["close"].rolling(SLOW_MA).mean().iloc[-1]
    vol = atr(df, ATR_PERIOD)

    if pd.isna(fast) or pd.isna(slow) or pd.isna(vol):
        return price, "NO_SIGNAL"

    trend = "BULLISH" if fast > slow else "BEARISH"

    current_vol_ratio = vol / price

    state["vol_history"][symbol].append(current_vol_ratio)
    if len(state["vol_history"][symbol]) > 20:
        state["vol_history"][symbol].pop(0)

    avg = sum(state["vol_history"][symbol]) / len(state["vol_history"][symbol])
    dynamic_threshold = max(get_threshold(symbol), avg * 0.85)

    logger.info(
        f"{symbol} TREND={trend} VolRatio={current_vol_ratio:.4f} TH={dynamic_threshold:.4f}"
    )

    # FIX: allow some LOW VOL trades instead of blocking everything
    if current_vol_ratio < dynamic_threshold:
        return price, f"{trend}_LOW_VOL_SKIP"

    return price, trend


# =========================
# BUY ENGINE (FIXED TRADING LOGIC)
# =========================
def buy(symbol):
    global ENABLE_TRADING

    if not ENABLE_TRADING:
        return

    if state["trade_count"] >= MAX_TRADES_PER_DAY:
        return

    positions = api.get_all_positions()
    if any(p.symbol == symbol for p in positions):
        return

    price, signal = analyze(symbol)

    logger.info(f"{symbol} SIGNAL: {signal}")

    # FIXED TRADE RULES (this is what was blocking you before)
    if signal not in ["BULLISH", "BULLISH_LOW_VOL_SKIP"]:
        return

    account = api.get_account()
    spend = float(account.buying_power) * MAX_CAPITAL_USAGE

    if signal == "BULLISH_LOW_VOL_SKIP":
        spend *= 0.6  # reduced conviction sizing

    if spend < 5:
        return

    try:
        order = MarketOrderRequest(
            symbol=symbol,
            notional=round(spend, 2),
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY
        )

        api.submit_order(order)

        state["last_trade_time"][symbol] = time.time()
        state["trade_count"] += 1

        trade_stats["trades"] += 1

        logger.info(f"BUY SENT {symbol} ${spend:.2f}")

    except Exception as e:
        logger.error(f"{symbol} buy error: {e}")


# =========================
# POSITION MANAGEMENT
# =========================
def manage_positions():
    try:
        positions = api.get_all_positions()

        for p in positions:
            symbol = p.symbol
            entry = float(p.avg_entry_price)
            price = float(p.current_price)

            if symbol not in state["position_high"]:
                state["position_high"][symbol] = price

            state["position_high"][symbol] = max(
                state["position_high"][symbol],
                price
            )

            pnl_pct = (price - entry) / entry

            reason = None

            if pnl_pct >= TAKE_PROFIT_PCT:
                reason = "TAKE_PROFIT"
            elif pnl_pct <= -STOP_LOSS_PCT:
                reason = "STOP_LOSS"
            elif price <= state["position_high"][symbol] * (1 - TRAILING_STOP_PCT):
                reason = "TRAIL_STOP"

            if reason:
                api.close_position(symbol)
                logger.info(f"{symbol} EXIT ({reason})")

                trade_stats["pnl"] += pnl_pct

                if pnl_pct > 0:
                    trade_stats["wins"] += 1
                else:
                    trade_stats["losses"] += 1

                log_trade(symbol, "SELL", price, 1, pnl_pct, reason)

    except Exception as e:
        logger.error(f"position error: {e}")


# =========================
# MAIN LOOP
# =========================
logger.info("🚀 SENTINEL LIVE ENGINE STARTED")

while True:
    try:
        for sym in SYMBOLS:
            buy(sym)

        manage_positions()
        print_dashboard()

    except Exception as e:
        logger.error(f"loop error: {e}")

    time.sleep(60)
