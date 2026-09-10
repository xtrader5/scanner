import requests
import pandas as pd
import yfinance as yf
import os
import math

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5608017991")

# Complete Watchlist: Gold, Silver, Indices (Nifty, BankNifty, Sensex, FinNifty), Stocks & Crypto
WATCHLIST = [
    # Precious Metals / Commodities
    "GC=F",              # Gold (XAU/USD)
    "SI=F",              # Silver (XAG/USD)
    # Indian Indices (Spot for Option ATM & Gamma Blast)
    "^NSEI",             # Nifty 50
    "^NSEBANK",          # Bank Nifty
    "^BSESN",            # Sensex
    "^CNXFIN",           # FinNifty
    # High Momentum Stocks & Assets
    "JINDALSTEL.NS", "TRENT.NS", "HDFCBANK.NS", "PNB.NS", "ADANIPORTS.NS",
    "VOLTAS.NS", "DIXON.NS", "CHOLAFIN.NS", "RELIANCE.NS", "TCS.NS",
    "BAJFINANCE.NS", "JSWSTEEL.NS", "SUZLON.NS", "RPOWER.NS",
    "CL=F", "NG=F", "BTC-USD"
]

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram Error: {e}")

def get_atm_strike(symbol, price):
    """Calculates ATM strike price for index options (Zero-to-Hero setup)"""
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

        # 1. Technical Indicators (EMA & RSI)
        df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
        df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
        
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        df['ATR'] = (df['High'] - df['Low']).rolling(window=14).mean()
        
        # 2. Volume & Gamma Blast Parameters
        df['Volume'] = df['Volume'].fillna(0)
        df['Vol_SMA'] = df['Volume'].rolling(window=20).mean().fillna(1)

        v = df['Volume']
        tp_val = (df['High'] + df['Low'] + df['Close']) / 3
        df['VWAP'] = (tp_val * v).cumsum() / v.cumsum() if v.sum() > 0 else df['Close']

        curr = df.iloc[-1]
        prev = df.iloc[-2]

        # 3. Strategy Conditions
        bull_crossover = (prev['EMA20'] <= prev['EMA50']) and (curr['EMA20'] > curr['EMA50'])
        bull_momentum = (curr['RSI'] > 50) and (curr['RSI'] < 75)
        bull_trend = curr['Close'] > curr['VWAP']

        # Gamma Blast condition for explosive moves
        is_volume_data_valid = curr['Volume'] > 0
        is_gamma_blast = is_volume_data_valid and (curr['Volume'] > (curr['Vol_SMA'] * 2.0)) and ((curr['High'] - curr['Low']) > (curr['ATR'] * 1.4))

        bear_crossover = (prev['EMA20'] >= prev['EMA50']) and (curr['EMA20'] < curr['EMA50'])
        bear_momentum = (curr['RSI'] < 50) and (curr['RSI'] > 25)
        bear_trend = curr['Close'] < curr['VWAP']

        price = round(float(curr['Close']), 2)
        atr_val = float(curr['ATR'])
        rsi_val = round(float(curr['RSI']), 2)

        # Asset Friendly Names
        display_name = symbol
        if symbol == "GC=F": display_name = "XAU/USD (Gold)"
        elif symbol == "SI=F": display_name = "XAG/USD (Silver)"
        elif symbol == "^NSEI": display_name = "NIFTY 50"
        elif symbol == "^NSEBANK": display_name = "BANK NIFTY"
        elif symbol == "^BSESN": display_name = "SENSEX"
        elif symbol == "^CNXFIN": display_name = "FINNIFTY"

        # --- BUY SIGNAL / CALL OPTION (GAMMA BLAST + CONFLUENCE) ---
        if (bull_crossover and bull_momentum and bull_trend) or (is_gamma_blast and bull_trend) or (symbol in ["GC=F", "SI=F"] and bull_crossover):
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

        # --- SELL SIGNAL / PUT OPTION ---
        elif (bear_crossover and bear_momentum and bear_trend) or (is_gamma_blast and bear_trend) or (symbol in ["GC=F", "SI=F"] and bear_crossover):
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
    print("🚀 Running Ultimate Gamma Blast & Options Scanner...")
    for symbol in WATCHLIST:
        analyze_stock(symbol)
    print("Scan cycle completed successfully.")