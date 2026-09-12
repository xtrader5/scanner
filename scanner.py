import requests
import pandas as pd
import yfinance as yf
import os
from datetime import datetime, timezone

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
# Aap aur aapke friend ki chat IDs
TELEGRAM_CHAT_IDS = ["5608017991", "5643531288"]

WATCHLIST = [
    "XAUUSD=X", "CL=F", "NG=F", "BTC-USD",
    "^NSEI", "^NSEBANK", "^BSESN", "^CNXFIN",
    "JINDALSTEL.NS", "TRENT.NS", "HDFCBANK.NS", "PNB.NS", "ADANIPORTS.NS",
    "VOLTAS.NS", "DIXON.NS", "CHOLAFIN.NS", "RELIANCE.NS", "TCS.NS",
    "BAJFINANCE.NS", "JSWSTEEL.NS", "SUZLON.NS", "RPOWER.NS"
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
        df = yf.download(symbol, period="3d", interval="15m", progress=False)
        if df.empty or len(df) < 50:
            return

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Fresh Candle Check (Strictly latest 35 mins to avoid old/repeat spam)
        last_candle_time = df.index[-1]
        now_utc = datetime.now(timezone.utc)
        if hasattr(last_candle_time, 'tzinfo') and last_candle_time.tzinfo:
            time_diff = (now_utc - last_candle_time).total_seconds() / 60
        else:
            time_diff = 20

        if time_diff > 35:
            return

        # --- EXACT PINE SCRIPT INDICATOR CALCULATIONS ---
        df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
        df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
        
        # RSI 14 Calculation
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        # ATR 14 Calculation
        high_low = df['High'] - df['Low']
        high_close = (df['High'] - df['Close'].shift()).abs()
        low_close = (df['Low'] - df['Close'].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['ATR'] = tr.rolling(window=14).mean()

        curr = df.iloc[-1]
        prev = df.iloc[-2]
        prev2 = df.iloc[-3]

        price = round(float(curr['Close']), 2)
        atr_val = float(curr['ATR'])
        rsi_val = round(float(curr['RSI']), 2)

        display_name = symbol
        if symbol == "XAUUSD=X": display_name = "XAU/USD (Gold Spot)"
        elif symbol == "CL=F": display_name = "CRUDE OIL (CL=F)"
        elif symbol == "^NSEI": display_name = "NIFTY 50"
        elif symbol == "^NSEBANK": display_name = "BANK NIFTY"
        elif symbol == "^BSESN": display_name = "SENSEX"
        elif symbol == "^CNXFIN": display_name = "FINNIFTY"

        # --- PINE SCRIPT EXACT BUY / SELL SIGNALS ---
        bull_momentum = rsi_val > 50
        bear_momentum = rsi_val < 50

        buy_signal = (prev['EMA20'] <= prev['EMA50']) and (curr['EMA20'] > curr['EMA50']) and bull_momentum
        sell_signal = (prev['EMA20'] >= prev['EMA50']) and (curr['EMA20'] < curr['EMA50']) and bear_momentum

        # Prevent duplicate firing on the same candle sequence
        was_buy_earlier = (prev2['EMA20'] <= prev2['EMA50']) and (prev['EMA20'] > prev['EMA50'])
        was_sell_earlier = (prev2['EMA20'] >= prev2['EMA50']) and (prev['EMA20'] < prev['EMA50'])

        # --- BUY SETUP (Matching Pine Script inputs: slATR=1.5, rr1=1.0, rr2=2.0, rr3=3.0) ---
        if buy_signal and not was_buy_earlier:
            entry = price
            sl = round(entry - (atr_val * 1.5), 2)
            risk = entry - sl
            tp1 = round(entry + (risk * 1.0), 2)
            tp2 = round(entry + (risk * 2.0), 2)
            tp3 = round(entry + (risk * 3.0), 2)
            
            option_info = f"\n💡 **Zero-to-Hero Option:** `{get_atm_strike(symbol, price)} CE`" if symbol in ["^NSEI", "^NSEBANK", "^BSESN", "^CNXFIN"] else ""

            msg = (
                f"🟢 **BUY SIGNAL (Indicator Aligned)**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📌 **Asset:** `{display_name}`{option_info}\n"
                f"💵 **Entry Price:** `{entry}`\n"
                f"🛑 **Stop Loss (SL):** `{sl}`\n"
                f"🎯 **Target 1 (TP1):** `{tp1}`\n"
                f"🎯 **Target 2 (TP2):** `{tp2}`\n"
                f"🎯 **Target 3 (TP3):** `{tp3}`\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📊 **Metrics:** RSI: `{rsi_val}` | ATR: `{round(atr_val, 2)}`"
            )
            print(msg)
            send_telegram_alert(msg)

        # --- SELL SETUP ---
        elif sell_signal and not was_sell_earlier:
            entry = price
            sl = round(entry + (atr_val * 1.5), 2)
            risk = sl - entry
            tp1 = round(entry - (risk * 1.0), 2)
            tp2 = round(entry - (risk * 2.0), 2)
            tp3 = round(entry - (risk * 3.0), 2)
            
            option_info = f"\n💡 **Zero-to-Hero Option:** `{get_atm_strike(symbol, price)} PE`" if symbol in ["^NSEI", "^NSEBANK", "^BSESN", "^CNXFIN"] else ""

            msg = (
                f"🔴 **SELL SIGNAL (Indicator Aligned)**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📌 **Asset:** `{display_name}`{option_info}\n"
                f"💵 **Entry Price:** `{entry}`\n"
                f"🛑 **Stop Loss (SL):** `{sl}`\n"
                f"🎯 **Target 1 (TP1):** `{tp1}`\n"
                f"🎯 **Target 2 (TP2):** `{tp2}`\n"
                f"🎯 **Target 3 (TP3):** `{tp3}`\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📊 **Metrics:** RSI: `{rsi_val}` | ATR: `{round(atr_val, 2)}`"
            )
            print(msg)
            send_telegram_alert(msg)

    except Exception as e:
        print(f"Error analyzing {symbol}: {e}")

if __name__ == "__main__":
    print("🚀 Running Exact Pine Script Indicator Scanner...")
    for symbol in WATCHLIST:
        analyze_stock(symbol)
    print("Scan cycle completed.")