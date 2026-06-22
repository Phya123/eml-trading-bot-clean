# --- IMPORTS AND INITIALIZATION ---
import csv, os, time
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestTradeRequest
from alpaca.data.timeframe import TimeFrame

# Initialize clients
trading_client = TradingClient(os.getenv('APCA_API_KEY_ID'), os.getenv('APCA_API_SECRET_KEY'), paper=True)
data_client = StockHistoricalDataClient(os.getenv('APCA_API_KEY_ID'), os.getenv('APCA_API_SECRET_KEY'))

# Create aliases
api = trading_client
data_api = data_client

# --- HELPER FUNCTIONS (At top level, not inside others!) ---
def _get_bars_dataframe(symbol, limit):
    request = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Minute,
        limit=limit
    )
    bars = data_api.get_stock_bars(request)
    return bars.df

# --- TRADING LOGIC ---
def force_buy(symbol, amount=None):
    try:
        # Now this call works perfectly
        bars = _get_bars_dataframe(symbol, limit=60)
        current_price = float(bars['close'].iloc[-1])
        
        order = api.submit_order(symbol=symbol, qty=1, side='buy', type='market', time_in_force='day')
        print(f"✅ FORCED BUY: {symbol}")
        return True
    except Exception as e:
        print(f"❌ FORCED BUY FAILED: {symbol} - {e}")
        return False
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Minute,
        limit=limit
    )
    bars = data_api.get_stock_bars(request)
    return bars.df

def force_buy(symbol, amount=None):
    try:
        # Get market data using our helper
        bars = _get_bars_dataframe(symbol, limit=60)
        current_price = float(bars['close'].iloc[-1])
        
        # Calculate ATR and trade logic...
        # (Keep your existing ATR and quantity calculation here)
        
        # Execute the order using the trading_client (aliased as 'api')
        order = api.submit_order(
            symbol=symbol,
            qty=qty,
            side='buy',
            type='market',
            time_in_force='day'
        )
        print(f"✅ FORCED BUY: {symbol}")
        return True
    except Exception as e:
        print(f"❌ FORCED BUY FAILED: {symbol} - {e}")
        return False
    def calculate_position_size(self, current_price, atr_value, atr_multiplier=2.0):
        # Dollar amount to risk: 1% of your $400 = $4.00
        risk_amount = self.equity * self.risk_per_trade
        # The stop-loss zone based on volatility
        stop_loss_distance = atr_value * atr_multiplier
        if stop_loss_distance <= 0: return 1 # Default to 1 share if ATR is missing
        shares = int(risk_amount / stop_loss_distance)
        return max(shares, 1)
TRADE_LOG_FILE = "trade_log.csv"


# ==========================================
# RETRY LOGIC FOR API REQUESTS
# ==========================================

def retry_api_call(func, max_retries=3, retry_delay=1.0, backoff_factor=2.0):
    """
    Retry an API call with exponential backoff.
    
    Args:
        func: Callable that makes the API request
        max_retries: Maximum number of retry attempts
        retry_delay: Initial delay between retries in seconds
        backoff_factor: Multiplier for delay after each retry
    
    Returns:
        Result of func if successful, None if all retries fail
    """
    last_error = None
    
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                wait_time = retry_delay * (backoff_factor ** attempt)
                print(f"  API request failed (attempt {attempt + 1}/{max_retries}): {e}")
                print(f"  Retrying in {wait_time:.1f} seconds...")
                time.sleep(wait_time)
            else:
                print(f"  API request failed after {max_retries} attempts: {e}")
    
    return None


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

def _calculate_rsi(close_series, period=14):
    delta = close_series.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    
    avg_gain = gains.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = losses.ewm(alpha=1 / period, adjust=False).mean()
    
    relative_strength = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + relative_strength))
    return rsi.fillna(50.0)

def _clamp(value, minimum=0.0, maximum=1.0):
    clamped = max(minimum, min(maximum, value))
    if 0.0 < clamped < 1.00:
        return 10.00
    return clamped
def _get_bars_dataframe(symbol, limit=60):
    for timeframe in ["1Min", "5Min", "1Day"]:
        try:
            # We added feed='iex' at the end of the parameters below:
            bars = api.get_bars(symbol, timeframe, limit=limit, adjustment='all', feed='iex')
            df = bars.df
            if df is not None and not df.empty:
                if isinstance(df.index, pd.MultiIndex):
                    df = df.xs(symbol, level=0)
                print(f"✅ Loaded historical data for {symbol} using {timeframe} bars.")
                return df.sort_index()
        except Exception as data_error:
            print(f"⚠️ Debug {symbol} ({timeframe}): {data_error}")
            continue
    
    print(f"❌ {symbol} - All market data attempts failed.")
    return None
