from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

CHROMA_PATH = str(Path("data/chroma"))
COLLECTION_NAME = "user_content"
CHUNK_SIZE = 1000  # characters per chunk


def _get_collection() -> chromadb.Collection:
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    ef = embedding_functions.DefaultEmbeddingFunction()
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE) -> list[str]:
    """Split text into overlapping chunks."""
    chunks = []
    for i in range(0, len(text), chunk_size - 100):
        chunks.append(text[i : i + chunk_size])
        if i + chunk_size >= len(text):
            break
    return chunks or [text]


def embed_posts(posts: list[dict]) -> None:
    """
    Embeds user's own posts into ChromaDB.
    posts: list of {title, content, url}
    """
    collection = _get_collection()
    documents = []
    metadatas = []
    ids = []

    for post in posts:
        title = post.get("title", "")
        content = post.get("content", "")
        url = post.get("url", "")
        chunks = _chunk_text(f"{title}\n\n{content}")

        for idx, chunk in enumerate(chunks):
            doc_id = f"post_{_safe_id(url)}_{idx}"
            documents.append(chunk)
            metadatas.append({"type": "written", "title": title, "url": url})
            ids.append(doc_id)

    if documents:
        collection.upsert(documents=documents, metadatas=metadatas, ids=ids)


def embed_reading_history(items: list[dict]) -> None:
    """
    Embeds reading history into ChromaDB.
    items: list of {title, publication, url, summary}
    """
    collection = _get_collection()
    documents = []
    metadatas = []
    ids = []

    for item in items:
        title = item.get("title", "")
        publication = item.get("publication", "")
        url = item.get("url", "")
        summary = item.get("summary", "")
        text = f"{title} — {publication}\n\n{summary}"

        doc_id = f"read_{_safe_id(url)}"
        documents.append(text)
        metadatas.append(
            {"type": "read", "title": title, "publication": publication, "url": url}
        )
        ids.append(doc_id)

    if documents:
        collection.upsert(documents=documents, metadatas=metadatas, ids=ids)


def get_coverage_gaps(candidate_topics: list[str]) -> list[dict]:
    """
    For each candidate topic string, compute cosine distance to nearest neighbor.
    Returns candidates sorted by distance descending (most novel first).
    Candidates with distance > 0.4 are considered genuine gaps.
    """
    collection = _get_collection()

    # Need at least one document in the collection to query
    if collection.count() == 0:
        return [
            {"topic": t, "distance": 1.0, "is_gap": True} for t in candidate_topics
        ]

    results = []
    for topic in candidate_topics:
        query_result = collection.query(
            query_texts=[topic],
            n_results=1,
            include=["distances"],
        )
        distances = query_result.get("distances", [[]])[0]
        distance = distances[0] if distances else 1.0
        results.append(
            {
                "topic": topic,
                "distance": distance,
                "is_gap": distance > 0.4,
            }
        )

    results.sort(key=lambda x: x["distance"], reverse=True)
    return results


def _safe_id(url: str) -> str:
    """Convert URL to a safe ChromaDB document ID."""
    return (
        url.replace("https://", "")
        .replace("http://", "")
        .replace("/", "_")
        .replace(".", "_")[:80]
    )
