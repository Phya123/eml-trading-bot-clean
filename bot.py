import os
import time
import logging
import sys
import csv

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

STOP_LOSS_PCT = 0.03
TAKE_PROFIT_PCT = 0.08

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
    "entry_time": {},
    "highest_price": {},
    "trade_count": 0,
    "day": date.today(),
    "vol_history": {},
    "order_map": {}
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
# BUY ENGINE
# =========================

def buy(symbol):


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
    # ORDER SUBMISSION
    # WHOLE + FRACTIONAL SHARES
    # =========================

    try:



        if spend >= price:


            # BUY WHOLE SHARES

            qty = int(
                spend // price
            )



            if qty < 1:

                log(
                    f"{symbol} SHARE SIZE TOO SMALL"
                )

                return



            order = MarketOrderRequest(

                symbol=symbol,

                qty=qty,

                side=OrderSide.BUY,

                time_in_force=TimeInForce.DAY

            )



        else:


            # BUY FRACTIONAL SHARES

            order = MarketOrderRequest(

                symbol=symbol,

                notional=round(spend, 2),

                side=OrderSide.BUY,

                time_in_force=TimeInForce.DAY

            )





        submitted = api.submit_order(
            order_data=order
        )



        order_id = submitted.id



        state["order_map"][order_id] = symbol



        # TRACK ENTRY TIME

        state["entry_time"][symbol] = datetime.now()

        state["last_trade_time"][symbol] = datetime.now()

        state["highest_price"][symbol] = price

        log(
            f"{symbol} ORDER SENT id={order_id}"
        )



        # WAIT FOR FILL CHECK

        time.sleep(1)



        try:


            filled = api.get_order(order_id)



            log(
                f"{symbol} FILL STATUS={filled.status}"
            )


            log(
                f"{symbol} FILLED_QTY={filled.filled_qty}"
            )


            log(
                f"{symbol} AVG_PRICE={filled.filled_avg_price}"
            )



        except Exception as e:


            log(
                f"{symbol} FILL_CHECK_ERROR {e}"
            )





        state["trade_count"] += 1


        trade_stats["trades"] += 1



        log(
            f"BUY CONFIRMED {symbol} ${spend:.2f}"
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
# LIVE DASHBOARD
# =========================

def log_dashboard():

    try:


        acc = api.get_account()


        clock = api.get_clock()


        positions = api.get_all_positions()



        win_rate = 0



        if trade_stats["trades"] > 0:


            win_rate = (

                trade_stats["wins"]

                /

                trade_stats["trades"]

            ) * 100




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
            f"Trades: {trade_stats['trades']}"
        )


        log(
            f"Wins: {trade_stats['wins']} | Losses: {trade_stats['losses']}"
        )


        log(
            f"Win Rate: {win_rate:.2f}%"
        )


        log(
            f"PnL: {trade_stats['pnl']:.4f}"
        )


        log(
            "==================================="
        )



    except Exception as e:


        log(
            f"DASHBOARD ERROR {e}"
        )






# =========================
# MAIN LOOP
# =========================

log(
    "SENTINEL LIVE ENGINE STARTED"
)



initialize_symbol_stats()



while True:


    try:


        check_circuit_breaker()



        clock = api.get_clock()



        if not clock.is_open:



            log(
                "MARKET CLOSED - MONITORING ONLY"
            )



            log_dashboard()




        else:



            for sym in SYMBOLS:


                log(
                    f"LOOP START -> {sym}"
                )


                buy(sym)




            manage_positions()



            log_dashboard()




    except Exception as e:


        log(
            f"LOOP ERROR {e}"
        )



    time.sleep(60)