def calculate_signal(symbol, debug=False):
    if debug:
        print(f"Calculating signal for {symbol}")

    bars = _get_bars_dataframe(symbol, limit=60)
    if bars is None:
        if debug:
            print(f"{symbol} signal score: 0.00")
            print(f"{symbol} trend indicators: unavailable")
        return (0.0, {}) if debug else 0.0

    if "close" not in bars.columns or bars["close"].dropna().empty:
        if debug:
            print(f"{symbol} signal score: 0.00")
            print(f"{symbol} trend indicators: unavailable")
        return (0.0, {}) if debug else 0.0

    close_prices = bars['close'].astype(float)
    bars['TR'] = bars[['high', 'low', 'close']].apply(lambda x: max(x['high']-x['low'], abs(x['high']-x['close']), abs(x['low']-x['close'])), axis=1)
    bars['ATR'] = bars['TR'].rolling(window=14).mean()
    
    latest_price = float(close_prices.iloc[-1])
    short_ema = float(close_prices.ewm(span=9, adjust=False).mean().iloc[-1])
    long_ema = float(close_prices.ewm(span=21, adjust=False).mean().iloc[-1])
    rsi_series = _calculate_rsi(close_prices, period=14)
    latest_rsi = float(rsi_series.iloc[-1])

    if len(close_prices) >= 6:
        momentum_5d = (latest_price / float(close_prices.iloc[-6])) - 1.0
    else:
        momentum_5d = 0.0

    if "volume" in bars.columns and bars["volume"].dropna().shape[0] >= 2:
        volume_series = bars["volume"].astype(float)
        average_volume = float(volume_series.rolling(window=20, min_periods=1).mean().iloc[-1])
        latest_volume = float(volume_series.iloc[-1])
        volume_ratio = (latest_volume / average_volume) if average_volume > 0 else 1.0
    else:
        volume_ratio = 1.0

    trend_score = 1.0 if short_ema > long_ema else 0.0
    price_score = 1.0 if latest_price > short_ema else 0.5 if latest_price > long_ema else 0.0
    momentum_score = _clamp((momentum_5d + 0.02) / 0.04)

    if 50 <= latest_rsi <= 65:
        rsi_score = 1.0
    elif 45 <= latest_rsi < 50 or 65 < latest_rsi <= 72:
        rsi_score = 0.7
    elif 35 <= latest_rsi < 45:
        rsi_score = 0.3
    else:
        rsi_score = 0.0

    volume_score = _clamp(volume_ratio / 2.0)

    signal_score = (
        0.40 * trend_score
        + 0.20 * price_score
        + 0.20 * momentum_score
        + 0.10 * rsi_score
        + 0.10 * volume_score
    )

    if debug:
        print(f"{symbol} signal score: {signal_score:.2f}")
        print(f"{symbol} price: {latest_price:.2f}")
        print(
            f"{symbol} trend indicators used: "
            f"EMA9={short_ema:.2f}, EMA21={long_ema:.2f}, RSI14={latest_rsi:.2f}, "
            f"5D Momentum={momentum_5d * 100:.2f}%, VolumeRatio={volume_ratio:.2f}"
        )

    details = {
        "trend_score": float(trend_score),
        "price_score": float(price_score),
        "momentum_score": float(momentum_score),
        "rsi_score": float(rsi_score),
        "volume_score": float(volume_score),
        "latest_price": float(latest_price),
        "latest_rsi": float(latest_rsi),
        "volume_ratio": float(volume_ratio),
        "ema9": float(short_ema),
        "ema21": float(long_ema),
        "momentum_5d": float(momentum_5d),
    }

    if debug:
        return round(signal_score, 4), details

    return round(signal_score, 4)

MIN_SIGNAL_SCORE = 0.40  # Lowered from 0.5 for more trading opportunities
SELL_SIGNAL_SCORE = 0.30  # Lowered from 0.35 to hold positions longer
PROFIT_TARGET_PCT = 0.03  # Take profit at 3%
STOP_LOSS_PCT = 0.02  # Stop loss at 2%
CHECK_INTERVAL_SECONDS = 60  # Check signals every 60 seconds


