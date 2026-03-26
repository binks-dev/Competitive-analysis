"""
/api/search — Meta / Google 広告検索 Serverless Function
"""
import json
import os
import time
from urllib.parse import urlparse
from http.server import BaseHTTPRequestHandler

import requests as http_requests

API_BASE = "https://www.searchapi.io/api/v1/search"


def get_api_key():
    return os.environ.get("SEARCHAPI_KEY", "")


# ============================================================
# Meta Ad Library
# ============================================================

def search_meta(keyword, country, max_pages):
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
        except Exception:
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
        })

    return results


# ============================================================
# Google Ads Transparency Center
# ============================================================

def search_google(keyword, region, max_pages):
    api_key = get_api_key()

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

    domain_names = []
    for dom in search_data.get("domains", []):
        name = dom.get("name", "") if isinstance(dom, dict) else str(dom)
        if name:
            domain_names.append(name)

    advertisers = search_data.get("advertisers", [])
    all_results = []

    for domain in domain_names:
        creatives = _fetch_google_creatives(api_key, region, max_pages, domain=domain)
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

    for adv in advertisers:
        adv_id = adv.get("id", "")
        adv_name = adv.get("name", "")
        creatives = _fetch_google_creatives(api_key, region, max_pages, advertiser_id=adv_id)
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


def _fetch_google_creatives(api_key, region, max_pages, domain="", advertiser_id=""):
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
# Handler
# ============================================================

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        data = json.loads(body)

        keyword = data.get("keyword", "").strip()
        platforms = data.get("platforms", ["meta", "google"])
        country = data.get("country", "jp")
        max_pages = min(int(data.get("max_pages", 3)), 10)

        if not keyword:
            self._json_response({"error": "キーワードを入力してください"}, 400)
            return

        if not get_api_key():
            self._json_response({"error": "APIキーが設定されていません"}, 500)
            return

        results = []

        if "meta" in platforms:
            results.extend(search_meta(keyword, country, max_pages))

        if "google" in platforms:
            results.extend(search_google(keyword, country, max_pages))

        domain_counts = {}
        for r in results:
            d = r.get("domain", "")
            if d:
                domain_counts[d] = domain_counts.get(d, 0) + 1

        self._json_response({
            "results": results,
            "total": len(results),
            "domain_count": len(domain_counts),
            "top_domains": sorted(domain_counts.items(), key=lambda x: -x[1])[:10],
        })

    def _json_response(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))
