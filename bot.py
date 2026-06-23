import os, time, logging, json
import pandas as pd

from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.requests import LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# =========================
# CONFIG & LOGGING
# =========================
MY_SYMBOLS = ["XLE", "SPCX", "QQQ", "SPY"]
# ... (Keep all your existing constants: MAX_CAPITAL_USAGE, etc.) ...
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger()

# ... (Keep your API and STATE functions as they are) ...

# =========================
# NEW DIAGNOSTIC FUNCTION
# =========================
def log_diagnostics():
    logger.info("--- DIAGNOSTIC SIGNAL SCAN START ---")
    for sym in MY_SYMBOLS:
        bars = get_bars(sym, limit=200)
        if bars is None: continue
        
        price = float(bars["close"].iloc[-1])
        ma = float(bars["close"].mean())
        
        logger.info(f"Calculating signal for {sym}")
        logger.info(f"{sym} Price: {price:.2f}")
        
        if price > ma:
            logger.info(f"{sym} Decision: YES | Reason: Bullish (Price {price:.2f} > MA {ma:.2f})")
        else:
            logger.info(f"{sym} Decision: NO | Reason: Trend not bullish (Price {price:.2f} < MA {ma:.2f})")
    logger.info("--- DIAGNOSTIC SIGNAL SCAN END ---")

# =========================
# MAIN LOOP
# =========================
logger.info("🚀 Sentinel v2 Running")

while True:
    try:
        if api.get_clock().is_open and trading_enabled:
            # Trigger diagnostics every 30 minutes (1800 seconds)
            if int(time.time()) % 1800 < 60:
                log_diagnostics()

            check_circuit_breaker()
            manage_positions()

            if market_trend_ok():
                for sym in MY_SYMBOLS:
                    try_buy(sym)
        
        time.sleep(60)

    except Exception as e:
        logger.error(f"Loop crash: {e}")
        time.sleep(120)
