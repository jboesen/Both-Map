import json
import os
import re
import time
from typing import Optional

from services.llm_client import get_client
from services.profile_service import load_profile
from services.vector_store import get_coverage_gaps

PROMPTS_DIR_PATH = "prompts"

# Simple in-memory cache for topics (TTL: 1 hour)
_topic_cache: dict[str, dict] = {}
_CACHE_TTL = 3600  # 1 hour


def _model() -> str:
    return os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
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
    try:
        client = get_client()

        prompt_template = _load_prompt("generate_candidates.txt")
        prompt = (
            prompt_template.replace("{profile}", json.dumps(profile, indent=2))
            .replace("{covered_topics}", json.dumps(profile["topics"].get("covered", [])))
            .replace("{exclusions}", json.dumps(profile["topics"].get("exclusions", [])))
            .replace("{n}", str(n))
        )

        message = client.create_message(
            model=_model(),
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        # Extract text from response (MiniMax returns thinking + text blocks)
        print(f"[DEBUG] generate_candidates response blocks: {[b.get('type') for b in message.get('content', [])]}")

        raw = None
        text_block = None
        thinking_block = None

        for block in message["content"]:
            if block.get("type") == "text":
                text_block = block["text"]
            elif block.get("type") == "thinking":
                thinking_block = block["thinking"]

        # Prefer text block, fallback to thinking if no text
        raw = text_block or thinking_block

        if not raw:
            print(f"[ERROR] No text OR thinking block found. Full content: {message['content']}")
            raise ValueError(f"No content found in response: {message['content']}")

        if not text_block and thinking_block:
            print(f"[WARNING] No text block, using thinking block as fallback ({len(thinking_block)} chars)")

        print(f"[DEBUG] generate_candidates raw text length: {len(raw)} chars")
        extracted = _extract_json(raw)
        print(f"[DEBUG] generate_candidates extracted JSON length: {len(extracted)} chars")
        print(f"[DEBUG] generate_candidates extracted JSON preview: {extracted[:300]}...")

        candidates = json.loads(extracted)
        print(f"[DEBUG] generate_candidates parsed {len(candidates)} candidates")
        return candidates
    except Exception as e:
        print(f"[ERROR] generate_candidates failed: {type(e).__name__}: {str(e)}")
        print(f"[ERROR] Model: {_model()}")
        if 'raw' in locals() and raw:
            print(f"[ERROR] Raw text (first 500 chars): {raw[:500]}")
        if 'extracted' in locals() and extracted:
            print(f"[ERROR] Extracted text (first 500 chars): {extracted[:500]}")
        raise RuntimeError(f"Failed to generate topic candidates via Claude API: {str(e)}") from e


def rank_candidates(candidates: list[dict], profile: dict, user_id: str = "") -> list[dict]:
    """
    Ranks candidates using MMR (Maximal Marginal Relevance):
      MMR = λ * relevance - (1-λ) * max_similarity_to_already_selected
    Also filters using vector_store coverage gap scores.
    Returns top 5 ranked candidates with scores and rationale.
    """
    if not candidates:
        return []

    try:
        client = get_client()

        # Step 1: Get Claude relevance scores
        prompt_template = _load_prompt("rank_candidates.txt")
        candidates_text = json.dumps(
            [{"topic": c["topic"]} for c in candidates], indent=2
        )
        prompt = prompt_template.replace(
            "{profile}", json.dumps(profile, indent=2)
        ).replace("{candidates}", candidates_text)

        message = client.create_message(
            model=_model(),
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )

        # Extract text from response (MiniMax returns thinking + text blocks)
        print(f"[DEBUG] rank_candidates response blocks: {[b.get('type') for b in message.get('content', [])]}")

        raw = None
        text_block = None
        thinking_block = None

        for block in message["content"]:
            if block.get("type") == "text":
                text_block = block["text"]
            elif block.get("type") == "thinking":
                thinking_block = block["thinking"]

        # Prefer text block, fallback to thinking if no text
        raw = text_block or thinking_block

        if not raw:
            print(f"[ERROR] No text OR thinking block found. Full content: {message['content']}")
            raise ValueError(f"No content found in response: {message['content']}")

        if not text_block and thinking_block:
            print(f"[WARNING] No text block, using thinking block as fallback ({len(thinking_block)} chars)")

        print(f"[DEBUG] rank_candidates raw text length: {len(raw)} chars")
        extracted = _extract_json(raw)
        print(f"[DEBUG] rank_candidates extracted JSON length: {len(extracted)} chars")
        print(f"[DEBUG] rank_candidates extracted JSON preview: {extracted[:300]}...")

        scores = json.loads(extracted)
        print(f"[DEBUG] rank_candidates parsed {len(scores)} scores")
        score_map = {s["topic"]: float(s["relevance_score"]) for s in scores}
    except Exception as e:
        print(f"[ERROR] rank_candidates Claude API call failed: {type(e).__name__}: {str(e)}")
        if 'raw' in locals() and raw:
            print(f"[ERROR] Raw text (first 500 chars): {raw[:500]}")
        if 'extracted' in locals() and extracted:
            print(f"[ERROR] Extracted text (first 500 chars): {extracted[:500]}")
        raise RuntimeError(f"Failed to rank candidates via Claude API: {str(e)}") from e

    try:
        # Step 2: Get novelty scores from vector store
        topic_strings = [c["topic"] for c in candidates]
        gap_results = get_coverage_gaps(user_id, topic_strings)
        gap_map = {g["topic"]: g["distance"] for g in gap_results}
    except Exception as e:
        print(f"[ERROR] get_coverage_gaps failed: {type(e).__name__}: {str(e)}")
        # Continue with default novelty scores if vector store fails
        gap_map = {c["topic"]: 0.5 for c in candidates}

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
    Uses in-memory cache to avoid expensive API calls on every request.
    """
    cache_key = f"topics_{user_id}"

    # Check cache
    if cache_key in _topic_cache:
        cached = _topic_cache[cache_key]
        if time.time() - cached["timestamp"] < _CACHE_TTL:
            print(f"[CACHE HIT] Returning cached topics for {user_id}")
            return cached["data"]
        else:
            print(f"[CACHE EXPIRED] Regenerating topics for {user_id}")

    # Generate fresh topics
    print(f"[CACHE MISS] Generating topics for {user_id}")
    candidates = generate_candidates(profile, n=20)
    ranked = rank_candidates(candidates, profile, user_id=user_id)
    result = {"top": ranked[0] if ranked else None, "ranked": ranked}

    # Cache the result
    _topic_cache[cache_key] = {
        "data": result,
        "timestamp": time.time()
    }

    return result


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
