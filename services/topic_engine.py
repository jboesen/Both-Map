import json
import re

import anthropic
import numpy as np

from services.profile_service import load_profile
from services.vector_store import get_coverage_gaps

PROMPTS_DIR_PATH = "prompts"
LAMBDA = 0.6  # MMR tuning: higher = more relevance, lower = more diversity


def _load_prompt(name: str) -> str:
    with open(f"{PROMPTS_DIR_PATH}/{name}") as f:
        return f.read()


def _extract_json(text: str) -> str:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        return match.group(1)
    return text


def generate_candidates(profile: dict, n: int = 20) -> list[dict]:
    """
    Uses Claude to generate n candidate topics based on the cognitive profile.
    Returns list of {topic, rationale, mental_model_fit, third_order_fit}.
    """
    client = anthropic.Anthropic()

    prompt_template = _load_prompt("generate_candidates.txt")
    prompt = (
        prompt_template.replace("{profile}", json.dumps(profile, indent=2))
        .replace("{covered_topics}", json.dumps(profile["topics"].get("covered", [])))
        .replace("{exclusions}", json.dumps(profile["topics"].get("exclusions", [])))
        .replace("{n}", str(n))
    )

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text
    candidates = json.loads(_extract_json(raw))
    return candidates


def rank_candidates(candidates: list[dict], profile: dict, user_id: str = "") -> list[dict]:
    """
    Ranks candidates using MMR (Maximal Marginal Relevance):
      MMR = λ * relevance - (1-λ) * max_similarity_to_already_selected
    Also filters using vector_store coverage gap scores.
    Returns top 5 ranked candidates with scores and rationale.
    """
    if not candidates:
        return []

    client = anthropic.Anthropic()

    # Step 1: Get Claude relevance scores
    prompt_template = _load_prompt("rank_candidates.txt")
    candidates_text = json.dumps(
        [{"topic": c["topic"]} for c in candidates], indent=2
    )
    prompt = prompt_template.replace(
        "{profile}", json.dumps(profile, indent=2)
    ).replace("{candidates}", candidates_text)

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text
    scores = json.loads(_extract_json(raw))
    score_map = {s["topic"]: float(s["relevance_score"]) for s in scores}

    # Step 2: Get novelty scores from vector store
    topic_strings = [c["topic"] for c in candidates]
    gap_results = get_coverage_gaps(user_id, topic_strings)
    gap_map = {g["topic"]: g["distance"] for g in gap_results}

    # Step 3: Build combined relevance (relevance * novelty_boost)
    for c in candidates:
        t = c["topic"]
        relevance = score_map.get(t, 0.5)
        novelty = gap_map.get(t, 0.5)
        # Penalize topics that are too close to already-covered content
        c["relevance_score"] = relevance
        c["novelty_score"] = novelty
        c["combined_score"] = relevance * 0.7 + novelty * 0.3

    # Step 4: MMR selection
    # Use combined_score as the relevance signal
    # For diversity, use simple string-overlap similarity as a proxy
    # (full embedding-based MMR would require embedding all candidates)
    selected: list[dict] = []
    remaining = candidates[:]

    while remaining and len(selected) < 5:
        if not selected:
            # Pick the highest combined_score first
            best = max(remaining, key=lambda c: c["combined_score"])
        else:
            # MMR: score = λ * relevance - (1-λ) * max_sim_to_selected
            best = None
            best_mmr = float("-inf")
            for c in remaining:
                sim_to_selected = max(
                    _topic_similarity(c["topic"], s["topic"]) for s in selected
                )
                mmr = LAMBDA * c["combined_score"] - (1 - LAMBDA) * sim_to_selected
                if mmr > best_mmr:
                    best_mmr = mmr
                    best = c
                    best["mmr_score"] = mmr

        selected.append(best)
        remaining.remove(best)

    return selected


def select_topic(user_id: str, profile: dict) -> dict:
    """
    Generates candidates, ranks them, and returns the top-ranked topic.
    Returns {top: candidate_dict, ranked: [candidate_dict, ...]}
    """
    candidates = generate_candidates(profile, n=20)
    ranked = rank_candidates(candidates, profile, user_id=user_id)
    return {"top": ranked[0] if ranked else None, "ranked": ranked}


def _topic_similarity(a: str, b: str) -> float:
    """
    Simple bigram-overlap similarity as a fast proxy for semantic similarity.
    Returns 0..1.
    """
    def bigrams(text: str) -> set[str]:
        words = re.findall(r"\w+", text.lower())
        return {f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)}

    bg_a = bigrams(a)
    bg_b = bigrams(b)
    if not bg_a or not bg_b:
        return 0.0
    intersection = len(bg_a & bg_b)
    union = len(bg_a | bg_b)
    return intersection / union if union else 0.0
