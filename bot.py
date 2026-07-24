# =========================
# IMPORTS
# =========================

import os
import time
import logging

from dotenv import load_dotenv

from alpaca.trading.client import TradingClient


# =========================
# LOAD ENVIRONMENT
# =========================

load_dotenv()


API_KEY = os.getenv(
    "ALPACA_API_KEY"
)

API_SECRET = os.getenv(
    "ALPACA_SECRET_KEY"
)


if not API_KEY or not API_SECRET:

    raise Exception(
        "Missing Alpaca API credentials"
    )


# =========================
# ALPACA CONNECTION
# =========================

api = TradingClient(
    API_KEY,
    API_SECRET,
    paper=False
)


logging.info(
    "ALPACA CONNECTION ONLINE"
)
def buy(symbol):

    # your buy logic here


    submitted = api.submit_order(
        order_data=order
    )


    order_id = submitted.id


    time.sleep(2)


    filled = api.get_order_by_id(
        order_id
    )

filled = api.get_order_by_id(
    GetOrderByIdRequest(order_id=order_id)
)
# =========================
# CONFIG
# =========================

SYMBOLS = [
    "SPY",
    "QQQ",
    "AAPL",
    "LMT",
    "XLE",
    "SPCX",
    "NVDA",
    "ASML",
    "TSM",
    "DEO",
    "NVS"
]

TIMEFRAME = TimeFrame.Minute

FAST_MA = 20
SLOW_MA = 50
MA200 = 200
ATR_PERIOD = 14


MAX_CAPITAL_USAGE = 0.15


# UPDATED RISK SETTINGS

STOP_LOSS_PCT = 0.02
TAKE_PROFIT_PCT = 0.12
MIN_HOLD_MINUTES = 30
TRAILING_STOP_PCT = 0.03
BREAKEVEN_TRIGGER = 0.05

COOLDOWN_SECONDS = 900      # 15 minutes
MIN_HOLD_MINUTES = 15
# SMART PROFIT SYSTEM
TRAILING_STOP_PCT = 0.02      # 2% trail
BREAKEVEN_TRIGGER = 0.03      # activate trailing after +3%

DAILY_LOSS_LIMIT = 0.03
MAX_TRADES_PER_DAY = 10

ENABLE_TRADING = True



# =========================
# ASSET SAFETY FILTER
# =========================

ALLOWED_ASSET_CLASS = "us_equity"


def verify_stock_asset(symbol):

    try:

        asset = api.get_asset(symbol)

        if asset.asset_class != ALLOWED_ASSET_CLASS:

            log(f"{symbol} BLOCKED - NOT STOCK")

            return False

        return True


    except Exception as e:

        log(f"{symbol} ASSET CHECK ERROR {e}")

        return False



# =========================
# LOGGING
# =========================

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout
)

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
    "order_map": {},
    "pending_orders": {}
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
# RECOVER EXISTING POSITIONS
# =========================

def recover_positions():

    try:

        positions = api.get_all_positions()

        for p in positions:

            symbol = p.symbol

            entry = float(
                p.avg_entry_price
            )

            current = float(
                p.current_price
            )


            if symbol not in state["entry_time"]:

                state["entry_time"][symbol] = datetime.now()

                state["highest_price"][symbol] = max(
                    entry,
                    current
                )

                log(
                    f"{symbol} POSITION RECOVERED ENTRY={entry:.2f}"
                )


    except Exception as e:

        log(
            f"POSITION RECOVERY ERROR {e}"
        )
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


    stats["Trades"] = str(
        int(stats["Trades"]) + 1
    )


    if pnl > 0:

        stats["Wins"] = str(
            int(stats["Wins"]) + 1
        )

    else:

        stats["Losses"] = str(
            int(stats["Losses"]) + 1
        )



    total = float(stats["Total_PnL"]) + pnl


    stats["Total_PnL"] = str(total)

    stats["Average_PnL"] = str(
        total / int(stats["Trades"])
    )



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


        drawdown = (
            state["start_equity"] - equity
        ) / state["start_equity"]



        if drawdown >= DAILY_LOSS_LIMIT:

            global ENABLE_TRADING

            ENABLE_TRADING = False


            log(
                f"🚨 CIRCUIT BREAKER TRIGGERED DD={drawdown:.2%}"
            )



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



    return tr.rolling(ATR_PERIOD).mean().iloc[-1]





