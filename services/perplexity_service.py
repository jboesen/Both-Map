"""
Uses the Perplexity Sonar API to deeply research a person based on provided
public/demographic info, then returns a synthesis of their intellectual background,
published work, and stated interests.

The raw output is ONLY used for mental model extraction — it is never passed
directly to the article generation pipeline.
"""

import os

import httpx

PERPLEXITY_BASE = "https://api.perplexity.ai"
# sonar-pro has real-time web search + higher context
PERPLEXITY_MODEL = "sonar-pro"


def _build_research_query(user_info: dict) -> str:
    """
    Build a focused research prompt from whatever user_info fields are provided.
    Accepted keys (all optional, provide what's available):
      name, title, company, twitter, linkedin, substack_url, location,
      academic_background, other_urls (list of str)
    """
    parts = []

    if user_info.get("name"):
        parts.append(f"Person: {user_info['name']}")
    if user_info.get("title") and user_info.get("company"):
        parts.append(f"Role: {user_info['title']} at {user_info['company']}")
    elif user_info.get("title"):
        parts.append(f"Title: {user_info['title']}")
    if user_info.get("twitter"):
        parts.append(f"Twitter/X: {user_info['twitter']}")
    if user_info.get("linkedin"):
        parts.append(f"LinkedIn: {user_info['linkedin']}")
    if user_info.get("substack_url"):
        parts.append(f"Substack: {user_info['substack_url']}")
    if user_info.get("academic_background"):
        parts.append(f"Academic background: {user_info['academic_background']}")
    if user_info.get("other_urls"):
        parts.append("Other URLs: " + ", ".join(user_info["other_urls"]))

    identity_block = "\n".join(parts) if parts else "No identifying information provided."

    return f"""Research this person as thoroughly as possible using all available public sources.

{identity_block}

I need to deeply understand how this person thinks — their intellectual frameworks, the domains they draw from, the kinds of arguments they make, what topics they are drawn to and why, and what types of insights they find most compelling.

Please find and synthesize:
1. Their published writing (essays, papers, blog posts, threads) — what ideas do they return to? What mental models appear repeatedly?
2. Their public intellectual influences — who do they cite, engage with, push back against?
3. Their academic or professional training — what disciplines shaped how they reason?
4. Any interviews, podcasts, or talks — how do they describe their own thinking?
5. The types of questions they ask publicly — what puzzles them? What do they find underexplored?

Focus on COGNITIVE STYLE and INTELLECTUAL HABITS, not biography. I don't need their resume — I need to understand the shape of their mind: how they structure arguments, what abstraction level they prefer, what kinds of cross-domain connections they make, what they find surprising or compelling.

Synthesize your findings into 4-6 paragraphs focused entirely on intellectual style and recurring mental frameworks."""


def research_user(user_info: dict) -> str:
    """
    Calls Perplexity Sonar to research a person from their public presence.
    Returns the raw synthesis text.

    Raises if PERPLEXITY_API_KEY is not set.
    """
    api_key = os.environ.get("PERPLEXITY_API_KEY")
    if not api_key:
        raise EnvironmentError("PERPLEXITY_API_KEY is not set")

    query = _build_research_query(user_info)

    payload = {
        "model": PERPLEXITY_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a research assistant specializing in intellectual profiling. "
                    "You synthesize public information about a person's cognitive style, "
                    "mental models, and intellectual habits. You are thorough and specific. "
                    "You do not speculate — you only report what the sources show."
                ),
            },
            {"role": "user", "content": query},
        ],
        "search_recency_filter": "month",  # prioritize recent content
        "return_citations": True,
    }

    with httpx.Client(timeout=60) as client:
        response = client.post(
            f"{PERPLEXITY_BASE}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()

    data = response.json()
    content = data["choices"][0]["message"]["content"]
    citations = data.get("citations", [])

    # Append citations to the synthesis so Claude can reference them
    if citations:
        content += "\n\nSources consulted:\n" + "\n".join(
            f"- {c}" for c in citations
        )

    return content