def _get_rejection_reason(score, details):
    if score >= MIN_SIGNAL_SCORE:
        return ""

    if not details:
        return "Signal unavailable or market data insufficient"

    reasons = []
    if details.get("trend_score", 0) < 0.5:
        reasons.append(f"trend not bullish (EMA9={details.get('ema9'):.2f} <= EMA21={details.get('ema21'):.2f})")
    if details.get("price_score", 0) <= 0.5:
        reasons.append(f"price below/near EMAs (price={details.get('latest_price'):.2f})")
    if details.get("momentum_score", 0) < 0.5:
        reasons.append(f"low momentum (5d={details.get('momentum_5d') * 100:.2f}%)")
    if details.get("rsi_score", 0) < 0.7:
        reasons.append(f"RSI not ideal (RSI={details.get('latest_rsi'):.2f})")
    if details.get("volume_score", 0) < 0.5:
        reasons.append(f"low relative volume (vol_ratio={details.get('volume_ratio'):.2f})")

    if not reasons:
        return "Strong Buy Signal"
    return "; ".join(reasons)


def _print_scan_result(symbol, score, details):
    latest_price = details.get("latest_price") if details else None
    print(f"{symbol}")
    print(f"  Price: {latest_price:.2f}" if latest_price is not None else f"  Price: unavailable")
    print(f"  Signal Score: {score:.4f}")
    print(f"  Minimum Required: {MIN_SIGNAL_SCORE:.2f}")
    buy_decision = score >= MIN_SIGNAL_SCORE
    print(f"  Decision: {'YES' if buy_decision else 'NO'}")
    if not buy_decision:
        print(f"  Reason: {_get_rejection_reason(score, details)}")
    print("")


def run_diagnostic_scan(symbols_to_scan):
    print("\n--- DIAGNOSTIC SIGNAL SCAN START ---")
    results = []

    for symbol in symbols_to_scan:
        # Request debug output from calculate_signal
        try:
            score, details = calculate_signal(symbol, debug=True)
        except Exception as e:
            print(f"{symbol} diagnostic failed: {e}")
            score = 0.0
            details = {}

        _print_scan_result(symbol, score, details)
        results.append({"symbol": symbol, "score": score, "details": details})

    # Highest signal found
    highest = max(results, key=lambda r: r["score"]) if results else None
    highest_score = highest["score"] if highest else 0.0
    highest_symbol = highest["symbol"] if highest else "N/A"

    print("Highest Signal Found This Cycle:")
    print(f"  {highest_symbol}: {highest_score:.4f}\n")

    if highest_score < MIN_SIGNAL_SCORE:
        print("No symbol exceeded the minimum required signal score this cycle.")

    # Check for constant/identical scores across symbols (possible bug)
    scores = [r["score"] for r in results]
    if len(scores) > 1 and all(abs(scores[0] - v) < 1e-8 for v in scores[1:]):
        print("WARNING: All scanned symbols returned the same signal score. This may indicate a bug or constant return value in calculate_signal().")

    print("--- DIAGNOSTIC SIGNAL SCAN END ---\n")


# ==========================================
# SPACEX EVENT MODE
# ==========================================

SPACEX_MODE = True
SPACEX_SYMBOL = "SPCX"
SPACEX_MAX_ALLOC = 0.25
SPACEX_MAX_SPREAD_PCT = 0.05
SPACEX_WAIT_MINUTES = 5
SPACEX_ASSET = None


def _now_et():
    return datetime.now(ZoneInfo("America/New_York"))


def _extract_float_value(source, *attribute_names):
    for attribute_name in attribute_names:
        value = getattr(source, attribute_name, None)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _get_spcx_session(now=None):
    now = now or _now_et()
    minutes_since_midnight = now.hour * 60 + now.minute + (now.second / 60.0)

    if minutes_since_midnight >= (20 * 60) or minutes_since_midnight < (4 * 60):
        return "overnight"
    if minutes_since_midnight < (9 * 60 + 30):
        return "pre-market"
    if minutes_since_midnight < (16 * 60):
        return "regular"
    return "closed"


def minutes_since_market_open(now=None):
    now = now or _now_et()
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    return (now - market_open).total_seconds() / 60


