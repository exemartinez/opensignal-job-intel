from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class LlmJsonResult:
    ok: bool
    data: dict[str, Any] | None
    error: str | None


class LocalLlmClient:
    """Very small HTTP client for a locally running LLM server.

    Supports:
    - OpenAI-compatible chat completions: POST /v1/chat/completions
    - llama.cpp server completion endpoint fallback: POST /completion

    This client is intentionally minimal and only used for extraction fallback.
    """

    def __init__(
        self,
        base_url: str,
        model: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds

    def extract_json(self, system_prompt: str, user_prompt: str) -> LlmJsonResult:
        # Try OpenAI-compatible first.
        chat_url = f"{self._base_url}/v1/chat/completions"
        payload: dict[str, Any] = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
        }
        if self._model:
            payload["model"] = self._model
        chat = self._post_json(chat_url, payload)
        if chat.ok:
            content = _extract_openai_content(chat.data)
            return _parse_json_from_text(content)
        # Fallback to llama.cpp style endpoint.
        completion_url = f"{self._base_url}/completion"
        payload2: dict[str, Any] = {
            "prompt": f"{system_prompt}\n\n{user_prompt}",
            "temperature": 0,
        }
        completion = self._post_json(completion_url, payload2)
        if completion.ok:
            text = (completion.data or {}).get("content") or ""
            return _parse_json_from_text(str(text))
        return LlmJsonResult(ok=False, data=None, error=chat.error or completion.error)

    def _post_json(self, url: str, payload: dict[str, Any]) -> LlmJsonResult:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return LlmJsonResult(ok=True, data=data, error=None)
        except urllib.error.HTTPError as exc:
            return LlmJsonResult(
                ok=False,
                data=None,
                error=f"HTTP {exc.code} calling LLM endpoint {url}",
            )
        except urllib.error.URLError as exc:
            return LlmJsonResult(
                ok=False,
                data=None,
                error=f"Failed to reach LLM endpoint {url}: {exc}",
            )
        except Exception as exc:  # pragma: no cover
            return LlmJsonResult(ok=False, data=None, error=str(exc))


def _extract_openai_content(payload: dict[str, Any] | None) -> str:
    if not payload:
        return ""
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return str(content) if content is not None else ""


def _parse_json_from_text(text: str) -> LlmJsonResult:
    # Allow responses that include extra text around a JSON object.
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return LlmJsonResult(ok=False, data=None, error="LLM did not return JSON")
    snippet = text[start : end + 1]
    try:
        return LlmJsonResult(ok=True, data=json.loads(snippet), error=None)
    except Exception as exc:
        return LlmJsonResult(ok=False, data=None, error=f"Invalid JSON from LLM: {exc}")
