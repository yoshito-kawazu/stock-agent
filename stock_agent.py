import os
import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import requests
import google.generativeai as genai

SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

MACRO_SYMBOLS = {
    "USD/JPY": "USDJPY=X",
    "WTI原油先物": "CL=F",
    "日本10年国債利回り": "^TNX",
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

def get_target_ticker():
    url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/gviz/tq?tqx=out:csv"
    df = pd.read_csv(url)
    ticker = str(df.columns[0]).strip()
    return ticker if ".T" in ticker else f"{ticker}.T"

def generate_chart(ticker):
    stock = yf.Ticker(ticker)
    df = stock.history(period="6mo")
    
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

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), gridspec_kw={'height_ratios': [3, 1]}, sharex=True)

    ax1.plot(df.index, df['Close'], label="Close Price", color="black", alpha=0.7)
    ax1.plot(df.index, df['SMA25'], label="25 SMA", color="blue", linewidth=1.2)
    ax1.plot(df.index, df['SMA75'], label="75 SMA", color="orange", linewidth=1.2)
    ax1.axhline(recent_high, color="red", linestyle="--", alpha=0.8, label=f"Resistance: ¥{recent_high:.0f}")
    ax1.axhline(recent_low, color="green", linestyle="--", alpha=0.8, label=f"Support: ¥{recent_low:.0f}")
    ax1.plot(df.index[-30:], trend_line, color="purple", linestyle=":", linewidth=1.5, label="Trend Line")
    ax1.set_title(f"{ticker} Technical Chart & Trends", fontsize=14, fontweight="bold")
    ax1.legend(loc="upper left")
    ax1.grid(True, alpha=0.3)

    ax2.plot(df.index, df['MACD'], label="MACD", color="blue")
    ax2.plot(df.index, df['Signal'], label="Signal", color="red", linestyle="--")
    ax2.bar(df.index, df['Hist'], label="Hist", color="gray", alpha=0.5)
    ax2.axhline(0, color="black", linewidth=0.5)
    ax2.legend(loc="upper left")
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    chart_path = "technical_chart.png"
    plt.savefig(chart_path, dpi=120)
    plt.close()
    return chart_path, recent_high, recent_low, df

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
    ticker = get_target_ticker()
    chart_path, r_high, r_low, df = generate_chart(ticker)
    
    curr_price = df['Close'].iloc[-1]
    prev_price = df['Close'].iloc[-2]
    pct = ((curr_price - prev_price) / prev_price) * 100
    day_high = df['High'].iloc[-1]
    day_low = df['Low'].iloc[-1]
    
    macro_table = fetch_macro()

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"""
以下の市場データをもとに、毎時更新の投資家向けレポートを作成してください。

【個別銘柄 ({ticker})】
・現在値: ¥{curr_price:.1f} (前日比: {pct:+.2f}%)
・当日レンジ: 安値 ¥{day_low:.1f} 〜 高値 ¥{day_high:.1f}
・25日移動平均線: ¥{df['SMA25'].iloc[-1]:.1f}, 75日線: ¥{df['SMA75'].iloc[-1]:.1f}
・レジスタンスライン（売り場目安）: ¥{r_high:.0f}
・サポートライン（押し目目安）: ¥{r_low:.0f}
・MACD: {df['MACD'].iloc[-1]:.2f}, シグナル: {df['Signal'].iloc[-1]:.2f}

【主要マクロ指標・先物一覧】
{macro_table}

【今後1か月のマクロイベント】
{MACRO_CALENDAR}

■ 作成ルール:
1. 冒頭に個別銘柄の株価・前日比・高安値およびサポート/レジスタンス価格を整理。
2. MACDやトレンドラインの状況を含めたテクニカル所見を記載。
3. マクロ指標一覧表と、重要度（★★★/★★☆/★☆☆）付きマクロイベントカレンダーを掲載。
4. Discordで見やすいMarkdown形式で出力してください。
"""
    response = model.generate_content(prompt)

    with open(chart_path, "rb") as f:
        requests.post(
            DISCORD_WEBHOOK_URL,
            data={"content": response.text},
            files={"file": ("chart.png", f, "image/png")}
        )

if __name__ == "__main__":
    main()