def _get_spcx_quote_data():
    try:
        quote = api.get_latest_quote(SPACEX_SYMBOL)
    except Exception as error:
        print(f"SPCX skipped: quote lookup failed: {error}")
        return None

    bid_price = _extract_float_value(quote, "bid_price", "bp")
    ask_price = _extract_float_value(quote, "ask_price", "ap")

    if bid_price is None or ask_price is None or bid_price <= 0 or ask_price <= 0:
        print("SPCX skipped: invalid quote data")
        return None

    if ask_price <= bid_price:
        print("SPCX skipped: invalid bid/ask spread")
        return None

    mid_price = (bid_price + ask_price) / 2.0
    spread_pct = (ask_price - bid_price) / mid_price if mid_price > 0 else None

    if spread_pct is None:
        print("SPCX skipped: spread calculation failed")
        return None

    return {
        "bid": bid_price,
        "ask": ask_price,
        "spread_pct": spread_pct,
    }


def _has_spcx_position():
    try:
        result = retry_api_call(lambda: api.get_position(SPACEX_SYMBOL))
        return result is not None
    except Exception:
        return False


def _seconds_until_next_spcx_session(now=None):
    now = now or _now_et()
    minutes_since_midnight = now.hour * 60 + now.minute + (now.second / 60.0)

    if minutes_since_midnight < (4 * 60):
        target = now.replace(hour=4, minute=0, second=0, microsecond=0)
    elif minutes_since_midnight < (9 * 60 + 30):
        target = now.replace(hour=9, minute=30, second=0, microsecond=0)
    elif minutes_since_midnight < (16 * 60):
        target = now.replace(hour=16, minute=0, second=0, microsecond=0)
    elif minutes_since_midnight < (20 * 60):
        target = now.replace(hour=20, minute=0, second=0, microsecond=0)
    else:
        target = (now + timedelta(days=1)).replace(hour=4, minute=0, second=0, microsecond=0)

    return max(60.0, (target - now).total_seconds())


def run_spcx_scheduler():
    print("SPCX scheduler active")
    while True:
        try:
            now = _now_et()
            session = _get_spcx_session(now)

            if session == "closed":
                sleep_seconds = _seconds_until_next_spcx_session(now)
                print(f"SPCX scheduler sleeping until next session: {sleep_seconds / 60:.1f} minutes")
                time.sleep(sleep_seconds)
                continue

            if _has_spcx_position():
                print("SPCX position already open; scheduler skipping new entry")
            else:
                account = api.get_account()
                equity = float(account.equity)
                buying_power = float(account.buying_power)
                spacex_price = float(api.get_latest_trade(SPACEX_SYMBOL).price)
                handle_spacex(spacex_price, equity, buying_power)

        except Exception as error:
            print(f"SPCX scheduler error: {error}")

        time.sleep(300)


def handle_spacex(price, equity, buying_power=None):
    if not SPACEX_MODE:
        return

    print("Checking SPCX...")

    if SPACEX_ASSET is None:
        print("SPCX skipped: asset lookup unavailable")
        return

    asset_status = str(getattr(SPACEX_ASSET, "status", "")).lower()
    if asset_status == "halted":
        print("SPCX skipped: asset is halted")
        return

    if not bool(getattr(SPACEX_ASSET, "tradable", True)):
        print("SPCX skipped: asset is not tradable")
        return

    now = _now_et()
    session = _get_spcx_session(now)

    if session == "overnight":
        print("SPCX overnight trading active")
    elif session == "pre-market":
        print("SPCX pre-market trading active")
    elif session == "regular":
        print("SPCX regular session active")
    else:
        print("SPCX skipped: outside supported trading sessions")
        return

    quote_data = _get_spcx_quote_data()
    if quote_data is None:
        return

    if quote_data["spread_pct"] > SPACEX_MAX_SPREAD_PCT:
        print(
            "SPCX skipped: spread exceeds threshold "
            f"({quote_data['spread_pct']:.2%} > {SPACEX_MAX_SPREAD_PCT:.2%})"
        )
        return

    signal_score = calculate_signal(SPACEX_SYMBOL)
    print(f"SPCX signal score: {signal_score}")

    if signal_score < MIN_SIGNAL_SCORE:
        print("SPCX signal below threshold")
        return

    max_dollars = equity * SPACEX_MAX_ALLOC
    buying_power_value = float(buying_power) if buying_power is not None else max_dollars
    allocation_allowed = min(max_dollars, buying_power_value)
    print(f"SPCX allocation allowed: ${allocation_allowed:.2f}")

    if allocation_allowed <= 0:
        print("SPCX skipped: allocation unavailable")
        return

    whole_share_only = session in ("overnight", "pre-market") or minutes_since_market_open(now) < SPACEX_WAIT_MINUTES

    if whole_share_only:
        print("SPCX whole-share restriction active")
        order_price = float(quote_data["ask"])
        qty = int(allocation_allowed / order_price)
        print(f"SPCX calculated quantity: {qty}")

        if qty < 1:
            print("SPCX allocation exceeded")
            return

        required_buying_power = qty * order_price
        if buying_power is not None and float(buying_power) < required_buying_power:
            print("SPCX buying power insufficient")
            return

        try:
            api.submit_order(
                symbol=SPACEX_SYMBOL,
                qty=qty,
                side="buy",
                type="limit",
                limit_price=round(order_price, 2),
                time_in_force="day",
                extended_hours=session in ("overnight", "pre-market"),
            )
            print(f"SPACEX order submitted: {qty} shares")
        except Exception as e:
            print(f"SPCX order failed: {e}")
    else:
        estimated_qty = allocation_allowed / price if price > 0 else 0.0
        print(f"SPCX calculated quantity: {estimated_qty:.4f}")

        try:
            api.submit_order(
                symbol=SPACEX_SYMBOL,
                notional=round(allocation_allowed, 2),
                side="buy",
                type="market",
                time_in_force="day",
            )
            print(f"SPACEX order submitted: notional ${allocation_allowed:.2f}")
        except Exception as e:
            print(f"SPCX order failed: {e}")


