"""
Format-agnostic consumption history ingestion.

Accepts raw pasted or exported content from any source — Claude conversation
history, Pocket CSV, Kindle highlights, browser bookmarks, YouTube watch
history, OPML files, plain lists of URLs/titles, etc. — and uses Claude to:

  1. Parse it into structured consumption items
  2. Extract cognitive signals (mental models, third-order patterns, interests)
     from the consumption pattern as a whole

Parsed items are embedded into ChromaDB for topic gap detection.
Cognitive signals are merged into cognitive_profile.json.
Raw content is never stored.

Supported format hints (all optional — Claude auto-detects if omitted):
  "claude"    — Claude.ai conversation history (JSON export or copy-pasted text)
  "pocket"    — Pocket CSV export
  "kindle"    — Kindle highlights CSV (My Clippings or export)
  "browser"   — Browser bookmarks HTML (Chrome, Firefox, Safari)
  "youtube"   — Google Takeout watch-history.json
  "opml"      — OPML RSS subscription list
  "twitter"   — Twitter/X bookmarks JSON or copy-pasted threads
  "raw"       — Any plain text: URLs, titles, freeform notes
"""

import json
import re
from pathlib import Path

import anthropic

PROMPTS_DIR = Path("prompts")

FORMAT_DESCRIPTIONS = {
    "claude": "Claude.ai conversation history — JSON export or copy-pasted conversation text",
    "pocket": "Pocket export — CSV with title, url, time_added, tags columns",
    "kindle": "Kindle highlights — CSV or plain text from My Clippings or Kindle export",
    "browser": "Browser bookmarks — HTML export from Chrome, Firefox, or Safari",
    "youtube": "YouTube watch history — JSON from Google Takeout",
    "opml": "OPML file — RSS/podcast subscription list",
    "twitter": "Twitter/X — bookmarks JSON export or copy-pasted threads",
    "raw": "Plain text — freeform list of URLs, titles, or notes",
}


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text()


def _extract_json(text: str) -> str:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        return match.group(1)
    return text


def _format_hint_description(format_hint: str | None) -> str:
    if not format_hint:
        return "Unknown — auto-detect from content structure and patterns."
    desc = FORMAT_DESCRIPTIONS.get(format_hint)
    if desc:
        return f"{format_hint}: {desc}"
    return format_hint


def parse_and_extract(
    raw_content: str,
    format_hint: str | None = None,
) -> dict:
    """
    Sends raw content to Claude for parsing and cognitive extraction.

    Returns:
      {
        "items": [{title, url, source, summary, content_type}, ...],
        "cognitive_signals": {
          "mental_models": [...],
          "third_order": [...],
          "interests": [...]
        }
      }
    """
    client = anthropic.Anthropic()

    # Truncate very large pastes to avoid hitting context limits.
    # 80k chars ≈ ~20k tokens, well within claude-sonnet-4's context.
    content_to_send = raw_content[:80_000]
    if len(raw_content) > 80_000:
        content_to_send += f"\n\n[Content truncated — {len(raw_content):,} chars total, first 80,000 shown]"

    prompt_template = _load_prompt("parse_consumption_history.txt")
    prompt = prompt_template.replace(
        "{format_hint}", _format_hint_description(format_hint)
    ).replace("{raw_content}", content_to_send)

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8096,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text
    return json.loads(_extract_json(raw))


def ingest(
    raw_content: str,
    format_hint: str | None = None,
    extract_signals: bool = True,
) -> dict:
    """
    Full ingest pipeline:
      1. Parse raw content → structured items + cognitive signals
      2. Embed items into ChromaDB
      3. If extract_signals=True, merge cognitive signals into profile

    Returns summary of what was ingested and what changed in the profile.
    """
    from services.vector_store import embed_reading_history
    from services.profile_service import load_profile, save_profile

    parsed = parse_and_extract(raw_content, format_hint)
    items = parsed.get("items", [])
    signals = parsed.get("cognitive_signals", {})

    # Normalize items to match embed_reading_history schema
    reading_items = [
        {
            "title": item.get("title", ""),
            "publication": item.get("source", ""),
            "url": item.get("url") or "",
            "summary": item.get("summary", ""),
        }
        for item in items
    ]

    embed_reading_history(reading_items)

    profile_changes: dict = {}
    if extract_signals and signals:
        profile = load_profile()
        profile_changes = _merge_signals_into_profile(profile, signals)
        save_profile(profile)

    return {
        "items_parsed": len(items),
        "items_embedded": len(reading_items),
        "profile_changes": profile_changes,
    }


def _merge_signals_into_profile(profile: dict, signals: dict) -> dict:
    """
    Merges cognitive signals into the profile in-place.
    Returns a summary dict of what was added.
    """
    added_models = []
    added_patterns = []
    added_interests = []

    # Mental models
    existing_models = {m["model"] for m in profile.get("mental_models", [])}
    for model in signals.get("mental_models", []):
        name = model.get("model", "")
        if name and name not in existing_models:
            profile.setdefault("mental_models", []).append(model)
            existing_models.add(name)
            added_models.append(name)

    # Third-order patterns
    existing_patterns = {t["pattern"] for t in profile.get("third_order", [])}
    for pattern in signals.get("third_order", []):
        name = pattern.get("pattern", "")
        if name and name not in existing_patterns:
            profile.setdefault("third_order", []).append(pattern)
            existing_patterns.add(name)
            added_patterns.append(name)

    # Interests → topics.interests
    existing_interests = set(profile.get("topics", {}).get("interests", []))
    for interest in signals.get("interests", []):
        if interest and interest not in existing_interests:
            profile.setdefault("topics", {}).setdefault("interests", []).append(interest)
            existing_interests.add(interest)
            added_interests.append(interest)

    return {
        "mental_models_added": added_models,
        "third_order_added": added_patterns,
        "interests_added": added_interests,
    }
