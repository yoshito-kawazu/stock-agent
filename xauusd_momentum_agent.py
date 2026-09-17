import os
import datetime
import requests
import yfinance as yf
import matplotlib.pyplot as plt
import pandas as pd

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

def fetch_gold_data():
    """金（COMEX金先物 GC=F）のデータを取得（Yahoo Finance公式の安定ティッカー）"""
    # XAUUSD=X はYahoo側で404になるため、最もデータが安定している GC=F を使用
    gold = yf.Ticker("GC=F")
    df = gold.history(period="1mo", interval="1d")
    
    if df.empty:
        raise ValueError("データの取得に失敗しました。Yahoo Financeのサーバーを確認してください。")
    
    # 運動量（1日の高値 - 安値のドル幅）を計算
    df['Daily_Range'] = df['High'] - df['Low']
    df['Change'] = df['Close'] - df['Open']
    
    return df

def generate_momentum_chart(df, output_path="momentum_chart.png"):
    """直近7営業日分の運動量を綺麗な縦棒グラフにプロット"""
    recent_df = df.tail(7).copy()
    avg_range_5d = df['Daily_Range'].tail(5).mean()
    
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
    
    # 棒グラフの色分け（陽線日はゴールド/緑、陰線日は赤/オレンジ）
    colors = ['#FFD700' if c >= 0 else '#FF6347' for c in recent_df['Change']]
    
    # 安全に日付フォーマットを変換
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
    
    # 5日平均運動量（ADR）の水平ラインを描画
    ax.axhline(avg_range_5d, color='#00FFFF', linestyle='--', linewidth=1.5, 
               label=f'5-Day Avg Range: ${avg_range_5d:.1f}')
    
    # 棒の上に数値を表示
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

def send_to_discord(avg_range, recent_df, chart_path="momentum_chart.png"):
    """Discordへ今日戦うための『値幅ファクト』だけを簡潔に投稿"""
    latest = recent_df.iloc[-1]
    today_range = latest['Daily_Range']
    change = latest['Change']
    direction = "陽線 (上昇)" if change >= 0 else "陰線 (下落)"
    
    # 現場での余計なアドバイスは全削除し、今日使う「物差し（ファクト）」だけに特化
    msg_content = f"""📊 **【XAUUSD 運動量＆ADRデータ】**
━━━━━━━━━━━━━━━━━━
📏 **本日想定される平均値幅 (ADR):** `${avg_range:.2f}`
🔥 **前日の値幅実績:** `${today_range:.2f}` （{direction}）
━━━━━━━━━━━━━━━━━━
💡 **実戦での物差し:**
・本日これからの高安値幅が **${avg_range:.1f}** に到達、または近づいているか？
（これに満たない段階での中途半端な逆張りエントリーは原則禁止！）"""

    payload = {"content": msg_content}
    
    with open(chart_path, "rb") as f:
        files = {"file": (chart_path, f, "image/png")}
        res = requests.post(DISCORD_WEBHOOK_URL, data=payload, files=files)
        
    if res.status_code in [200, 204]:
        print("✅ Discordへの画像・レポート送信に成功しました。")
    else:
        print(f"❌ エラー: {res.status_code}, {res.text}")

def main():
    if not DISCORD_WEBHOOK_URL:
        print("❌ DISCORD_WEBHOOK_URL が設定されていません。")
        return
        
    df = fetch_gold_data()
    avg_range, recent_df = generate_momentum_chart(df)
    send_to_discord(avg_range, recent_df)

if __name__ == "__main__":
    main()
