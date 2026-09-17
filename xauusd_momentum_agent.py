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
    上海金（SGE AU9999連動 518880.SS）と国際スポット金を取得し、
    中国現物プレミアム（$/oz）を算出する（海外IPブロック対策版）
    """
    try:
        # 1. 上海金ETF (518880.SS: 華安黄金ETF) から AU9999 (元/g) を算出
        # ※ 1口 = 0.01g の純金現物（AU9999）に完全連動しているため、100倍で 1g あたりの元価格になる
        sge_etf = yf.Ticker("518880.SS").history(period="5d")
        if sge_etf.empty:
            raise ValueError("518880.SS のデータが空です")
        sge_etf_price = sge_etf['Close'].iloc[-1]
        sge_cny_per_g = sge_etf_price * 100.0  # 元/g
        
        # 2. 為替レート (USD/CNY) を取得
        fx = yf.Ticker("USDCNY=X").history(period="5d")
        usdcny = fx['Close'].iloc[-1]
        
        # 3. 上海金をドル/トロイオンス ($/oz) に換算 (1 oz = 31.1034768 g)
        shanghai_gold_usd = (sge_cny_per_g * 31.1034768) / usdcny
        
        # 4. 国際スポット金価格 (XAUUSD) を取得
        # まず新浪财经のロンドン金(hf_XAU)を試行し、ブロックされた場合は COMEX金先物で代用
        spot_gold_usd = None
        try:
            sina_url = "https://hq.sinajs.cn/list=hf_XAU"
            headers = {"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"}
            res = requests.get(sina_url, headers=headers, timeout=5)
            if '="' in res.text:
                spot_gold_usd = float(res.text.split('="').split(',')[0])
        except Exception:
            pass
            
        if not spot_gold_usd or spot_gold_usd <= 0:
            # バックアップ: COMEX先物 (GC=F) から現物近似値を採用
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
            
        print(f"✅ 上海プレミアム算出成功: 上海=${shanghai_gold_usd:.2f}, 国際=${spot_gold_usd:.2f}, 差額={premium:+.2f}")
        return {
            "available": True,
            "sge_cny": sge_cny_per_g,
            "shanghai_usd": shanghai_gold_usd,
            "spot_usd": spot_gold_usd,
            "premium": premium,
            "sentiment": sentiment
        }
    except Exception as e:
        print(f"❌ 上海プレミアム取得エラー: {e}")
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
    
    if premium_data.get("available"):
        p_val = premium_data['premium']
        p_str = f"+${p_val:.2f}" if p_val >= 0 else f"-${abs(p_val):.2f}"
        msg_lines.extend([
            f"🇨🇳 **上海金 (AU9999換算):** `${premium_data['shanghai_usd']:,.2f} /oz`",
            f"🌍 **国際スポット金 (XAUUSD):** `${premium_data['spot_usd']:,.2f} /oz`",
            f"⚖️ **上海プレミアム:** `{p_str} /oz`",
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
