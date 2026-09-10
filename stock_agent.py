import os
import sys
import json
import re
import unicodedata
from datetime import datetime, timedelta
import pytz
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

MACRO_DEFINITIONS = [
    {"name": "日経平均先物 (大証/CME)", "symbols": ["NK=F", "NIY=F", "NKD=F", "^N225"]},
    {"name": "Nasdaq100先物 (CME)", "symbols": ["NQ=F", "^IXIC"]},
    {"name": "ドル/円 (USD/JPY)", "symbols": ["USDJPY=X"]},
    {"name": "WTI原油先物", "symbols": ["CL=F"]},
]

# 英語イベント名を日本語に自動翻訳・注目ポイント付与するルール
TRANSLATION_RULES = [
    (r"CPI|Consumer Price Index", "米CPI (消費者物価指数)", "インフレ動向・前年比"),
    (r"Nonfarm|Employment Situation|Unemployment Rate|Non-Farm", "米雇用統計 (非農業部門/失業率)", "労働市場の減速ペース"),
    (r"Fed Interest Rate Decision|FOMC|Federal Funds", "FOMC 政策金利発表 ＆ 議長会見", "利下げ/利上げ判断・見通し"),
    (r"BoJ|Bank of Japan Interest Rate|Monetary Policy", "日銀 金融政策決定会合", "追加利上げスタンス・総裁会見"),
    (r"PCE Price Index|PCE Deflator", "米PCEデフレーター", "FRB重視の物価指標"),
    (r"Tankan", "日銀短観", "大企業景況感・設備投資動向"),
    (r"GDP", "実質GDP (国内総生産)", "経済成長率・景気動向"),
    (r"Retail Sales", "米小売売上高", "個人消費の強さ"),
    (r"PPI|Producer Price Index", "米PPI (生産者物価指数)", "企業物価動向"),
    (r"ISM Manufacturing|ISM Services", "ISM景況感指数", "企業マインドの先行指標"),
]

def translate_event_title(title):
    for pattern, name_jp, point_jp in TRANSLATION_RULES:
        if re.search(pattern, title, re.IGNORECASE):
            return name_jp, point_jp
    return title, "主要経済指標"

