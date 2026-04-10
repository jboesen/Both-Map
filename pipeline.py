import json
import logging
import os
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
      4. Generate audio overview (if ELEVENLABS_API_KEY is set)
         — if AUDIO_PUBLIC_BASE_URL is set, embeds <audio> player in post
      5. Publish to Substack
      6. Mark topic as published
      7. Log run

    Returns the log entry dict.
    """
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "topic": None,
        "post_url": None,
        "audio_path": None,
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

        # 4. Audio overview (optional)
        if os.environ.get("ELEVENLABS_API_KEY"):
            try:
                logger.info("Generating audio overview...")
                from services.audio_service import generate_audio_overview
                audio = generate_audio_overview(title, body_html)
                log_entry["audio_path"] = audio["audio_path"]
                logger.info(f"Audio saved: {audio['audio_path']}")

                # If we have a public URL, prepend the player to the post body
                if audio.get("embed_html"):
                    body_html = audio["embed_html"] + "\n" + body_html
                    logger.info("Audio player embedded in post body")
            except Exception:
                logger.exception("Audio generation failed — publishing without audio")

        # 5. Publish
        logger.info("Publishing post...")
        post_url = publish_post(title, body_html)
        log_entry["post_url"] = post_url
        logger.info(f"Published: {post_url}")

        # 6. Mark topic published
        mark_topic_published(topic)

        log_entry["status"] = "success"

    except Exception as exc:
        logger.exception("Pipeline failed")
        log_entry["status"] = "error"
        log_entry["error"] = str(exc)

    finally:
        # 7. Log run
        with open(LOG_PATH, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

    return log_entry
