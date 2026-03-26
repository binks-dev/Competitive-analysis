# 広告LP URL 一括取得ツール

SearchAPI.io経由でMeta / Google の広告ライブラリからキーワード検索し、広告のLP URLを一括取得するCLIツール。

## セットアップ

```bash
pip install -r requirements.txt
```

APIキーは `.env` ファイルに設定済み。変更する場合は `.env` を編集するか環境変数で上書き：

```bash
export SEARCHAPI_KEY=your_api_key
```

---

## Meta Ad Library (`meta_lp_fetcher.py`)

### 基本

```bash
# 「買取」で日本の広告を検索 → LP一覧をCSV出力
python meta_lp_fetcher.py "買取"

# 5ページ分取得
python meta_lp_fetcher.py "不動産" --max-pages 5

# JSON形式で出力
python meta_lp_fetcher.py "相続" --format json
```

### オプション

| オプション | デフォルト | 説明 |
|---|---|---|
| `--country` | `jp` | 国コード (us, gb, jp, etc.) |
| `--max-pages` | `3` | 最大取得ページ数 |
| `--ad-type` | `all` | 広告タイプ (all, political_and_issue_ads, housing_ads, etc.) |
| `--media-type` | `all` | メディアタイプ (all, image, video) |
| `--output` / `-o` | `{keyword}_lps.csv` | 出力ファイルパス |
| `--format` / `-f` | `csv` | 出力形式 (csv, json) |
| `--dedupe-strict` | off | UTMパラメータ除去後のURLで厳密に重複排除 |
| `--raw` | off | 生APIレスポンスをJSON出力（デバッグ用） |

### 出力フィールド（CSV）

| フィールド | 説明 |
|---|---|
| `advertiser` | 広告主名 |
| `page_id` | FacebookページID |
| `lp_url` | LP URL（フルURL） |
| `lp_url_clean` | LP URL（UTMパラメータ除去） |
| `domain` | ドメイン |
| `cta_text` | CTAテキスト |
| `title` | 広告タイトル |
| `link_description` | リンク説明文 |
| `display_format` | フォーマット (IMAGE/VIDEO等) |
| `page_categories` | ページカテゴリ |

---

## Google Ads Transparency Center (`google_lp_fetcher.py`)

### 基本

```bash
# キーワードで広告主検索 → ドメイン + 広告主の広告LP URLを取得
python google_lp_fetcher.py "買取" --region jp

# 特定ドメインの広告を直接取得
python google_lp_fetcher.py --domain example.com --region jp

# JSON形式で出力
python google_lp_fetcher.py "不動産" --region jp --format json
```

### オプション

| オプション | デフォルト | 説明 |
|---|---|---|
| `--domain` | - | 直接ドメイン指定（キーワード検索スキップ） |
| `--region` | `jp` | 地域コード (us, gb, jp, etc.) |
| `--max-pages` | `3` | ドメイン/広告主ごとの最大ページ数 |
| `--max-advertisers` | `20` | キーワード検索時の最大広告主数 |
| `--max-domains` | `20` | キーワード検索時の最大ドメイン数 |
| `--output` / `-o` | `{keyword}_google_lps.csv` | 出力ファイルパス |
| `--format` / `-f` | `csv` | 出力形式 (csv, json) |
| `--raw` | off | 生APIレスポンスをJSON出力 |

### 出力フィールド（CSV）

| フィールド | 説明 |
|---|---|
| `source` | 検索元（ドメインまたは広告主名） |
| `target_domain` | LP先ドメイン |
| `lp_url` | LP URL |
| `advertiser_id` | 広告主ID |
| `advertiser_name` | 広告主名 |
| `ad_format` | フォーマット (text/image/video) |
| `first_shown` | 初回表示日 |
| `last_shown` | 最終表示日 |
| `total_days_shown` | 表示日数 |
| `details_link` | Google広告透明性センターの詳細URL |

---

## 一括取得例

```bash
# Meta + Google で複数キーワード一括取得
for kw in "買取" "不動産" "相続" "保険"; do
  python meta_lp_fetcher.py "$kw" --max-pages 5 --dedupe-strict
  python google_lp_fetcher.py "$kw" --region jp --max-pages 3
done
```

## 注意事項

- SearchAPI.io無料枠: 月100リクエスト
- Meta: `--max-pages 3` で約3リクエスト消費
- Google: キーワード検索1回 + (ドメイン数 + 広告主数) × max-pages リクエスト消費
- レート制限: ページ間にウェイト挿入済み
