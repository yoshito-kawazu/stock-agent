import os
import requests
import yfinance as yf
import matplotlib.pyplot as plt
import pandas as pd

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

def fetch_gold_momentum_data():
    """COMEX金先物（GC=F）から1週間の値幅・運動量データを安定取得"""
    gold = yf.Ticker("GC=F")
    df = gold.history(period="1mo", interval="1d")
    
    if df.empty:
        raise ValueError("金先物データの取得に失敗しました。")
    
    df['Daily_Range'] = df['High'] - df['Low']
    df['Change'] = df['Close'] - df['Open']
    return df

def fetch_macro_market_data():
    """
    WTI原油先物（CL=F）と米国10年債利回り（^TNX）を取得
    """
    macro_data = {}
    
    # 1. WTI原油先物 (CL=F)
    try:
        oil = yf.Ticker("CL=F").history(period="5d")
        if not oil.empty:
            oil_price = oil['Close'].iloc[-1]
            oil_prev = oil['Close'].iloc[-2] if len(oil) >= 2 else oil_price
            oil_change = oil_price - oil_prev
            oil_pct = (oil_change / oil_prev) * 100 if oil_prev else 0
            macro_data['oil'] = {
                "available": True,
                "price": oil_price,
                "change": oil_change,
                "pct": oil_pct
            }
    except Exception as e:
        print(f"⚠️ 原油先物取得エラー: {e}")
        macro_data['oil'] = {"available": False}
        
    # 2. 米国10年債利回り (^TNX)
    try:
        tnx = yf.Ticker("^TNX").history(period="5d")
        if not tnx.empty:
            tnx_yield = tnx['Close'].iloc[-1]
            tnx_prev = tnx['Close'].iloc[-2] if len(tnx) >= 2 else tnx_yield
            tnx_change = tnx_yield - tnx_prev
            macro_data['tnx'] = {
                "available": True,
                "yield": tnx_yield,
                "change": tnx_change
            }
    except Exception as e:
        print(f"⚠️ 米10年債利回り取得エラー: {e}")
        macro_data['tnx'] = {"available": False}
        
    return macro_data

def generate_momentum_chart(df, output_path="momentum_chart.png"):
    """直近7営業日分の運動量を綺麗な縦棒グラフにプロット"""
    recent_df = df.tail(7).copy()
    avg_range_5d = df['Daily_Range'].tail(5).mean()
    
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
    
    colors = ['#FFD700' if c >= 0 else '#FF6347' for c in recent_df['Change']]
    date_labels = pd.to_datetime(recent_df.index).strftime('%m/%d (%a)')
    
    bars = ax.bar(
        date_labels,
        recent_df['Daily_Range'],
        color=colors,
        width=0.55,
        edgecolor='white',
        linewidth=0.8,
        label='Daily Range ($)'
    )
    
    ax.axhline(avg_range_5d, color='#00FFFF', linestyle='--', linewidth=1.5, 
               label=f'5-Day Avg Range: ${avg_range_5d:.1f}')
    
    for bar in bars:
        yval = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2.0, yval + 0.8, f"${yval:.1f}", 
                ha='center', va='bottom', fontsize=9, fontweight='bold', color='white')
        
    ax.set_title("XAUUSD 1-Week Momentum & Daily Range ($ High - Low)", fontsize=13, fontweight='bold', pad=15)
    ax.set_ylabel("Price Range (USD / oz)", fontsize=10)
    ax.grid(axis='y', linestyle=':', alpha=0.3)
    ax.legend(loc='upper left')
    
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()
    
    return avg_range_5d, recent_df

def send_to_discord(avg_range, recent_df, macro_data, chart_path="momentum_chart.png"):
    """Discordへ運動量データ、原油、米10年債利回り、グラフ画像を投稿"""
    latest = recent_df.iloc[-1]
    today_range = latest['Daily_Range']
    change = latest['Change']
    direction = "陽線 (上昇)" if change >= 0 else "陰線 (下落)"
    
    msg_lines = [
        "📊 **【XAUUSD 運動量＆マクロ指標データ】**",
        "━━━━━━━━━━━━━━━━━━",
        f"📏 **本日想定される平均値幅 (ADR 5日平均):** `${avg_range:.2f}`",
        f"🔥 **前日の値幅実績:** `${today_range:.2f}` （{direction}）",
        "━━━━━━━━━━━━━━━━━━"
    ]
    
    # 🛢️ WTI原油先物
    oil_info = macro_data.get('oil', {})
    if oil_info.get('available'):
        sign = "+" if oil_info['change'] >= 0 else ""
        msg_lines.append(f"🛢️ **WTI原油先物:** `${oil_info['price']:.2f}` ({sign}{oil_info['change']:.2f} / {sign}{oil_info['pct']:.2f}%)")
        
    # 🇺🇸 米国10年債利回り
    tnx_info = macro_data.get('tnx', {})
    if tnx_info.get('available'):
        sign = "+" if tnx_info['change'] >= 0 else ""
        msg_lines.append(f"🇺🇸 **米10年債利回り:** `{tnx_info['yield']:.3f}%` ({sign}{tnx_info['change']:.3f}%p)")
        
    msg_lines.append("━━━━━━━━━━━━━━━━━━")
    
    msg_content = "\n".join(msg_lines)
    payload = {"content": msg_content}
    
    with open(chart_path, "rb") as f:
        files = {"file": (chart_path, f, "image/png")}
        res = requests.post(DISCORD_WEBHOOK_URL, data=payload, files=files)
        
    if res.status_code in [200, 204]:
        print("✅ Discordへの送信に成功しました。")
    else:
        print(f"❌ エラー: {res.status_code}, {res.text}")

def main():
    if not DISCORD_WEBHOOK_URL:
        print("❌ DISCORD_WEBHOOK_URL が設定されていません。")
        return
        
    df = fetch_gold_momentum_data()
    avg_range, recent_df = generate_momentum_chart(df)
    macro_data = fetch_macro_market_data()
    send_to_discord(avg_range, recent_df, macro_data)

if __name__ == "__main__":
    main()
