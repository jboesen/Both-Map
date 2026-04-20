import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
# from fastapi import Depends, Security
# from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
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

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="Substack Autopilot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Auth ──────────────────────────────────────────────────────────────────────
# Auth disabled for development - all requests use user_id="default"
# TODO: Re-enable auth for production
#
# security = HTTPBearer()
#
# def get_current_user(
#     credentials: HTTPAuthorizationCredentials = Security(security),
# ) -> str:
#     """
#     Extract user_id from the Authorization: Bearer <user_id> header.
#     For development/testing, the token is simply the user_id.
#     TODO: Implement proper JWT validation for production.
#     """
#     return credentials.credentials


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
def onboard(req: OnboardRequest, user_id: str = "default"):
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

    exa_ran = False
    if req.user_info:
        try:
            from services.exa_service import research_user
            user_info_dict = req.user_info.model_dump(exclude_none=True)
            user_info_dict.setdefault("substack_url", req.substack_url)
            synthesis = research_user(user_info_dict)
            profile = enrich_profile_from_perplexity(user_id, synthesis)
            exa_ran = True
        except EnvironmentError:
            logger.warning("EXA_API_KEY not set — skipping enrichment")
        except Exception:
            logger.exception("Exa enrichment failed")

    update_user_settings(user_id, onboarded=True)
    return {"profile": profile, "exa_enrichment_ran": exa_ran}


@app.post("/enrich-profile")
def enrich_profile(user_info: UserInfo, user_id: str = "default"):
    from services.exa_service import research_user
    user_info_dict = user_info.model_dump(exclude_none=True)
    synthesis = research_user(user_info_dict)
    profile = enrich_profile_from_perplexity(user_id, synthesis)
    return {"profile": profile}


@app.post("/ingest")
def ingest_history(req: IngestRequest, user_id: str = "default"):
    result = ingest(
        user_id=user_id,
        raw_content=req.content,
        format_hint=req.format,
        extract_signals=req.extract_signals,
    )
    return result


@app.post("/feedback")
def feedback(req: FeedbackRequest, user_id: str = "default"):
    updated = update_profile_from_feedback(user_id, req.transcript, req.post_topic)
    changes = ""
    if updated.get("feedback_history"):
        changes = updated["feedback_history"][-1].get("changes_summary", "")
    return {"changes": changes, "updated_profile": updated}


@app.get("/profile")
def get_profile(user_id: str = "default"):
    return load_profile(user_id)


@app.put("/profile")
def put_profile(partial: dict, user_id: str = "default"):
    existing = load_profile(user_id)
    updated = merge_profile_update(existing, partial)
    save_profile(user_id, updated)
    return updated


@app.get("/topics")
def topics(user_id: str = "default", use_mock: bool = False):
    try:
        logger.info(f"GET /topics called for user_id={user_id}, use_mock={use_mock}")

        # Return mock topics if requested (useful for testing)
        if use_mock:
            logger.info("Returning mock topics")
            return {
                "candidates": [
                    {
                        "topic": "The Hidden Economics of Attention Markets",
                        "rationale": "Explores how attention has become a traded commodity",
                        "mental_model_fit": "supply and demand, network effects",
                        "third_order_fit": "social feedback loops",
                        "novelty_score": 0.85,
                        "relevance_score": 0.90
                    }
                ],
                "top": {
                    "topic": "The Hidden Economics of Attention Markets",
                    "rationale": "Explores how attention has become a traded commodity"
                }
            }

        profile = load_profile(user_id)
        logger.info(f"Profile loaded: {len(profile.get('topics', {}).get('interests', []))} interests")

        # Don't generate topics if profile is empty - nothing to base suggestions on
        has_interests = len(profile.get('topics', {}).get('interests', [])) > 0
        has_models = len(profile.get('mental_models', [])) > 0
        has_history = len(profile.get('topics', {}).get('covered', [])) > 0

        if not (has_interests or has_models or has_history):
            logger.warning("Profile is empty - cannot generate personalized topics")
            raise HTTPException(
                status_code=400,
                detail="Profile is empty. Please complete onboarding first by calling POST /onboard with your Substack URL."
            )

        selection = select_topic(user_id, profile)
        logger.info(f"Topic selection complete: {len(selection.get('ranked', []))} candidates")
        return {"candidates": selection["ranked"], "top": selection["top"]}
    except Exception as e:
        logger.error(f"Error in /topics: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get topics: {str(e)}")


@app.post("/generate")
def generate(req: GenerateRequest, user_id: str = "default"):
    profile = load_profile(user_id)
    return research_and_write(req.topic, profile)


@app.post("/audio")
def audio(req: AudioRequest, user_id: str = "default"):
    from services.audio_service import generate_audio_overview
    try:
        return generate_audio_overview(user_id, req.title, req.body_html)
    except EnvironmentError as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/publish")
def publish(req: PublishRequest, user_id: str = "default"):
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
def run(user_id: str = "default"):
    log_entry = run_pipeline(user_id)
    if log_entry["status"] == "error":
        raise HTTPException(status_code=500, detail=log_entry.get("error"))
    return log_entry


@app.get("/runs")
def runs(user_id: str = "default", limit: int = 20):
    """Returns recent pipeline run history for the current user."""
    return get_run_history(user_id, limit=limit)
