import logging
import os
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

load_dotenv()

from pipeline import run_pipeline, run_pipeline_all_users
from services.db_service import (
    get_client,
    get_run_history,
    get_user_settings,
    load_profile,
    save_profile,
    update_user_settings,
)
from services.history_ingest_service import ingest
from services.profile_service import (
    build_profile_from_history,
    enrich_profile_from_perplexity,
    merge_profile_update,
    update_profile_from_feedback,
)
from services.research_service import research_and_write
from services.publisher_service import publish_post
from services.substack_scraper import scrape_reading_history, scrape_user_posts
from services.topic_engine import select_topic
from services.vector_store import embed_posts, embed_reading_history

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Auth ──────────────────────────────────────────────────────────────────────

_bearer = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
) -> str:
    """
    Verifies the Supabase JWT and returns the user_id.
    The frontend passes the token from supabase.auth.getSession().
    """
    token = credentials.credentials
    try:
        result = get_client().auth.get_user(token)
        return result.user.id
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ── Cron scheduler ────────────────────────────────────────────────────────────

scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    hours = int(os.getenv("CRON_SCHEDULE_HOURS", "24"))
    scheduler.add_job(run_pipeline_all_users, "interval", hours=hours, id="autopilot")
    scheduler.start()
    logger.info(f"Cron scheduler started (every {hours}h, all users)")
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="Substack Autopilot", lifespan=lifespan)

# ── Request models ────────────────────────────────────────────────────────────


class UserInfo(BaseModel):
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
    substack_email: str | None = None
    substack_password: str | None = None
    user_info: UserInfo | None = None


class FeedbackRequest(BaseModel):
    transcript: str
    post_topic: str | None = None


class IngestRequest(BaseModel):
    content: str
    format: str | None = None
    extract_signals: bool = True


class GenerateRequest(BaseModel):
    topic: str


class AudioRequest(BaseModel):
    title: str
    body_html: str


class PublishRequest(BaseModel):
    title: str
    body_html: str


# ── Endpoints ─────────────────────────────────────────────────────────────────


@app.post("/onboard")
def onboard(req: OnboardRequest, user_id: str = Depends(get_current_user)):
    """
    Full onboarding: scrape posts + reading history, build cognitive profile,
    embed into vector store, optionally enrich via Perplexity.
    Saves Substack credentials to the user's profile row.
    """
    # Save Substack settings
    update_user_settings(
        user_id,
        substack_url=req.substack_url,
        substack_email=req.substack_email,
        substack_password=req.substack_password,
    )

    user_posts = scrape_user_posts(req.substack_url)
    reading_history = scrape_reading_history(req.session_cookie)

    profile = build_profile_from_history(user_id, user_posts, reading_history)
    embed_posts(user_id, user_posts)
    embed_reading_history(user_id, reading_history)

    perplexity_ran = False
    if req.user_info:
        try:
            from services.perplexity_service import research_user
            user_info_dict = req.user_info.model_dump(exclude_none=True)
            user_info_dict.setdefault("substack_url", req.substack_url)
            synthesis = research_user(user_info_dict)
            profile = enrich_profile_from_perplexity(user_id, synthesis)
            perplexity_ran = True
        except EnvironmentError:
            logger.warning("PERPLEXITY_API_KEY not set — skipping enrichment")
        except Exception:
            logger.exception("Perplexity enrichment failed")

    update_user_settings(user_id, onboarded=True)
    return {"profile": profile, "perplexity_enrichment_ran": perplexity_ran}


@app.post("/enrich-profile")
def enrich_profile(user_info: UserInfo, user_id: str = Depends(get_current_user)):
    from services.perplexity_service import research_user
    user_info_dict = user_info.model_dump(exclude_none=True)
    synthesis = research_user(user_info_dict)
    profile = enrich_profile_from_perplexity(user_id, synthesis)
    return {"profile": profile}


@app.post("/ingest")
def ingest_history(req: IngestRequest, user_id: str = Depends(get_current_user)):
    result = ingest(
        user_id=user_id,
        raw_content=req.content,
        format_hint=req.format,
        extract_signals=req.extract_signals,
    )
    return result


@app.post("/feedback")
def feedback(req: FeedbackRequest, user_id: str = Depends(get_current_user)):
    updated = update_profile_from_feedback(user_id, req.transcript, req.post_topic)
    changes = ""
    if updated.get("feedback_history"):
        changes = updated["feedback_history"][-1].get("changes_summary", "")
    return {"changes": changes, "updated_profile": updated}


@app.get("/profile")
def get_profile(user_id: str = Depends(get_current_user)):
    return load_profile(user_id)


@app.put("/profile")
def put_profile(partial: dict, user_id: str = Depends(get_current_user)):
    existing = load_profile(user_id)
    updated = merge_profile_update(existing, partial)
    save_profile(user_id, updated)
    return updated


@app.get("/topics")
def topics(user_id: str = Depends(get_current_user)):
    profile = load_profile(user_id)
    selection = select_topic(user_id, profile)
    return {"candidates": selection["ranked"], "top": selection["top"]}


@app.post("/generate")
def generate(req: GenerateRequest, user_id: str = Depends(get_current_user)):
    profile = load_profile(user_id)
    return research_and_write(req.topic, profile)


@app.post("/audio")
def audio(req: AudioRequest, user_id: str = Depends(get_current_user)):
    from services.audio_service import generate_audio_overview
    try:
        return generate_audio_overview(user_id, req.title, req.body_html)
    except EnvironmentError as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/publish")
def publish(req: PublishRequest, user_id: str = Depends(get_current_user)):
    settings = get_user_settings(user_id)
    try:
        url = publish_post(
            title=req.title,
            body_html=req.body_html,
            substack_url=settings.get("substack_url"),
            email=settings.get("substack_email"),
            password=settings.get("substack_password"),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"url": url}


@app.post("/run")
def run(user_id: str = Depends(get_current_user)):
    log_entry = run_pipeline(user_id)
    if log_entry["status"] == "error":
        raise HTTPException(status_code=500, detail=log_entry.get("error"))
    return log_entry


@app.get("/runs")
def runs(user_id: str = Depends(get_current_user), limit: int = 20):
    """Returns recent pipeline run history for the current user."""
    return get_run_history(user_id, limit=limit)
