"""
Creator Brain — Modal Webhook
Receives Apify run-complete webhooks, fetches comment data,
inserts posts + comments into Supabase, then classifies each comment.
"""

import modal
import os
import httpx
from datetime import datetime, timezone

app = modal.App("creator-brain")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("supabase", "anthropic", "httpx", "fastapi[standard]")
    .add_local_python_source("classify")
)


def get_supabase():
    from supabase import create_client
    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_KEY"],
    )


# ---------------------------------------------------------------------------
# Classification worker — background Modal function, one per comment
# ---------------------------------------------------------------------------

@app.function(
    image=image,
    secrets=[modal.Secret.from_name("creator-brain-secrets")],
    retries=2,
)
def classify_and_store(comment_id: str, comment_text: str, platform: str):
    """Classify a single comment and write results back to Supabase."""
    from classify import classify_comment

    supabase = get_supabase()

    try:
        result = classify_comment(comment_text, platform)
        supabase.table("comments").update({
            "intent": result["intent"],
            "product_signals": result["product_signals"],
            "emotional_tone": result["emotional_tone"],
            "superfan_score": result["superfan_score"],
            "classification_raw": result,
            "classified_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", comment_id).execute()
        print(f"[classify] OK comment={comment_id} intent={result['intent']} score={result['superfan_score']}")
    except Exception as e:
        print(f"[classify] FAILED comment={comment_id}: {e}")
        raise


# ---------------------------------------------------------------------------
# Apify webhook endpoint
# ---------------------------------------------------------------------------

@app.function(
    image=image,
    secrets=[modal.Secret.from_name("creator-brain-secrets")],
)
@modal.fastapi_endpoint(method="POST", label="apify-webhook")
async def apify_webhook(body: dict):
    """
    Receives Apify webhook on actor run completion.
    Payload shape:
    {
      "eventType": "ACTOR.RUN.SUCCEEDED",
      "resource": {
        "actId": "BDec00yAmCm1QbMEI",
        "defaultDatasetId": "...",
        "status": "SUCCEEDED"
      }
    }
    """
    event_type = body.get("eventType", "")
    resource = body.get("resource", {})
    status = resource.get("status", "")

    print(f"[webhook] event={event_type} status={status}")

    if status != "SUCCEEDED":
        print(f"[webhook] Skipping — run status is {status}")
        return {"ok": True, "skipped": True, "reason": f"status={status}"}

    dataset_id = resource.get("defaultDatasetId")
    actor_id = resource.get("actId", "")

    if not dataset_id:
        print("[webhook] No defaultDatasetId in payload")
        return {"ok": False, "error": "missing defaultDatasetId"}

    # Fetch all items from the Apify dataset
    apify_key = os.environ["APIFY_API_KEY"]
    items = await fetch_apify_dataset(dataset_id, apify_key)
    print(f"[webhook] Fetched {len(items)} items from dataset {dataset_id}")

    if not items:
        return {"ok": True, "inserted": 0}

    platform = "instagram" if "instagram" in actor_id.lower() else "tiktok"
    supabase = get_supabase()

    inserted_comments = 0
    post_cache: dict[str, str] = {}  # platform_post_id -> supabase post uuid

    for item in items:
        try:
            post_uuid = upsert_post(supabase, item, platform, post_cache)
            comment_uuid = upsert_comment(supabase, item, platform, post_uuid)
            if comment_uuid:
                inserted_comments += 1
                classify_and_store.spawn(comment_uuid, item.get("text", ""), platform)
        except Exception as e:
            print(f"[webhook] Error on item {item.get('id')}: {e}")
            continue

    # Mark all touched posts as complete
    for post_uuid in set(post_cache.values()):
        supabase.table("posts").update({
            "scrape_status": "complete",
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", post_uuid).execute()

    print(f"[webhook] Done. inserted={inserted_comments}")
    return {"ok": True, "inserted": inserted_comments}


async def fetch_apify_dataset(dataset_id: str, api_key: str) -> list[dict]:
    url = f"https://api.apify.com/v2/datasets/{dataset_id}/items"
    params = {"token": api_key, "format": "json", "limit": 5000}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


def upsert_post(supabase, item: dict, platform: str, cache: dict) -> str:
    """Upsert parent post from a comment item. Returns Supabase post UUID."""
    video_meta = item.get("videoMeta") or {}
    platform_post_id = str(
        video_meta.get("id") or item.get("videoId") or "unknown"
    )

    if platform_post_id in cache:
        return cache[platform_post_id]

    result = supabase.table("posts").upsert({
        "platform": platform,
        "platform_post_id": platform_post_id,
        "url": video_meta.get("url") or item.get("videoUrl") or None,
        "scrape_status": "scraping",
    }, on_conflict="platform_post_id").execute()

    post_uuid = result.data[0]["id"]
    cache[platform_post_id] = post_uuid
    return post_uuid


def upsert_comment(supabase, item: dict, platform: str, post_uuid: str) -> str | None:
    """Upsert a single comment. Returns Supabase comment UUID or None if skipped."""
    platform_comment_id = str(item.get("id", ""))
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

    author = item.get("authorMeta") or {}

    result = supabase.table("comments").upsert({
        "post_id": post_uuid,
        "platform": platform,
        "platform_comment_id": platform_comment_id,
        "author_username": author.get("name") or author.get("uniqueId") or None,
        "text": text,
        "likes": int(item.get("diggCount") or item.get("likeCount") or 0),
        "posted_at": posted_at,
    }, on_conflict="platform_comment_id").execute()

    return result.data[0]["id"]
