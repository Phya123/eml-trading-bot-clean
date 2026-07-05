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
SYMBOLS = ["SPY", "QQQ", "AAPL", "LMT", "XLE", "SPCX", "NVDA", "ASML", "TSM", "DEO", "NVS"]

TIMEFRAME = TimeFrame.Minute

FAST_MA = 20
SLOW_MA = 50
MA200 = 200
ATR_PERIOD = 14

MAX_CAPITAL_USAGE = 0.05

STOP_LOSS_PCT = 0.02
TAKE_PROFIT_PCT = 0.04

COOLDOWN_SECONDS = 120
DAILY_LOSS_LIMIT = 0.03
MAX_TRADES_PER_DAY = 10

ENABLE_TRADING = True


# =========================
# LOGGING
# =========================
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger()

def log(msg):
    logger.info(msg)


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
    "trade_count": 0,
    "day": date.today(),
    "vol_history": {},
    "order_map": {}   # ✅ ADDED: track orders
}

for s in SYMBOLS:
    state["vol_history"][s] = []


trade_stats = {
    "trades": 0,
    "wins": 0,
    "losses": 0,
    "pnl": 0.0
}
# =========================
# SYMBOL PERFORMANCE TRACKER
# =========================
SYMBOL_STATS_FILE = "symbol_stats.csv"


def initialize_symbol_stats():
    if not os.path.exists(SYMBOL_STATS_FILE):
        with open(SYMBOL_STATS_FILE, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Symbol",
                "Trades",
                "Wins",
                "Losses",
                "Total_PnL",
                "Average_PnL"
            ])


def update_symbol_stats(symbol, pnl):

    rows = {}

    if os.path.exists(SYMBOL_STATS_FILE):
        with open(SYMBOL_STATS_FILE, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows[row["Symbol"]] = row

    if symbol not in rows:
        rows[symbol] = {
            "Symbol": symbol,
            "Trades": "0",
            "Wins": "0",
            "Losses": "0",
            "Total_PnL": "0",
            "Average_PnL": "0"
        }

    stats = rows[symbol]

    stats["Trades"] = str(int(stats["Trades"]) + 1)

    if pnl > 0:
        stats["Wins"] = str(int(stats["Wins"]) + 1)
    else:
        stats["Losses"] = str(int(stats["Losses"]) + 1)

    total = float(stats["Total_PnL"]) + pnl
    stats["Total_PnL"] = str(total)
    stats["Average_PnL"] = str(total / int(stats["Trades"]))

    with open(SYMBOL_STATS_FILE, "w", newline="") as f:
        writer = csv.writer(f)

        writer.writerow([
            "Symbol",
            "Trades",
            "Wins",
            "Losses",
            "Total_PnL",
            "Average_PnL"
        ])

        for row in rows.values():
            writer.writerow([
                row["Symbol"],
                row["Trades"],
                row["Wins"],
                row["Losses"],
                row["Total_PnL"],
                row["Average_PnL"]
            ])

# =========================
# CIRCUIT BREAKER
# =========================
def check_circuit_breaker():
    try:
        acc = api.get_account()

        if state["start_equity"] is None:
            state["start_equity"] = float(acc.equity)

        equity = float(acc.equity)
        drawdown = (state["start_equity"] - equity) / state["start_equity"]

        if drawdown >= DAILY_LOSS_LIMIT:
            global ENABLE_TRADING
            ENABLE_TRADING = False
            log(f"🚨 CIRCUIT BREAKER TRIGGERED DD={drawdown:.2%}")

    except Exception as e:
        log(f"CIRCUIT ERROR {e}")


# =========================
# DATA
# =========================
def get_data(symbol):
    try:
        req = StockBarsRequest(
            symbol_or_symbols=[symbol],
            timeframe=TIMEFRAME,
            limit=250
        )

        bars = data_api.get_stock_bars(req)

        if bars is None or bars.df is None or len(bars.df) == 0:
            log(f"{symbol} BAD_DATA")
            return None

        df = bars.df

        if isinstance(df.index, pd.MultiIndex):
            df = df.xs(symbol)

        df = df.dropna()

        if len(df) < 210:
            return None

        return df

    except Exception as e:
        log(f"{symbol} DATA_ERROR {e}")
        return None


# =========================
# ATR
# =========================
def atr(df):
    high = df["high"]
    low = df["low"]
    close = df["close"]

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)

    return tr.rolling(14).mean().iloc[-1]


