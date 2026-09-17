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

def fetch_shanghai_premium():
    """
    上海金（SGE AU9999）と国際スポット金（XAUUSD）を取得し、
    中国現物プレミアム（$/oz）を算出する
    """
    try:
        # 1. 上海金 (SGE AU9999: 元/g) の最新価格を取得 (東方財富API)
        eastmoney_url = "https://push2.eastmoney.com/api/qt/stock/get?secid=118.AU9999&fields=f43"
        res = requests.get(eastmoney_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10).json()
        f43_val = res.get('data', {}).get('f43', 0)
        
        # 100倍表記の場合は100で割る
        sge_cny_per_g = f43_val / 100.0 if f43_val > 5000 else float(f43_val)
        
        # 2. 為替レート (USD/CNY) を取得
        usdcny = yf.Ticker("CNY=X").history(period="1d")['Close'].iloc[-1]
        
        # 3. 上海金をドル/トロイオンス ($/oz) に単位換算 (1 oz = 31.1034768 g)
        shanghai_gold_usd = (sge_cny_per_g * 31.1034768) / usdcny
        
        # 4. 国際スポット金価格 (XAUUSD) を取得 (新浪财经 伦敦金 hf_XAU)
        sina_url = "https://hq.sinajs.cn/list=hf_XAU"
        sina_res = requests.get(sina_url, headers={"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"}, timeout=10)
        sina_text = sina_res.text
        
        if '="' in sina_text:
            raw_data = sina_text.split('="').split('";')[0].split(',')
            spot_gold_usd = float(raw_data[0])  # リアルタイムのスポット金価格 ($/oz)
        else:
            # 取得失敗時は COMEX 先物で代用
            spot_gold_usd = yf.Ticker("GC=F").history(period="1d")['Close'].iloc[-1]
            
        # 5. 上海プレミアム ($/oz) の算出
        premium = shanghai_gold_usd - spot_gold_usd
        
        # 6. アジア時間の地合い判定
        if premium >= 15.0:
            sentiment = "🔥【超強気】中国現物買い殺到（アジア時間ロング主体推奨）"
        elif premium > 0.0:
            sentiment = "📈【底堅い】中国現物プレミアム買い優勢"
        else:
            sentiment = "⚠️【軟調】中国需要減退（上値重い）"
            
        return {
            "available": True,
            "sge_cny": sge_cny_per_g,
            "shanghai_usd": shanghai_gold_usd,
            "spot_usd": spot_gold_usd,
            "premium": premium,
            "sentiment": sentiment
        }
    except Exception as e:
        print(f"⚠️ 上海プレミアム取得スキップ (理由: {e})")
        return {"available": False}

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

def send_to_discord(avg_range, recent_df, premium_data, chart_path="momentum_chart.png"):
    """Discordへ運動量データ、上海プレミアム、グラフ画像を投稿"""
    latest = recent_df.iloc[-1]
    today_range = latest['Daily_Range']
    change = latest['Change']
    direction = "陽線 (上昇)" if change >= 0 else "陰線 (下落)"
    
    msg_lines = [
        "📊 **【XAUUSD 運動量＆中国現物プレミアム】**",
        "━━━━━━━━━━━━━━━━━━",
        f"📏 **本日想定される平均値幅 (ADR 5日平均):** `${avg_range:.2f}`",
        f"🔥 **前日の値幅実績:** `${today_range:.2f}` （{direction}）",
        "━━━━━━━━━━━━━━━━━━"
    ]
    
    # 上海プレミアムデータが正常に取れている場合は追記
    if premium_data.get("available"):
        msg_lines.extend([
            f"🇨🇳 **上海金 (AU9999換算):** `${premium_data['shanghai_usd']:,.2f} /oz`",
            f"🌍 **国際スポット金 (XAUUSD):** `${premium_data['spot_usd']:,.2f} /oz`",
            f"⚖️ **上海プレミアム:** `+${premium_data['premium']:.2f} /oz`" if premium_data['premium'] >= 0 else f"⚖️ **上海プレミアム:** `-${abs(premium_data['premium']):.2f} /oz`",
            f"💡 **アジア時間需給判定:** {premium_data['sentiment']}",
            "━━━━━━━━━━━━━━━━━━"
        ])
        
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
    premium_data = fetch_shanghai_premium()
    send_to_discord(avg_range, recent_df, premium_data)

if __name__ == "__main__":
    main()
