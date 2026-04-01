# スプレッドシート連携の設定

Ad LP Finder の検索結果を Google スプレッドシートに自動転記するための設定手順です。

## 手順

### 1. スプレッドシートを作成
Google Drive で新しいスプレッドシートを作成します。シート名はそのままで OK です。

### 2. Apps Script を開く
`拡張機能` → `Apps Script` をクリック

### 3. コードを貼り付け
デフォルトの `function myFunction()` を**すべて削除**して、以下のコードを貼り付けます：

```javascript
function doPost(e) {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var data = JSON.parse(e.postData.contents);
  var results = data.results || [];

  // ヘッダーがなければ追加
  if (sheet.getLastRow() === 0) {
    sheet.appendRow([
      '取得日時', '検索キーワード', '媒体', '広告主', '出稿元',
      'ドメイン', 'LP URL', 'LP URL（クリーン）', 'タイトル', 'CTA',
      '形式', '説明', '広告開始日', '広告終了日', '詳細リンク'
    ]);
    // ヘッダー行を太字に
    sheet.getRange(1, 1, 1, 15).setFontWeight('bold');
  }

  // データを追記
  results.forEach(function(r) {
    sheet.appendRow([
      r.fetchedAt || '',
      r.keyword || '',
      r.source || '',
      r.advertiser || '',
      r.publisher || '',
      r.domain || '',
      r.lp_url || '',
      r.lp_url_clean || '',
      r.title || '',
      r.cta_text || '',
      r.ad_format || '',
      r.description || '',
      r.first_shown || '',
      r.last_shown || '',
      r.details_link || ''
    ]);
  });

  return ContentService.createTextOutput(
    JSON.stringify({ status: 'ok', count: results.length })
  ).setMimeType(ContentService.MimeType.JSON);
}
```

### 4. デプロイ
1. 右上の `デプロイ` → `新しいデプロイ`
2. ⚙️ アイコン → `ウェブアプリ` を選択
3. 設定:
   - **説明**: `Ad LP Finder 連携`
   - **次のユーザーとして実行**: `自分`
   - **アクセスできるユーザー**: `全員`
4. `デプロイ` をクリック
5. `アクセスを承認` → Google アカウントで許可
6. 表示された **URL をコピー**

### 5. Ad LP Finder に URL を設定
1. Ad LP Finder のヘッダーにある `📊 スプシ設定` をクリック
2. コピーした URL を貼り付けて `保存`

### 6. 使い方
検索結果画面の `📊 スプシに送信` ボタンをクリックすると、結果がスプレッドシートに追記されます。
