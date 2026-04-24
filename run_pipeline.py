"""
Creator Brain — Local Pipeline Runner
Fetches a dataset from Apify, inserts posts + comments into Supabase,
then classifies every comment with Claude Haiku.

Uses direct Supabase REST API via httpx — no supabase-py version issues.

Usage:
  python run_pipeline.py --dataset <dataset_id>
  python run_pipeline.py --dataset xLvwIKxllgNa4cy62
"""

import os
import argparse
import httpx
from datetime import datetime, timezone
from dotenv import load_dotenv
from classify import classify_comment

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
APIFY_KEY    = os.environ["APIFY_API_KEY"]

BASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}


def rest(method: str, table: str, prefer: str = "return=representation,resolution=merge-duplicates", **kwargs) -> list[dict]:
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = {**BASE_HEADERS, "Prefer": prefer}
    resp = httpx.request(method, url, headers=headers, timeout=15, **kwargs)
    resp.raise_for_status()
    return resp.json() if resp.content else []


def fetch_dataset(dataset_id: str) -> list[dict]:
    resp = httpx.get(
        f"https://api.apify.com/v2/datasets/{dataset_id}/items",
        params={"token": APIFY_KEY, "format": "json", "limit": 5000},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def upsert_post(item: dict, platform: str, cache: dict) -> str:
    video_url = item.get("videoWebUrl") or item.get("submittedVideoUrl") or ""
    platform_post_id = video_url.rstrip("/").split("/")[-1] if video_url else "unknown"

    if platform_post_id in cache:
        return cache[platform_post_id]

    rows = rest("POST", "posts", params={"on_conflict": "platform_post_id"}, json={
        "platform": platform,
        "platform_post_id": platform_post_id,
        "url": video_url or None,
        "scrape_status": "scraping",
    })

    post_uuid = rows[0]["id"]
    cache[platform_post_id] = post_uuid
    print(f"  [post] {platform_post_id} → {post_uuid}")
    return post_uuid


def upsert_comment(item: dict, platform: str, post_uuid: str) -> str | None:
    platform_comment_id = str(item.get("cid") or item.get("id") or "")
    text = (item.get("text") or "").strip()
    if not platform_comment_id or not text:
        return None

    create_time = item.get("createTime")
    posted_at = None
    if create_time:
        try:
            posted_at = datetime.fromtimestamp(int(create_time), tz=timezone.utc).isoformat()
        except (ValueError, TypeError):
            pass

    rows = rest("POST", "comments", params={"on_conflict": "platform_comment_id"}, json={
        "post_id": post_uuid,
        "platform": platform,
        "platform_comment_id": platform_comment_id,
        "author_username": item.get("uniqueId") or item.get("uid") or None,
        "text": text,
        "likes": int(item.get("diggCount") or item.get("likeCount") or 0),
        "posted_at": posted_at,
    })

    return rows[0]["id"]


def classify_and_store(comment_uuid: str, text: str, platform: str) -> dict:
    result = classify_comment(text, platform)
    rest("PATCH", "comments",
         prefer="return=minimal",
         params={"id": f"eq.{comment_uuid}"},
         json={
             "intent": result["intent"],
             "product_signals": result["product_signals"],
             "emotional_tone": result["emotional_tone"],
             "superfan_score": result["superfan_score"],
             "classification_raw": result,
             "classified_at": datetime.now(timezone.utc).isoformat(),
         })
    return result


def run(dataset_id: str, platform: str = "tiktok"):
    print(f"\nFetching dataset {dataset_id} from Apify...")
    items = fetch_dataset(dataset_id)
    print(f"Fetched {len(items)} items\n")

    post_cache: dict[str, str] = {}
    comment_rows: list[tuple[str, str]] = []  # (uuid, text)

    print("--- Inserting posts + comments ---")
    for item in items:
        try:
            post_uuid = upsert_post(item, platform, post_cache)
            comment_uuid = upsert_comment(item, platform, post_uuid)
            if comment_uuid:
                comment_rows.append((comment_uuid, (item.get("text") or "").strip()))
        except Exception as e:
            print(f"  [insert error] {e}")
            continue

    # Mark posts complete
    for post_uuid in set(post_cache.values()):
        rest("PATCH", "posts", params={"id": f"eq.{post_uuid}"}, json={
            "scrape_status": "complete",
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "comment_count": len(comment_rows),
        })

    print(f"\nInserted {len(comment_rows)} comments across {len(post_cache)} post(s)\n")

    print("--- Classifying with Claude Haiku ---")
    success = 0
    for i, (comment_uuid, text) in enumerate(comment_rows, 1):
        try:
            result = classify_and_store(comment_uuid, text, platform)
            print(f"  [{i:>3}/{len(comment_rows)}] {result['intent']:<16} score={result['superfan_score']:>3}  {text[:55]}")
            success += 1
        except Exception as e:
            print(f"  [{i:>3}/{len(comment_rows)}] FAILED: {e}")

    print(f"\nDone. {success}/{len(comment_rows)} classified.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--platform", default="tiktok", choices=["tiktok", "instagram"])
    args = parser.parse_args()
    run(args.dataset, args.platform)
