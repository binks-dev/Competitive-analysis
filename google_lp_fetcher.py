#!/usr/bin/env python3
"""
Google Ads Transparency Center LP Fetcher
==========================================
SearchAPI.io経由でGoogle Ads Transparency Centerから
広告主を検索し、広告のLP URLを一括取得するCLIツール。

使い方:
  # キーワードで広告主検索 → ドメイン → LP URL取得
  python google_lp_fetcher.py "買取" --region jp --max-pages 3

  # 特定ドメインの広告LP直接取得
  python google_lp_fetcher.py --domain example.com --region jp

  # JSON形式で出力
  python google_lp_fetcher.py "不動産" --region jp --format json
"""

import argparse
import csv
import json
import os
import sys
import time
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    print("ERROR: requests ライブラリが必要です。")
    print("  pip install requests")
    sys.exit(1)


API_BASE = "https://www.searchapi.io/api/v1/search"
ENGINE_ADVERTISER_SEARCH = "google_ads_transparency_center_advertiser_search"
ENGINE_ADS = "google_ads_transparency_center"


def get_api_key() -> str:
    """APIキーを環境変数または.envファイルから取得"""
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

    print("ERROR: APIキーが見つかりません。")
    print("  以下のいずれかで設定してください:")
    print("  1. 環境変数: export SEARCHAPI_KEY=your_key")
    print("  2. .envファイル: SEARCHAPI_KEY=your_key")
    sys.exit(1)


# ============================================================
# Step 1: キーワードで広告主・ドメインを検索
# ============================================================

def search_advertisers(keyword: str, region: str, api_key: str,
                       num_advertisers: int = 20, num_domains: int = 20) -> dict:
    """
    キーワードで広告主・ドメインを検索。
    戻り値: {"advertisers": [...], "domains": [...]}
    """
    params = {
        "engine": ENGINE_ADVERTISER_SEARCH,
        "q": keyword,
        "region": region,
        "num_advertisers": num_advertisers,
        "num_domains": num_domains,
        "api_key": api_key,
    }

    print(f"  広告主を検索中: \"{keyword}\"...", end="", flush=True)

    try:
        response = requests.get(API_BASE, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f" エラー: {e}")
        return {"advertisers": [], "domains": []}
    except json.JSONDecodeError:
        print(f" JSONパースエラー")
        return {"advertisers": [], "domains": []}

    advertisers = data.get("advertisers", [])
    domains = data.get("domains", [])
    print(f" 広告主{len(advertisers)}件, ドメイン{len(domains)}件")

    return {"advertisers": advertisers, "domains": domains}


# ============================================================
# Step 2: ドメインまたは広告主IDから広告クリエイティブを取得
# ============================================================

