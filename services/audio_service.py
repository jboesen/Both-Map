"""
ElevenLabs audio overview generation.

Flow:
  1. Claude converts the post HTML into a narration-friendly spoken script
  2. ElevenLabs TTS voices the script → MP3 bytes
  3. MP3 saved to data/audio/<slug>.mp3
  4. If AUDIO_PUBLIC_BASE_URL is set, returns a public URL for embedding

Env vars:
  ELEVENLABS_API_KEY      — required
  ELEVENLABS_VOICE_ID     — optional, defaults to Rachel (calm, clear)
  ELEVENLABS_MODEL_ID     — optional, defaults to eleven_turbo_v2_5
  AUDIO_PUBLIC_BASE_URL   — optional, e.g. https://cdn.example.com/audio
                            If set, the returned URL is used to embed an
                            <audio> player in the Substack post HTML.
"""

import json
import os
import re
import unicodedata
from pathlib import Path

import anthropic
import httpx

ELEVENLABS_BASE = "https://api.elevenlabs.io/v1"
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"   # Rachel — calm, clear narration
DEFAULT_MODEL_ID = "eleven_turbo_v2_5"

AUDIO_DIR = Path("data/audio")
PROMPTS_DIR = Path("prompts")


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text()


def _extract_json(text: str) -> str:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        return match.group(1)
    return text


def _slugify(title: str) -> str:
    title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    title = re.sub(r"[^\w\s-]", "", title.lower())
    return re.sub(r"[-\s]+", "-", title).strip("-")[:80]


def generate_script(title: str, body_html: str) -> str:
    """
    Uses Claude to convert post HTML into a narration script for audio.
    Returns plain text script.
    """
    client = anthropic.Anthropic()

    prompt_template = _load_prompt("generate_audio_script.txt")
    prompt = prompt_template.replace("{title}", title).replace(
        "{body_html}", body_html
    )

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text
    data = json.loads(_extract_json(raw))
    return data["script"]


def synthesize(script: str) -> bytes:
    """
    Sends the narration script to ElevenLabs TTS.
    Returns raw MP3 bytes.
    """
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise EnvironmentError("ELEVENLABS_API_KEY is not set")

    voice_id = os.environ.get("ELEVENLABS_VOICE_ID", DEFAULT_VOICE_ID)
    model_id = os.environ.get("ELEVENLABS_MODEL_ID", DEFAULT_MODEL_ID)

    url = f"{ELEVENLABS_BASE}/text-to-speech/{voice_id}"

    with httpx.Client(timeout=120) as client:
        response = client.post(
            url,
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json={
                "text": script,
                "model_id": model_id,
                "voice_settings": {
                    "stability": 0.45,
                    "similarity_boost": 0.75,
                    "style": 0.0,
                    "use_speaker_boost": True,
                },
            },
        )
        response.raise_for_status()

    return response.content


def audio_embed_html(public_url: str) -> str:
    """Returns an HTML audio player snippet for embedding in post body."""
    return (
        f'<p><audio controls style="width:100%">'
        f'<source src="{public_url}" type="audio/mpeg">'
        f"Your browser doesn't support the audio element."
        f"</audio></p>"
    )


def generate_audio_overview(user_id: str, title: str, body_html: str) -> dict:
    """
    Full pipeline: script → TTS → upload to Supabase Storage.

    Returns:
      {
        "script": str,          — the narration text
        "public_url": str,      — Supabase Storage public URL
        "embed_html": str,      — <audio> tag ready to prepend to post body
      }
    """
    from services.db_service import upload_audio

    script = generate_script(title, body_html)
    mp3_bytes = synthesize(script)

    filename = f"{_slugify(title)}.mp3"
    public_url = upload_audio(user_id, filename, mp3_bytes)
    embed_html = audio_embed_html(public_url)

    return {
        "script": script,
        "public_url": public_url,
        "embed_html": embed_html,
    }
