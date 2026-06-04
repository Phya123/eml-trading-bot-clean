import csv
import os
from datetime import datetime
import alpaca_trade_api as tradeapi

TRADE_LOG_FILE = "trade_log.csv"


# ==========================================
# CREATE CSV FILE IF IT DOESN'T EXIST
# ==========================================

def initialize_trade_log():
    if not os.path.exists(TRADE_LOG_FILE):
        with open(TRADE_LOG_FILE, mode="w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow([
                "Timestamp",
                "Symbol",
                "Side",
                "Entry Price",
                "Exit Price",
                "Quantity",
                "PnL",
                "Reason"
            ])
        print("✅ Trade log initialized.")


# ==========================================
# LOG A TRADE
# ==========================================

def log_trade(symbol, side, entry_price, exit_price, quantity, pnl, reason):
    with open(TRADE_LOG_FILE, mode="a", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            symbol,
            side,
            entry_price,
            exit_price,
            quantity,
            pnl,
            reason
        ])
    print(f"📈 Trade logged: {symbol} | PnL={pnl}")


def calculate_signal(symbol):
    # TODO: replace this placeholder with your real signal logic
    print(f"Calculating signal for {symbol}")
    return 0.0

MIN_SIGNAL_SCORE = 0.5


# ==========================================
# INITIALIZE ON STARTUP
# ==========================================

initialize_trade_log()

# ==========================================
# MAIN TRADING LOGIC
# ==========================================

# Alpaca API setup (replace with your credentials)
API_KEY = os.getenv('ALPACA_API_KEY', 'your_api_key')
API_SECRET = os.getenv('ALPACA_API_SECRET', 'your_secret')
BASE_URL = 'https://paper-api.alpaca.markets'  # Use live URL for live trading

api = tradeapi.REST(API_KEY, API_SECRET, BASE_URL, api_version='v2')

# Example symbols and trade size (customize as needed)
symbols = ['SPY', 'QQQ', 'XLE']
trade_size = 100  # Notional value in dollars
open_positions = {}

try:
    positions = api.list_positions()
    open_positions = {
        p.symbol: {
            "qty": float(p.qty),
            "avg_entry": float(p.avg_entry_price)
        }
        for p in positions
    }
    print(f"Synced positions: {list(open_positions.keys())}")
except Exception as e:
    print(f"Position sync failed: {e}")
    open_positions = {}

for symbol in symbols:
    if trade_size < 1:
        print("Trade size too small. Skipping.")
        continue

    signal_score = calculate_signal(symbol)
    print(f"{symbol} signal score = {signal_score}")
    print(f"Checking buy conditions for {symbol}")

    if signal_score >= MIN_SIGNAL_SCORE:
        try:
            order = api.submit_order(
                symbol=symbol,
                notional=trade_size,
                side="buy",
                type="market",
                time_in_force="day"
            )
            print(f"✅ ORDER SUCCESS: {symbol}")
        except Exception as e:
            print(f"❌ ORDER FAILED: {symbol}")
            print(f"ERROR: {e}")
            # Prevent crash loop
            continue
    else:
        print(f"Skipping {symbol}: signal score below minimum ({MIN_SIGNAL_SCORE}).")
