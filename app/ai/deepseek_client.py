from __future__ import annotations

import json
import logging
import os
import sys
import importlib
from typing import Dict, Generator, Iterable, List, Optional, Union

from .errors import DeepSeekError, normalize_exception
from .key_provider import KeyProvider


class DeepSeekClient:
    """Thin wrapper around OpenAI-compatible client for DeepSeek.

    - Auth via KeyProvider
    - JSON response helper
    - Optional streaming support (yields text deltas)
    - Error normalization without leaking secrets
    """

    def __init__(
        self,
        key_provider: KeyProvider,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> None:
        self._key_provider = key_provider
        self._base_url = base_url or os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        self._model_name = model_name or os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
        self._client: Optional["openai.OpenAI"] = None

    # --- lifecycle ---
    def reset(self) -> None:
        self._client = None

    def _ensure_client(self) -> Optional["openai.OpenAI"]:
        if self._client is not None:
            return self._client
        api_key = self._key_provider.get_key()
        if not api_key:
            logging.info("DeepSeek API key not set; client unavailable")
            return None
        # Lazily resolve the OpenAI-compatible SDK so tests can stub sys.modules['openai']
        try:
            openai_sdk = sys.modules.get("openai") or importlib.import_module("openai")  # type: ignore[assignment]
        except Exception:
            logging.error("openai SDK not available; cannot initialize DeepSeek client")
            return None
        try:
            self._client = openai_sdk.OpenAI(api_key=api_key, base_url=self._base_url)  # type: ignore[attr-defined]
            return self._client
        except Exception as e:
            logging.error("Failed to initialize DeepSeek client: %s", e)
            self._client = None
            return None

    # --- high-level ops ---
    def test_key(self) -> Dict[str, Union[bool, Optional[str]]]:
        client = self._ensure_client()
        if client is None:
            return {"ok": False, "error": "api_key_missing"}
        try:
            client.models.list()
            return {"ok": True, "error": None}
        except Exception as e:
            err = normalize_exception(e)
            # Map a couple of codes to spec-friendly short strings
            code = err.code
            if code == "invalid_api_key":
                return {"ok": False, "error": "invalid_key"}
            if code == "rate_limited":
                return {"ok": False, "error": "rate_limit"}
            if code == "timeout" or code == "network_error":
                return {"ok": False, "error": "network"}
            if code == "server_error":
                return {"ok": False, "error": "server_error"}
            return {"ok": False, "error": code}

    def chat_text(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.5,
        stream: bool = False,
    ) -> Union[str, Generator[str, None, None]]:
        client = self._ensure_client()
        if client is None:
            raise DeepSeekError(code="api_client_unavailable", message="API key missing or client unavailable")
        try:
            if stream:
                # Streaming token deltas; yield pieces of content text
                with client.chat.completions.stream(  # type: ignore[attr-defined]
                    model=self._model_name, messages=messages, temperature=temperature
                ) as stream_obj:
                    for event in stream_obj:
                        try:
                            # Newer SDKs expose events with .delta
                            delta = getattr(event, "delta", None)
                            if delta and getattr(delta, "content", None):
                                yield delta.content  # type: ignore[misc]
                        except Exception:
                            # Be resilient to SDK event shape
                            pass
                    # End of stream
                    return
            else:
                resp = client.chat.completions.create(
                    model=self._model_name,
                    messages=messages,
                    temperature=temperature,
                )
                if resp.choices and resp.choices[0].message and resp.choices[0].message.content:
                    return resp.choices[0].message.content
                return ""
        except Exception as e:
            raise normalize_exception(e)

    def chat_json(
        self,
        system_prompt: str,
        user_content: str,
        temperature: float = 0.5,
    ) -> Dict:
        """Request JSON response and parse it; raises DeepSeekError on failure."""
        client = self._ensure_client()
        if client is None:
            raise DeepSeekError(code="api_client_unavailable", message="API key missing or client unavailable")
        try:
            resp = client.chat.completions.create(
                model=self._model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=temperature,
                response_format={"type": "json_object"},
            )
            if resp.choices and resp.choices[0].message and resp.choices[0].message.content:
                raw = resp.choices[0].message.content
                return json.loads(raw)
            raise DeepSeekError(code="server_error", message="Missing content in response")
        except json.JSONDecodeError as e:
            raise DeepSeekError(code="bad_response", message=f"Invalid JSON from provider: {e}")
        except Exception as e:
            raise normalize_exception(e)
