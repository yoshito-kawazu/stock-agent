import os
import sys
import json
import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import requests

SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

if not SPREADSHEET_ID or not DISCORD_WEBHOOK_URL:
    print("【エラー】SPREADSHEET_ID または DISCORD_WEBHOOK_URL が設定されていません。")
    sys.exit(1)

MACRO_SYMBOLS = {
    "USD/JPY": "USDJPY=X",
    "WTI原油先物": "CL=F",
    "日経平均先物": "NK=F",
    "Nasdaq100先物": "NQ=F",
}

MACRO_CALENDAR = """
| 日程 (日本時間) | 国 / 地域 | イベント / 経済指標 | 影響度 | 注目ポイント |
|---|---|---|---|---|
| 09/11 (金) 21:30 | 🇺🇸 米国 | 米8月 CPI (消費者物価指数) | ★★★ (大) | インフレ鈍化の継続性 |
| 09/18 (木) 未定  | 🇯🇵 日本 | 日銀 金融政策決定会合 | ★★★ (大) | 追加利上げスタンス |
| 09/19 (金) 03:00 | 🇺🇸 米国 | FOMC 政策金利発表 ＆ 会見 | ★★★ (大) | 利下げ幅（25bp vs 50bp） |
| 09/26 (金) 21:30 | 🇺🇸 米国 | 米8月 PCEデフレーター | ★★☆ (中) | FRB重視の物価指標 |
| 10/01 (木) 08:50 | 🇯🇵 日本 | 日銀短観 (9月調査) | ★★☆ (中) | 国内企業の景況感 |
| 10/02 (金) 21:30 | 🇺🇸 米国 | 米9月 雇用統計 | ★★★ (大) | 労働市場の減速ペース |
"""

def get_target_tickers():
    try:
        url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv"
        df = pd.read_csv(url, header=None)
        
        raw_items = []
        for val in df.values.flatten():
            if pd.notna(val):
                for item in str(val).split(","):
                    item_clean = item.strip()
                    if item_clean:
                        raw_items.append(item_clean)
        
        tickers = []
        for t in raw_items:
            t_formatted = t if ".T" in t else f"{t}.T"
            if t_formatted not in tickers:
                tickers.append(t_formatted)
        
        print(f"取得した監視銘柄: {tickers}")
        return tickers if tickers else ["7003.T", "6525.T"]
    except Exception as e:
        print(f"スプレッドシート読込警告: {e} ➜ デフォルト 7003.T, 6525.T を使用")
        return ["7003.T", "6525.T"]

def analyze_and_plot(ticker, idx):
    print(f"[{ticker}] チャート生成 ＆ 分析中...")
    stock = yf.Ticker(ticker)
    df = stock.history(period="6mo")
    if df.empty:
        return None, f"・`{ticker}`: データ取得エラー\n"

    company_name = ""
    try:
        info = stock.info
        company_name = info.get("shortName") or info.get("longName") or ""
    except Exception:
        company_name = ""

    display_title = f"{ticker} {company_name}".strip()

    df['SMA25'] = df['Close'].rolling(window=25).mean()
    df['SMA75'] = df['Close'].rolling(window=75).mean()

    exp12 = df['Close'].ewm(span=12, adjust=False).mean()
    exp26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp12 - exp26
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['Hist'] = df['MACD'] - df['Signal']

    recent_high = df['High'].iloc[-30:].max()
    recent_low = df['Low'].iloc[-30:].min()

    x = np.arange(len(df))[-30:]
    y = df['Low'].iloc[-30:].values
    slope, intercept = np.polyfit(x, y, 1)
    trend_line = slope * x + intercept

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 6), gridspec_kw={'height_ratios':}, sharex=True)

    ax1.plot(df.index, df['Close'], label="Close", color="black", alpha=0.7)
    ax1.plot(df.index, df['SMA25'], label="25 SMA", color="blue", linewidth=1.2)
    ax1.plot(df.index, df['SMA75'], label="75 SMA", color="orange", linewidth=1.2)
    ax1.axhline(recent_high, color="red", linestyle="--", alpha=0.8, label=f"Resistance: ¥{recent_high:.0f}")
    ax1.axhline(recent_low, color="green", linestyle="--", alpha=0.8, label=f"Support: ¥{recent_low:.0f}")
    ax1.plot(df.index[-30:], trend_line, color="purple", linestyle=":", linewidth=1.5, label="Trend Line")
    ax1.set_title(f"{display_title} - Technical Chart", fontsize=12, fontweight="bold")
    ax1.legend(loc="upper left", fontsize=8)
   
