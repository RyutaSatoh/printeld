# Print-ETL-D: 設計ドキュメント (Design Document)

## 1. プロジェクト概要
**Print-ETL-D** (Print Extract-Transform-Load Daemon) は、物理的な書類（学校のプリント、請求書、チラシなど）のデジタル化を自動化する、スタンドアロンのPythonアプリケーションです。指定されたディレクトリに追加されたPDFや画像ファイルを監視し、LLM (Gemini API) を使用して構造化データを抽出した後、設定されたエンドポイント（Webhook、JSONファイル保存）へ送信します。

### 基本思想
* **設定駆動 (Config-Driven):** 抽出ルールやスキーマはすべて `config.yaml` で定義します。新しい種類の書類に対応するためにコードを変更する必要はありません。
* **LLMネイティブ:** OCRおよび意味的なデータ抽出に、LLMのマルチモーダル機能を全面的に採用します。
* **モジュール構成:** 「監視 (Watcher)」「処理 (Processor)」「通知 (Notifier)」のコンポーネントを疎結合に保ちます。

## 2. アーキテクチャと技術スタック

### 技術スタック
* **言語:** Python 3.10以上
* **主要ライブラリ:**
    * `watchdog`: ファイルシステムの変更監視
    * `google-generativeai`: LLMとの対話 (Gemini 1.5 Pro/Flash)
    * `pydantic`: データバリデーションとスキーマ定義
    * `pyyaml`: 設定ファイルの管理
    * `httpx`: Webhook送信用の非同期HTTPクライアント
    * `loguru`: 構造化ロギング

### システムコンポーネント
1.  **Watcher Service (監視):** 対象ディレクトリを監視し、ファイル作成イベント（.pdf, .jpg, .png）を検知します。
2.  **Ingestion Pipeline (取り込み):**
    * イベントをキューに入れ、重複処理を防止します。
    * 必要に応じてファイルの前処理を行います。
3.  **LLM Processor (処理):**
    * `config.yaml` を読み込み、適用すべきスキーマを決定します。
    * ファイルとプロンプトをGemini APIに送信します。
    * 「JSONモード」を強制し、構造化されたレスポンスを取得します。
4.  **Dispatcher (配送):**
    * 出力をPydanticモデルで検証します。
    * 設定された送信先（Home AssistantのWebhook、GoogleカレンダーAPIラッパーなど）へペイロードを送信します。

## 3. 設定ファイル設計 (`config.yaml`)
挙動はすべて設定ファイルで制御します。システムは `fields` 定義に基づいて動的にJSONスキーマを構築します。

```yaml
system:
  watch_dir: "./mnt/gdrive/scans"      # 監視ディレクトリ
  processed_dir: "./mnt/gdrive/processed" # 処理済みファイルの移動先
  gemini_model: "gemini-1.5-flash"

profiles:
  - name: "school_event"
    match_pattern: "*print*.pdf"       # ファイル名マッチングパターン
    description: "学校のプリントから行事情報を抽出する"
    # 抽出フィールド定義（LLMへの指示となる）
    fields:
      event_date: 
        type: "string"
        description: "イベントの日付 (YYYY-MM-DD形式)"
      title:
        type: "string"
        description: "イベントのタイトル"
      items_to_bring:
        type: "list[string]"
        description: "持ち物リスト"
      deadline:
        type: "string"
        description: "提出期限があれば記載"
    actions:
      - type: "webhook"
        url: "[http://homeassistant.local:8123/api/webhook/school_event](http://homeassistant.local:8123/api/webhook/school_event)"
      - type: "save_json"
        path: "./output/events.json"

  - name: "invoice"
    match_pattern: "*invoice*.jpg"
    description: "請求書から金額と期限を抽出"
    fields:
      amount:
        type: "integer"
        description: "請求金額（円）"
      due_date:
        type: "string"
        description: "支払期限"
    actions:
      - type: "webhook"
        url: "[https://maker.ifttt.com/trigger/example/json](https://maker.ifttt.com/trigger/example/json)"
```

## 4. モジュール構造
パッケージ化を見据えたクリーンな構成にします。

```text
print_etl_d/
├── main.py              # エントリーポイント
├── config.py            # YAML読み込み & Pydantic設定
├── watcher.py           # Watchdogイベントハンドラ
├── processor.py         # LLM対話ロジック (Core)
├── dispatcher.py        # アクションハンドラ (Webhook, ファイル保存)
├── schema_builder.py    # 動的スキーマ生成ヘルパー
└── utils.py             # ロギング, ファイル操作ユーティリティ
```

## 5. 実装ガイドライン (AIエージェントへの指示)

### A. 動的スキーマ生成
フィールドはYAMLで定義されるため、Pythonコード内に固定のPydanticモデルを持つことができません。
* **戦略:** アクティブなプロファイルの `fields` セクションに基づいて、Gemini API呼び出し用のJSONスキーマを動的に構築します。
* **プロンプト:** システムプロンプトには次を含めます。「あなたはドキュメントパーサーです。以下のフィールド定義に基づいて情報を抽出し、有効なJSONのみを返してください: {fields_definition}」

### B. エラー処理とリトライ
* LLM呼び出しは失敗したり、無効なJSONを返す可能性があります。指数バックオフを用いたリトライ機構を実装します。
* リトライ後も解析に失敗した場合、無限ループを防ぐためにファイルを `error/` ディレクトリに移動します。

### C. 並行処理
* 特にLLM呼び出しとWebhook送信において、可能な限り `asyncio` を使用します。
* `watchdog` はデフォルトで同期処理であるため、`Queue` を使用してファイル検知と非同期処理を分離します。

## 6. 開発ロードマップ

1.  **Phase 1: 骨格と設定 (Skeleton & Config)**
    * `config.py` を実装し、`config.yaml` をパースできるようにする。
    * ロギングとディレクトリ構造のセットアップ。
2.  **Phase 2: プロセッサ (The Processor)**
    * ファイルパスと設定プロファイルを受け取り、Gemini APIを使用してPython辞書を返す `processor.py` を実装する。
3.  **Phase 3: 監視 (The Watcher)**
    * 新しいファイルを検知してプロセッサをトリガーする `watcher.py` を実装する。
4.  **Phase 4: アクションとパッケージ化**
    * `dispatcher.py` を実装する。
    * `Dockerfile` と `docker-compose.yml` を作成する。

---

# Gemini CLI への指示 (Instructions)
* **役割:** あなたはリードバックエンドエンジニアです。
* **制約:** 可能な限り標準ライブラリを使用し、依存関係を最小限に抑えてください。
* **スタイル:** 型ヒント付きのクリーンなコード (Python 3.10+) を書いてください。フォーマッタには `black` を想定します。
* **出力:** コードを求められた際は、import文を含む完全なファイル内容を出力してください。