# =========================
# ANALYZE
# =========================

def analyze(symbol):

    log(f"{symbol} START ANALYSIS")



    df = get_data(symbol)



    if df is None:

        log(f"{symbol} SIGNAL=BAD_DATA")

        return 0.0, "BAD_DATA"




    price = float(
        df["close"].iloc[-1]
    )



    fast = (
        df["close"]
        .rolling(FAST_MA)
        .mean()
        .iloc[-1]
    )


    slow = (
        df["close"]
        .rolling(SLOW_MA)
        .mean()
        .iloc[-1]
    )


    ma200 = (
        df["close"]
        .rolling(MA200)
        .mean()
        .iloc[-1]
    )



    vol = atr(df)



    log(f"{symbol} PRICE={price:.2f}")

    log(f"{symbol} FAST_MA={fast:.2f} SLOW_MA={slow:.2f}")

    log(f"{symbol} MA200={ma200:.2f}")

    log(f"{symbol} ATR={vol:.4f}")



    if pd.isna(fast) or pd.isna(slow) or pd.isna(ma200):

        log(f"{symbol} SIGNAL=NO_SIGNAL")

        return price, "NO_SIGNAL"



    # =========================
    # NEW VOLATILITY FILTER
    # =========================

    vol_ratio = vol / price



    log(
        f"{symbol} VOL_RATIO={vol_ratio:.4f}"
    )



    if (

        fast > slow and

        price > ma200 and

        vol_ratio > 0.002

    ):

        trend = "BULLISH"


    else:

        trend = "BEARISH"




    log(f"{symbol} TREND={trend}")

    log(f"{symbol} SIGNAL={trend}")



    return price, trend
# =========================
# ORDER STATUS MANAGER
# =========================

def check_pending_orders():

    try:

        completed = []

        for symbol, order_id in state["pending_orders"].items():

            try:

                order = api.get_order(order_id)


                log(
                    f"{symbol} ORDER STATUS={order.status}"
                )


                if order.status == "filled":

                    fill_price = float(
                        order.filled_avg_price
                    )


                    state["entry_time"][symbol] = datetime.now()


                    state["highest_price"][symbol] = fill_price


                    log(
                        f"{symbol} ENTRY TRACKING STARTED PRICE={fill_price:.2f}"
                    )


                    completed.append(symbol)



                elif order.status in [
                    "canceled",
                    "rejected",
                    "expired"
                ]:

                    log(
                        f"{symbol} ORDER FAILED STATUS={order.status}"
                    )

                    completed.append(symbol)



            except Exception as e:

                log(
                    f"{symbol} ORDER CHECK ERROR {e}"
                )


        # remove completed orders

        for symbol in completed:

            state["pending_orders"].pop(
                symbol,
                None
            )


    except Exception as e:

        log(
            f"PENDING ORDER MANAGER ERROR {e}"
        )
# =========================
# BUY ENGINE
# =========================

