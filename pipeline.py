import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from services.profile_service import load_profile, mark_topic_published
from services.publisher_service import publish_post
from services.research_service import research_and_write
from services.topic_engine import select_topic

LOG_PATH = Path("data/pipeline_log.jsonl")
logger = logging.getLogger(__name__)


def run_pipeline() -> dict:
    """
    Full end-to-end pipeline:
      1. Load cognitive profile
      2. Select best topic
      3. Research and write post
      4. Publish to Substack
      5. Mark topic as published
      6. Log run

    Returns the log entry dict.
    """
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "topic": None,
        "post_url": None,
        "status": "started",
        "error": None,
    }

    try:
        # 1. Load profile
        logger.info("Loading cognitive profile...")
        profile = load_profile()

        # 2. Select topic
        logger.info("Selecting topic...")
        selection = select_topic(profile)
        top = selection["top"]
        if top is None:
            raise RuntimeError("No topic candidates generated")

        topic = top["topic"]
        log_entry["topic"] = topic
        logger.info(f"Selected topic: {topic}")

        # 3. Research and write
        logger.info("Researching and writing post...")
        post = research_and_write(topic, profile)
        title = post["title"]
        body_html = post["body_html"]

        # 4. Publish
        logger.info("Publishing post...")
        post_url = publish_post(title, body_html)
        log_entry["post_url"] = post_url
        logger.info(f"Published: {post_url}")

        # 5. Mark topic published
        mark_topic_published(topic)

        log_entry["status"] = "success"

    except Exception as exc:
        logger.exception("Pipeline failed")
        log_entry["status"] = "error"
        log_entry["error"] = str(exc)

    finally:
        # 6. Log run
        with open(LOG_PATH, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

    return log_entry
