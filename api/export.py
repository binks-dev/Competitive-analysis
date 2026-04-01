"""
/api/export — CSV出力 Serverless Function
"""
import csv
import datetime
import io
import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import quote


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        data = json.loads(body)

        results = data.get("results", [])
        keyword = data.get("keyword", "lp_urls")
        filter_label = data.get("filter", "")

        if not results:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "データがありません"}).encode("utf-8"))
            return

        output = io.BytesIO()
        # BOM付きUTF-8（Excel対応）
        output.write(b'\xef\xbb\xbf')

        fieldnames = ["source", "advertiser", "domain", "lp_url", "lp_url_clean",
                       "title", "cta_text", "ad_format", "description",
                       "first_shown", "last_shown", "details_link"]
        header_labels = {
            "source": "媒体", "advertiser": "広告主/会社名", "domain": "ドメイン",
            "lp_url": "LP URL", "lp_url_clean": "LP URL（クリーン）",
            "title": "タイトル", "cta_text": "CTA", "ad_format": "形式",
            "description": "説明", "first_shown": "広告開始日",
            "last_shown": "広告終了日", "details_link": "詳細リンク",
        }

        text_wrapper = io.TextIOWrapper(output, encoding='utf-8', newline='')
        writer = csv.DictWriter(text_wrapper, fieldnames=fieldnames, extrasaction='ignore')
        writer.writerow(header_labels)
        writer.writerows(results)
        text_wrapper.flush()
        text_wrapper.detach()

        csv_bytes = output.getvalue()

        # ファイル名
        date_str = datetime.date.today().isoformat()
        safe_keyword = keyword.replace(' ', '_').replace('/', '_')
        filter_part = f"_{filter_label}" if filter_label else ""
        filename = f"{safe_keyword}{filter_part}_{date_str}.csv"

        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition",
                         f"attachment; filename*=UTF-8''{quote(filename)}")
        self.send_header("Content-Length", str(len(csv_bytes)))
        self.end_headers()
        self.wfile.write(csv_bytes)
