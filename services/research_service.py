import json
import os
import re
from pathlib import Path

import anthropic

PROMPTS_DIR = Path("prompts")


def _anthropic_client() -> anthropic.Anthropic:
    kwargs = {}
    base_url = os.environ.get("ANTHROPIC_BASE_URL")
    if base_url:
        kwargs["base_url"] = base_url
    return anthropic.Anthropic(**kwargs)


def _model() -> str:
    return os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text()


def _extract_json(text: str) -> str:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        return match.group(1)
    return text


def research_and_write(topic: str, profile: dict) -> dict:
    """
    Two-step pipeline:
      1. Claude with web_search tool researches the topic
      2. Claude writes the post using the research + cognitive profile

    Returns {title, body_html, topic, sources}
    """
    client = _anthropic_client()

    # ── Step 1: Research ──────────────────────────────────────────────────────
    research_prompt_template = _load_prompt("research_topic.txt")
    research_prompt = research_prompt_template.replace("{topic}", topic).replace(
        "{profile}", json.dumps(profile, indent=2)
    )

    web_search_tool = {
        "type": "web_search_20250305",
        "name": "web_search",
    }

    research_message = client.messages.create(
        model=_model(),
        max_tokens=4096,
        tools=[web_search_tool],
        messages=[{"role": "user", "content": research_prompt}],
    )

    # Extract text from the final response (after tool use rounds)
    research_text = _extract_final_text(research_message)
    research_data = json.loads(_extract_json(research_text))

    sources = research_data.get("sources", [])
    synthesis = research_data.get("synthesis", "")

    # ── Step 2: Write ─────────────────────────────────────────────────────────
    tone = profile.get("tone_preferences", {})
    mental_models = ", ".join(
        m["model"] for m in profile.get("mental_models", [])
    )
    third_order = ", ".join(
        t["pattern"] for t in profile.get("third_order", [])
    )

    write_prompt_template = _load_prompt("research_and_write.txt")
    write_prompt = (
        write_prompt_template.replace("{topic}", topic)
        .replace("{profile}", json.dumps(profile, indent=2))
        .replace("{research}", synthesis)
        .replace("{style}", tone.get("style", ""))
        .replace("{depth}", tone.get("depth", ""))
        .replace("{avoid}", tone.get("avoid", ""))
        .replace("{mental_models}", mental_models)
        .replace("{third_order}", third_order)
    )

    write_message = client.messages.create(
        model=_model(),
        max_tokens=6000,
        messages=[{"role": "user", "content": write_prompt}],
    )

    write_text = write_message.content[0].text
    post_data = json.loads(_extract_json(write_text))

    return {
        "title": post_data["title"],
        "body_html": post_data["body_html"],
        "topic": topic,
        "sources": sources,
    }


def _extract_final_text(message: anthropic.types.Message) -> str:
    """
    Extract the final text content from a message that may have gone through
    tool use rounds. Returns the last text block.
    """
    text_blocks = [
        block.text
        for block in message.content
        if hasattr(block, "text")
    ]
    return text_blocks[-1] if text_blocks else ""