# ==========================================
# MARKET HOURS & TRADING DAYS VALIDATION
# ==========================================

# US Market Holidays 2026
US_MARKET_HOLIDAYS_2026 = [
    (1, 1),    # New Year's Day
    (1, 19),   # MLK Jr. Day
    (2, 16),   # Presidents' Day
    (3, 27),   # Good Friday
    (5, 25),   # Memorial Day
    (7, 3),    # Independence Day (observed, market closed Fri 7/3)
    (9, 7),    # Labor Day
    (11, 26),  # Thanksgiving
    (12, 25),  # Christmas
]


def is_trading_day(now=None):
    """Check if today is a trading day (not weekend or US market holiday)."""
    now = now or _now_et()
    
    # Check weekends (Monday=0, Sunday=6)
    if now.weekday() >= 5:  # 5=Saturday, 6=Sunday
        return False
    
    # Check US market holidays
    if (now.month, now.day) in US_MARKET_HOLIDAYS_2026:
        return False
    
    return True


def is_market_open(now=None):
    """Check if the market is currently open (9:30 AM - 4:00 PM ET, trading days only)."""
    now = now or _now_et()
    
    # First check if it's a trading day
    if not is_trading_day(now):
        return False
    
    # Check regular market hours: 9:30 AM to 4:00 PM ET
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    
    return market_open <= now < market_close


def time_until_market_open(now=None):
    """Calculate minutes until market opens."""
    now = now or _now_et()
    
    # If market is currently open, return 0
    if is_market_open(now):
        return 0
    
    # Check if today is a trading day
    if is_trading_day(now):
        # Market opens at 9:30 AM ET
        
        if now < market_open:
            return (market_open - now).total_seconds() / 60
    
    # Find next trading day
    next_day = now + timedelta(days=1)
    while not is_trading_day(next_day):
        next_day += timedelta(days=1)
    
    # Market opens at 9:30 AM ET on the next trading day
    next_market_open = next_day.replace(hour=9, minute=30, second=0, microsecond=0)
    return (next_market_open - now).total_seconds() / 60


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

import os

# Force the bot to pull directly from your Railway environment settings
API_KEY = os.getenv('API_KEY') or os.getenv('ALPACA_API_KEY')
API_SECRET = os.getenv('API_SECRET') or os.getenv('ALPACA_API_SECRET')
BASE_URL = os.getenv('BASE_URL') or os.getenv('ALPACA_API_URL') or 'https://paper-api.alpaca.markets'

# Create the client directly using the grabbed variables
api = tradeapi.REST(API_KEY, API_SECRET, BASE_URL, api_version='v2')

# Bypass the strict string check to ensure it loads
if not API_KEY or API_KEY in ['your_api_key', 'your_real_key', '']:
    print("\n❌ ERROR: Missing or placeholder Alpaca API credentials!")
    raise RuntimeError("Invalid API credentials")

