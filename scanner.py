import requests
import pandas as pd
import yfinance as yf
import os
import math

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5608017991")

# Watchlist including Stocks, Commodities, Crypto, Forex, and Indian Indices
WATCHLIST = [
    # Indian Indices (Spot for Option ATM calculation)
    "^NSEI",         # Nifty 50
    "^NSEBANK",      # Bank Nifty
    "^BSESN",        # Sensex
    # Indian Stocks
    "JINDALSTEL.NS", "TRENT.NS", "HDFCBANK.NS", "PNB.NS", "ADANIPORTS.NS",
    "VOLTAS.NS", "DIXON.NS", "SOLARINDS.NS", "AMBER.NS", "CHOLAFIN.NS",
    "UPL.NS", "ULTRACEMCO.NS", "AMBUJACEM.NS", "M&M.NS", "SBILIFE.NS",
    "BAJFINANCE.NS", "JSWSTEEL.NS", "IRFC.NS", "RELIANCE.NS", "TCS.NS",
    "COALINDIA.NS", "LUPIN.NS", "RTNPOWER.NS", "KPIGREEN.NS", "ADANIPOWER.NS",
    "RPOWER.NS", "SUZLON.NS",
    # Commodities, Crypto & Forex
    "GC=F",          # Gold (XAUUSD)
    "SI=F",          # Silver (XAGUSD)
    "CL=F",          # Crude Oil
    "NG=F",          # Natural Gas
    "BTC-USD",       # Bitcoin
    "EURUSD=X", 
    "GBPUSD=X", 
    "USDJPY=X"
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
    """Calculates ATM strike price and returns option symbol format"""
    if symbol == "^NSEI":  # Nifty (Interval: 50)
        atm = round(price / 50) * 50
        return f"Nifty {atm}"
    elif symbol == "^NSEBANK":  # Bank Nifty (Interval: 100)
        atm = round(price / 100) * 100
        return f"BankNifty {atm}"
    elif symbol == "^BSESN":  # Sensex (Interval: 100)
        atm = round(price / 100) * 100
        return f"Sensex {atm}"
    return None

def analyze_stock(symbol):
    try:
        df = yf.download(symbol, period="5d", interval="15m", progress=False)
        if df.empty or len(df) < 60:
            return

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Technical Indicators
        df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
        df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
        
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        df['ATR'] = (df['High'] - df['Low']).rolling(window=14).mean()

        v = df['Volume']
        tp_val = (df['High'] + df['Low'] + df['Close']) / 3
        df['VWAP'] = (tp_val * v).cumsum() / v.cumsum()

        curr = df.iloc[-1]
        prev = df.iloc[-2]

        bull_crossover = (prev['EMA20'] <= prev['EMA50']) and (curr['EMA20'] > curr['EMA50'])
        bull_momentum = (curr['RSI'] > 50) and (curr['RSI'] < 75)
        bull_trend = curr['Close'] > curr['VWAP']

        bear_crossover = (prev['EMA20'] >= prev['EMA50']) and (curr['EMA20'] < curr['EMA50'])
        bear_momentum = (curr['RSI'] < 50) and (curr['RSI'] > 25)
        bear_trend = curr['Close'] < curr['VWAP']

        price = round(float(curr['Close']), 2)
        atr_val = float(curr['ATR'])
        rsi_val = round(float(curr['RSI']), 2)
        vwap_val = round(float(curr['VWAP']), 2)

        # Friendly display name for indices
        display_name = symbol
        if symbol == "^NSEI": display_name = "NIFTY 50"
        elif symbol == "^NSEBANK": display_name = "BANK NIFTY"
        elif symbol == "^BSESN": display_name = "SENSEX"

        # --- BUY SIGNAL (CALL OPTION SETUP FOR INDICES) ---
        if bull_crossover and bull_momentum and bull_trend:
            sl = round(float(price - (atr_val * 1.5)), 2)
            tp1 = round(float(price + (atr_val * 1.5)), 2)
            tp2 = round(float(price + (atr_val * 3.0)), 2)
            tp3 = round(float(price + (atr_val * 4.5)), 2)
            
            option_info = ""
            if symbol in ["^NSEI", "^NSEBANK", "^BSESN"]:
                atm_strike = get_atm_strike(symbol, price)
                option_info = f"\n💡 **Suggested Option Trade:** `{atm_strike} CE` (ATM Call Buying)"

            msg = (
                f"🚀 **PRO BUY SETUP TRIGGERED**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📌 **Asset:** `{display_name}`{option_info}\n"
                f"💵 **Underlying Price:** `{price}`\n"
                f"🛑 **Stop Loss (SL):** `{sl}`\n"
                f"🎯 **Target 1 (TP1):** `{tp1}`\n"
                f"🎯 **Target 2 (TP2):** `{tp2}`\n"
                f"🎯 **Target 3 (TP3):** `{tp3}`\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📊 **Metrics:** RSI: `{rsi_val}` | VWAP: `{vwap_val}`"
            )
            print(msg)
            send_telegram_alert(msg)

        # --- SELL SIGNAL (PUT OPTION SETUP FOR INDICES) ---
        elif bear_crossover and bear_momentum and bear_trend:
            sl = round(float(price + (atr_val * 1.5)), 2)
            tp1 = round(float(price - (atr_val * 1.5)), 2)
            tp2 = round(float(price - (atr_val * 3.0)), 2)
            tp3 = round(float(price - (atr_val * 4.5)), 2)
            
            option_info = ""
            if symbol in ["^NSEI", "^NSEBANK", "^BSESN"]:
                atm_strike = get_atm_strike(symbol, price)
                option_info = f"\n💡 **Suggested Option Trade:** `{atm_strike} PE` (ATM Put Buying)"

            msg = (
                f"🔻 **PRO SELL SETUP TRIGGERED**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📌 **Asset:** `{display_name}`{option_info}\n"
                f"💵 **Underlying Price:** `{price}`\n"
                f"🛑 **Stop Loss (SL):** `{sl}`\n"
                f"🎯 **Target 1 (TP1):** `{tp1}`\n"
                f"🎯 **Target 2 (TP2):** `{tp2}`\n"
                f"🎯 **Target 3 (TP3):** `{tp3}`\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📊 **Metrics:** RSI: `{rsi_val}` | VWAP: `{vwap_val}`"
            )
            print(msg)
            send_telegram_alert(msg)

    except Exception as e:
        print(f"Error analyzing {symbol}: {e}")

if __name__ == "__main__":
    print("🚀 Running Advanced Index Options & Multi-Market Scanner...")
    for symbol in WATCHLIST:
        analyze_stock(symbol)
    print("Scan cycle completed successfully.")