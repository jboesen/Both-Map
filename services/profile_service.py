import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from services.db_service import load_profile, save_profile
from services.llm_client import get_client


def _model() -> str:
    return os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

PROMPTS_DIR = Path("prompts")


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text()


def _extract_json(text: str) -> str:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        return match.group(1)
    return text


def build_profile_from_history(
    user_id: str,
    user_posts: list[dict],
    reading_history: list[dict],
) -> dict:
    client = get_client()

    posts_text = "\n\n".join(
        f"### {p['title']}\nURL: {p.get('url', '')}\n\n{p.get('content', '')[:3000]}"
        for p in user_posts
    )
    reading_text = "\n\n".join(
        f"- {r['title']} ({r.get('publication', '')})\n  URL: {r.get('url', '')}\n  Summary: {r.get('summary', '')}"
        for r in reading_history
    )

    prompt_template = _load_prompt("build_profile.txt")
    prompt = prompt_template.replace("{user_posts}", posts_text).replace(
        "{reading_history}", reading_text
    )

    message = client.create_message(
        model=_model(),
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message["content"][0]["text"]
    updates = json.loads(_extract_json(raw))

    profile = load_profile(user_id)
    profile["topics"] = updates.get("topics", profile["topics"])
    profile["mental_models"] = updates.get("mental_models", profile["mental_models"])
    profile["third_order"] = updates.get("third_order", profile["third_order"])
    profile["tone_preferences"] = updates.get("tone_preferences", profile["tone_preferences"])

    save_profile(user_id, profile)
    return profile


def update_profile_from_feedback(
    user_id: str,
    transcript: str,
    post_topic: str | None = None,
) -> dict:
    client = get_client()

    profile = load_profile(user_id)
    prompt_template = _load_prompt("update_profile_from_feedback.txt")
    prompt = (
        prompt_template.replace("{current_profile}", json.dumps(profile, indent=2))
        .replace("{transcript}", transcript)
        .replace("{post_topic}", post_topic or "N/A")
    )

    message = client.create_message(
        model=_model(),
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message["content"][0]["text"]
    result = json.loads(_extract_json(raw))

    changes_summary = result.get("changes_summary", "")
    updates = result.get("profile_updates", {})

    for key, value in updates.items():
        if key == "topics" and isinstance(value, dict):
            for subkey, subval in value.items():
                if isinstance(subval, list):
                    existing = profile["topics"].get(subkey, [])
                    profile["topics"][subkey] = list(dict.fromkeys(existing + subval))
                else:
                    profile["topics"][subkey] = subval
        elif key == "mental_models" and isinstance(value, list):
            existing_names = {m["model"] for m in profile.get("mental_models", [])}
            for model in value:
                if model["model"] not in existing_names:
                    profile.setdefault("mental_models", []).append(model)
        elif key == "third_order" and isinstance(value, list):
            existing_names = {t["pattern"] for t in profile.get("third_order", [])}
            for pattern in value:
                if pattern["pattern"] not in existing_names:
                    profile.setdefault("third_order", []).append(pattern)
        elif key == "tone_preferences" and isinstance(value, dict):
            profile["tone_preferences"].update(value)
        else:
            profile[key] = value

    profile.setdefault("feedback_history", []).append(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "post_topic": post_topic,
            "transcript": transcript,
            "changes_summary": changes_summary,
        }
    )

    save_profile(user_id, profile)
    return profile


def enrich_profile_from_perplexity(user_id: str, perplexity_synthesis: str) -> dict:
    client = get_client()

    profile = load_profile(user_id)
    prompt_template = _load_prompt("extract_mental_models_from_research.txt")
    prompt = prompt_template.replace("{research}", perplexity_synthesis).replace(
        "{existing_profile}", json.dumps(profile, indent=2)
    )

    message = client.create_message(
        model=_model(),
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message["content"][0]["text"]
    extracted = json.loads(_extract_json(raw))

    existing_models = {m["model"] for m in profile.get("mental_models", [])}
    for model in extracted.get("mental_models", []):
        if model.get("model") and model["model"] not in existing_models:
            profile.setdefault("mental_models", []).append(model)
            existing_models.add(model["model"])

    existing_patterns = {t["pattern"] for t in profile.get("third_order", [])}
    for pattern in extracted.get("third_order", []):
        if pattern.get("pattern") and pattern["pattern"] not in existing_patterns:
            profile.setdefault("third_order", []).append(pattern)
            existing_patterns.add(pattern["pattern"])

    tone_inf = extracted.get("tone_inferences", {})
    tone_prefs = profile.setdefault("tone_preferences", {})
    for field in ("style", "depth", "avoid"):
        if tone_inf.get(field) and not tone_prefs.get(field):
            tone_prefs[field] = tone_inf[field]

    save_profile(user_id, profile)
    return profile


def mark_topic_published(user_id: str, topic: str) -> None:
    profile = load_profile(user_id)
    covered = profile["topics"].get("covered", [])
    if topic not in covered:
        covered.append(topic)
    profile["topics"]["covered"] = covered
    save_profile(user_id, profile)


def mark_topic_rejected(user_id: str, topic: str) -> None:
    profile = load_profile(user_id)
    exclusions = profile["topics"].get("exclusions", [])
    if topic not in exclusions:
        exclusions.append(topic)
    profile["topics"]["exclusions"] = exclusions
    save_profile(user_id, profile)


def merge_profile_update(existing: dict, partial: dict) -> dict:
    for key, value in partial.items():
        if key in ("topics", "tone_preferences") and isinstance(value, dict):
            existing.setdefault(key, {}).update(value)
        elif key == "feedback_history":
            pass
        else:
            existing[key] = value
    return existing
