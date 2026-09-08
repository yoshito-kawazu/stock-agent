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

    ratio_list = [3, 1]
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 6), gridspec_kw=dict(height_ratios=ratio_list), sharex=True)

    ax1.plot(df.index, df['Close'], label="Close", color="black", alpha=0.7)
    ax1.plot(df.index, df['SMA25'], label="25 SMA", color="blue", linewidth=1.2)
    ax1.plot(df.index, df['SMA75'], label="75 SMA", color="orange", linewidth=1.2)
    ax1.axhline(recent_high, color="red", linestyle="--", alpha=0.8, label=f"Resistance: ¥{recent_high:.0f}")
    ax1.axhline(recent_low, color="green", linestyle="--", alpha=0.8, label=f"Support: ¥{recent_low:.0f}")
    ax1.plot(df.index[-30:], trend_line, color="purple", linestyle=":", linewidth=1.5, label="Trend Line")
    ax1.set_title(f"{display_title} - Technical Chart", fontsize=12, fontweight="bold")
    ax1.legend(loc="upper left", fontsize=8)
    ax1.grid(True, alpha=0.3)

    ax2.plot(df.index, df['MACD'], label="MACD", color="blue")
    ax2.plot(df.index, df['Signal'], label="Signal", color="red", linestyle="--")
    ax2.bar(df.index, df['Hist'], label="Hist", color="gray", alpha=0.5)
    ax2.axhline(0, color="black", linewidth=0.5)
    ax2.legend(loc="upper left", fontsize=8)
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    chart_path = f"chart_{idx}.png"
    plt.savefig(chart_path, dpi=100)
    plt.close()

    curr_price = df['Close'].iloc[-1]
    prev_price = df['Close'].iloc[-2] if len(df) > 1 else curr_price
    pct = ((curr_price - prev_price) / prev_price) * 100
    day_high = df['High'].iloc[-1]
    day_low = df['Low'].iloc[-1]
    
    macd_val = df['MACD'].iloc[-1]
    sig_val = df['Signal'].iloc[-1]
    macd_status = "ゴールデンクロス圏（買い優勢）" if macd_val > sig_val else "デッドクロス圏（調整警戒）"

    text = f"""▼ **{display_title}**
・**現在値**: ¥{curr_price:.1f} (前日比: `{pct:+.2f}%`)
・**当日レンジ**: 安値 ¥{day_low:.1f} 〜 高値 ¥{day_high:.1f}
・**移動平均線**: 25日線 ¥{df['SMA25'].iloc[-1]:.1f} / 75日線 ¥{df['SMA75'].iloc[-1]:.1f}
・🔴 **レジスタンス**: ¥{recent_high:.0f} / 🟢 **サポート**: ¥{recent_low:.0f}
・📊 **MACD**: {macd_status} (MACD: {macd_val:.2f} / Signal: {sig_val:.2f})
"""
    return chart_path, text

def fetch_macro():
    res = []
    for name, sym in MACRO_SYMBOLS.items():
        try:
            m_ticker = yf.Ticker(sym)
            m_hist = m_ticker.history(period="5d")
            if not m_hist.empty:
                curr = m_hist['Close'].iloc[-1]
                prev = m_hist['Close'].iloc[-2] if len(m_hist) > 1 else curr
                high = m_hist['High'].iloc[-1]
                low = m_hist['Low'].iloc[-1]
                pct = ((curr - prev) / prev) * 100
                res.append({
                    "指標 / 先物": name,
                    "現在値": f"{curr:.2f}",
                    "前日比(%)": f"{pct:+.2f}%",
                    "当日安値": f"{low:.2f}",
                    "当日高値": f"{high:.2f}"
                })
        except Exception as e:
            print(f"Error {name}: {e}")
    return pd.DataFrame(res).to_markdown(index=False)

def main():
    tickers = get_target_tickers()
    
    stock_texts = []
    files = {}
    
    for i, t in enumerate(tickers):
        chart_path, text = analyze_and_plot(t, i)
        stock_texts.append(text)
        if chart_path and os.path.exists(chart_path):
            files[f"files[{i}]"] = (os.path.basename(chart_path), open(chart_path, "rb"), "image/png")

    macro_table = fetch_macro()
    stock_summary = "\n".join(stock_texts)

    report_text = f"""## 📅 【相場 ＆ テクニカル分析レポート】

### ■ 1. 注目個別銘柄サマリー
{stock_summary}
---

### ■ 2. 主要マクロ指標 ＆ 先物一覧
{macro_table}

---

### ■ 3. 今後1か月の主要マクロイベントカレンダー
{MACRO_CALENDAR}
"""
    if len(report_text) > 1950:
        report_text = report_text[:1950] + "\n..."

    payload = {
        "payload_json": json.dumps({"content": report_text})
    }

    print("Discordへ送信中...")
    res = requests.post(
        DISCORD_WEBHOOK_URL,
        data=payload,
        files=files
    )
    print(f"Discord送信ステータス: {res.status_code}")
    if res.status_code not in [200, 204]:
        print(f"エラー詳細: {res.text}")
        sys.exit(1)

if __name__ == "__main__":
    main()
