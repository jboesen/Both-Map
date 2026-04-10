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
    build_profile_from_history,
    enrich_profile_from_perplexity,
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


class UserInfo(BaseModel):
    """
    Optional public/demographic info used to research the user via Perplexity
    and extract cognitive signals for the profile.
    All fields are optional — provide whatever is available.
    """
    name: str | None = None
    title: str | None = None
    company: str | None = None
    twitter: str | None = None
    linkedin: str | None = None
    academic_background: str | None = None
    other_urls: list[str] | None = None


class OnboardRequest(BaseModel):
    substack_url: str
    session_cookie: str
    # Optional: if provided, Perplexity will research the user and enrich the
    # cognitive profile with inferred mental models. Raw research is never
    # passed to the article generator.
    user_info: UserInfo | None = None


class FeedbackRequest(BaseModel):
    transcript: str
    post_topic: str | None = None


class IngestRequest(BaseModel):
    content: str
    # Optional format hint. Supported values:
    #   "claude"   — Claude.ai conversation history (JSON or copy-pasted text)
    #   "pocket"   — Pocket CSV export
    #   "kindle"   — Kindle highlights CSV or My Clippings text
    #   "browser"  — Browser bookmarks HTML (Chrome / Firefox / Safari)
    #   "youtube"  — Google Takeout watch-history.json
    #   "opml"     — OPML RSS/podcast subscription list
    #   "twitter"  — Twitter/X bookmarks JSON or copy-pasted threads
    #   "raw"      — Freeform text: URLs, titles, notes — anything
    # Omit (null) to let Claude auto-detect.
    format: str | None = None
    # Set False to skip cognitive signal extraction and only embed items.
    extract_signals: bool = True


class GenerateRequest(BaseModel):
    topic: str


class PublishRequest(BaseModel):
    title: str
    body_html: str


# ── Endpoints ─────────────────────────────────────────────────────────────────


@app.post("/onboard")
def onboard(req: OnboardRequest):
    """
    Full onboarding flow:
      1. Scrape user posts + reading history
      2. Build cognitive profile from writing/reading (Claude)
      3. Embed everything into ChromaDB
      4. If user_info provided: Perplexity researches the user publicly,
         Claude extracts cognitive signals, merges into profile.
         Raw research is discarded — only extracted mental models are kept.
    """
    user_posts = scrape_user_posts(req.substack_url)
    reading_history = scrape_reading_history(req.session_cookie)

    profile = build_profile_from_history(user_posts, reading_history)

    embed_posts(user_posts)
    embed_reading_history(reading_history)

    perplexity_ran = False
    if req.user_info:
        try:
            from services.perplexity_service import research_user
            user_info_dict = req.user_info.model_dump(exclude_none=True)
            # Add substack_url so Perplexity can find their writing
            user_info_dict.setdefault("substack_url", req.substack_url)
            synthesis = research_user(user_info_dict)
            profile = enrich_profile_from_perplexity(synthesis)
            perplexity_ran = True
        except EnvironmentError:
            logger.warning("PERPLEXITY_API_KEY not set — skipping user research enrichment")
        except Exception:
            logger.exception("Perplexity enrichment failed — profile still saved from writing analysis")

    return {"profile": profile, "perplexity_enrichment_ran": perplexity_ran}


@app.post("/enrich-profile")
def enrich_profile(user_info: UserInfo):
    """
    Standalone endpoint: research the user via Perplexity and enrich the
    cognitive profile with inferred mental models.
    Can be called independently after initial onboarding.
    Raw research is never stored — only extracted cognitive signals are merged.
    """
    from services.perplexity_service import research_user

    user_info_dict = user_info.model_dump(exclude_none=True)
    synthesis = research_user(user_info_dict)
    profile = enrich_profile_from_perplexity(synthesis)
    return {"profile": profile}


@app.post("/ingest")
def ingest_history(req: IngestRequest):
    """
    Ingest any consumption history — Claude conversations, Pocket exports,
    Kindle highlights, browser bookmarks, YouTube history, OPML files,
    or plain text — and use it to enrich the cognitive profile.

    Claude parses the raw content into structured items (embedded into
    ChromaDB for topic gap detection) and extracts cognitive signals
    (mental models, third-order patterns, interests) from the consumption
    pattern, which are merged into cognitive_profile.json.

    Raw content is never stored.
    """
    from services.history_ingest_service import ingest

    result = ingest(
        raw_content=req.content,
        format_hint=req.format,
        extract_signals=req.extract_signals,
    )
    return result


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