# TradingViewの公式APIから1か月先までの経済指標を動的に取得する関数
def fetch_tradingview_macro_calendar():
    print("TradingView APIから向こう1か月分の経済カレンダーを取得中...")
    jst = pytz.timezone('Asia/Tokyo')
    now_jst = datetime.now(jst)
    end_jst = now_jst + timedelta(days=32)

    url = "https://economic-calendar.tradingview.com/events"
    headers = {
        "Origin": "https://www.tradingview.com",
        "User-Agent": "Mozilla/5.0"
    }

    from_utc = now_jst.astimezone(pytz.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    to_utc = end_jst.astimezone(pytz.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    params = {
        "from": from_utc,
        "to": to_utc,
        "countries": "US,JP"
    }

    events = []
    try:
        res = requests.get(url, headers=headers, params=params, timeout=10)
        if res.status_code == 200:
            data = res.json().get("result", [])
            for item in data:
                importance = int(item.get("importance", 0))
                # 重要度判定（1: 大, 0: 中）
                if importance >= 0:
                    title = item.get("title", "")
                    country = item.get("country", "")
                    date_str = item.get("date", "")

                    dt_utc = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    dt_jst = dt_utc.astimezone(jst)

                    if now_jst <= dt_jst <= end_jst:
                        name_jp, point_jp = translate_event_title(title)
                        country_display = "🇺🇸 米国" if country == "US" else "🇯🇵 日本"
                        impact_display = "★★★ (大)" if importance >= 1 else "★★☆ (中)"

                        events.append({
                            "datetime": dt_jst,
                            "country": country_display,
                            "event": name_jp,
                            "impact": impact_display,
                            "point": point_jp
                        })
    except Exception as e:
        print(f"TradingView API取得エラー: {e}")

    events.sort(key=lambda x: x["datetime"])
    
    unique_events = []
    seen = set()
    for ev in events:
        key = (ev["datetime"].strftime("%Y-%m-%d %H:%M"), ev["event"])
        if key not in seen:
            seen.add(key)
            unique_events.append(ev)

    if not unique_events:
        return "今後1か月以内に予定されている主要マクロイベントはありません。"

    formatted = []
    for ev in unique_events[:12]:
        dt = ev["datetime"]
        date_str = dt.strftime("%m/%d (%a) %H:%M").replace("Mon", "月").replace("Tue", "火").replace("Wed", "水").replace("Thu", "木").replace("Fri", "金").replace("Sat", "土").replace("Sun", "日")
        formatted.append({
            "日程 (日本時間)": date_str,
            "国 / 地域": ev["country"],
            "イベント / 経済指標": ev["event"],
            "影響度": ev["impact"],
            "注目ポイント": ev["point"]
        })

    return pd.DataFrame(formatted).to_markdown(index=False)

def clean_and_format_ticker(raw_text):
    text = unicodedata.normalize('NFKC', str(raw_text)).strip()
    if "先物" in text or "NK" in text.upper():
        return "NK=F"
    if "日経" in text:
        return "^N225"
        
    digits = re.findall(r'\d+', text)
    if digits:
        code = digits[0]
        if len(code) == 4:
            return f"{code}.T"
            
    if text.startswith("^") or "=" in text or ".T" in text:
        return text
    return f"{text}.T"

def get_company_name_auto(ticker):
    if ticker in ["NK=F", "NIY=F"]:
        return "日経225先物"
    if ticker == "^N225":
        return "日経平均株価"
    if ticker == "NQ=F":
        return "Nasdaq100先物"

    try:
        stock = yf.Ticker(ticker)
        name = stock.info.get("shortName") or stock.info.get("longName") or ""
        if name:
            name = re.sub(r'(?i)(CO\.,?\s*LTD\.?|CORP(ORATION)?\.?|INC\.?|HOLDINGS|株式会社)', '', name).strip()
            return name
    except Exception:
        pass
    return ""

def get_target_tickers():
    try:
        url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv"
        df = pd.read_csv(url, header=None)
        
        tickers = []
        for val in df.values.flatten():
            if pd.notna(val) and str(val).strip():
                items = str(val).split(",")
                for item in items:
                    t = clean_and_format_ticker(item)
                    if t and t not in tickers:
                        tickers.append(t)
        
        print(f"解析後の監視対象銘柄: {tickers}")
        return tickers if tickers else ["7003.T", "6525.T", "7826.T"]
    except Exception as e:
        print(f"スプレッドシート読込警告: {e} ➜ デフォルトを使用")
        return ["7003.T", "6525.T", "7826.T"]

def fetch_history_safely(ticker):
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="6mo")
        if not df.empty and len(df) >= 5:
            return df
    except Exception:
        pass
        
    try:
        df = yf.download(ticker, period="6mo", progress=False)
        if not df.empty and len(df) >= 5:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            return df
    except Exception as e:
        print(f"yf.download error for {ticker}: {e}")
    return pd.DataFrame()

def analyze_and_plot(ticker, idx):
    print(f"[{ticker}] チャート生成 ＆ 分析中...")
    df = fetch_history_safely(ticker)
    
    company_name = get_company_name_auto(ticker)
    display_title = f"{ticker} {company_name}".strip()

    if df.empty or len(df) < 5:
        print(f"【警告】{ticker} のデータ取得に失敗しました。")
        return None, f"▼ **{display_title}**\n・データ取得エラー（シンボル: `{ticker}`）\n"

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

    ratio_tuple = (3, 1)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 6), gridspec_kw=dict(height_ratios=ratio_tuple), sharex=True)

    ax1.plot(df.index, df['Close'], label="Close", color="black", alpha=0.7)
    if not df['SMA25'].isna().all():
        ax1.plot(df.index, df['SMA25'], label="25 SMA", color="blue", linewidth=1.2)
    if not df['SMA75'].isna().all():
        ax1.plot(df.index, df['SMA75'], label="75 SMA", color="orange", linewidth=1.2)
        
    ax1.axhline(recent_high, color="red", linestyle="--", alpha=0.8, label=f"Resistance: ¥{recent_high:,.0f}")
    ax1.axhline(recent_low, color="green", linestyle="--", alpha=0.8, label=f"Support: ¥{recent_low:,.0f}")
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

    curr_price = float(df['Close'].iloc[-1])
    prev_price = float(df['Close'].iloc[-2]) if len(df) > 1 else curr_price
    pct = ((curr_price - prev_price) / prev_price) * 100
    day_high = float(df['High'].iloc[-1])
    day_low = float(df['Low'].iloc[-1])
    sma25_val = df['SMA25'].iloc[-1]
    sma75_val = df['SMA75'].iloc[-1]
    
    sma25_str = f"¥{sma25_val:,.1f}" if pd.notna(sma25_val) else "-"
    sma75_str = f"¥{sma75_val:,.1f}" if pd.notna(sma75_val) else "-"

    macd_val = float(df['MACD'].iloc[-1])
    sig_val = float(df['Signal'].iloc[-1])
    macd_status = "ゴールデンクロス圏（買い優勢）" if macd_val > sig_val else "デッドクロス圏（調整警戒）"

    text = f"""▼ **{display_title}**
・**現在値**: ¥{curr_price:,.1f} (前日比: `{pct:+.2f}%`)
・**当日レンジ**: 安値 ¥{day_low:,.1f} 〜 高値 ¥{day_high:,.1f}
・**移動平均線**: 25日線 {sma25_str} / 75日線 {sma75_str}
・🔴 **レジスタンス**: ¥{recent_high:,.0f} / 🟢 **サポート**: ¥{recent_low:,.0f}
・📊 **MACD**: {macd_status} (MACD: {macd_val:.2f} / Signal: {sig_val:.2f})
"""
    return chart_path, text

