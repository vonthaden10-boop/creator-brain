import os
import json
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

SYSTEM_PROMPT = """You are an audience intelligence classifier for creator content.

Given a TikTok or Instagram comment, classify it and return a JSON object with exactly these fields:

{
  "intent": one of ["question", "purchase_intent", "complaint", "praise", "spam", "other"],
  "product_signals": array of strings describing specific product/purchase/topic signals (empty array if none),
  "emotional_tone": one of ["positive", "negative", "neutral", "mixed"],
  "superfan_score": integer 0-100 representing how likely this person is a superfan or high-value audience member,
  "reasoning": one sentence explaining your classification
}

Superfan score rubric:
- 80-100: Highly engaged, expresses strong admiration, asks personal questions, wants to buy, repeat commenter signals
- 50-79: Engaged, positive, asks genuine questions, shares the content with others
- 20-49: Passive engagement, generic praise, neutral curiosity
- 0-19: Spam, hate, irrelevant, or bot-like behavior

Return only valid JSON. No markdown, no explanation outside the JSON."""


def classify_comment(comment_text: str, platform: str = "tiktok") -> dict:
    """
    Classify a single comment using Claude API.
    Returns the classification dict or raises on failure.
    """
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Platform: {platform}\nComment: {comment_text}"
            }
        ]
    )

    raw = message.content[0].text.strip()
    result = json.loads(raw)

    # Enforce types and clamp superfan_score
    result["superfan_score"] = max(0, min(100, int(result.get("superfan_score", 0))))
    result["product_signals"] = result.get("product_signals") or []

    return result


def classify_batch(comments: list[dict], platform: str = "tiktok") -> list[dict]:
    """
    Classify a list of comment dicts (each must have 'id' and 'text').
    Returns list of {id, classification} dicts.
    """
    results = []
    for comment in comments:
        try:
            classification = classify_comment(comment["text"], platform)
            results.append({
                "id": comment["id"],
                "classification": classification,
                "error": None
            })
        except json.JSONDecodeError as e:
            results.append({
                "id": comment["id"],
                "classification": None,
                "error": f"JSON parse error: {e}"
            })
        except Exception as e:
            results.append({
                "id": comment["id"],
                "classification": None,
                "error": str(e)
            })
    return results
