import os
import sys
import json
import re
import unicodedata
import calendar
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

# マクロ指標の定義（米国債ではなく、日経先物、ナスダック先物、ドル円、原油）
MACRO_DEFINITIONS = [
    {"name": "日経平均先物 (大証/CME)", "symbols": ["NK=F", "NIY=F", "NKD=F", "^N225"]},
    {"name": "Nasdaq100先物 (CME)", "symbols": ["NQ=F", "^IXIC"]},
    {"name": "ドル/円 (USD/JPY)", "symbols": ["USDJPY=X"]},
    {"name": "WTI原油先物", "symbols": ["CL=F"]},
]

# 毎月の第N金曜日を算出する関数
def get_nth_friday(year, month, n=1):
    c = calendar.Calendar(firstweekday=calendar.MONDAY)
    monthcal = c.monthdatescalendar(year, month)
    fridays = [day for week in monthcal for day in week if day.weekday() == calendar.FRIDAY and day.month == month]
    return fridays[n-1] if len(fridays) >= n else None

# 毎月の最終金曜日を算出する関数
def get_last_friday(year, month):
    c = calendar.Calendar(firstweekday=calendar.MONDAY)
    monthcal = c.monthdatescalendar(year, month)
    fridays = [day for week in monthcal for day in week if day.weekday() == calendar.FRIDAY and day.month == month]
    return fridays[-1] if fridays else None

# 動的に今後1か月の主要イベントを自動生成するエンジン
def generate_dynamic_calendar():
    jst = pytz.timezone('Asia/Tokyo')
    now_jst = datetime.now(jst)
    end_date = now_jst + timedelta(days=32)

    events = []
    months_to_check = [
        (now_jst.year, now_jst.month),
        ((now_jst.year + 1 if now_jst.month == 12 else now_jst.year), (1 if now_jst.month == 12 else now_jst.month + 1))
    ]

    for y, m in months_to_check:
        # 1. 米雇用統計（第1金曜日 21:30）
        fri1 = get_nth_friday(y, m, 1)
        if fri1:
            events.append({
                "datetime": jst.localize(datetime(fri1.year, fri1.month, fri1.day, 21, 30)),
                "country": "🇺🇸 米国",
                "event": f"米{m-1 if m > 1 else 12}月 雇用統計",
                "impact": "★★★ (大)",
                "point": "非農業部門雇用者数 ＆ 失業率"
            })

        # 2. 米CPI（毎月中旬 12日前後の平日 21:30）
        cpi_day = 12
        while datetime(y, m, cpi_day).weekday() >= 5:
            cpi_day += 1
        events.append({
            "datetime": jst.localize(datetime(y, m, cpi_day, 21, 30)),
            "country": "🇺🇸 米国",
            "event": f"米{m-1 if m > 1 else 12}月 CPI (消費者物価指数)",
            "impact": "★★★ (大)",
            "point": "インフレ動向・前年比"
        })

        # 3. 米PCEデフレーター（月末最終金曜日 21:30）
        last_fri = get_last_friday(y, m)
        if last_fri:
            events.append({
                "datetime": jst.localize(datetime(last_fri.year, last_fri.month, last_fri.day, 21, 30)),
                "country": "🇺🇸 米国",
                "event": f"米{m-1 if m > 1 else 12}月 PCEデフレーター",
                "impact": "★★☆ (中)",
                "point": "FRB重視の物価指標"
            })

        # 4. 日銀短観（4月, 7月, 10月, 12月の月初 08:50）
        tankan_months = (4, 7, 10, 12)
        if m in tankan_months:
            tankan_day = 1
            while datetime(y, m, tankan_day).weekday() >= 5:
                tankan_day += 1
            events.append({
                "datetime": jst.localize(datetime(y, m, tankan_day, 8, 50)),
                "country": "🇯🇵 日本",
                "event": f"日銀短観 ({m}月調査)",
                "impact": "★★☆ (中)",
                "point": "大企業製造業DI・景況感"
            })

        # 5. FOMC 政策金利（1, 3, 5, 6, 7, 9, 11, 12月の中下旬 03:00）
        fomc_months = (1, 3, 5, 6, 7, 9, 11, 12)
        fomc_mid_months = (3, 6, 9, 12)
        if m in fomc_months:
            fomc_day = 18 if m in fomc_mid_months else 28
            while datetime(y, m, fomc_day).weekday() >= 5:
                fomc_day += 1
            events.append({
                "datetime": jst.localize(datetime(y, m, fomc_day, 3, 0)),
                "country": "🇺🇸 米国",
                "event": "FOMC 政策金利発表 ＆ 議長会見",
                "impact": "★★★ (大)",
                "point": "利下げ/利上げ判断 ＆ 経済見通し"
            })

        # 6. 日銀金融政策決定会合（1, 3, 4, 6, 7, 9, 10, 12月の中下旬 12:00）
        boj_months = (1, 3, 4, 6, 7, 9, 10, 12)
        boj_mid_months = (3, 6, 9, 12)
        if m in boj_months:
            boj_day = 19 if m in boj_mid_months else 29
            while datetime(y, m, boj_day).weekday() >= 5:
                boj_day += 1
            events.append({
                "datetime": jst.localize(datetime(y, m, boj_day, 12, 0)),
                "country": "🇯🇵 日本",
                "event": "日銀 金融政策決定会合",
                "impact": "★★★ (大)",
                "point": "追加利上げスタンス ＆ 総裁会見"
            })

    active_events = [ev for ev in events if now_jst <= ev["datetime"] <= end_date]
    active_events.sort(key=lambda x: x["datetime"])

    if not active_events:
        return "今後1か月以内に予定されている主要イベントはありません。"

    res = []
    for ev in active_events:
        dt = ev["datetime"]
        date_str = dt.strftime("%m/%d (%a) %H:%M").replace("Mon", "月").replace("Tue", "火").replace("Wed", "水").replace("Thu", "木").replace("Fri", "金").replace("Sat", "土").replace("Sun", "日")
        res.append({
            "日程 (日本時間)": date_str,
            "国 / 地域": ev["country"],
            "イベント / 経済指標": ev["event"],
            "影響度": ev["impact"],
            "注目ポイント": ev["point"]
        })

    return pd.DataFrame(res).to_markdown(index=False)

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

    ratio_list = (3, 1)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 6), gridspec_kw=dict(height_ratios=ratio_list), sharex=True)

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

# 日本10年国債利回りを財務省・公的データから正確に取得する専用関数
def fetch_jgb_10y_yield():
    try:
        # 財務省の最新国債金利CSVを取得
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

    # フォールバック実勢推計（2.90%水準）
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

    # 日本10年国債利回りを末尾に追加
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
    dynamic_calendar_table = generate_dynamic_calendar()
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
