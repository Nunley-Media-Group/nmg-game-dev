"""The Meshy REST client over a fake transport (#98 FR1, AC10)."""

from __future__ import annotations

import io
import json
import urllib.error
from collections.abc import Mapping
from email.message import Message
from pathlib import Path

import pytest

from nmg_game_dev.meshy.client import MeshyClient, UrllibTransport
from nmg_game_dev.meshy.errors import MeshyError
from tests.meshy_fakes import API, GLB_BYTES, GLB_URL, TEST_KEY, FakeMeshy

TEXT_URL = f"{API}/openapi/v2/text-to-3d"
IMAGE_URL = f"{API}/openapi/v1/image-to-3d"
MULTI_URL = f"{API}/openapi/v1/multi-image-to-3d"
RETEX_URL = f"{API}/openapi/v1/retexture"


class _Echo:
    """A transport that answers every request with one fixed status and message."""

    def __init__(self, status: int, message: str) -> None:
        self._status = status
        self._body = json.dumps({"message": message}).encode("utf-8")

    def send(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
    ) -> tuple[int, bytes]:
        return self._status, self._body


def test_preview_is_posted_with_bearer_auth_and_no_pose_by_default() -> None:
    fake = FakeMeshy()
    task_id = MeshyClient(TEST_KEY, fake).create_text_preview("weathered wooden crate")
    assert task_id == "task-1"
    sent = fake.sent[0]
    assert sent.method == "POST" and sent.url == TEXT_URL
    assert sent.headers["Authorization"] == f"Bearer {TEST_KEY}"
    assert sent.json_body() == {"mode": "preview", "prompt": "weathered wooden crate"}


def test_pose_mode_is_sent_only_when_given() -> None:
    fake = FakeMeshy()
    client = MeshyClient(TEST_KEY, fake)
    client.create_text_preview("knight", pose_mode="t-pose")
    client.create_text_preview("crate")
    with_pose, without_pose = (body for _path, body in fake.posts())
    assert with_pose["pose_mode"] == "t-pose"
    assert "pose_mode" not in without_pose


def test_refine_names_the_preview_and_enables_pbr() -> None:
    fake = FakeMeshy()
    MeshyClient(TEST_KEY, fake).create_text_refine("task-9")
    assert fake.posts() == [
        (
            "/openapi/v2/text-to-3d",
            {"mode": "refine", "preview_task_id": "task-9", "enable_pbr": True},
        )
    ]


def test_image_request_carries_texture_flags_and_optional_fields() -> None:
    fake = FakeMeshy()
    client = MeshyClient(TEST_KEY, fake)
    client.create_image_to_3d(
        "data:image/png;base64,AAAA", texture=True, texture_prompt="pale", pose_mode="a-pose"
    )
    client.create_image_to_3d("data:image/png;base64,AAAA", texture=False)
    textured, untextured = fake.sent[0].json_body(), fake.sent[1].json_body()
    assert fake.sent[0].url == IMAGE_URL
    assert textured == {
        "image_url": "data:image/png;base64,AAAA",
        "should_texture": True,
        "enable_pbr": True,
        "texture_prompt": "pale",
        "pose_mode": "a-pose",
    }
    assert untextured["should_texture"] is False and untextured["enable_pbr"] is False
    assert "texture_prompt" not in untextured and "pose_mode" not in untextured


def test_multi_image_request_sends_every_uri() -> None:
    fake = FakeMeshy()
    MeshyClient(TEST_KEY, fake).create_multi_image_to_3d(
        ["data:image/jpeg;base64,AA", "data:image/webp;base64,BB"], texture=True
    )
    assert fake.sent[0].url == MULTI_URL
    assert fake.sent[0].json_body()["image_urls"] == [
        "data:image/jpeg;base64,AA",
        "data:image/webp;base64,BB",
    ]


