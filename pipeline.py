import logging
import os

from services.db_service import (
    get_user_settings,
    list_onboarded_users,
    load_profile,
    log_run,
)
from services.profile_service import mark_topic_published
from services.publisher_service import publish_post
from services.research_service import research_and_write
from services.topic_engine import select_topic

logger = logging.getLogger(__name__)


def run_pipeline(user_id: str) -> dict:
    """
    Full end-to-end pipeline for a single user:
      1. Load cognitive profile
      2. Select best topic
      3. Research and write post
      4. Generate audio overview (if ELEVENLABS_API_KEY set)
      5. Publish to Substack
      6. Mark topic published
      7. Log run to Supabase

    Returns the log entry dict.
    """
    run = {
        "topic": None,
        "post_url": None,
        "audio_url": None,
        "status": "started",
        "error": None,
    }

    try:
        # 1. Load profile
        profile = load_profile(user_id)

        # 2. Select topic
        selection = select_topic(user_id, profile)
        top = selection["top"]
        if top is None:
            raise RuntimeError("No topic candidates generated")

        topic = top["topic"]
        run["topic"] = topic
        logger.info(f"[{user_id[:8]}] Selected topic: {topic}")

        # 3. Research and write
        logger.info(f"[{user_id[:8]}] Researching and writing...")
        post = research_and_write(topic, profile)
        title = post["title"]
        body_html = post["body_html"]

        # 4. Audio overview (optional)
        if os.environ.get("ELEVENLABS_API_KEY"):
            try:
                from services.audio_service import generate_audio_overview
                audio = generate_audio_overview(user_id, title, body_html)
                run["audio_url"] = audio["public_url"]
                logger.info(f"[{user_id[:8]}] Audio uploaded: {audio['public_url']}")
                if audio.get("embed_html"):
                    body_html = audio["embed_html"] + "\n" + body_html
            except Exception:
                logger.exception(f"[{user_id[:8]}] Audio generation failed — publishing without audio")

        # 5. Publish — pull Substack creds from user's profile row
        settings = get_user_settings(user_id)
        post_url = publish_post(
            title=title,
            body_html=body_html,
            substack_url=settings["substack_url"],
            email=settings["substack_email"],
            password=settings["substack_password"],
        )
        run["post_url"] = post_url
        logger.info(f"[{user_id[:8]}] Published: {post_url}")

        # 6. Mark topic published
        mark_topic_published(user_id, topic)

        run["status"] = "success"

    except Exception as exc:
        logger.exception(f"[{user_id[:8]}] Pipeline failed")
        run["status"] = "error"
        run["error"] = str(exc)

    finally:
        log_run(user_id, run)

    return run


def run_pipeline_all_users() -> list[dict]:
    """Cron entry point — runs the pipeline for every onboarded user."""
    user_ids = list_onboarded_users()
    logger.info(f"Cron: running pipeline for {len(user_ids)} user(s)")
    return [run_pipeline(uid) for uid in user_ids]