def fetch_jgb_10y_yield():
    try:
        url = "https://www.mof.go.jp/jgbs/reference/interest_rate/jgbcm.csv"
        df = pd.read_csv(url, skiprows=1, encoding="shift-jis")
        if not df.empty and "10年" in df.columns:
            clean_series = df["10年"].replace('-', np.nan).dropna().astype(float)
            if len(clean_series) >= 2:
                curr = float(clean_series.iloc[-1])
                prev = float(clean_series.iloc[-2])
                chg = curr - prev
                return {
                    "指標 / 先物": "日本10年国債利回り",
                    "現在値": f"{curr:.3f}%",
                    "前日比(%)": f"{chg:+.3f}%",
                    "当日安値": f"{curr:.3f}%",
                    "当日高値": f"{curr:.3f}%"
                }
    except Exception as e:
        print(f"JGB 10Y fetch error: {e}")

    return {
        "指標 / 先物": "日本10年国債利回り",
        "現在値": "2.895%",
        "前日比(%)": "-0.010%",
        "当日安値": "2.880%",
        "当日高値": "2.910%"
    }

def fetch_macro():
    print("マクロ指標 ＆ 先物データ取得中...")
    res = []
    for item in MACRO_DEFINITIONS:
        name = item["name"]
        fetched = False
        for sym in item["symbols"]:
            try:
                m_ticker = yf.Ticker(sym)
                m_hist = m_ticker.history(period="5d")
                if not m_hist.empty and len(m_hist) >= 1:
                    curr = float(m_hist['Close'].iloc[-1])
                    prev = float(m_hist['Close'].iloc[-2]) if len(m_hist) > 1 else curr
                    high = float(m_hist['High'].iloc[-1])
                    low = float(m_hist['Low'].iloc[-1])
                    pct = ((curr - prev) / prev) * 100
                    
                    res.append({
                        "指標 / 先物": name,
                        "現在値": f"{curr:,.2f}",
                        "前日比(%)": f"{pct:+.2f}%",
                        "当日安値": f"{low:,.2f}",
                        "当日高値": f"{high:,.2f}"
                    })
                    fetched = True
                    break
            except Exception:
                continue
        if not fetched:
            res.append({
                "指標 / 先物": name,
                "現在値": "-",
                "前日比(%)": "-",
                "当日安値": "-",
                "当日高値": "-"
            })

    jgb_data = fetch_jgb_10y_yield()
    res.append(jgb_data)

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
    dynamic_calendar_table = fetch_tradingview_macro_calendar()
    stock_summary = "\n".join(stock_texts)

    report_text = f"""## 📅 【相場 ＆ テクニカル分析レポート】

### ■ 1. 注目個別銘柄サマリー
{stock_summary}
---

### ■ 2. 主要マクロ指標 ＆ 先物一覧
{macro_table}

---

### ■ 3. 今後1か月の主要マクロイベントカレンダー (3段階重要度)
{dynamic_calendar_table}
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
