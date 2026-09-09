import requests
import pandas as pd
import yfinance as yf
import os

# --- CONFIGURATION (Environment Secrets se values lega) ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN", "8928957792:AAHsm3vxxwSTdhQA37Dbdcp0DniBNLWa3NQ")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5608017991")

# Watchlist (Stocks + Forex Pairs)
WATCHLIST = [
    "RELIANCE.NS", 
    "TCS.NS", 
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

def analyze_stock(symbol):
    try:
        df = yf.download(symbol, period="5d", interval="15m", progress=False)
        if df.empty or len(df) < 50:
            return

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Technical Indicators (EMA, RSI, ATR)
        df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
        df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
        
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        df['ATR'] = (df['High'] - df['Low']).rolling(window=14).mean()

        # VWAP Calculation
        v = df['Volume']
        tp = (df['High'] + df['Low'] + df['Close']) / 3
        df['VWAP'] = (tp * v).cumsum() / v.cumsum()

        curr = df.iloc[-1]
        prev = df.iloc[-2]

        bull_crossover = (prev['EMA20'] <= prev['EMA50']) and (curr['EMA20'] > curr['EMA50'])
        bull_momentum = (curr['RSI'] > 50) and (curr['Close'] > curr['VWAP'])

        bear_crossover = (prev['EMA20'] >= prev['EMA50']) and (curr['EMA20'] < curr['EMA50'])
        bear_momentum = (curr['RSI'] < 50) and (curr['Close'] < curr['VWAP'])

        if bull_crossover and bull_momentum:
            price = round(float(curr['Close']), 4)
            sl = round(float(price - (curr['ATR'] * 1.5)), 4)
            vwap_val = round(float(curr['VWAP']), 4)
            msg = f"🟢 **BUY SIGNAL (VWAP Confirmed): {symbol}**\nPrice: {price}\nVWAP: {vwap_val}\nStop Loss: {sl}\nRSI: {round(float(curr['RSI']), 2)}"
            print(msg)
            send_telegram_alert(msg)

        elif bear_crossover and bear_momentum:
            price = round(float(curr['Close']), 4)
            sl = round(float(price + (curr['ATR'] * 1.5)), 4)
            vwap_val = round(float(curr['VWAP']), 4)
            msg = f"🔴 **SELL SIGNAL (VWAP Confirmed): {symbol}**\nPrice: {price}\nVWAP: {vwap_val}\nStop Loss: {sl}\nRSI: {round(float(curr['RSI']), 2)}"
            print(msg)
            send_telegram_alert(msg)

    except Exception as e:
        print(f"Error analyzing {symbol}: {e}")

if __name__ == "__main__":
    print("🚀 Running single-scan cycle...")
    for symbol in WATCHLIST:
        analyze_stock(symbol)
    print("Scan completed successfully.")