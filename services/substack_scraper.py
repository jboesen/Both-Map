import re
import time

import requests
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; SubstackAutopilot/1.0)"
    )
}


def _slug_from_url(url: str) -> str:
    return url.rstrip("/").split("/")[-1]


def _extract_body_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    # Substack post body lives in .available-content or article
    for selector in (".available-content", "article", ".post-content"):
        node = soup.select_one(selector)
        if node:
            return node.get_text(separator="\n", strip=True)
    return soup.get_text(separator="\n", strip=True)[:5000]


def scrape_user_posts(substack_url: str) -> list[dict]:
    """
    Returns list of {title, content, url} from the user's own Substack.
    Fetches up to 50 posts via the archive API, then fetches each post's body.
    """
    substack_url = substack_url.rstrip("/")
    archive_url = f"{substack_url}/api/v1/archive?sort=new&limit=50"

    resp = requests.get(archive_url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    items = resp.json()

    posts = []
    for item in items:
        title = item.get("title", "")
        slug = item.get("slug", "")
        post_url = item.get("canonical_url") or f"{substack_url}/p/{slug}"

        content = ""
        try:
            post_resp = requests.get(post_url, headers=HEADERS, timeout=20)
            post_resp.raise_for_status()
            content = _extract_body_text(post_resp.text)
        except Exception:
            content = item.get("description", "")

        posts.append({"title": title, "content": content, "url": post_url})
        time.sleep(0.3)  # be polite

    return posts


def scrape_reading_history(session_cookie: str) -> list[dict]:
    """
    Returns list of {title, publication, url, summary} from Substack reading history.
    Requires the connect.sid cookie value from an authenticated Substack session.
    """
    cookies = {"connect.sid": session_cookie}
    history_url = "https://substack.com/api/v1/reader/reading-history"

    resp = requests.get(
        history_url,
        headers=HEADERS,
        cookies=cookies,
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()

    # The API returns a list of post objects under various keys depending on version
    items = data if isinstance(data, list) else data.get("posts", data.get("items", []))

    results = []
    for item in items:
        title = item.get("title", "")
        url = item.get("canonical_url") or item.get("url", "")
        publication = (
            item.get("publication", {}).get("name", "")
            if isinstance(item.get("publication"), dict)
            else item.get("publication_name", "")
        )
        summary = item.get("description") or item.get("subtitle") or ""

        results.append(
            {
                "title": title,
                "publication": publication,
                "url": url,
                "summary": summary,
            }
        )

    return results
