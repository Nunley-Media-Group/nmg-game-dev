#!/usr/bin/env python3
"""Check every Mobile variant under a consumer's game/assets/ folder against mobile budgets (#6).

    python3 scripts/audit-mobile-budgets.py --project-root <consumer dir> [--game-dir game]

Reads <consumer>/<game-dir>/assets/**/Mobile/nmg-asset.json and the optional
<consumer>/nmg-budgets.json overrides. Exits 0 when every Mobile variant is within budget, 1 when
any check fails, and 2 with a Remediation line when the project root is missing. A thin CLI over
nmg_game_dev.quality.mobile_budgets.check_mobile_budgets.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from nmg_game_dev.quality.mobile_budgets import OVERRIDES_NAME, check_mobile_budgets  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Mobile variants against mobile budgets.")
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--game-dir", default="game", help="Godot project folder (default: game).")
    args = parser.parse_args(argv)
    root: Path = args.project_root
    if not root.is_dir():
        print(f"ERROR: project root not found: {root}", file=sys.stderr)
        print("Remediation: pass the consumer project directory that holds game/assets/.")
        return 2
    audit = check_mobile_budgets(root / args.game_dir / "assets", root / OVERRIDES_NAME)
    for finding in audit.findings:
        print(f"FAIL [{finding.code}] {finding.message}")
        print(f"Remediation: {finding.remediation}")
    if audit.passed:
        print(f"PASS: {len(audit.assets)} Mobile variant(s) within budget")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