def buy(symbol):
    # =========================
    # GLOBAL TRADING LOCK
    # =========================

    if not ENABLE_TRADING:
        log(f"{symbol} BLOCKED - TRADING DISABLED")
        return
    # =========================
    # DAILY TRADE LIMIT
    # =========================

    if state["trade_count"] >= MAX_TRADES_PER_DAY:
        log(
            f"{symbol} BLOCKED - MAX DAILY TRADES REACHED"
        )
        return
    # =========================
    # STOCK ONLY SAFETY LOCK
    # =========================

    if symbol not in SYMBOLS:

        log(f"{symbol} BLOCKED - NOT IN STOCK LIST")

        return



    if not verify_stock_asset(symbol):

        return




    # =========================
    # MARKET OPEN CHECK
    # =========================

    try:

        if not api.get_clock().is_open:

            log(f"{symbol} MARKET_CLOSED")

            return


    except Exception as e:

        log(f"{symbol} CLOCK_ERROR {e}")

        return





    # =========================
    # EXISTING POSITION CHECK
    # =========================

    try:

        positions = api.get_all_positions()



        for p in positions:

            if p.symbol == symbol:

                log(
                    f"{symbol} SKIPPED - POSITION_EXISTS"
                )

                return



    except Exception as e:

        log(
            f"{symbol} POSITION_CHECK_ERROR {e}"
        )

        return





    # =========================
    # COOLDOWN CHECK
    # =========================

    last_trade = state["last_trade_time"].get(symbol)



    if last_trade:


        elapsed = (

            datetime.now() - last_trade

        ).total_seconds()



        if elapsed < COOLDOWN_SECONDS:


            log(
                f"{symbol} COOLDOWN ACTIVE"
            )

            return





    # =========================
    # ANALYSIS
    # =========================

    price, signal = analyze(symbol)



    log(
        f"{symbol} SIGNAL={signal}"
    )



    if signal != "BULLISH":

        return






    # =========================
    # CAPITAL CHECK
    # =========================

    account = api.get_account()



    spend = (

        float(account.buying_power)

        *

        MAX_CAPITAL_USAGE

    )



    if spend < 5:


        log(
            f"{symbol} SKIPPED - INSUFFICIENT_BUYING_POWER"
        )

        return








        


    # =========================
    # CHECK PENDING ORDERS
    # =========================

    if symbol in state["pending_orders"]:

        log(
            f"{symbol} SKIPPED - ORDER_PENDING"
        )

        return


# =========================
# ORDER SUBMISSION
# WHOLE + FRACTIONAL SHARES
# =========================

try:

    # Calculate whole shares first
    qty = int(spend // price)

    if qty >= 1:

        order = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY
        )

    else:

        # Fractional shares fallback
        order = MarketOrderRequest(
            symbol=symbol,
            notional=round(spend, 2),
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY
        )


    # Submit order
    submitted = api.submit_order(
        order_data=order
    )

    order_id = submitted.id

    state["order_map"][order_id] = symbol
    state["pending_orders"][symbol] = order_id


    log(
        f"{symbol} ORDER SENT id={order_id}"
    )


    # Wait for Alpaca execution
    time.sleep(2)


    try:

        filled = api.get_order_by_id(
            order_id
        )


        log(
            f"{symbol} STATUS={filled.status}"
        )

        log(
            f"{symbol} FILLED={filled.filled_qty}"
        )

        log(
            f"{symbol} PRICE={filled.filled_avg_price}"
        )


        if str(filled.status).lower() == "filled":


            entry_price = float(
                filled.filled_avg_price
            )


            state["entry_time"][symbol] = datetime.now()

            state["last_trade_time"][symbol] = datetime.now()

            state["highest_price"][symbol] = entry_price


            state["pending_orders"].pop(
                symbol,
                None
            )


            state["trade_count"] += 1

            trade_stats["trades"] += 1


            log(
                f"BUY CONFIRMED {symbol} ${spend:.2f}"
            )


            log(
                f"{symbol} ENTRY TRACKING STARTED"
            )


        else:

            log(
                f"{symbol} NOT FILLED STATUS={filled.status}"
            )


    except Exception as e:

        log(
            f"{symbol} FILL_CHECK_ERROR {e}"
        )


except Exception as e:

    log(
        f"{symbol} BUY_ERROR {e}"
    )
# =========================
# POSITION MANAGEMENT
# =========================

