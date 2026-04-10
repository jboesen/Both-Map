import os
from functools import lru_cache

from supabase import Client


@lru_cache(maxsize=1)
def _get_client() -> Client:
    from services.db_service import get_client
    return get_client()


def _safe_id(url: str) -> str:
    return (
        url.replace("https://", "")
        .replace("http://", "")
        .replace("/", "_")
        .replace(".", "_")[:80]
    )


def embed_posts(user_id: str, posts: list[dict]) -> None:
    rows = []
    for post in posts:
        title = post.get("title", "")
        content = post.get("content", "")
        url = post.get("url", "")
        doc_id = f"post_{_safe_id(url)}"
        rows.append({
            "id": doc_id,
            "content": f"{title}\n\n{content}"[:2000],
            "metadata": {"type": "written", "title": title, "url": url},
        })
    if rows:
        _get_client().table("content_embeddings").upsert(rows).execute()


def embed_reading_history(user_id: str, items: list[dict]) -> None:
    rows = []
    for item in items:
        title = item.get("title", "")
        publication = item.get("publication", "")
        url = item.get("url", "")
        summary = item.get("summary", "")
        rows.append({
            "id": f"read_{_safe_id(url)}",
            "content": f"{title} — {publication}\n\n{summary}",
            "metadata": {"type": "read", "title": title, "publication": publication, "url": url},
        })
    if rows:
        _get_client().table("content_embeddings").upsert(rows).execute()


def get_coverage_gaps(user_id: str, candidate_topics: list[str]) -> list[dict]:
    # Stub: treat every candidate as a gap until real embeddings are added
    return [{"topic": t, "distance": 1.0, "is_gap": True} for t in candidate_topics]
