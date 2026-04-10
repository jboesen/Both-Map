"""
Supabase wrapper — replaces all file-based profile I/O.

Uses the service role key (bypasses RLS) so the backend can act on
behalf of any user. The frontend uses the anon key + user JWT directly.
"""

import os
from datetime import datetime, timezone
from functools import lru_cache

from supabase import create_client, Client


@lru_cache(maxsize=1)
def get_client() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, key)


# ── Profile ───────────────────────────────────────────────────────────────────

def load_profile(user_id: str) -> dict:
    """Returns the cognitive_profile JSONB for a user. Creates row if missing."""
    client = get_client()
    result = (
        client.table("profiles")
        .select("cognitive_profile")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    if result.data is None:
        # First time — create the row
        _ensure_profile_row(user_id)
        return _default_profile()
    return result.data["cognitive_profile"]


def save_profile(user_id: str, profile: dict) -> None:
    profile["last_updated"] = datetime.now(timezone.utc).isoformat()
    client = get_client()
    client.table("profiles").upsert(
        {"id": user_id, "cognitive_profile": profile, "updated_at": profile["last_updated"]}
    ).execute()


def get_user_settings(user_id: str) -> dict:
    """Returns substack_url, cron_schedule_hours, onboarded."""
    client = get_client()
    result = (
        client.table("profiles")
        .select("substack_url, substack_email, substack_password, cron_schedule_hours, onboarded")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    return result.data or {}


def update_user_settings(user_id: str, **kwargs) -> None:
    """Update any top-level profile columns (substack_url, onboarded, etc.)."""
    client = get_client()
    client.table("profiles").upsert({"id": user_id, **kwargs}).execute()


def list_onboarded_users() -> list[str]:
    """Returns user_ids of all users who have completed onboarding. Used by cron."""
    client = get_client()
    result = (
        client.table("profiles")
        .select("id")
        .eq("onboarded", True)
        .execute()
    )
    return [row["id"] for row in (result.data or [])]


# ── Pipeline runs ─────────────────────────────────────────────────────────────

def log_run(user_id: str, run: dict) -> None:
    client = get_client()
    client.table("pipeline_runs").insert(
        {
            "user_id": user_id,
            "topic": run.get("topic"),
            "post_url": run.get("post_url"),
            "audio_url": run.get("audio_url"),
            "status": run.get("status", "error"),
            "error": run.get("error"),
        }
    ).execute()


def get_run_history(user_id: str, limit: int = 20) -> list[dict]:
    client = get_client()
    result = (
        client.table("pipeline_runs")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


# ── Audio storage ─────────────────────────────────────────────────────────────

def upload_audio(user_id: str, filename: str, mp3_bytes: bytes) -> str:
    """
    Uploads an MP3 to Supabase Storage under audio/{user_id}/{filename}.
    Returns the public URL.
    """
    client = get_client()
    path = f"{user_id}/{filename}"
    client.storage.from_("audio").upload(
        path=path,
        file=mp3_bytes,
        file_options={"content-type": "audio/mpeg", "upsert": "true"},
    )
    url_response = client.storage.from_("audio").get_public_url(path)
    return url_response


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ensure_profile_row(user_id: str) -> None:
    client = get_client()
    client.table("profiles").upsert(
        {"id": user_id, "cognitive_profile": _default_profile()}
    ).execute()


def _default_profile() -> dict:
    return {
        "version": 1,
        "last_updated": None,
        "topics": {"covered": [], "interests": [], "exclusions": []},
        "mental_models": [],
        "third_order": [],
        "tone_preferences": {"style": "", "depth": "", "avoid": ""},
        "feedback_history": [],
    }
