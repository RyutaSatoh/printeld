# Print-ETL-D (Print Extract-Transform-Load Daemon)

Print-ETL-D は、指定したフォルダを監視し、追加された書類（PDFや画像）から Gemini API を使用して自動的にデータを抽出し、JSONファイルへの保存やWebhook通知を行う常駐型アプリケーションです。

## 主な機能

*   **自動監視**: `scans` ディレクトリに追加されたファイルを即座に検知。
*   **AIデータ抽出**: Gemini 1.5 Pro/Flash を使用し、事前に定義したスキーマに基づいて高精度に情報を抽出。
*   **柔軟な出力**: 抽出結果を JSON ファイルに追記保存したり、Home Assistant などの外部サービスへ Webhook 送信が可能。
*   **設定駆動**: プログラミング不要で、YAMLファイルで抽出ルールを自由に定義可能。

## 動作環境

*   Python 3.10 以上
*   Docker & Docker Compose (コンテナ実行の場合)
*   Google Gemini API Key

## セットアップ

### 1. APIキーの取得

Google AI Studio から [Gemini API Key](https://aistudio.google.com/app/apikey) を取得してください。

### 2. インストール

プロジェクトをクローンまたはダウンロードし、ディレクトリへ移動します。

#### ローカル実行の場合

```bash
# 仮想環境の作成と有効化 (推奨)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 依存関係のインストール
pip install -r requirements.txt
```

#### Docker実行の場合

特に追加のインストールは不要です。

### 3. 環境変数の設定

`.env` ファイルを作成し、APIキーを設定します。

```bash
echo "GEMINI_API_KEY=あなたのAPIキー" > .env
```

### 4. 設定ファイルの作成

サンプル設定ファイルをコピーして、自分用の `config.yaml` を作成します。

```bash
cp config.yaml.sample config.yaml
```

その後、必要に応じて `config.yaml` の `base_dir` や `profiles` を調整してください。

## 設定方法 (config.yaml)

`config.yaml` で全ての挙動を制御します。
**注意**: `config.yaml` や `.env` には個人情報やAPIキーが含まれるため、Git管理から除外されています（`.gitignore` 済み）。


```yaml
system:
  watch_dir: "./scans"          # 監視するディレクトリ
  processed_dir: "./processed"  # 処理成功後の移動先
  error_dir: "./error"          # エラー時の移動先
  gemini_model: "gemini-1.5-flash"

profiles:
  - name: "school_print"        # プロファイル名
    match_pattern: "*print*.pdf" # 対象ファイルパターン (glob形式)
    description: "学校のプリントから行事情報を抽出する" # LLMへの指示

    # 抽出したいフィールド定義
    fields:
      event_date: 
        type: "string"
        description: "イベントの日付 (YYYY-MM-DD)"
      items:
        type: "list[string]"
        description: "持ち物リスト"

    # 実行するアクション
    actions:
      - type: "save_json"
        path: "./output/events.json"
      - type: "webhook"
        url: "http://my-home-server/webhook"
```

### フィールドの型
* `string`: 文字列
* `integer`, `number`: 数値
* `boolean`: 真偽値
* `list[string]`: 文字列のリスト（例: 持ち物リスト、ToDoなど）

## 実行方法

### A. Pythonスクリプトとして実行

```bash
export PYTHONPATH=$PYTHONPATH:.
python print_etl_d/main.py
```

### B. Docker Compose で実行 (推奨)

バックグラウンドで常駐させるのに最適です。

```bash
docker-compose up -d --build
```

ログを確認するには:
```bash
docker-compose logs -f
```

## 使い方

1.  アプリケーションを起動します。
2.  `config.yaml` の `watch_dir` で設定したフォルダ（デフォルトは `./scans`）に、PDFや画像ファイルを置きます。
3.  自動的に処理が開始されます。
    *   **成功時**: ファイルは `./processed` に移動し、抽出データが `./output` や Webhook に送信されます。
    *   **失敗時**: ファイルは `./error` に移動します。ログを確認してください。

## トラブルシューティング

*   **APIエラー**: `.env` ファイルに正しい `GEMINI_API_KEY` が設定されているか確認してください。
*   **ファイルが反応しない**: ファイル名が `match_pattern` に一致しているか確認してください。
*   **JSONパースエラー**: Geminiモデルが不安定な場合があります。`processor.py` は自動的にリトライを行いますが、頻発する場合はプロンプト（`description`）を具体的に書き直してください。
