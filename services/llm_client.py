"""
Unified LLM client that works with both Anthropic and MiniMax APIs.

For MiniMax: Uses the official Anthropic SDK with MiniMax's Anthropic-compatible endpoint
For Anthropic (legacy): Falls back to ANTHROPIC_* env vars if MINIMAX_* are not set

Configuration via environment variables:
- MINIMAX_API_KEY: Your MiniMax API key (required, falls back to ANTHROPIC_API_KEY)
- MINIMAX_BASE_URL: MiniMax base URL (default: https://api.minimax.io/anthropic)
- MINIMAX_MODEL: Model name (default: MiniMax-M2.7)
- LLM_PROVIDER: Set to "minimax_http" to use legacy Minimax HTTP API (optional, not recommended)
"""

import os
import json
import httpx
import anthropic
from typing import List, Dict, Any, Optional


def _is_minimax() -> bool:
    """
    Detect if we should use Minimax-specific formatting (legacy HTTP API).

    NOTE: MiniMax now officially supports Anthropic SDK via https://api.minimax.io/anthropic
    This function only returns True if you explicitly set LLM_PROVIDER=minimax_http
    to use the old Minimax-native HTTP endpoints.
    """
    provider = os.environ.get("LLM_PROVIDER", "").lower()
    return provider == "minimax_http"


def _get_model() -> str:
    """Get the model name from environment."""
    return os.environ.get("MINIMAX_MODEL") or os.environ.get("ANTHROPIC_MODEL", "MiniMax-M2.7-highspeed")


