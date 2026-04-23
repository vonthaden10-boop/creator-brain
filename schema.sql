-- Creator Brain — Supabase Schema
-- Run this in the Supabase SQL editor

-- Posts table
-- Represents a TikTok or Instagram post being tracked
create table if not exists posts (
  id uuid primary key default gen_random_uuid(),
  platform text not null check (platform in ('tiktok', 'instagram')),
  platform_post_id text not null unique,
  creator_id text,
  url text,
  caption text,
  posted_at timestamptz,
  comment_count integer,
  scrape_status text not null default 'pending' check (scrape_status in ('pending', 'scraping', 'complete', 'failed')),
  scraped_at timestamptz,
  created_at timestamptz not null default now()
);

-- Comments table
-- Represents a single scraped and classified comment
create table if not exists comments (
  id uuid primary key default gen_random_uuid(),
  post_id uuid not null references posts(id) on delete cascade,
  platform text not null check (platform in ('tiktok', 'instagram')),
  platform_comment_id text not null unique,
  author_username text,
  text text not null,
  likes integer not null default 0,
  posted_at timestamptz,

  -- Classification fields (populated by Claude after scrape)
  intent text check (intent in ('question', 'purchase_intent', 'complaint', 'praise', 'spam', 'other')),
  product_signals jsonb,       -- array of strings: ["wants merch", "asking about course"]
  emotional_tone text check (emotional_tone in ('positive', 'negative', 'neutral', 'mixed')),
  superfan_score integer check (superfan_score >= 0 and superfan_score <= 100),
  classification_raw jsonb,    -- full Claude response for debugging
  classified_at timestamptz,

  created_at timestamptz not null default now()
);

-- Indexes for common query patterns
create index if not exists comments_post_id_idx on comments(post_id);
create index if not exists comments_intent_idx on comments(intent);
create index if not exists comments_superfan_score_idx on comments(superfan_score desc);
create index if not exists comments_classified_at_idx on comments(classified_at);
create index if not exists posts_platform_post_id_idx on posts(platform_post_id);
create index if not exists posts_scrape_status_idx on posts(scrape_status);
