"""AC4 — each stub returns FINISHED, emits its log record, and mutates nothing."""

from __future__ import annotations

import logging

import pytest

_OPS = ("cleanup_desktop", "optimize_mobile", "generate_variants")
_LOGGER_NAME = "nmg_game_dev_blender_addon"


@pytest.fixture(scope="module")
def addon_logger_handler():
    # Blender may install its own logging configuration that bypasses
    # pytest's caplog, so attach a list handler directly.
    records: list[logging.LogRecord] = []

    class _ListHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _ListHandler(level=logging.DEBUG)
    logger = logging.getLogger(_LOGGER_NAME)
    logger.addHandler(handler)
    yield records
    logger.removeHandler(handler)


@pytest.mark.parametrize("op_name", _OPS)
def test_stub_returns_finished(blender_context, op_name: str) -> None:  # noqa: ARG001
    import bpy  # noqa: PLC0415

    result = getattr(bpy.ops.nmggamedev, op_name)()
    assert result == {"FINISHED"}, (
        f"Expected {{'FINISHED'}}, got {result!r} for nmggamedev.{op_name}"
    )


@pytest.mark.parametrize("op_name", _OPS)
def test_stub_emits_log_record(
    blender_context,  # noqa: ARG001
    addon_logger_handler: list[logging.LogRecord],
    op_name: str,
) -> None:
    import bpy  # noqa: PLC0415

    addon_logger_handler.clear()
    getattr(bpy.ops.nmggamedev, op_name)()

    expected_fragment = f"nmggamedev.{op_name}: stub invoked"
    matching = [
        r
        for r in addon_logger_handler
        if r.levelno == logging.INFO and expected_fragment in r.getMessage()
    ]
    assert matching, (
        f"No INFO record containing '{expected_fragment}'. "
        f"Records seen: {[r.getMessage() for r in addon_logger_handler]}"
    )


@pytest.mark.parametrize("op_name", _OPS)
def test_stub_does_not_mutate_scene(blender_context, op_name: str) -> None:  # noqa: ARG001
    import bpy  # noqa: PLC0415

    before = tuple(sorted(bpy.data.objects.keys()))
    getattr(bpy.ops.nmggamedev, op_name)()
    after = tuple(sorted(bpy.data.objects.keys()))
    assert before == after, (
        f"Scene objects changed after nmggamedev.{op_name}: before={before!r} after={after!r}"
    )
