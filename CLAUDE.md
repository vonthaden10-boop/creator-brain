# CREATOR BRAIN — CLAUDE CODE OPERATING MANUAL
# GSD MODE: No asking for permission. No explaining what you're about to do. Just build.

---

## WHAT IS CREATOR BRAIN

Creator Brain is a creator audience intelligence platform. It scrapes public TikTok and Instagram comments using Apify, classifies them using Claude API, stores everything in Supabase, and surfaces audience intelligence to creators through a dashboard.

This project is completely standalone. Do not reference, import, or depend on anything from Von Solutions or any other project in this repo.

---

## STACK (LOCKED — DO NOT DEVIATE)

- **Scraping:** Apify (TikTok Comments Scraper actor ID: `BDec00yAmCm1QbMEI`, Instagram actor TBD)
- **Webhooks & Scheduling:** Modal (Python serverless — modal.com)
- **Database:** Supabase
- **AI Classification:** Anthropic Claude API
- **API Endpoints:** Node.js (Express) for any additional API surface
- **Environment:** All keys live in `.env` — never hardcode, never commit

---

## WHAT WE'RE BUILDING

A fully automated intelligence pipeline:

**SCRAPE → INGEST → CLASSIFY → STORE → SURFACE**

1. **SCRAPE** — Apify pulls public TikTok/Instagram comments for a given post or creator
2. **INGEST** — Apify webhooks fire to a Modal endpoint, which receives and normalizes the data
3. **CLASSIFY** — Claude API classifies each comment for intent, product signals, emotional tone, and superfan score
4. **STORE** — Classified comments and post metadata stored in Supabase
5. **SURFACE** — Dashboard surfaces audience intelligence: top signals, superfans, product demand, sentiment

---

## CORE DATA MODEL

### `posts` table
Represents a TikTok or Instagram post being tracked.

```sql
id uuid primary key default gen_random_uuid(),
platform text,                        -- 'tiktok' | 'instagram'
platform_post_id text unique,         -- native ID from the platform
creator_id text,                      -- references creators table (future)
url text,
caption text,
posted_at timestamptz,
comment_count integer,
scrape_status text default 'pending', -- pending | scraping | complete | failed
scraped_at timestamptz,
created_at timestamptz default now()
```

### `comments` table
Represents a single scraped and classified comment.

```sql
id uuid primary key default gen_random_uuid(),
post_id uuid references posts(id),
platform text,
platform_comment_id text unique,
author_username text,
text text,
likes integer default 0,
posted_at timestamptz,
-- Classification fields (populated by Claude)
intent text,                          -- 'question' | 'purchase_intent' | 'complaint' | 'praise' | 'spam' | 'other'
product_signals jsonb,                -- array of product/topic signals detected
emotional_tone text,                  -- 'positive' | 'negative' | 'neutral' | 'mixed'
superfan_score integer,               -- 0–100
classification_raw jsonb,             -- full Claude response for debugging
classified_at timestamptz,
created_at timestamptz default now()
```

---

## CLASSIFICATION SCHEMA (Claude output per comment)

```json
{
  "intent": "purchase_intent",
  "product_signals": ["wants merch", "asking about course"],
  "emotional_tone": "positive",
  "superfan_score": 82,
  "reasoning": "User asks where to buy and expresses strong admiration"
}
```

---

## FILE STRUCTURE (end state)

```
creator-brain/
├── .env                        # never commit
├── CLAUDE.md
├── modal_webhook.py            # Modal endpoint — receives Apify webhook, inserts to Supabase
├── classify.py                 # Claude API classification logic (called by Modal)
├── schema.sql                  # Supabase schema — posts + comments tables
├── server.js                   # Optional Node.js Express API for dashboard
└── dashboard/                  # Future — React + Vite frontend
```

---

## RULES FOR CLAUDE CODE

1. Never ask "should I proceed?" — just build
2. Never create placeholder comments like `// TODO` — implement it
3. Never use mock data — real Supabase and Claude API calls only
4. Always handle errors — wrap all external calls in try/catch with meaningful logs
5. All keys from `.env`: `SUPABASE_URL`, `SUPABASE_KEY`, `ANTHROPIC_API_KEY`, `APIFY_API_KEY`
6. Classification must be non-blocking — classify asynchronously after ingest if needed
7. Every comment row must have `post_id` — never insert orphaned comments
8. This is completely separate from Von Solutions — do not reference or import anything from that project

---

## THIS IS JACOB'S PRODUCT — SHIP IT.
