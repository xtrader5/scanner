import requests
import pandas as pd
import yfinance as yf
import os
import math
from datetime import datetime, timezone

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")

# Aapki aur aapke friend ki Chat IDs yahan list mein hain
TELEGRAM_CHAT_IDS = ["5608017991", "5643531288"]

WATCHLIST = [
    "GC=F", "SI=F",                  # Gold & Silver
    "^NSEI", "^NSEBANK", "^BSESN", "^CNXFIN", # Indices
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
        df = yf.download(symbol, period="5d", interval="15m", progress=False)
        if df.empty or len(df) < 60:
            return

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        last_candle_time = df.index[-1]
        now_utc = datetime.now(timezone.utc)
        
        if hasattr(last_candle_time, 'tzinfo') and last_candle_time.tzinfo:
            time_diff = (now_utc - last_candle_time).total_seconds() / 60
        else:
            time_diff = 30

        if time_diff > 45:
            return

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
        prev2 = df.iloc[-3]

        bull_crossover = (prev['EMA20'] <= prev['EMA50']) and (curr['EMA20'] > curr['EMA50'])
        bull_momentum = (curr['RSI'] > 50) and (curr['RSI'] < 75)
        bull_trend = curr['Close'] > curr['VWAP']

        is_volume_data_valid = curr['Volume'] > 0
        is_gamma_blast = is_volume_data_valid and (curr['Volume'] > (curr['Vol_SMA'] * 2.0)) and ((curr['High'] - curr['Low']) > (curr['ATR'] * 1.4))

        bear_crossover = (prev['EMA20'] >= prev['EMA50']) and (curr['EMA20'] < curr['EMA50'])
        bear_momentum = (curr['RSI'] < 50) and (curr['RSI'] > 25)
        bear_trend = curr['Close'] < curr['VWAP']

        was_bull_previously = (prev2['EMA20'] <= prev2['EMA50']) and (prev['EMA20'] > prev['EMA50'])
        was_bear_previously = (prev2['EMA20'] >= prev2['EMA50']) and (prev['EMA20'] < prev['EMA50'])

        price = round(float(curr['Close']), 2)
        atr_val = float(curr['ATR'])
        rsi_val = round(float(curr['RSI']), 2)

        display_name = symbol
        if symbol == "GC=F": display_name = "XAU/USD (Gold)"
        elif symbol == "SI=F": display_name = "XAG/USD (Silver)"
        elif symbol == "^NSEI": display_name = "NIFTY 50"
        elif symbol == "^NSEBANK": display_name = "BANK NIFTY"
        elif symbol == "^BSESN": display_name = "SENSEX"
        elif symbol == "^CNXFIN": display_name = "FINNIFTY"

        if ((bull_crossover and bull_momentum and bull_trend and not was_bull_previously) or 
            (is_gamma_blast and bull_trend) or 
            (symbol in ["GC=F", "SI=F"] and bull_crossover and not was_bull_previously)):
            
            sl = round(float(price - (atr_val * 1.5)), 2)
            tp1 = round(float(price + (atr_val * 1.5)), 2)
            tp2 = round(float(price + (atr_val * 3.0)), 2)
            tp3 = round(float(price + (atr_val * 4.5)), 2)
            
            blast_tag = "⚡ [GAMMA BLAST EXPANSION SETUP]" if is_gamma_blast else "🚀 [PRO BUY SETUP]"
            
            option_info = ""
            if symbol in ["^NSEI", "^NSEBANK", "^BSESN", "^CNXFIN"]:
                atm_strike = get_atm_strike(symbol, price)
                option_info = f"\n💡 **Zero-to-Hero Option:** `{atm_strike} CE` (Call Buying)"

            msg = (
                f"{blast_tag}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📌 **Asset:** `{display_name}`{option_info}\n"
                f"💵 **Entry Price:** `{price}`\n"
                f"🛑 **Stop Loss (SL):** `{sl}`\n"
                f"🎯 **Target 1 (TP1):** `{tp1}`\n"
                f"🎯 **Target 2 (TP2):** `{tp2}`\n"
                f"🎯 **Target 3 (TP3):** `{tp3}`\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📊 **Metrics:** RSI: `{rsi_val}` | Vol Spike: `{'Yes 🚀' if is_gamma_blast else 'Normal'}`"
            )
            print(msg)
            send_telegram_alert(msg)

        elif ((bear_crossover and bear_momentum and bear_trend and not was_bear_previously) or 
              (symbol in ["GC=F", "SI=F"] and bear_crossover and not was_bear_previously)):
            
            sl = round(float(price + (atr_val * 1.5)), 2)
            tp1 = round(float(price - (atr_val * 1.5)), 2)
            tp2 = round(float(price - (atr_val * 3.0)), 2)
            tp3 = round(float(price - (atr_val * 4.5)), 2)
            
            blast_tag = "⚡ [GAMMA BLAST DUMP SETUP]" if is_gamma_blast else "🔻 [PRO SELL SETUP]"
            
            option_info = ""
            if symbol in ["^NSEI", "^NSEBANK", "^BSESN", "^CNXFIN"]:
                atm_strike = get_atm_strike(symbol, price)
                option_info = f"\n💡 **Zero-to-Hero Option:** `{atm_strike} PE` (Put Buying)"

            msg = (
                f"{blast_tag}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📌 **Asset:** `{display_name}`{option_info}\n"
                f"💵 **Entry Price:** `{price}`\n"
                f"🛑 **Stop Loss (SL):** `{sl}`\n"
                f"🎯 **Target 1 (TP1):** `{tp1}`\n"
                f"🎯 **Target 2 (TP2):** `{tp2}`\n"
                f"🎯 **Target 3 (TP3):** `{tp3}`\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📊 **Metrics:** RSI: `{rsi_val}` | Vol Spike: `{'Yes 🔻' if is_gamma_blast else 'Normal'}`"
            )
            print(msg)
            send_telegram_alert(msg)

    except Exception as e:
        print(f"Error analyzing {symbol}: {e}")

if __name__ == "__main__":
    print("🚀 Running Anti-Spam Optimized Scanner...")
    for symbol in WATCHLIST:
        analyze_stock(symbol)
    print("Scan completed.")