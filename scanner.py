import requests
import pandas as pd
import yfinance as yf
import os
import math
from datetime import datetime, timezone

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_IDS = ["5608017991", "1856754382"]  # Apni aur friend ki ID yahan hain

# Watchlist (XAG/USD removed, Gold & all major indices/stocks included)
WATCHLIST = [
    "GC=F",                              # Gold (XAU/USD)
    "^NSEI", "^NSEBANK", "^BSESN", "^CNXFIN", # Indian Indices
    "JINDALSTEL.NS", "TRENT.NS", "HDFCBANK.NS", "PNB.NS", "ADANIPORTS.NS",
    "VOLTAS.NS", "DIXON.NS", "CHOLAFIN.NS", "RELIANCE.NS", "TCS.NS",
    "BAJFINANCE.NS", "JSWSTEEL.NS", "SUZLON.NS", "RPOWER.NS",
    "CL=F", "NG=F", "BTC-USD"
]

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for chat_id in TELEGRAM_CHAT_IDS:
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        try:
            requests.post(url, json=payload)
        except Exception as e:
            print(f"Telegram Error for {chat_id}: {e}")

def get_atm_strike(symbol, price):
    if symbol == "^NSEI":  
        atm = round(price / 50) * 50
        return f"Nifty {atm}"
    elif symbol == "^NSEBANK":  
        atm = round(price / 100) * 100
        return f"BankNifty {atm}"
    elif symbol == "^BSESN":  
        atm = round(price / 100) * 100
        return f"Sensex {atm}"
    elif symbol == "^CNXFIN":  
        atm = round(price / 50) * 50
        return f"FinNifty {atm}"
    return None