def manage_positions():

    try:

        positions = api.get_all_positions()

        for p in positions:

            entry = float(
                p.avg_entry_price
            )

            price = float(
                p.current_price
            )

            # =========================
            # TRACK HIGHEST PRICE
            # =========================
            highest = state["highest_price"].get(
                p.symbol,
                price
            )

            if price > highest:
                highest = price
                state["highest_price"][p.symbol] = highest

            # Continue with your existing code...
            # entry_time = state["entry_time"].get(p.symbol)
            

            # =========================
            # MINIMUM HOLD PROTECTION
            # =========================

            entry_time = state["entry_time"].get(
                p.symbol
            )



            if entry_time:


                held_minutes = (

                    datetime.now() - entry_time

                ).total_seconds() / 60



                if held_minutes < MIN_HOLD_MINUTES:


                    log(
                        f"{p.symbol} HOLDING ({held_minutes:.1f} min)"
                    )


                    continue






            pnl_pct = (

                price - entry

            ) / entry



            log(
                f"{p.symbol} UNREALIZED_PNL={pnl_pct:.2%}"
            )


            log(
                f"{p.symbol} TP={TAKE_PROFIT_PCT:.2%} | CURRENT={pnl_pct:.2%}"
            )





           
            # =========================
            # SMART PROFIT SYSTEM
            # =========================

            if pnl_pct >= BREAKEVEN_TRIGGER:

                trail_price = highest * (
                    1 - TRAILING_STOP_PCT
                )

                log(
                    f"{p.symbol} HIGH={highest:.2f} TRAIL={trail_price:.2f}"
                )

                if price <= trail_price:

                    api.close_position(
                        p.symbol
                    )

                    log(
                        f"{p.symbol} EXIT TRAILING STOP"
                    )

                    realized_pnl = (
                        price - entry
                    ) / entry * 100


                    update_symbol_stats(
                        p.symbol,
                        realized_pnl
                    )


                    trade_stats["pnl"] += realized_pnl


                    if realized_pnl > 0:

                        trade_stats["wins"] += 1

                    else:

                        trade_stats["losses"] += 1







            # =========================
            # STOP LOSS
            # =========================

            elif pnl_pct <= -STOP_LOSS_PCT:



                api.close_position(
                    p.symbol
                )



                log(
                    f"{p.symbol} EXIT STOP LOSS"
                )



                realized_pnl = (

                    price - entry

                ) / entry * 100



                update_symbol_stats(
                    p.symbol,
                    realized_pnl
                )



                trade_stats["pnl"] += realized_pnl



                if realized_pnl > 0:

                    trade_stats["wins"] += 1

                else:

                    trade_stats["losses"] += 1





    except Exception as e:


        log(
            f"POSITION ERROR {e}"
        )



# =========================
# ALPACA PERFORMANCE TRACKER
# =========================

def get_trade_history_stats():

    try:

        request = GetOrdersRequest(
            status=QueryOrderStatus.CLOSED,
            limit=500
        )


        orders = api.get_orders(
            filter=request
        )


        trades = 0
        wins = 0
        losses = 0
        pnl = 0.0


        for order in orders:

            if order.side == OrderSide.SELL:

                trades += 1


                if order.filled_avg_price:

                    # Alpaca does not provide full realized PnL here,
                    # this is the framework. We will connect fills next.

                    if float(order.filled_avg_price) > 0:

                        wins += 1



        if trades > 0:

            win_rate = (
                wins / trades
            ) * 100

        else:

            win_rate = 0


        return {

            "trades": trades,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "pnl": pnl

        }


    except Exception as e:

        log(
            f"PERFORMANCE ERROR {e}"
        )


        return {

            "trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0,
            "pnl": 0

        }
# =========================
# REAL PERFORMANCE ENGINE
# =========================

def get_real_performance():

    try:

        request = GetOrdersRequest(
            status=QueryOrderStatus.CLOSED,
            limit=500
        )


        orders = api.get_orders(
            filter=request
        )


        buys = {}
        wins = 0
        losses = 0
        realized_pnl = 0.0
        total_trades = 0


        for order in orders:

            if order.status != "filled":
                continue


            symbol = order.symbol


            if order.side == OrderSide.BUY:

                buys[symbol] = {
                    "qty": float(order.filled_qty),
                    "price": float(order.filled_avg_price)
                }


            elif order.side == OrderSide.SELL:

                if symbol in buys:

                    entry = buys[symbol]["price"]

                    exit_price = float(
                        order.filled_avg_price
                    )

                    qty = buys[symbol]["qty"]


                    pnl = (
                        exit_price - entry
                    ) * qty


                    realized_pnl += pnl

                    total_trades += 1


                    if pnl > 0:
                        wins += 1
                    else:
                        losses += 1


        


        return {

            "trades": total_trades,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "pnl": realized_pnl

        }


    except Exception as e:

        log(
            f"REAL PERFORMANCE ERROR {e}"
        )


        return {

            "trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0,
            "pnl": 0

        }
