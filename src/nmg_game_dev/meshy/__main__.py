"""CLI: ``python -m nmg_game_dev.meshy generate|retexture|status|run-job`` (#98 FR8, AC12).

The CLI calls the same ``jobs`` functions as the MCP tools and prints the same JSON. ``generate``
and ``retexture`` print ``{"job_id"}`` and, with ``--wait``, the job's final status. ``run-job`` is
the internal entry the detached child runs. A ``PipelineError`` prints ``ERROR [<code>]: …`` and
``Remediation: …`` to stderr and exits 1. Argument errors exit 2.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from nmg_game_dev.meshy import jobs
from nmg_game_dev.meshy.request import GenerateRequest, RetextureRequest
from nmg_game_dev.pipeline.errors import PipelineError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m nmg_game_dev.meshy",
        description="Generate and retexture models with the optional Meshy API (#98).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="Start a generate job from a prompt, images, or both.")
    gen.add_argument("--name", required=True, help="PascalCase collection name, e.g. Crate.")
    gen.add_argument("--prompt", default=None, help="What the model shows.")
    gen.add_argument(
        "--image",
        dest="images",
        action="append",
        default=None,
        metavar="PATH",
        help="A reference image (PNG, JPEG, or WebP); repeat for up to four.",
    )
    gen.add_argument(
        "--no-texture",
        dest="texture",
        action="store_false",
        help="Stop after the untextured mesh.",
    )
    gen.add_argument(
        "--pose",
        default=None,
        help="a-pose or t-pose, for characters and creatures with limbs only.",
    )
    gen.add_argument("--wait", action="store_true", help="Poll until the job finishes.")

    retex = sub.add_parser("retexture", help="Start a retexture job for an authored collection.")
    retex.add_argument("--name", required=True, help="PascalCase collection name, e.g. Crate.")
    retex.add_argument("--prompt", default=None, help="Text style for the new maps.")
    retex.add_argument("--image", default=None, metavar="PATH", help="A style image.")
    retex.add_argument("--wait", action="store_true", help="Poll until the job finishes.")

    status_cmd = sub.add_parser("status", help="Print a job's status document.")
    status_cmd.add_argument("job_id")

    run_job = sub.add_parser("run-job", help="Internal: run a started job to completion.")
    run_job.add_argument("job_dir", type=Path)
    return parser


def _start_result(job_id: str, wait: bool) -> dict[str, Any]:
    if wait:
        return jobs.wait(job_id)
    return {"job_id": job_id}


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "generate":
            job_id = jobs.start_generate(
                GenerateRequest(
                    name=args.name,
                    prompt=args.prompt,
                    image_paths=tuple(args.images or ()),
                    texture=args.texture,
                    pose=args.pose,
                )
            )
            result = _start_result(job_id, args.wait)
        elif args.command == "retexture":
            job_id = jobs.start_retexture(
                RetextureRequest(name=args.name, prompt=args.prompt, image_path=args.image)
            )
            result = _start_result(job_id, args.wait)
        elif args.command == "status":
            result = jobs.status(args.job_id)
        else:
            result = jobs.run_job(args.job_dir)
    except PipelineError as error:
        print(f"ERROR [{error.code}]: {error.message}", file=sys.stderr)
        print(f"Remediation: {error.remediation}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
