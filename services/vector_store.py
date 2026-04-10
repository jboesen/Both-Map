from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

CHROMA_PATH = str(Path("data/chroma"))
CHUNK_SIZE = 1000


def _get_collection(user_id: str) -> chromadb.Collection:
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    ef = embedding_functions.DefaultEmbeddingFunction()
    # One collection per user, named by first 16 chars of their UUID
    collection_name = f"user_{user_id.replace('-', '')[:16]}"
    return client.get_or_create_collection(
        name=collection_name,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE) -> list[str]:
    chunks = []
    for i in range(0, len(text), chunk_size - 100):
        chunks.append(text[i : i + chunk_size])
        if i + chunk_size >= len(text):
            break
    return chunks or [text]


def embed_posts(user_id: str, posts: list[dict]) -> None:
    collection = _get_collection(user_id)
    documents, metadatas, ids = [], [], []

    for post in posts:
        title = post.get("title", "")
        content = post.get("content", "")
        url = post.get("url", "")
        for idx, chunk in enumerate(_chunk_text(f"{title}\n\n{content}")):
            documents.append(chunk)
            metadatas.append({"type": "written", "title": title, "url": url})
            ids.append(f"post_{_safe_id(url)}_{idx}")

    if documents:
        collection.upsert(documents=documents, metadatas=metadatas, ids=ids)


def embed_reading_history(user_id: str, items: list[dict]) -> None:
    collection = _get_collection(user_id)
    documents, metadatas, ids = [], [], []

    for item in items:
        title = item.get("title", "")
        publication = item.get("publication", "")
        url = item.get("url", "")
        summary = item.get("summary", "")
        text = f"{title} — {publication}\n\n{summary}"
        documents.append(text)
        metadatas.append({"type": "read", "title": title, "publication": publication, "url": url})
        ids.append(f"read_{_safe_id(url)}")

    if documents:
        collection.upsert(documents=documents, metadatas=metadatas, ids=ids)


def get_coverage_gaps(user_id: str, candidate_topics: list[str]) -> list[dict]:
    collection = _get_collection(user_id)

    if collection.count() == 0:
        return [{"topic": t, "distance": 1.0, "is_gap": True} for t in candidate_topics]

    results = []
    for topic in candidate_topics:
        query_result = collection.query(
            query_texts=[topic], n_results=1, include=["distances"]
        )
        distances = query_result.get("distances", [[]])[0]
        distance = distances[0] if distances else 1.0
        results.append({"topic": topic, "distance": distance, "is_gap": distance > 0.4})

    results.sort(key=lambda x: x["distance"], reverse=True)
    return results


def _safe_id(url: str) -> str:
    return (
        url.replace("https://", "")
        .replace("http://", "")
        .replace("/", "_")
        .replace(".", "_")[:80]
    )