# =========================
# LIVE DASHBOARD
# =========================
def get_real_performance():

    return {
        "trades": trade_stats["trades"],
        "wins": trade_stats["wins"],
        "losses": trade_stats["losses"],
        "win_rate": (
            trade_stats["wins"] / trade_stats["trades"] * 100
            if trade_stats["trades"] > 0
            else 0
        ),
        "pnl": trade_stats["pnl"]
    }


def log_dashboard():

    try:


        acc = api.get_account()


        clock = api.get_clock()


        positions = api.get_all_positions()



        # =========================
        # REAL PERFORMANCE DATA
        # =========================

        performance = get_real_performance()

        trades = performance["trades"]

        wins = performance["wins"]

        losses = performance["losses"]

        win_rate = performance["win_rate"]

        realized_pnl = performance["pnl"]




        log(
            "==================================="
        )


        log(
            "📊 SENTINEL LIVE DASHBOARD"
        )


        log(
            f"Market: {'OPEN' if clock.is_open else 'CLOSED'}"
        )


        log(
            f"Equity: ${float(acc.equity):.2f}"
        )


        log(
            f"Buying Power: ${float(acc.buying_power):.2f}"
        )


        log(
            f"Open Positions: {len(positions)}"
        )


        log(
            f"Trades: {trades}"
        )


        log(
            f"Wins: {wins} | Losses: {losses}"
        )


        log(
            f"Win Rate: {win_rate:.2f}%"
        )


        log(
            f"Realized PnL: {realized_pnl:.2f}"
        )


        log(
            "==================================="
        )



    except Exception as e:


        log(
            f"DASHBOARD ERROR {e}"
        )




# =========================
# DAILY RESET MANAGER
# =========================

def check_daily_reset():

    global ENABLE_TRADING

    today = date.today()


    if state["day"] != today:

        log(
            "NEW TRADING DAY - RESETTING DAILY STATS"
        )


        state["day"] = today

        state["trade_count"] = 0

        state["start_equity"] = None

        ENABLE_TRADING = True

# =========================
# MAIN LOOP
# =========================

log(
    "SENTINEL LIVE ENGINE STARTED"
)


initialize_symbol_stats()

recover_positions()


while True:

    try:

        # =========================
        # DAILY RESET CHECK
        # =========================

        check_daily_reset()


        # =========================
        # RISK PROTECTION
        # =========================

        if check_circuit_breaker():

            log(
                "CIRCUIT BREAKER ACTIVE - NO NEW TRADES"
            )

            manage_positions()

            log_dashboard()

            time.sleep(60)

            continue



        # =========================
        # MARKET STATUS
        # =========================

        clock = api.get_clock()



        if not clock.is_open:


            log(
                "MARKET CLOSED - MONITORING ONLY"
            )


            manage_positions()

            log_dashboard()



        else:


            # =========================
            # CHECK EXISTING ORDERS
            # =========================

            check_pending_orders()



            # =========================
            # SCAN WATCHLIST
            # =========================

            if ENABLE_TRADING:


                for sym in SYMBOLS:


                    try:


                        log(
                            f"SCANNING {sym}"
                        )


                        buy(sym)



                    except Exception as e:


                        log(
                            f"{sym} BUY ERROR {e}"
                        )



            else:


                log(
                    "TRADING DISABLED - MONITORING ONLY"
                )



            # =========================
            # POSITION MANAGEMENT
            # =========================

            manage_positions()



            # =========================
            # DASHBOARD UPDATE
            # =========================

            log_dashboard()



    except Exception as e:


        log(
            f"MAIN LOOP ERROR {e}"
        )



    # Engine heartbeat

    time.sleep(60)
