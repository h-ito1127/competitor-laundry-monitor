# 競合コインランドリー稼働モニタリング

伊勢崎エリアの競合コインランドリー4店舗の機器稼働状況を定期的にスクレイピングし、SQLiteに蓄積するシステムです。

## 対象店舗

| ID | 店舗名 | データソース |
|----|--------|-------------|
| 2 | Baluko Laundry Place 伊勢崎宮子町 | baluko.jp |
| 3 | ブルースカイランドリー トライアル伊勢崎中央店 | edms.bsl-line.jp |
| 4 | fluffy 伊勢崎韮塚店 | coin-laundry.co.jp |
| 5 | コインランドリー Wish | laundry-wish.com |

## セットアップ手順

### 1. GitHubリポジトリを作成

```bash
# 新しいプライベートリポジトリを作成（GitHub CLIを使う場合）
gh repo create competitor-laundry-monitor --private --clone
cd competitor-laundry-monitor

# このフォルダの中身をコピー
cp -r /path/to/this/folder/* .
cp -r /path/to/this/folder/.github .
cp /path/to/this/folder/.gitignore .
```

### 2. 初回コミット & プッシュ

```bash
# DB を初期化
pip install -r requirements.txt
python setup_db.py

# コミット
git add -A
git commit -m "初期セットアップ"
git push -u origin main
```

### 3. GitHub Actions の有効化

リポジトリの **Settings → Actions → General** で以下を確認：

- **Actions permissions**: "Allow all actions" が選択されている
- **Workflow permissions**: "Read and write permissions" が選択されている

### 4. 動作確認

リポジトリの **Actions** タブ → 「競合コインランドリー稼働モニタリング」→ **Run workflow** で手動実行できます。

## ファイル構成

```
├── .github/workflows/scrape.yml   # GitHub Actions ワークフロー（10分間隔）
├── scraper.py                     # メインスクレイパー
├── setup_db.py                    # DB初期化スクリプト
├── requirements.txt               # Python依存パッケージ
├── data/
│   └── competitor_monitor.db      # SQLite データベース（自動生成）
└── README.md
```

## DBスキーマ

- `stores` - 店舗マスタ
- `machines` - 機器マスタ（自動登録）
- `availability_log` - 稼働状況ログ（生データ、7日間保持）
- `scrape_log` - スクレイピング実行ログ
- `hourly_summary` - 1時間単位の集計（7〜90日分）
- `daily_summary` - 日次集計（90日以降）

## データ圧縮ポリシー

実行のたびに自動で以下の圧縮が行われます：

1. **7日以上前**の生データ → `hourly_summary` に集計後、生データを削除
2. **90日以上前**の時間帯データ → `daily_summary` に集計後、時間帯データを削除

## ローカルでの手動実行

```bash
pip install -r requirements.txt
python scraper.py
```

## 注意事項

- GitHub Actions の無料枠は月2,000分（パブリックリポジトリは無制限）
- 10分間隔×24時間×30日 = 約4,320回/月（1回あたり約1分なので十分収まります）
- プライベートリポジトリの場合、月2,000分の無料枠内で運用可能です
- 各サイトの構造変更があった場合はパーサーの修正が必要です
