import os
from functools import lru_cache

from supabase import create_client, Client

FIXED_PROFILE_ID = "00000000-0000-0000-0000-000000000001"


@lru_cache(maxsize=1)
def get_client() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ["SUPABASE_SERVICE_KEY"]
    return create_client(url, key)


# ── Profile ───────────────────────────────────────────────────────────────────

def load_profile(user_id: str = FIXED_PROFILE_ID) -> dict:
    result = (
        get_client()
        .table("cognitive_profiles")
        .select("profile")
        .eq("id", FIXED_PROFILE_ID)
        .maybe_single()
        .execute()
    )
    if result.data is None:
        return _default_profile()
    return result.data["profile"]


def save_profile(user_id: str, profile: dict) -> None:
    from datetime import datetime, timezone
    profile["last_updated"] = datetime.now(timezone.utc).isoformat()
    get_client().table("cognitive_profiles").upsert(
        {"id": FIXED_PROFILE_ID, "profile": profile, "updated_at": profile["last_updated"]}
    ).execute()


def get_user_settings(user_id: str) -> dict:
    result = (
        get_client()
        .table("cognitive_profiles")
        .select("profile")
        .eq("id", FIXED_PROFILE_ID)
        .maybe_single()
        .execute()
    )
    if not result.data:
        return {}
    p = result.data["profile"]
    return {
        "substack_url": p.get("substack_url", ""),
        "substack_email": p.get("substack_email", ""),
        "substack_password": p.get("substack_password", ""),
        "cron_schedule_hours": p.get("cron_schedule_hours", 24),
        "onboarded": p.get("onboarded", False),
    }


def update_user_settings(user_id: str, **kwargs) -> None:
    profile = load_profile(user_id)
    profile.update(kwargs)
    save_profile(user_id, profile)


def list_onboarded_users() -> list[str]:
    result = (
        get_client()
        .table("cognitive_profiles")
        .select("id")
        .eq("id", FIXED_PROFILE_ID)
        .execute()
    )
    return [row["id"] for row in (result.data or [])]


# ── Pipeline logs ─────────────────────────────────────────────────────────────

def log_run(user_id: str, run: dict) -> None:
    get_client().table("pipeline_logs").insert({"log_entry": run}).execute()


def get_run_history(user_id: str, limit: int = 20) -> list[dict]:
    result = (
        get_client()
        .table("pipeline_logs")
        .select("id, log_entry, created_at")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


# ── Audio storage ─────────────────────────────────────────────────────────────

def upload_audio(user_id: str, filename: str, mp3_bytes: bytes) -> str:
    path = f"{filename}"
    get_client().storage.from_("audio").upload(
        path=path,
        file=mp3_bytes,
        file_options={"content-type": "audio/mpeg", "upsert": "true"},
    )
    return get_client().storage.from_("audio").get_public_url(path)


# ── Helpers ───────────────────────────────────────────────────────────────────

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