def test_retexture_request_takes_a_text_or_image_style() -> None:
    fake = FakeMeshy()
    client = MeshyClient(TEST_KEY, fake)
    client.create_retexture("data:application/octet-stream;base64,AA", text_style_prompt="moss")
    client.create_retexture("data:application/octet-stream;base64,AA", image_style_uri="data:x")
    first, second = fake.sent[0].json_body(), fake.sent[1].json_body()
    assert fake.sent[0].url == RETEX_URL
    assert first == {
        "model_url": "data:application/octet-stream;base64,AA",
        "enable_pbr": True,
        "text_style_prompt": "moss",
    }
    assert second["image_style_url"] == "data:x" and "text_style_prompt" not in second


def test_get_task_polls_the_create_path_with_auth() -> None:
    fake = FakeMeshy()
    MeshyClient(TEST_KEY, fake).get_task("text", "task-9")
    sent = fake.sent[0]
    assert sent.method == "GET" and sent.url == f"{TEXT_URL}/task-9"
    assert sent.headers["Authorization"] == f"Bearer {TEST_KEY}"


def test_download_sends_no_auth_header() -> None:
    fake = FakeMeshy()
    data = MeshyClient(TEST_KEY, fake).download(GLB_URL)
    assert data == GLB_BYTES
    assert "Authorization" not in fake.sent[0].headers


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, "meshy.auth_failed"),
        (402, "meshy.insufficient_credits"),
        (429, "meshy.rate_limited"),
        (500, "meshy.request_failed"),
        (404, "meshy.request_failed"),
    ],
)
def test_http_failures_map_to_structured_codes(status: int, code: str) -> None:
    client = MeshyClient(TEST_KEY, FakeMeshy(create_status=status))
    with pytest.raises(MeshyError) as info:
        client.create_text_preview("crate")
    assert info.value.code == code
    assert info.value.remediation
    assert TEST_KEY not in info.value.message and TEST_KEY not in info.value.remediation


def test_meshy_messages_are_redacted_of_the_key() -> None:
    client = MeshyClient(TEST_KEY, _Echo(403, f"bad key {TEST_KEY}"))
    with pytest.raises(MeshyError) as info:
        client.create_text_preview("crate")
    assert info.value.code == "meshy.request_failed"
    assert TEST_KEY not in info.value.message
    assert "***" in info.value.message


def test_network_errors_map_to_request_failed_without_the_key() -> None:
    client = MeshyClient(TEST_KEY, FakeMeshy(send_error=OSError(f"no route {TEST_KEY}")))
    with pytest.raises(MeshyError) as info:
        client.create_text_preview("crate")
    assert info.value.code == "meshy.request_failed"
    assert TEST_KEY not in info.value.message


def test_a_non_json_success_is_a_request_failure() -> None:
    class _Html:
        def send(
            self, method: str, url: str, headers: Mapping[str, str], body: bytes | None
        ) -> tuple[int, bytes]:
            return 200, b"<html>"

    with pytest.raises(MeshyError) as info:
        MeshyClient(TEST_KEY, _Html()).get_task("text", "task-1")
    assert info.value.code == "meshy.request_failed"


def test_a_success_without_a_task_id_is_a_request_failure() -> None:
    with pytest.raises(MeshyError) as info:
        MeshyClient(TEST_KEY, _Echo(200, "no result field")).create_text_preview("crate")
    assert info.value.code == "meshy.request_failed"


def test_urllib_transport_returns_http_errors_as_status_and_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: object, timeout: float) -> object:
        raise urllib.error.HTTPError(
            "https://api.meshy.ai/x",
            401,
            "Unauthorized",
            Message(),
            io.BytesIO(b'{"message": "no"}'),
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    status, body = UrllibTransport().send("GET", "https://api.meshy.ai/x", {}, None)
    assert status == 401 and json.loads(body) == {"message": "no"}


def test_download_failure_is_a_request_failure(tmp_path: Path) -> None:
    with pytest.raises(MeshyError) as info:
        MeshyClient(TEST_KEY, FakeMeshy()).download("https://assets.meshy.test/missing.glb")
    assert info.value.code == "meshy.request_failed"
