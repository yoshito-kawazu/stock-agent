import os
import time  # 🚀 時間待機用に追加
import requests
from google import genai
from google.genai import types
from google.genai.errors import ServerError, ClientError  # 🚀 エラーハンドリング用に追加

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

# 1. 環境変数の取得
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

if not GEMINI_API_KEY or not DISCORD_WEBHOOK_URL:
    raise ValueError("GEMINI_API_KEY または DISCORD_WEBHOOK_URL が設定されていません。")

# 2. プロンプトの定義（3銘柄選定の指定を追加）
ANALYSIS_PROMPT = """
あなたは、日本株の成長株投資とテーマ投資に精通したトップクラスの株式アナリスト兼ファンドマネージャーです。

日本の全上場企業（プライム・スタンダード・グロース）を対象に、今後6～12カ月程度で株価が2倍になる可能性を持つ「テーマ性のある割安成長株」を【厳選して3銘柄】選定してください。

単に話題性がある銘柄ではなく、テーマによる需要拡大が実際の受注、売上高、利益、キャッシュフローに波及する可能性を、株式投資家が唸るほど論理的に説明してください。

【情報源】
必ず企業の一次情報を確認してください（Web検索をフル活用してください）。
・直近の決算短信、決算説明資料
・有価証券報告書、半期報告書
・中期経営計画、事業計画
・適時開示、月次情報、受注高
・会社公式サイト、製品資料
・官公庁の政策資料、法令、予算、統計
・取引先企業が開示している設備投資計画
ニュース、SNS、証券会社レポートは補足にとどめ、根拠の中心にしないでください。参照した一次情報の資料名、開示日、URLを銘柄ごとに明記してください。

【テーマ性の評価】
AI、半導体、フィジカルAI、ロボット、省人化、防衛、宇宙、データセンター、電力インフラ、サイバーセキュリティ、事業承継、インバウンド、法令改正などから、有望なテーマを幅広く調査してください。
テーマについて、次の因果関係を具体的に説明してください。
社会・産業構造の変化 → 顧客企業の課題や投資需要 → 対象企業の商品・サービスが必要になる理由 → 受注・契約数・単価・継続率への影響 → 売上高と利益への波及 → 株式市場で評価が見直される条件
「市場が拡大するから関連企業も伸びる」といった抽象的な説明は禁止します。対象企業がテーマの中でどの部分を担い、競合ではなく同社が受注できる根拠を示してください。

【割安成長株の判定】
調査時点の最新株価を取得し、株価基準日を明記したうえで、予想PER、PBR、EV/EBITDA、PEGレシオ、ROE、時価総額、ネットキャッシュまたは有利子負債を算出してください。
直近決算をもとに、次を確認してください。
・売上高、営業利益、EPSの増減率
・通期計画に対する進捗率と季節性
・受注高、受注残、契約数、顧客数などの先行指標
・利益率の改善余地
・営業キャッシュフロー
・会社予想の上方修正余地
・一過性利益に依存していないか
原則として、売上高と営業利益が中期的に年率10％以上、理想は20％以上成長し、予想PER20倍以下を目安とします。ただし、成長率や利益率改善が極めて高い場合は、PERが高くても理由を示したうえで採用可能です。

【株価2倍の実現性】
各銘柄について、株価2倍に必要な時価総額、予想利益、適用PERを逆算してください。
6～12カ月以内に起こり得る具体的なカタリスト（業績上振れ、新規受注、新市場参入、政策予算、自社株買い等）を示し、カタリスト不発条件やリスクも記載してください。

【採点（100点満点）】
・テーマの強さと持続性：25点 / 業績への波及確度：25点 / 成長性：20点 / 割安度：15点 / 短期カタリスト：10点 / 財務健全性：5点

【出力形式】
各銘柄について次を記載してください。
順位／企業名／証券コード／株価／時価総額／総合点
テーマと選定理由
テーマが業績につながる論理
直近決算の評価
割安度と成長性
株価2倍までの業績・バリュエーションシナリオ
今後6～12カ月のカタリスト
主要リスク
確認すべき次回決算のKPI
一次情報の出典

最後に、銘柄を「実現確度重視」「上振れ余地重視」「ハイリスク・ハイリターン」に分類してください。株価2倍を断定せず、事実、会社計画、合理的な推計を明確に区別してください。
"""

def generate_report():
    print("レポート生成中（最新のGemini 3.6 Flash & Web検索グラウンディング有効）...")
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    # 🚀 自動リトライ設定（最大5回、一時的な503 / 429に対処）
    max_retries = 5
    base_delay = 5  # 秒
    
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-3.6-flash',
                contents=ANALYSIS_PROMPT,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    temperature=0.2,
                )
            )
            return response.text
            
        except (ServerError, ClientError) as e:
            # 503 (Unavailable), 500 (Internal), または 429 (Resource Exhausted) の場合は時間をおいて再試行
            is_transient = "503" in str(e) or "500" in str(e) or "429" in str(e)
            
            if is_transient and attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)  # 5秒, 10秒, 20秒, 40秒と徐々に増やす
                print(f"⚠️ 一時的なエラー（{e}）を検出しました。{delay}秒後に再試行します（試行 {attempt + 1}/{max_retries}）...")
                time.sleep(delay)
            else:
                # 404など致命的なエラー、またはリトライ上限に達した場合はエラーを投げる
                print("❌ 復旧不可能なエラーまたはリトライ上限に達しました。")
                raise e

def send_to_discord(report_text):
    print("Discordへレポート送信中...")
    
    # レポートをファイルとして保存
    filename = "weekly_stock_report.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(report_text)
    
    # 冒頭サマリー（Discordの2000文字上限に収める）
    summary = (
        "📈 **【週次日本株分析レポート】テーマ性のある割安成長株（厳選3銘柄）**\n"
        "今週の自動スクリーニング・分析が完了しました。\n"
        "詳細な因果関係・KPI・一次情報URLは添付のMarkdownファイルをご確認ください。\n\n"
    )
    
    # 本文の先頭部分を抜粋してプレビュー表示
    preview_limit = 1500
    if len(report_text) > preview_limit:
        preview = report_text[:preview_limit] + "\n\n...（続きは添付ファイル参照）"
    else:
        preview = report_text

    payload = {"content": summary + "```markdown\n" + preview + "\n```"}
    
    with open(filename, "rb") as f:
        files = {"file": (filename, f, "text/markdown")}
        res = requests.post(DISCORD_WEBHOOK_URL, data=payload, files=files)
        res.raise_for_status()
        
    print("Discord送信完了！")

if __name__ == "__main__":
    report = generate_report()
    send_to_discord(report)