if SPACEX_MODE:
    try:
        SPACEX_ASSET = api.get_asset(SPACEX_SYMBOL)
        print(f"✅ SpaceX asset found: {SPACEX_ASSET.symbol}")
    except Exception as e:
        print(f"❌ SPCX asset lookup failed: {e}")

if SPACEX_MODE:
    try:
        from alpaca.data.requests import StockLatestTradeRequest
        # Use data_api to get the trade
        request = StockLatestTradeRequest(symbol_or_symbols=SPACEX_SYMBOL)
        trade = data_api.get_stock_latest_trade(request)
        spacex_price = float(trade[SPACEX_SYMBOL].price)
        
        # Use trading_client (aliased as 'api') for the account info
        account = api.get_account()
        equity = float(account.equity)
        buying_power = float(account.buying_power)
        
        handle_spacex(spacex_price, equity, buying_power)
    except Exception as e:
        print(f"SPACEX mode skipped: {e}")
    try:
        account = api.get_account()
        equity = float(account.equity)
        # Fixed line

        spacex_price = float(api.get_latest_trade(SPACEX_SYMBOL).price)
        handle_spacex(spacex_price, equity, buying_power)
    except Exception as e:
        print(f"SPACEX mode skipped: {e}")
def _get_bars_dataframe(symbol, limit)
# Example symbols and trade size (customize as needed)
symbols = ['SPY', 'QQQ', 'XLE']
trade_size = 100  # Notional value in dollars

    """Force a buy order for a specific symbol."""
    try:
        # Get market data
        bars = _get_bars_dataframe(symbol, limit=60)
        current_price = float(bars['close'].iloc[-1])
        
        # Calculate ATR for volatility-adjusted sizing
        bars['TR'] = bars[['high', 'low', 'close']].apply(lambda x: max(x['high']-x['low'], abs(x['high']-x['close']), abs(x['low']-x['close'])), axis=1)
        bars['ATR'] = bars['TR'].rolling(window=14).mean()
        current_atr = float(bars['ATR'].iloc[-1])
        
        # Calculate quantity dynamically
        qty = risk_engine.calculate_position_size(
            current_price=current_price,
            atr_value=current_atr
        )
        
        # Execute the order
        order = api.submit_order(
            symbol=symbol,
            qty=qty,
            side='buy',
            type='market',
            time_in_force='day'
        )
        
        print(f"✅ FORCED BUY: {symbol} | Qty: {qty} | Price: {current_price}")
        log_trade(symbol, "BUY", current_price, None, qty, 0, "FORCED BUY")
        return True
    except Exception as e:
        print(f"❌ FORCED BUY FAILED: {symbol} - {e}")
        return False
def should_sell_position(symbol, entry_price, current_price):
    """Determine if a position should be sold based on price targets or signal strength."""
    profit_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0
    
    # Check profit target
    if profit_pct >= PROFIT_TARGET_PCT:
        return True, f"Profit target reached ({profit_pct * 100:.2f}%)"
    
    # Check stop loss
    if profit_pct <= -STOP_LOSS_PCT:
        return True, f"Stop loss hit ({profit_pct * 100:.2f}%)"
    
    # Check signal strength
    signal_score = calculate_signal(symbol, debug=False)
    if signal_score < SELL_SIGNAL_SCORE:
        return True, f"Signal weakened (score: {signal_score:.4f})"
    
    return False, ""


def manage_positions():
    """Check open positions and sell if conditions are met."""
    try:
        positions = retry_api_call(lambda: api.list_positions())
        if not positions:
            return
        
        for position in positions:
            symbol = position.symbol
            qty = float(position.qty)
            entry_price = float(position.avg_entry_price)
            current_trade = api.get_latest_trade(symbol)
            current_price = float(current_trade.price)
            
            should_sell, reason = should_sell_position(symbol, entry_price, current_price)
            
            if should_sell:
                try:
                    api.submit_order(
                        symbol=symbol,
                        qty=qty,
                        side="sell",
                        type="market",
                        time_in_force="day"
                    )
                    pnl = (current_price - entry_price) * qty
                    print(f"✅ SELL {symbol}: {qty} shares @ ${current_price:.2f} | Reason: {reason} | PnL: ${pnl:.2f}")
                    log_trade(symbol, "SELL", entry_price, current_price, qty, pnl, reason)
                except Exception as e:
                    print(f"❌ SELL FAILED: {symbol} - {e}")
    except Exception as e:
        print(f"Position management error: {e}")


