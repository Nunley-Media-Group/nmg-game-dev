"""Meshy REST client over an injectable transport (#98 FR1, AC10).

Requests carry ``Authorization: Bearer <key>``. Asset downloads carry no auth header. HTTP 401, 402,
and 429 map to ``meshy.auth_failed``, ``meshy.insufficient_credits``, and ``meshy.rate_limited``;
any other failure, or a network error, maps to ``meshy.request_failed``. Every message is passed
through ``redact``, so the key never appears in an error.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from typing import Any, Final, Protocol

from nmg_game_dev.meshy.config import redact
from nmg_game_dev.meshy.errors import MeshyError

BASE_URL: Final = "https://api.meshy.ai"
REQUEST_TIMEOUT_S: Final = 120.0
TERMINAL_FAILURES: Final = ("FAILED", "CANCELED", "EXPIRED")
TASK_PATHS: Final[Mapping[str, str]] = {
    "text": "/openapi/v2/text-to-3d",
    "image": "/openapi/v1/image-to-3d",
    "multi_image": "/openapi/v1/multi-image-to-3d",
    "retexture": "/openapi/v1/retexture",
}


class Transport(Protocol):
    """Sends one HTTP request and returns ``(status, body)``. Network failures raise OSError."""

    def send(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
    ) -> tuple[int, bytes]: ...


class UrllibTransport:
    """The default transport, built on the standard library so no dependency is added."""

    def __init__(self, timeout: float = REQUEST_TIMEOUT_S) -> None:
        self._timeout = timeout

    def send(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
    ) -> tuple[int, bytes]:
        request = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                return int(response.status), response.read()
        except urllib.error.HTTPError as error:
            return int(error.code), error.read()


class MeshyClient:
    """Calls the Meshy endpoints for one key over one transport."""

    def __init__(
        self,
        key: str,
        transport: Transport | None = None,
        *,
        base_url: str = BASE_URL,
    ) -> None:
        self._key = key
        self._transport: Transport = transport if transport is not None else UrllibTransport()
        self._base = base_url.rstrip("/")

    def create_text_preview(self, prompt: str, *, pose_mode: str | None = None) -> str:
        body: dict[str, Any] = {"mode": "preview", "prompt": prompt}
        if pose_mode is not None:
            body["pose_mode"] = pose_mode
        return self._create("text", body)

    def create_text_refine(self, preview_task_id: str) -> str:
        body = {"mode": "refine", "preview_task_id": preview_task_id, "enable_pbr": True}
        return self._create("text", body)

    def create_image_to_3d(
        self,
        image_uri: str,
        *,
        texture: bool,
        texture_prompt: str | None = None,
        pose_mode: str | None = None,
    ) -> str:
        body: dict[str, Any] = {
            "image_url": image_uri,
            "should_texture": texture,
            "enable_pbr": texture,
        }
        _add_optional(body, texture_prompt, pose_mode)
        return self._create("image", body)

    def create_multi_image_to_3d(
        self,
        image_uris: Sequence[str],
        *,
        texture: bool,
        texture_prompt: str | None = None,
        pose_mode: str | None = None,
    ) -> str:
        body: dict[str, Any] = {
            "image_urls": list(image_uris),
            "should_texture": texture,
            "enable_pbr": texture,
        }
        _add_optional(body, texture_prompt, pose_mode)
        return self._create("multi_image", body)

    def create_retexture(
        self,
        model_uri: str,
        *,
        text_style_prompt: str | None = None,
        image_style_uri: str | None = None,
    ) -> str:
        body: dict[str, Any] = {"model_url": model_uri, "enable_pbr": True}
        if text_style_prompt is not None:
            body["text_style_prompt"] = text_style_prompt
        if image_style_uri is not None:
            body["image_style_url"] = image_style_uri
        return self._create("retexture", body)

    def get_task(self, kind: str, task_id: str) -> dict[str, Any]:
        url = f"{self._base}{TASK_PATHS[kind]}/{urllib.parse.quote(task_id, safe='')}"
        return self._request("GET", url, None, authorized=True)

    def download(self, url: str) -> bytes:
        """Fetch an asset URL. Asset hosts take no auth header."""
        status, data = self._send("GET", url, None, authorized=False)
        if not 200 <= status < 300:
            raise MeshyError(
                "meshy.request_failed",
                f"Downloading a Meshy asset failed with HTTP {status}.",
                "Retry the job; Meshy asset links expire, so a new job may be needed.",
            )
        return data

    def _create(self, kind: str, body: Mapping[str, Any]) -> str:
        data = self._request("POST", f"{self._base}{TASK_PATHS[kind]}", body, authorized=True)
        task_id = data.get("result")
        if not isinstance(task_id, str) or not task_id:
            raise MeshyError(
                "meshy.request_failed",
                "Meshy accepted the request but returned no task id.",
                "Retry the job.",
            )
        return task_id

    def _request(
        self,
        method: str,
        url: str,
        body: Mapping[str, Any] | None,
        *,
        authorized: bool,
    ) -> dict[str, Any]:
        status, data = self._send(method, url, body, authorized=authorized)
        if not 200 <= status < 300:
            raise self._http_error(status, data)
        try:
            parsed = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise MeshyError(
                "meshy.request_failed",
                "Meshy returned a response that is not JSON.",
                "Retry the job; if it persists, check the Meshy status page.",
            ) from error
        if not isinstance(parsed, dict):
            raise MeshyError(
                "meshy.request_failed",
                "Meshy returned a JSON value that is not an object.",
                "Retry the job; if it persists, check the Meshy status page.",
            )
        return parsed

    def _send(
        self,
        method: str,
        url: str,
        body: Mapping[str, Any] | None,
        *,
        authorized: bool,
    ) -> tuple[int, bytes]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if authorized:
            headers["Authorization"] = f"Bearer {self._key}"
        payload: bytes | None = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            payload = json.dumps(body).encode("utf-8")
        try:
            return self._transport.send(method, url, headers, payload)
        except OSError as error:
            raise MeshyError(
                "meshy.request_failed",
                f"Could not reach Meshy: {redact(str(error), self._key)}",
                "Check the network connection to api.meshy.ai, then retry.",
            ) from error

    def _http_error(self, status: int, data: bytes) -> MeshyError:
        message = redact(_meshy_message(data), self._key)
        suffix = f": {message}" if message else ""
        if status == 401:
            return MeshyError(
                "meshy.auth_failed",
                f"Meshy rejected the API key (HTTP 401){suffix}",
                "Check MESHY_API_KEY in the environment or the project's git-ignored .env file.",
            )
        if status == 402:
            return MeshyError(
                "meshy.insufficient_credits",
                f"The Meshy account has no credits left (HTTP 402){suffix}",
                "Add credits to the Meshy account, then retry the job.",
            )
        if status == 429:
            return MeshyError(
                "meshy.rate_limited",
                f"Meshy is rate limiting requests (HTTP 429){suffix}",
                "Wait a minute, then retry the job.",
            )
        return MeshyError(
            "meshy.request_failed",
            f"Meshy answered HTTP {status}{suffix}",
            "Retry the job; if it persists, check the Meshy status page.",
        )


def _add_optional(body: dict[str, Any], texture_prompt: str | None, pose_mode: str | None) -> None:
    if texture_prompt is not None:
        body["texture_prompt"] = texture_prompt
    if pose_mode is not None:
        body["pose_mode"] = pose_mode


def _meshy_message(data: bytes) -> str:
    try:
        parsed = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ""
    message = parsed.get("message") if isinstance(parsed, dict) else None
    return message.strip() if isinstance(message, str) else ""