# =========================
# ANALYZE
# =========================
def analyze(symbol):
    log(f"{symbol} START ANALYSIS")

    df = get_data(symbol)
    if df is None:
        return 0.0, "BAD_DATA"

    price = float(df["close"].iloc[-1])

    fast = df["close"].rolling(FAST_MA).mean().iloc[-1]
    slow = df["close"].rolling(SLOW_MA).mean().iloc[-1]
    ma200 = df["close"].rolling(MA200).mean().iloc[-1]

    vol = atr(df)

    if price < ma200:
        log(f"{symbol} BELOW MA200 SKIP")
        return price, "BELOW_MA200"

    if pd.isna(fast) or pd.isna(slow):
        return price, "NO_SIGNAL"

    trend = "BULLISH" if fast > slow else "BEARISH"

    return price, trend


# =========================
# BUY ENGINE (ORDER TRACKING ADDED)
# =========================
def buy(symbol):

    try:
        if not api.get_clock().is_open:
            log(f"{symbol} MARKET_CLOSED")
            return

    except:
        return

    price, signal = analyze(symbol)

    log(f"{symbol} SIGNAL={signal}")

    if signal != "BULLISH":
        return

    account = api.get_account()
    spend = float(account.buying_power) * MAX_CAPITAL_USAGE

    if spend < 5:
        return

    try:
        order = MarketOrderRequest(
            symbol=symbol,
            notional=round(spend, 2),
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY
        )

        submitted = api.submit_order(order_data=order)

        # =========================
        # ✅ ORDER TRACKING (NEW FIX)
        # =========================
        order_id = submitted.id
        state["order_map"][order_id] = symbol

        log(f"{symbol} ORDER SENT id={order_id}")

        # wait briefly for fill (light polling)
        time.sleep(1)

        try:
            filled = api.get_order(order_id)

            log(f"{symbol} FILL STATUS={filled.status}")
            log(f"{symbol} FILLED_QTY={filled.filled_qty}")
            log(f"{symbol} AVG_PRICE={filled.filled_avg_price}")

        except Exception as e:
            log(f"{symbol} FILL_CHECK_ERROR {e}")

        state["trade_count"] += 1
        trade_stats["trades"] += 1

        log(f"BUY CONFIRMED {symbol} ${spend:.2f}")

    except Exception as e:
        log(f"{symbol} BUY_ERROR {e}")


# =========================
# POSITION MANAGEMENT (PnL LOG ADDED)
# =========================
def manage_positions():
    try:
        positions = api.get_all_positions()

        for p in positions:
            entry = float(p.avg_entry_price)
            price = float(p.current_price)

            pnl_pct = (price - entry) / entry

            log(f"{p.symbol} UNREALIZED_PNL={pnl_pct:.2%}")
            log(f"{p.symbol} TP={TAKE_PROFIT_PCT:.2%} | CURRENT={pnl_pct:.2%}")

            if pnl_pct >= TAKE_PROFIT_PCT:
                api.close_position(p.symbol)
                log(f"{p.symbol} EXIT TAKE_PROFIT")

                realized_pnl = (price - entry) / entry * 100
                update_symbol_stats(p.symbol, realized_pnl)

    except Exception as e:
        log(f"POSITION ERROR {e}")


# =========================
# MAIN LOOP
# =========================
log("SENTINEL LIVE ENGINE STARTED")
initialize_symbol_stats()
while True:
    try:
        check_circuit_breaker()

        for sym in SYMBOLS:
            log(f"LOOP START -> {sym}")
            buy(sym)

        manage_positions()

    except Exception as e:
        log(f"LOOP ERROR {e}")

    time.sleep(60)