def check_and_execute_trades():
    """Check signals and execute buy trades."""
    any_buy_signal = False

    for symbol in symbols:
        try:
            orders = api.list_orders(status='open')
            if symbol in [o.symbol for o in orders]:
                print(f"⏳ Pending order for {symbol}.")
                continue
        except Exception as e:
            print(f"⚠️ Check failed: {e}")

        if symbol == SPACEX_SYMBOL and SPACEX_MODE:
            trade_size = SPACEX_MAX_ALLOC
        else:
            trade_size = 1

        if trade_size < 1:
            print("Trade size too small...")
            continue

        signal_score, details = calculate_signal(symbol, debug=True)
        buy_decision = signal_score >= MIN_SIGNAL_SCORE

        print(f"({symbol})")
        print(f" Price: {details.get('latest_price', 'unavailable') if details.get('latest_price') is not None else 'unavailable'}")
        print(f" Signal Score: {signal_score:.4f}")
        print(f" Minimum Required: {MIN_SIGNAL_SCORE:.2f}")
        print(f" Decision: {'YES' if buy_decision else 'NO'}")

        if not buy_decision:
            print(f" Reason: {_get_rejection_reason(signal_score, details)}")

        if buy_decision:
            any_buy_signal = True
            current_price = details.get('latest_price', 0)

            # VALIDATE: Ensure price data is available before submitting order
            if current_price <= 0:
                print(f"⚠️ SKIPPED {symbol}: No valid price data available")
                print(f" Signal was strong ({signal_score:.4f}) but market data incomplete. Will retry next cycle.\n")
                continue

            try:
                order = api.submit_order(
                    symbol=symbol,
                    notional=trade_size,
                    side="buy",
                    type="market",
                    time_in_force="day"
                )
                qty = trade_size / current_price if current_price > 0 else 0
                print(f"✅ BUY ORDER SUBMITTED: {symbol} | Qty: {qty:.4f} | Price: ${current_price:.2f}")
                log_trade(symbol, "BUY", current_price, None, qty, 0, "Signal threshold exceeded")
            except Exception as e:
                print(f"❌ BUY ORDER FAILED: {symbol}")
                print(f"ERROR: {e}")
        else:
            print(f"Skipping {symbol}: signal score below minimum ({MIN_SIGNAL_SCORE}).")

        print("Running initial diagnostic scan...\n")
try: run_diagnostic_scan(['SPY', 'QQQ', 'XLE', 'SPCX'])
except Exception as e: print(f"Diagnostic scan failed: {e}")

force_buy_cmd = os.getenv('FORCE_BUY', '').strip()
force_sell_cmd = os.getenv('FORCE_SELL', '').strip()

if force_buy_cmd:
    parts = force_buy_cmd.split(':')
    symbol = parts[0].strip()
    amount = float(parts[1]) if len(parts) > 1 else 1
    print(f"\n📥 Executing forced buy: {symbol} (${amount:.2f})")
    force_buy(symbol, amount)

if force_sell_cmd:
    for symbol in force_sell_cmd.split(','): print(f"\n📤 Executing forced sell: {symbol.strip()}"); force_sell(symbol.strip())

print("🚀 Starting main trading loop...")
while True:
    try:
        now = _now_et()
        if not is_market_open(now): time.sleep(CHECK_INTERVAL_SECONDS); continue
        try: positions = retry_api_call(lambda: api.list_positions()); open_positions = {p.symbol: {"qty": float(p.qty), "avg_entry": float(p.avg_entry_price)} for p in (positions or [])}
        except Exception as e: print(f"⚠️ Position sync failed: {e}"); open_positions = {}
        manage_positions()
        check_and_execute_trades()
        if SPACEX_MODE:
            try: account = api.get_account(); handle_spacex(float(api.get_latest_trade(SPACEX_SYMBOL).price), float(account.equity), float(account.buying_power))
            except Exception as e: print(f"⚠️ SpaceX check failed: {e}")
        print(f"⏳ Sleeping for {CHECK_INTERVAL_SECONDS} seconds..."); time.sleep(CHECK_INTERVAL_SECONDS)
    except KeyboardInterrupt: print("\n🛑 Bot stopped by user."); break
    except Exception as e: print(f"❌ Trading loop error: {e}"); time.sleep(CHECK_INTERVAL_SECONDS)
