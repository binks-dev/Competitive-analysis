#!/usr/bin/env python3
"""
広告LP URL取得 WebUI
====================
Meta Ad Library / Google Ads Transparency Center から
キーワード検索でLP URLを一括取得するWebアプリ。
"""

import json
import os
import csv
import io
import time
from urllib.parse import urlparse, quote as requests_utils_quote

from flask import Flask, render_template, request, jsonify, Response

try:
    import requests as http_requests
except ImportError:
    print("ERROR: pip install requests flask")
    exit(1)

app = Flask(__name__, template_folder="templates", static_folder="static")

API_BASE = "https://www.searchapi.io/api/v1/search"


def get_api_key() -> str:
    key = os.environ.get("SEARCHAPI_KEY")
    if key:
        return key
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("SEARCHAPI_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


# ============================================================
# Meta Ad Library
# ============================================================

def search_meta(keyword: str, country: str, max_pages: int) -> list[dict]:
    """Meta Ad Libraryからキーワード検索してLP URL一覧を返す"""
    api_key = get_api_key()
    all_ads = []
    next_page_token = None

    for page in range(max_pages):
        params = {
            "engine": "meta_ad_library",
            "q": keyword,
            "country": country,
            "ad_type": "all",
            "media_type": "all",
            "active_status": "active",
            "api_key": api_key,
        }
        if next_page_token:
            params["next_page_token"] = next_page_token

        try:
            resp = http_requests.get(API_BASE, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            break

        ads = data.get("ads", [])
        if not ads:
            break

        all_ads.extend(ads)
        next_page_token = data.get("next_page_token")
        if not next_page_token:
            break
        if page < max_pages - 1:
            time.sleep(1)

    # Extract LP data
    seen_urls = set()
    results = []
    for ad in all_ads:
        snapshot = ad.get("snapshot", {})
        link_url = snapshot.get("link_url", "")
        if not link_url or link_url in seen_urls:
            continue
        seen_urls.add(link_url)

        try:
            parsed = urlparse(link_url)
            domain = parsed.netloc
            clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        except Exception:
            domain = ""
            clean_url = link_url

        results.append({
            "source": "Meta",
            "advertiser": ad.get("page_name", "") or snapshot.get("page_name", ""),
            "domain": domain,
            "lp_url": link_url,
            "lp_url_clean": clean_url,
            "title": snapshot.get("title", ""),
            "cta_text": snapshot.get("cta_text", ""),
            "ad_format": snapshot.get("display_format", ""),
            "description": snapshot.get("link_description", ""),
            "first_shown": ad.get("ad_delivery_start_time", ""),
            "last_shown": ad.get("ad_delivery_stop_time", ""),
        })

    return results


# ============================================================
# Google Ads Transparency Center
# ============================================================

def search_google(keyword: str, region: str, max_pages: int) -> list[dict]:
    """Google Ads Transparency Centerからキーワード検索してLP URL一覧を返す"""
    api_key = get_api_key()

    # Step 1: 広告主・ドメイン検索
    params = {
        "engine": "google_ads_transparency_center_advertiser_search",
        "q": keyword,
        "region": region,
        "num_advertisers": 20,
        "num_domains": 20,
        "api_key": api_key,
    }
    try:
        resp = http_requests.get(API_BASE, params=params, timeout=30)
        resp.raise_for_status()
        search_data = resp.json()
    except Exception:
        return []

    # ドメインリスト
    domain_names = []
    for dom in search_data.get("domains", []):
        name = dom.get("name", "") if isinstance(dom, dict) else str(dom)
        if name:
            domain_names.append(name)

    # 広告主リスト
    advertisers = search_data.get("advertisers", [])

    all_results = []

    # Step 2a: ドメイン検索
    for domain in domain_names:
        creatives = _fetch_google_creatives(
            api_key, region, max_pages, domain=domain
        )
        for c in creatives:
            target = c.get("target_domain", "")
            adv = c.get("advertiser", {})
            lp_url = f"https://{target}" if target and not target.startswith("http") else target
            all_results.append({
                "source": "Google",
                "advertiser": adv.get("name", ""),
                "domain": target,
                "lp_url": lp_url,
                "lp_url_clean": lp_url,
                "title": "",
                "cta_text": "",
                "ad_format": c.get("format", ""),
                "description": "",
                "first_shown": c.get("first_shown_datetime", ""),
                "last_shown": c.get("last_shown_datetime", ""),
                "details_link": c.get("details_link", ""),
            })
        time.sleep(0.5)

    # Step 2b: 広告主検索
    for adv in advertisers:
        adv_id = adv.get("id", "")
        adv_name = adv.get("name", "")
        creatives = _fetch_google_creatives(
            api_key, region, max_pages, advertiser_id=adv_id
        )
        for c in creatives:
            target = c.get("target_domain", "")
            c_adv = c.get("advertiser", {})
            lp_url = f"https://{target}" if target and not target.startswith("http") else (target or "")
            all_results.append({
                "source": "Google",
                "advertiser": c_adv.get("name", "") or adv_name,
                "domain": target or "(不明)",
                "lp_url": lp_url,
                "lp_url_clean": lp_url,
                "title": "",
                "cta_text": "",
                "ad_format": c.get("format", ""),
                "description": "",
                "first_shown": c.get("first_shown_datetime", ""),
                "last_shown": c.get("last_shown_datetime", ""),
                "details_link": c.get("details_link", ""),
            })
        time.sleep(0.5)

    # Dedupe by domain
    seen = set()
    deduped = []
    for r in all_results:
        key = r["domain"]
        if not key or key in seen:
            if key:
                continue
        seen.add(key)
        deduped.append(r)

    return deduped


def _fetch_google_creatives(api_key: str, region: str, max_pages: int,
                             domain: str = "", advertiser_id: str = "") -> list[dict]:
    """Google広告クリエイティブ取得（ページネーション対応）"""
    all_creatives = []
    next_page_token = None

    for page in range(max_pages):
        params = {
            "engine": "google_ads_transparency_center",
            "api_key": api_key,
            "num": 100,
        }
        if domain:
            params["domain"] = domain
        if advertiser_id:
            params["advertiser_id"] = advertiser_id
        if region:
            params["region"] = region
        if next_page_token:
            params["next_page_token"] = next_page_token

        try:
            resp = http_requests.get(API_BASE, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            break

        creatives = data.get("ad_creatives", [])
        if not creatives:
            break

        all_creatives.extend(creatives)

        pagination = data.get("pagination", {})
        next_page_token = pagination.get("next_page_token")
        if not next_page_token:
            break
        if page < max_pages - 1:
            time.sleep(1)

    return all_creatives


# ============================================================
# Routes
# ============================================================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/search", methods=["POST"])
def api_search():
    data = request.get_json()
    keyword = data.get("keyword", "").strip()
    platforms = data.get("platforms", ["meta", "google"])
    country = data.get("country", "jp")
    max_pages = min(int(data.get("max_pages", 3)), 10)

    if not keyword:
        return jsonify({"error": "キーワードを入力してください"}), 400

    if not get_api_key():
        return jsonify({"error": "APIキーが設定されていません"}), 500

    results = []

    if "meta" in platforms:
        meta_results = search_meta(keyword, country, max_pages)
        results.extend(meta_results)

    if "google" in platforms:
        google_results = search_google(keyword, country, max_pages)
        results.extend(google_results)

    # ドメイン集計
    domain_counts = {}
    for r in results:
        d = r.get("domain", "")
        if d:
            domain_counts[d] = domain_counts.get(d, 0) + 1

    return jsonify({
        "results": results,
        "total": len(results),
        "domain_count": len(domain_counts),
        "top_domains": sorted(domain_counts.items(), key=lambda x: -x[1])[:10],
    })


@app.route("/api/export", methods=["POST"])
def api_export():
    data = request.get_json()
    results = data.get("results", [])
    keyword = data.get("keyword", "lp_urls")
    filter_label = data.get("filter", "")

    if not results:
        return jsonify({"error": "エクスポートするデータがありません"}), 400

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
    # 日本語ヘッダー
    writer.writerow(header_labels)
    writer.writerows(results)
    text_wrapper.flush()
    text_wrapper.detach()

    csv_bytes = output.getvalue()

    # ファイル名組み立て
    import datetime
    date_str = datetime.date.today().isoformat()
    safe_keyword = keyword.replace(' ', '_').replace('/', '_')
    filter_part = f"_{filter_label}" if filter_label else ""
    filename = f"{safe_keyword}{filter_part}_{date_str}.csv"

    return Response(
        csv_bytes,
        mimetype="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{requests_utils_quote(filename)}",
            "Content-Type": "text/csv; charset=utf-8",
        }
    )


if __name__ == "__main__":
    print("\n🚀 広告LP URL取得ツール起動中...")
    print("   http://localhost:5050\n")
    app.run(host="0.0.0.0", port=5050, debug=True)
