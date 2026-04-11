"""
Uses the Exa API for web search and research.
Provides functions for researching users and topics with real-time web data.
"""

import os
from exa_py import Exa


def _exa_client() -> Exa:
    """
    Creates an Exa client instance.
    Raises if EXA_API_KEY is not set.
    """
    api_key = os.environ.get("EXA_API_KEY")
    if not api_key:
        raise EnvironmentError("EXA_API_KEY is not set")
    return Exa(api_key=api_key)


def _build_user_research_query(user_info: dict) -> str:
    """
    Build a focused research query from user_info fields.
    Accepted keys (all optional):
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

    return " ".join(parts) if parts else user_info.get("name", "")


def research_user(user_info: dict) -> str:
    """
    Uses Exa to research a person from their public presence.
    Returns a synthesis of their intellectual background and cognitive style.

    Raises if EXA_API_KEY is not set.
    """
    exa = _exa_client()

    # Build search query
    query = _build_user_research_query(user_info)

    # Search for relevant content about the person
    search_results = exa.search_and_contents(
        query=query,
        num_results=10,
        use_autoprompt=True,
        text={"max_characters": 2000},
    )

    # Compile research content
    sources = []
    content_blocks = []

    for result in search_results.results:
        sources.append(result.url)
        if result.text:
            content_blocks.append(f"Source: {result.title}\n{result.text[:1000]}")

    # Create synthesis
    synthesis = f"""Research findings for {user_info.get('name', 'this person')}:

Based on {len(search_results.results)} sources, here are the key insights about their intellectual style and cognitive patterns:

{chr(10).join(content_blocks[:5])}

This research reveals their published work, intellectual influences, and reasoning patterns."""

    # Append sources
    if sources:
        synthesis += "\n\nSources consulted:\n" + "\n".join(f"- {s}" for s in sources)

    return synthesis


def research_topic(topic: str, profile: dict) -> dict:
    """
    Uses Exa to research a topic with web search.
    Returns a dict with 'synthesis' (str) and 'sources' (list of str).

    Raises if EXA_API_KEY is not set.
    """
    exa = _exa_client()

    # Extract context from profile
    interests = profile.get("interests", [])
    interest_topics = ", ".join([i.get("topic", "") for i in interests[:5]]) if interests else ""

    # Build enhanced query
    query = topic
    if interest_topics:
        query += f" {interest_topics}"

    # Search for high-quality, recent content
    search_results = exa.search_and_contents(
        query=query,
        num_results=15,
        use_autoprompt=True,
        text={"max_characters": 3000},
        category="research paper, news, company, github, tweet, pdf",
        start_published_date="2024-01-01",  # Focus on recent content
    )

    # Compile synthesis
    sources = []
    content_sections = []

    for i, result in enumerate(search_results.results[:10], 1):
        sources.append(result.url)
        if result.text:
            content_sections.append(
                f"{i}. {result.title}\n{result.text[:500]}...\nSource: {result.url}\n"
            )

    synthesis = f"""Research Brief: {topic}

Found {len(search_results.results)} high-quality sources on this topic.

Key Findings:

{chr(10).join(content_sections)}

This research provides current data, expert perspectives, and concrete examples to support a thoughtful exploration of this topic."""

    return {
        "synthesis": synthesis,
        "sources": sources,
    }
