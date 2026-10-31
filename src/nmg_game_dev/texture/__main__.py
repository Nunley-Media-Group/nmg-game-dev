"""CLI: ``python -m nmg_game_dev.texture generate|status|run-job``.

``generate`` runs synchronously and prints the JSON result. ``status`` prints the availability
of each backend. ``run-job`` is the internal entry the detached job process runs. On
``TextureGenError`` the CLI prints ``ERROR [<code>]: …`` and ``Remediation: …`` to stderr and
exits 1. Argument errors exit 2.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from nmg_game_dev.texture import generate, jobs
from nmg_game_dev.texture.errors import TextureGenError


def _maps_from_args(args: argparse.Namespace) -> str | tuple[float, float] | None:
    maps_arg: str | None = args.maps
    if args.roughness is None and args.metallic is None:
        return maps_arg
    if args.roughness is None or args.metallic is None:
        raise TextureGenError(
            "texture.invalid_request",
            "Explicit maps need both --roughness and --metallic.",
            "Pass --roughness R and --metallic M together, or use --maps with a preset.",
        )
    if args.maps is not None:
        raise TextureGenError(
            "texture.invalid_request",
            "Pass either --maps or --roughness/--metallic, not both.",
            "Remove one of the two map options.",
        )
    return (args.roughness, args.metallic)


def _generate_request(args: argparse.Namespace) -> generate.TextureRequest:
    kwargs: dict[str, Any] = {
        "prompt": args.prompt,
        "backend": args.backend,
        "resolution": args.resolution,
        "name": args.name,
        "maps": _maps_from_args(args),
        "ao": args.ao,
        "style_suffix": args.style_suffix,
    }
    if args.seeds:
        kwargs["seeds"] = list(args.seeds)
    return generate.TextureRequest(**kwargs)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m nmg_game_dev.texture",
        description="Generate seamless albedo textures locally and derive PBR maps.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="Generate textures and wait for the JSON result.")
    gen.add_argument("--prompt", required=True, help="What the texture shows.")
    gen.add_argument(
        "--backend",
        default=generate.DEFAULT_BACKEND,
        help="z-image-turbo, flux2-klein-4b, or both (default: flux2-klein-4b).",
    )
    gen.add_argument(
        "--seed",
        dest="seeds",
        type=int,
        action="append",
        help="A seed; repeat for several images. Default: one random seed.",
    )
    gen.add_argument(
        "--resolution", type=int, default=1024, help="Square size in pixels (default 1024)."
    )
    gen.add_argument(
        "--name", default=None, help="Output folder name. Default: a slug of the prompt."
    )
    gen.add_argument(
        "--maps", default=None, help="Material preset: fabric, wood, stone, plastic, metal."
    )
    gen.add_argument("--roughness", type=float, default=None, help="Explicit roughness, 0 to 1.")
    gen.add_argument("--metallic", type=float, default=None, help="Explicit metallic, 0 to 1.")
    gen.add_argument("--ao", action="store_true", help="Also derive an AO map (needs --maps).")
    gen.add_argument(
        "--style-suffix",
        default=generate.STYLE_SUFFIX,
        help="Text appended to every prompt.",
    )

    sub.add_parser("status", help="Print the availability of each backend.")

    run_job = sub.add_parser("run-job", help="Internal: run a started job to completion.")
    run_job.add_argument("job_dir", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "generate":
            result = generate.run(_generate_request(args))
            print(json.dumps(result.as_json(), indent=2, sort_keys=True))
        elif args.command == "status":
            print(json.dumps(generate.backend_status(), indent=2, sort_keys=True))
        else:
            final = jobs.run_job(args.job_dir)
            print(json.dumps(final, indent=2, sort_keys=True))
    except TextureGenError as error:
        print(f"ERROR [{error.code}]: {error.message}", file=sys.stderr)
        print(f"Remediation: {error.remediation}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