def fetch_ad_creatives_by_domain(domain: str, api_key: str, region: str = "",
                                 max_pages: int = 3) -> list[dict]:
    """特定ドメインの広告クリエイティブを取得。ページネーション対応。"""
    all_creatives = []
    next_page_token = None

    for page in range(max_pages):
        params = {
            "engine": ENGINE_ADS,
            "domain": domain,
            "api_key": api_key,
            "num": 100,
        }
        if region:
            params["region"] = region
        if next_page_token:
            params["next_page_token"] = next_page_token

        print(f"    [{domain}] ページ {page + 1}/{max_pages} ...", end="", flush=True)

        try:
            response = requests.get(API_BASE, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            print(f" エラー: {e}")
            break
        except json.JSONDecodeError:
            print(f" JSONパースエラー")
            break

        creatives = data.get("ad_creatives", [])
        print(f" {len(creatives)}件")

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


def fetch_ad_creatives_by_advertiser(advertiser_id: str, advertiser_name: str,
                                     api_key: str, region: str = "",
                                     max_pages: int = 3) -> list[dict]:
    """広告主IDから広告クリエイティブを取得。ページネーション対応。"""
    all_creatives = []
    next_page_token = None

    for page in range(max_pages):
        params = {
            "engine": ENGINE_ADS,
            "advertiser_id": advertiser_id,
            "api_key": api_key,
            "num": 100,
        }
        if region:
            params["region"] = region
        if next_page_token:
            params["next_page_token"] = next_page_token

        label = advertiser_name[:20] if advertiser_name else advertiser_id[:15]
        print(f"    [{label}] ページ {page + 1}/{max_pages} ...", end="", flush=True)

        try:
            response = requests.get(API_BASE, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            print(f" エラー: {e}")
            break
        except json.JSONDecodeError:
            print(f" JSONパースエラー")
            break

        creatives = data.get("ad_creatives", [])
        print(f" {len(creatives)}件")

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
# Step 3: LP情報抽出・出力
# ============================================================

def extract_lp_data(creatives: list[dict], source: str = "") -> list[dict]:
    """広告クリエイティブからLP関連情報を抽出"""
    results = []

    for creative in creatives:
        target_domain = creative.get("target_domain", "")
        advertiser = creative.get("advertiser", {})

        # target_domainがある場合はURLを構築
        if target_domain:
            lp_url = f"https://{target_domain}" if not target_domain.startswith("http") else target_domain
        else:
            lp_url = ""

        results.append({
            "source": source,
            "target_domain": target_domain,
            "lp_url": lp_url,
            "advertiser_id": advertiser.get("id", ""),
            "advertiser_name": advertiser.get("name", ""),
            "ad_format": creative.get("format", ""),
            "first_shown": creative.get("first_shown_datetime", ""),
            "last_shown": creative.get("last_shown_datetime", ""),
            "total_days_shown": creative.get("total_days_shown", ""),
            "details_link": creative.get("details_link", ""),
        })

    return results


def dedupe_results(results: list[dict]) -> list[dict]:
    """target_domainベースで重複排除（空のtarget_domainは保持）"""
    seen = set()
    deduped = []
    for r in results:
        key = r["target_domain"]
        if not key:
            # target_domainが無い場合はdetails_linkで重複判定
            key = r.get("details_link", "")
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        deduped.append(r)
    return deduped


def print_summary(results: list[dict], keyword_or_domain: str):
    """結果のサマリーを表示"""
    print(f"\n{'='*60}")
    print(f"検索: {keyword_or_domain}")
    print(f"ユニーク広告数: {len(results)}")

    # ドメイン集計
    domain_counts = {}
    for r in results:
        d = r["target_domain"] or "(不明)"
        domain_counts[d] = domain_counts.get(d, 0) + 1

    print(f"ユニークドメイン数: {len(domain_counts)}")

    # 広告主集計
    adv_counts = {}
    for r in results:
        name = r["advertiser_name"] or "(不明)"
        adv_counts[name] = adv_counts.get(name, 0) + 1

    print(f"ユニーク広告主数: {len(adv_counts)}")

    print(f"\nTop 10 ドメイン:")
    for domain, count in sorted(domain_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"  {domain}: {count}件")

    print(f"\nTop 10 広告主:")
    for name, count in sorted(adv_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"  {name}: {count}件")
    print(f"{'='*60}")


def output_csv(results: list[dict], filepath: str):
    """CSV出力"""
    if not results:
        print("出力するデータがありません。")
        return

    fieldnames = results[0].keys()
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    print(f"CSV出力完了: {filepath} ({len(results)}件)")


def output_json(results: list[dict], filepath: str):
    """JSON出力"""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"JSON出力完了: {filepath} ({len(results)}件)")


def main():
    parser = argparse.ArgumentParser(
        description="Google Ads Transparency Center LP Fetcher - SearchAPI.io経由でLP URLを一括取得",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # キーワードで検索（ドメイン検索＋広告主検索）
  python google_lp_fetcher.py "買取" --region jp
  python google_lp_fetcher.py "不動産" --region jp --max-pages 5

  # 特定ドメインの広告を直接取得
  python google_lp_fetcher.py --domain example.com --region jp

  # JSON出力
  python google_lp_fetcher.py "相続" --region jp --format json

  # 生データ確認
  python google_lp_fetcher.py --domain example.com --raw -o debug.json
        """
    )

    parser.add_argument("keyword", nargs="?", default=None,
                        help="検索キーワード（広告主検索）")
    parser.add_argument("--domain", help="直接ドメイン指定（広告主検索をスキップ）")
    parser.add_argument("--region", default="jp", help="地域コード (default: jp)")
    parser.add_argument("--max-pages", type=int, default=3,
                        help="ドメイン/広告主ごとの最大ページ数 (default: 3)")
    parser.add_argument("--max-advertisers", type=int, default=20,
                        help="キーワード検索時の最大広告主数 (default: 20)")
    parser.add_argument("--max-domains", type=int, default=20,
                        help="キーワード検索時の最大ドメイン数 (default: 20)")
    parser.add_argument("--output", "-o", help="出力ファイルパス")
    parser.add_argument("--format", "-f", default="csv", choices=["csv", "json"],
                        help="出力フォーマット (default: csv)")
    parser.add_argument("--raw", action="store_true",
                        help="生データをJSONで出力（デバッグ用）")

    args = parser.parse_args()

    if not args.keyword and not args.domain:
        parser.error("キーワードまたは --domain を指定してください")

    api_key = get_api_key()

    print(f"Google Ads Transparency Center LP Fetcher")
    print(f"{'キーワード: ' + args.keyword if args.keyword else 'ドメイン: ' + args.domain}")
    print(f"地域: {args.region.upper()}")
    print(f"最大ページ数: {args.max_pages}")
    print(f"-" * 40)

    all_creatives = []

    if args.domain:
        # ------------------------------------------
        # モード1: 直接ドメイン指定
        # ------------------------------------------
        creatives = fetch_ad_creatives_by_domain(
            domain=args.domain, api_key=api_key,
            region=args.region, max_pages=args.max_pages,
        )
        all_creatives.extend([(c, args.domain) for c in creatives])

    else:
        # ------------------------------------------
        # モード2: キーワード検索 → ドメイン＋広告主
        # ------------------------------------------
        search_result = search_advertisers(
            keyword=args.keyword, region=args.region, api_key=api_key,
            num_advertisers=args.max_advertisers, num_domains=args.max_domains,
        )

        # ドメインリスト
        domain_names = []
        for dom in search_result.get("domains", []):
            name = dom.get("name", "") if isinstance(dom, dict) else str(dom)
            if name:
                domain_names.append(name)

        # 広告主リスト
        advertisers = search_result.get("advertisers", [])

        print(f"\n  検索結果: ドメイン{len(domain_names)}件, 広告主{len(advertisers)}件")

        if domain_names:
            print(f"\n  --- ドメイン検索 ---")
            for domain in domain_names:
                print(f"  ドメイン: {domain}")
                creatives = fetch_ad_creatives_by_domain(
                    domain=domain, api_key=api_key,
                    region=args.region, max_pages=args.max_pages,
                )
                all_creatives.extend([(c, domain) for c in creatives])
                time.sleep(0.5)

        if advertisers:
            print(f"\n  --- 広告主検索 ---")
            for adv in advertisers:
                adv_id = adv.get("id", "")
                adv_name = adv.get("name", "")
                ads_count = adv.get("ads_count", {})
                count_lower = ads_count.get("lower", 0) if isinstance(ads_count, dict) else 0
                print(f"  広告主: {adv_name} (広告数: {count_lower}+)")

                creatives = fetch_ad_creatives_by_advertiser(
                    advertiser_id=adv_id, advertiser_name=adv_name,
                    api_key=api_key, region=args.region,
                    max_pages=args.max_pages,
                )
                all_creatives.extend([(c, adv_name) for c in creatives])
                time.sleep(0.5)

    if not all_creatives:
        print("\n広告が見つかりませんでした。")
        sys.exit(0)

    print(f"\n合計取得広告クリエイティブ数: {len(all_creatives)}")

    # 生データ出力
    if args.raw:
        raw_data = [c for c, _ in all_creatives]
        raw_path = args.output or f"{args.keyword or args.domain}_raw.json"
        output_json(raw_data, raw_path)
        return

    # LP情報抽出
    results = []
    for creative, source in all_creatives:
        results.extend(extract_lp_data([creative], source=source))

    # 重複排除
    results = dedupe_results(results)
    print(f"重複排除後: {len(results)}件")

    # サマリー表示
    label = args.keyword or args.domain
    print_summary(results, label)

    # ファイル出力
    if not args.output:
        safe_name = (args.keyword or args.domain).replace(" ", "_").replace("/", "_")
        ext = "json" if args.format == "json" else "csv"
        args.output = f"{safe_name}_google_lps.{ext}"

    if args.format == "json":
        output_json(results, args.output)
    else:
        output_csv(results, args.output)


if __name__ == "__main__":
    main()
