import logging
import os
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

load_dotenv()

from pipeline import run_pipeline
from services.profile_service import (
    load_profile,
    mark_topic_rejected,
    merge_profile_update,
    save_profile,
    update_profile_from_feedback,
)
from services.research_service import research_and_write
from services.publisher_service import publish_post
from services.substack_scraper import scrape_reading_history, scrape_user_posts
from services.topic_engine import select_topic
from services.vector_store import embed_posts, embed_reading_history

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Cron scheduler ────────────────────────────────────────────────────────────

scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    hours = int(os.getenv("CRON_SCHEDULE_HOURS", "24"))
    scheduler.add_job(run_pipeline, "interval", hours=hours, id="autopilot")
    scheduler.start()
    logger.info(f"Cron scheduler started (every {hours}h)")
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="Substack Autopilot", lifespan=lifespan)


# ── Request / Response models ─────────────────────────────────────────────────


class OnboardRequest(BaseModel):
    substack_url: str
    session_cookie: str


class FeedbackRequest(BaseModel):
    transcript: str
    post_topic: str | None = None


class GenerateRequest(BaseModel):
    topic: str


class PublishRequest(BaseModel):
    title: str
    body_html: str


# ── Endpoints ─────────────────────────────────────────────────────────────────


@app.post("/onboard")
def onboard(req: OnboardRequest):
    """
    Scrapes user posts + reading history, builds cognitive profile,
    and embeds everything into ChromaDB.
    """
    from services.profile_service import build_profile_from_history

    user_posts = scrape_user_posts(req.substack_url)
    reading_history = scrape_reading_history(req.session_cookie)

    profile = build_profile_from_history(user_posts, reading_history)

    embed_posts(user_posts)
    embed_reading_history(reading_history)

    return {"profile": profile}


@app.get("/profile")
def get_profile():
    return load_profile()


@app.put("/profile")
def put_profile(partial: dict):
    """Merge a partial profile update and save."""
    existing = load_profile()
    updated = merge_profile_update(existing, partial)
    save_profile(updated)
    return updated


@app.post("/feedback")
def feedback(req: FeedbackRequest):
    updated_profile = update_profile_from_feedback(req.transcript, req.post_topic)
    # Return the changes_summary from the last feedback_history entry
    changes = ""
    if updated_profile.get("feedback_history"):
        changes = updated_profile["feedback_history"][-1].get("changes_summary", "")
    return {"changes": changes, "updated_profile": updated_profile}


@app.get("/topics")
def topics(refresh: bool = False):
    """
    Returns top 5 ranked topic candidates.
    Pass ?refresh=true to regenerate (otherwise returns cached if available).
    """
    profile = load_profile()
    selection = select_topic(profile)
    return {"candidates": selection["ranked"], "top": selection["top"]}


@app.post("/generate")
def generate(req: GenerateRequest):
    profile = load_profile()
    result = research_and_write(req.topic, profile)
    return result


@app.post("/publish")
def publish(req: PublishRequest):
    try:
        url = publish_post(req.title, req.body_html)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"url": url}


@app.post("/run")
def run():
    """Manually trigger the full pipeline (same as cron job)."""
    log_entry = run_pipeline()
    if log_entry["status"] == "error":
        raise HTTPException(status_code=500, detail=log_entry.get("error"))
    return log_entry