class UnifiedLLMClient:
    """
    Unified client that works with both Anthropic and Minimax APIs.

    Usage:
        client = UnifiedLLMClient()
        response = client.create_message(
            model="claude-sonnet-4",
            max_tokens=1000,
            messages=[{"role": "user", "content": "Hello"}]
        )
        text = response["content"][0]["text"]
    """

    def __init__(self):
        self.is_minimax = _is_minimax()
        # Prefer MINIMAX_* env vars, fall back to ANTHROPIC_* for backwards compatibility
        self.api_key = os.environ.get("MINIMAX_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        self.base_url = os.environ.get("MINIMAX_BASE_URL") or os.environ.get("ANTHROPIC_BASE_URL") or "https://api.minimax.io/anthropic"

        if not self.api_key:
            raise EnvironmentError("MINIMAX_API_KEY (or ANTHROPIC_API_KEY) environment variable is required")

        if self.is_minimax:
            print(f"[LLM] Using Minimax legacy HTTP API at {self.base_url}")
            self.http_client = httpx.Client(timeout=60.0)
        else:
            print(f"[LLM] Using Anthropic SDK with base_url={self.base_url}")
            kwargs = {"api_key": self.api_key}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self.anthropic_client = anthropic.Anthropic(**kwargs)

    def create_message(
        self,
        model: str,
        max_tokens: int,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        system: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a message using either Anthropic or Minimax API.

        Returns a dict with Anthropic-compatible format:
        {
            "id": "...",
            "content": [{"type": "text", "text": "..."}],
            "model": "...",
            "role": "assistant",
            ...
        }
        """
        if self.is_minimax:
            return self._create_message_minimax(model, max_tokens, messages, temperature, system)
        else:
            return self._create_message_anthropic(model, max_tokens, messages, temperature, system)

    def _create_message_anthropic(
        self,
        model: str,
        max_tokens: int,
        messages: List[Dict[str, str]],
        temperature: Optional[float],
        system: Optional[str],
    ) -> Dict[str, Any]:
        """Use Anthropic SDK."""
        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        if system:
            kwargs["system"] = system

        response = self.anthropic_client.messages.create(**kwargs)

        # Convert Anthropic SDK response to dict
        # Handle both TextBlock and ThinkingBlock (MiniMax returns both)
        content_blocks = []
        for block in response.content:
            if block.type == "text":
                content_blocks.append({"type": "text", "text": block.text})
            elif block.type == "thinking":
                content_blocks.append({"type": "thinking", "thinking": block.thinking})
            else:
                # Unknown block type - try to serialize it
                content_blocks.append({"type": block.type, "text": str(block)})

        return {
            "id": response.id,
            "type": response.type,
            "role": response.role,
            "content": content_blocks,
            "model": response.model,
            "stop_reason": response.stop_reason,
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        }

    def _create_message_minimax(
        self,
        model: str,
        max_tokens: int,
        messages: List[Dict[str, str]],
        temperature: Optional[float],
        system: Optional[str],
    ) -> Dict[str, Any]:
        """
        Use Minimax API with direct HTTP calls.

        Minimax API format:
        POST https://api.minimax.chat/v1/text/chatcompletion_v2
        Headers:
          - Authorization: Bearer {api_key}
          - Content-Type: application/json
        Body:
          {
            "model": "abab6.5s-chat",
            "messages": [{"role": "user", "content": "..."}],
            "max_tokens": 1000,
            "temperature": 0.7
          }
        """
        # Prepend system message if provided
        formatted_messages = messages.copy()
        if system:
            formatted_messages = [{"role": "system", "content": system}] + formatted_messages

        # Build request payload
        payload = {
            "model": model,
            "messages": formatted_messages,
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            payload["temperature"] = temperature

        # Determine endpoint - Minimax uses /v1/text/chatcompletion_v2
        # But also try to be compatible with /v1/chat/completions (OpenAI-style)
        base = self.base_url.rstrip("/")

        # Try Minimax native endpoint first
        endpoints_to_try = [
            f"{base}/v1/text/chatcompletion_v2",
            f"{base}/v1/chat/completions",
            f"{base}/chat/completions",
        ]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_error = None
        for endpoint in endpoints_to_try:
            try:
                response = self.http_client.post(
                    endpoint,
                    headers=headers,
                    json=payload,
                )

                if response.status_code == 200:
                    data = response.json()

                    # Convert Minimax response to Anthropic format
                    # Minimax format might be OpenAI-like:
                    # {"choices": [{"message": {"role": "assistant", "content": "..."}}]}

                    if "choices" in data and len(data["choices"]) > 0:
                        # OpenAI/Minimax format
                        choice = data["choices"][0]
                        content_text = choice.get("message", {}).get("content", "")

                        return {
                            "id": data.get("id", "minimax-" + str(hash(content_text))[:16]),
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "text", "text": content_text}],
                            "model": model,
                            "stop_reason": choice.get("finish_reason", "end_turn"),
                            "usage": {
                                "input_tokens": data.get("usage", {}).get("prompt_tokens", 0),
                                "output_tokens": data.get("usage", {}).get("completion_tokens", 0),
                            },
                        }
                    else:
                        # Unknown format - try to extract text
                        content_text = str(data)
                        return {
                            "id": "minimax-unknown",
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "text", "text": content_text}],
                            "model": model,
                            "stop_reason": "end_turn",
                            "usage": {"input_tokens": 0, "output_tokens": 0},
                        }

                elif response.status_code == 404:
                    # Try next endpoint
                    continue
                else:
                    # API error
                    last_error = f"HTTP {response.status_code}: {response.text}"
                    continue

            except Exception as e:
                last_error = f"{type(e).__name__}: {str(e)}"
                continue

        # All endpoints failed
        raise RuntimeError(
            f"Minimax API failed on all endpoints. Last error: {last_error}\n"
            f"Tried: {endpoints_to_try}\n"
            f"Model: {model}\n"
            f"Base URL: {self.base_url}"
        )

    def __del__(self):
        """Clean up HTTP client."""
        if hasattr(self, "http_client"):
            self.http_client.close()


def get_client() -> UnifiedLLMClient:
    """Get a unified LLM client (singleton pattern)."""
    global _client
    if "_client" not in globals():
        _client = UnifiedLLMClient()
    return _client