def analyze_stock(symbol):
    try:
        # Fetching 15m data for multi-timeframe analysis
        df = yf.download(symbol, period="5d", interval="15m", progress=False)
        if df.empty or len(df) < 60:
            return

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Fresh candle check (anti-spam)
        last_candle_time = df.index[-1]
        now_utc = datetime.now(timezone.utc)
        if hasattr(last_candle_time, 'tzinfo') and last_candle_time.tzinfo:
            time_diff = (now_utc - last_candle_time).total_seconds() / 60
        else:
            time_diff = 30

        if time_diff > 45:
            return

        # Resample to higher timeframes (1H and 4H) for SMC Structure
        df_1h = df.resample('1h').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
        df_4h = df.resample('4h').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()

        if len(df_1h) < 20 or len(df_4h) < 10:
            return

        # --- SMC & PRICE ACTION METRICS ---
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        prev2 = df.iloc[-3]

        # 1. Previous Day High / Low (PDH / PDL) approximation from daily range
        daily_df = df.resample('1D').agg({'High': 'max', 'Low': 'min', 'Close': 'last'}).dropna()
        pdh = daily_df['High'].iloc[-2] if len(daily_df) >= 2 else curr['High']
        pdl = daily_df['Low'].iloc[-2] if len(daily_df) >= 2 else curr['Low']

        # 2. Fibonacci Golden Pocket (0.618 retracement of recent 20-candle swing)
        swing_high = df['High'].tail(20).max()
        swing_low = df['Low'].tail(20).min()
        fib_zone_high = swing_high - (swing_high - swing_low) * 0.618
        fib_zone_low = swing_high - (swing_high - swing_low) * 0.786

        # 3. Liquidity Sweep Detection (Wick beyond recent high/low followed by reversal)
        recent_high = df['High'].iloc[-10:-1].max()
        recent_low = df['Low'].iloc[-10:-1].min()
        bullish_liquidity_sweep = (curr['Low'] < recent_low) and (curr['Close'] > recent_low) # Swept lows and rejected
        bearish_liquidity_sweep = (curr['High'] > recent_high) and (curr['Close'] < recent_high) # Swept highs and rejected

        # 4. Support & Resistance Reversal
        support_level = df['Low'].tail(30).min()
        resistance_level = df['High'].tail(30).max()
        at_support = abs(curr['Close'] - support_level) / support_level < 0.003
        at_resistance = abs(curr['Close'] - resistance_level) / resistance_level < 0.003

        # 5. Technical Indicators (EMA, RSI, ATR, VWAP)
        df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
        df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
        
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        df['ATR'] = (df['High'] - df['Low']).rolling(window=14).mean()
        df['Volume'] = df['Volume'].fillna(0)
        df['Vol_SMA'] = df['Volume'].rolling(window=20).mean().fillna(1)

        v = df['Volume']
        tp_val = (df['High'] + df['Low'] + df['Close']) / 3
        df['VWAP'] = (tp_val * v).cumsum() / v.cumsum() if v.sum() > 0 else df['Close']

        curr = df.iloc[-1]
        prev = df.iloc[-2]

        bull_trend = curr['Close'] > curr['VWAP'] and curr['EMA20'] > curr['EMA50']
        bear_trend = curr['Close'] < curr['VWAP'] and curr['EMA20'] < curr['EMA50']
        is_gamma_blast = (curr['Volume'] > (curr['Vol_SMA'] * 2.0)) and ((curr['High'] - curr['Low']) > (curr['ATR'] * 1.4))

        price = round(float(curr['Close']), 2)
        atr_val = float(curr['ATR'])
        rsi_val = round(float(curr['RSI']), 2)

        # Friendly display names
        display_name = symbol
        if symbol == "GC=F": display_name = "XAU/USD (Gold)"
        elif symbol == "^NSEI": display_name = "NIFTY 50"
        elif symbol == "^NSEBANK": display_name = "BANK NIFTY"
        elif symbol == "^BSESN": display_name = "SENSEX"
        elif symbol == "^CNXFIN": display_name = "FINNIFTY"

        # --- BUY / CALL SETUP (SMC Reversal, Liquidity Sweep at Support / Fib Zone) ---
        is_buy_setup = (
            (bull_trend and curr['EMA20'] > prev['EMA20']) or 
            bullish_liquidity_sweep or 
            (at_support and rsi_val < 40) or 
            (fib_zone_low <= price <= fib_zone_high and bull_trend) or
            (is_gamma_blast and bull_trend)
        )

        # --- SELL / PUT SETUP (SMC Reversal, Liquidity Sweep at Resistance / PDH) ---
        is_sell_setup = (
            (bear_trend and curr['EMA20'] < prev['EMA20']) or 
            bearish_liquidity_sweep or 
            (at_resistance and rsi_val > 60) or 
            (price >= pdh and bear_trend) or
            (is_gamma_blast and bear_trend)
        )

        # Avoid duplicate firing using prev2 check
        was_buy_previously = (df.iloc[-2]['Close'] > df.iloc[-2]['EMA20']) and (df.iloc[-3]['Close'] <= df.iloc[-3]['EMA20'])
        was_sell_previously = (df.iloc[-2]['Close'] < df.iloc[-2]['EMA20']) and (df.iloc[-3]['Close'] >= df.iloc[-3]['EMA20'])

        if is_buy_setup and not was_buy_previously:
            sl = round(float(price - (atr_val * 1.5)), 2)
            tp1 = round(float(price + (atr_val * 1.5)), 2)
            tp2 = round(float(price + (atr_val * 3.0)), 2)
            tp3 = round(float(price + (atr_val * 4.5)), 2)
            
            reason = "🚀 [SMC BUY / LIQUIDITY SWEEP REVERSAL]"
            if bullish_liquidity_sweep: reason = "⚡ [LOW LIQUIDITY SWEEP & REVERSAL]"
            elif at_support: reason = "🛡️ [SUPPORT BOUNCE SETUP]"
            elif fib_zone_low <= price <= fib_zone_high: reason = "🎯 [FIBONACCI GOLDEN ZONE BUY]"

            option_info = ""
            if symbol in ["^NSEI", "^NSEBANK", "^BSESN", "^CNXFIN"]:
                atm_strike = get_atm_strike(symbol, price)
                option_info = f"\n💡 **Zero-to-Hero Option:** `{atm_strike} CE`"

            msg = (
                f"{reason}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📌 **Asset:** `{display_name}`{option_info}\n"
                f"💵 **Entry Price:** `{price}`\n"
                f"🛑 **Stop Loss (SL):** `{sl}`\n"
                f"🎯 **Target 1 (TP1):** `{tp1}`\n"
                f"🎯 **Target 2 (TP2):** `{tp2}`\n"
                f"🎯 **Target 3 (TP3):** `{tp3}`\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📊 **Metrics:** RSI: `{rsi_val}` | PDL: `{pdl}`"
            )
            print(msg)
            send_telegram_alert(msg)

        elif is_sell_setup and not was_sell_previously:
            sl = round(float(price + (atr_val * 1.5)), 2)
            tp1 = round(float(price - (atr_val * 1.5)), 2)
            tp2 = round(float(price - (atr_val * 3.0)), 2)
            tp3 = round(float(price - (atr_val * 4.5)), 2)
            
            reason = "🔻 [SMC SELL / RESISTANCE REJECTION]"
            if bearish_liquidity_sweep: reason = "⚡ [HIGH LIQUIDITY SWEEP & DUMP]"
            elif at_resistance: reason = "🧱 [RESISTANCE REJECTION SETUP]"
            elif price >= pdh: reason = "🛑 [PREVIOUS DAY HIGH (PDH) REVERSAL]"

            option_info = ""
            if symbol in ["^NSEI", "^NSEBANK", "^BSESN", "^CNXFIN"]:
                atm_strike = get_atm_strike(symbol, price)
                option_info = f"\n💡 **Zero-to-Hero Option:** `{atm_strike} PE`"

            msg = (
                f"{reason}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📌 **Asset:** `{display_name}`{option_info}\n"
                f"💵 **Entry Price:** `{price}`\n"
                f"🛑 **Stop Loss (SL):** `{sl}`\n"
                f"🎯 **Target 1 (TP1):** `{tp1}`\n"
                f"🎯 **Target 2 (TP2):** `{tp2}`\n"
                f"🎯 **Target 3 (TP3):** `{tp3}`\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📊 **Metrics:** RSI: `{rsi_val}` | PDH: `{pdh}`"
            )
            print(msg)
            send_telegram_alert(msg)

    except Exception as e:
        print(f"Error analyzing {symbol}: {e}")

if __name__ == "__main__":
    print("🚀 Running Ultimate SMC & Multi-Timeframe Scanner...")
    for symbol in WATCHLIST:
        analyze_stock(symbol)
    print("Scan cycle completed successfully.")