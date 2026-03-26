#!/usr/bin/env python3
"""
Meta Ad Library LP Fetcher
==========================
SearchAPI.io経由でMeta Ad Libraryからキーワード検索し、
広告のランディングページ(LP) URLを一括取得するCLIツール。

使い方:
  python meta_lp_fetcher.py "買取" --country jp --max-pages 3
  python meta_lp_fetcher.py "不動産" --country jp --output results.csv
  python meta_lp_fetcher.py "相続" --country jp --format json
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
ENGINE = "meta_ad_library"


def get_api_key() -> str:
    """APIキーを環境変数または.envファイルから取得"""
    key = os.environ.get("SEARCHAPI_KEY")
    if key:
        return key

    # .envファイルから読み込み
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


def fetch_ads(keyword: str, country: str, api_key: str, max_pages: int = 1,
              ad_type: str = "all", media_type: str = "all",
              active_status: str = "active") -> list[dict]:
    """
    SearchAPI.io経由でMeta Ad Libraryを検索し、広告データを取得。
    ページネーション対応。
    """
    all_ads = []
    next_page_token = None

    for page in range(max_pages):
        params = {
            "engine": ENGINE,
            "q": keyword,
            "country": country,
            "ad_type": ad_type,
            "media_type": media_type,
            "active_status": active_status,
            "api_key": api_key,
        }

        if next_page_token:
            params["next_page_token"] = next_page_token

        print(f"  ページ {page + 1}/{max_pages} を取得中...", end="", flush=True)

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

        ads = data.get("ads", [])
        print(f" {len(ads)}件取得")

        if not ads:
            break

        all_ads.extend(ads)

        # ページネーション
        next_page_token = data.get("next_page_token")
        if not next_page_token:
            print("  全件取得完了。")
            break

        # レート制限対策
        if page < max_pages - 1:
            time.sleep(1)

    return all_ads


def extract_lp_data(ads: list[dict]) -> list[dict]:
    """広告データからLP関連情報を抽出・重複排除"""
    seen_urls = set()
    results = []

    for ad in ads:
        # APIレスポンスでは広告コンテンツはsnapshot内にネストされている
        snapshot = ad.get("snapshot", {})

        link_url = snapshot.get("link_url", "")
        if not link_url:
            continue

        # 重複チェック（UTMパラメータ除去前のURLで）
        if link_url in seen_urls:
            continue
        seen_urls.add(link_url)

        # ドメイン抽出
        try:
            parsed = urlparse(link_url)
            domain = parsed.netloc
        except Exception:
            domain = ""

        # クリーンURL（UTMパラメータ除去）
        try:
            parsed = urlparse(link_url)
            clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        except Exception:
            clean_url = link_url

        results.append({
            "advertiser": ad.get("page_name", "") or snapshot.get("page_name", ""),
            "page_id": ad.get("page_id", ""),
            "lp_url": link_url,
            "lp_url_clean": clean_url,
            "domain": domain,
            "cta_text": snapshot.get("cta_text", ""),
            "cta_type": snapshot.get("cta_type", ""),
            "caption": snapshot.get("caption", ""),
            "title": snapshot.get("title", ""),
            "link_description": snapshot.get("link_description", ""),
            "display_format": snapshot.get("display_format", ""),
            "page_categories": ", ".join(snapshot.get("page_categories", [])),
            "page_like_count": snapshot.get("page_like_count", ""),
        })

    return results


def dedupe_by_clean_url(results: list[dict]) -> list[dict]:
    """クリーンURL（UTMなし）ベースで重複排除"""
    seen = set()
    deduped = []
    for r in results:
        if r["lp_url_clean"] not in seen:
            seen.add(r["lp_url_clean"])
            deduped.append(r)
    return deduped


def print_summary(results: list[dict], keyword: str):
    """結果のサマリーを表示"""
    print(f"\n{'='*60}")
    print(f"検索キーワード: {keyword}")
    print(f"ユニークLP数: {len(results)}")

    # ドメイン集計
    domain_counts = {}
    for r in results:
        d = r["domain"]
        domain_counts[d] = domain_counts.get(d, 0) + 1

    print(f"ユニークドメイン数: {len(domain_counts)}")
    print(f"\nTop 10 ドメイン:")
    for domain, count in sorted(domain_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"  {domain}: {count}件")
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
        description="Meta Ad Library LP Fetcher - SearchAPI.io経由でLP URLを一括取得",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  python meta_lp_fetcher.py "買取" --country jp
  python meta_lp_fetcher.py "不動産" --country jp --max-pages 5 --output result.csv
  python meta_lp_fetcher.py "相続" --country jp --format json --output result.json
  python meta_lp_fetcher.py "insurance" --country us --ad-type all
        """
    )

    parser.add_argument("keyword", help="検索キーワード")
    parser.add_argument("--country", default="jp", help="国コード (default: jp)")
    parser.add_argument("--max-pages", type=int, default=3, help="最大ページ数 (default: 3)")
    parser.add_argument("--ad-type", default="all",
                        choices=["all", "political_and_issue_ads", "housing_ads",
                                 "employment_ads", "credit_ads"],
                        help="広告タイプ (default: all)")
    parser.add_argument("--media-type", default="all",
                        choices=["all", "image", "video", "meme", "none"],
                        help="メディアタイプ (default: all)")
    parser.add_argument("--output", "-o", help="出力ファイルパス (未指定時: keyword_lps.csv)")
    parser.add_argument("--format", "-f", default="csv", choices=["csv", "json"],
                        help="出力フォーマット (default: csv)")
    parser.add_argument("--dedupe-strict", action="store_true",
                        help="UTMパラメータ除去後のURLで重複排除")
    parser.add_argument("--raw", action="store_true",
                        help="生データをJSONで出力（デバッグ用）")

    args = parser.parse_args()

    api_key = get_api_key()

    print(f"Meta Ad Library LP Fetcher")
    print(f"キーワード: {args.keyword}")
    print(f"国: {args.country.upper()}")
    print(f"最大ページ数: {args.max_pages}")
    print(f"-" * 40)

    # 広告データ取得
    ads = fetch_ads(
        keyword=args.keyword,
        country=args.country,
        api_key=api_key,
        max_pages=args.max_pages,
        ad_type=args.ad_type,
        media_type=args.media_type,
    )

    if not ads:
        print("広告が見つかりませんでした。")
        sys.exit(0)

    print(f"\n合計取得広告数: {len(ads)}")

    # 生データ出力（デバッグ用）
    if args.raw:
        raw_path = args.output or f"{args.keyword}_raw.json"
        output_json(ads, raw_path)
        return

    # LP情報抽出
    results = extract_lp_data(ads)

    if args.dedupe_strict:
        results = dedupe_by_clean_url(results)
        print(f"厳密重複排除後: {len(results)}件")

    # サマリー表示
    print_summary(results, args.keyword)

    # ファイル出力
    if not args.output:
        safe_keyword = args.keyword.replace(" ", "_").replace("/", "_")
        ext = "json" if args.format == "json" else "csv"
        args.output = f"{safe_keyword}_lps.{ext}"

    if args.format == "json":
        output_json(results, args.output)
    else:
        output_csv(results, args.output)


if __name__ == "__main__":
    main()
