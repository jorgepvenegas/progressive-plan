#!/usr/bin/env python3
"""Print a resume report for an in-progress progressive-plan master plan."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _progressive_plan_scripts() -> Path | None:
    candidates = [
        Path(__file__).resolve().parents[2] / "progressive-plan" / "scripts",
        Path(__file__).resolve().parent.parent / "progressive-plan" / "scripts",
    ]
    for candidate in candidates:
        if (candidate / "planlib.py").exists():
            return candidate
    return None


SCRIPTS = _progressive_plan_scripts()
if SCRIPTS is None:
    print(
        "error: progressive-plan is not installed next to plan-resume; "
        "install both skills together",
        file=sys.stderr,
    )
    raise SystemExit(1)
sys.path.insert(0, str(SCRIPTS))

from planlib import build_resume_report, render_resume_text  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan_dir")
    parser.add_argument(
        "--phase", help="inspect a specific phase ID instead of the resume state"
    )
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = parser.parse_args()
    plan_dir = Path(args.plan_dir).resolve()
    report = build_resume_report(plan_dir, args.phase)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render_resume_text(report))


if __name__ == "__main__":
    main()
