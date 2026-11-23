#!/usr/bin/env python3
"""Scaffold, validate, and close master/phase plans.

Commands:
    new <title> [--root docs/plans] [--slug name] [--size small|medium|large]
        [--mode standard|yolo --authorized-by "<user>"]
    add-phase <plan-dir> <name> [--depends P1] [--outcome text] [--outline]
    write-plan <plan-dir> <phase>
    approve <plan-dir> <phase> --by <user> [--when YYYY-MM-DD] [--yolo]
    reopen <plan-dir> <phase>
    record-commit <plan-dir> <phase> [--hash HASH] [--by WORKER]
    close <plan-dir> <phase> [--by WORKER] [--hash HASH]
    add-discovery <plan-dir> <phase> <discovery> --affects P2 --type note --action text
    add-decision <plan-dir> <decision> --reason text [--affects all]
    discoveries <plan-dir> <phase>
    scope <plan-dir> <phase> [--base REF] [--strict] [--json]
    report <plan-dir> [--json]
    archive <plan-dir> [--dest ARCHIVE_ROOT]
    condense <plan-dir> [--base REF] [--branch NAME] [--plans keep|drop]
        [--keep HASH]... [--tag NAME] [--dry-run] [--force] [--json]
    check <plan-dir> [--strict] [--json]
    status <plan-dir> [--json]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from planlib import (
    VALID_LEDGER_STATUSES,
    VALID_MODES,
    VALID_SIZES,
    VALID_TYPES,
    affecting_ledger,
    build_status,
    bump_int_field,
    bump_master_version,
    closeout_rows,
    closeout_verdict,
    commit_date,
    commit_exists,
    commit_is_ancestor,
    commit_subject,
    current_branch,
    decision_rows,
    expand_phase_refs,
    fail,
    field,
    git,
    git_ok,
    git_root,
    identifier_number,
    invalid_phase_refs,
    is_pending,
    ledger_rows,
    master_history,
    master_mode,
    master_version,
    phase_plan_path,
    phase_rows,
    placeholder_findings,
    read_text,
    require_master_version,
    render_report,
    render_status_text,
    section,
    set_field,
    set_field_all,
    slugify,
    stale_phase_ids,
    validate_plan,
    working_tree,
    write_text,
)

SKILL_DIR = Path(__file__).resolve().parent.parent
REFERENCES = SKILL_DIR / "references"


def render(template_name: str, **values: object) -> str:
    text = read_text(REFERENCES / template_name)
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text


def _cell(value: str, label: str) -> str:
    value = value.strip()
    if not value:
        fail(f"{label} must not be empty")
    if "|" in value or "\n" in value or "\r" in value:
        fail(f"{label} must not contain '|' or a newline")
    return value


def _warn_stale_phases(master: str) -> None:
    stale = stale_phase_ids(master)
    if stale:
        print(
            "warning: master version bumped; revalidate these phases: "
            + ", ".join(stale)
        )


def _section_bounds(
    lines: list[str], section_keyword: str, *, missing_message: str
) -> tuple[int, int]:
    start = next(
        (
            index
            for index, line in enumerate(lines)
            if re.match(r"^##\s+.*" + re.escape(section_keyword), line, re.IGNORECASE)
        ),
        None,
    )
    if start is None:
        fail(missing_message)
    end = next(
        (
            index
            for index in range(start + 1, len(lines))
            if re.match(r"^##\s+", lines[index])
        ),
        len(lines),
    )
    return start, end


def _table_header_index(
    lines: list[str],
    start: int,
    end: int,
    header_pattern: str,
    *,
    missing_message: str,
) -> int:
    header = next(
        (index for index in range(start, end) if re.match(header_pattern, lines[index])),
        None,
    )
    if header is None:
        fail(missing_message)
    return header


def _row_indices(
    lines: list[str], start: int, end: int, prefix_pattern: str
) -> list[int]:
    return [
        index
        for index in range(start, end)
        if re.match(prefix_pattern, lines[index])
    ]


def _split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _format_row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _join_lines(lines: list[str]) -> str:
    return "\n".join(lines) + "\n"


def _insert_table_row(text: str, section_keyword: str, row: str, prefix: str) -> str:
    lines = text.splitlines()
    start, end = _section_bounds(
        lines,
        section_keyword,
        missing_message=f"master plan has no {section_keyword} section",
    )
    header = _table_header_index(
        lines,
        start,
        end,
        r"\|\s*ID\s*\|",
        missing_message=f"{section_keyword} has no table header",
    )
    indices = _row_indices(lines, header + 1, end, rf"^\|\s*{prefix}\s*\|")
    insert_at = max(indices) + 1 if indices else header + 2
    lines.insert(insert_at, row)
    return _join_lines(lines)


def _set_phase_status(master: str, phase_id: str, status: str) -> str:
    lines = master.splitlines()
    for index, line in enumerate(lines):
        if re.match(rf"^\|\s*{re.escape(phase_id)}\s*\|", line):
            cells = _split_row(line)
            if len(cells) != 6:
                fail(f"master row for {phase_id} is malformed")
            cells[4] = status
            lines[index] = _format_row(cells)
            return _join_lines(lines)
    fail(f"phase {phase_id} is not in the master phase map")


def _find_phase_row(plan_dir: Path, phase_id: str) -> tuple[str, dict[str, Any]]:
    master = read_text(plan_dir / "master.md")
    row = next((item for item in phase_rows(master) if item["id"] == phase_id), None)
    if row is None:
        fail(f"phase {phase_id} is not in the master phase map")
    return master, row


def _require_plan_file(plan_dir: Path, row: dict[str, Any]) -> Path:
    plan_file = phase_plan_path(plan_dir, row)
    if not plan_file.exists():
        fail(f"{plan_file} does not exist")
    return plan_file


def _require_repo(plan_dir: Path) -> Path:
    repo = git_root(plan_dir)
    if repo is None:
        fail(f"{plan_dir} is not inside a git repository")
    return repo


def _require_commit(repo: Path, commit_hash: str) -> None:
    if not commit_exists(repo, commit_hash):
        fail(f"commit {commit_hash} does not exist in {repo}")
    if not commit_is_ancestor(repo, commit_hash):
        fail(f"commit {commit_hash} is not an ancestor of HEAD")


def _set_implemented_at(plan_text: str, repo: Path, commit_hash: str) -> str:
    if is_pending(field(plan_text, "Implemented at")):
        return set_field(
            plan_text,
            "Implemented at",
            commit_date(repo, commit_hash) or date.today().isoformat(),
        )
    return plan_text


def _commit_updates(
    files: dict[Path, str], plan_dir: Path, *, only_phase: str | None = None
) -> dict[str, Any]:
    originals = {
        path: read_text(path) if path.exists() else None for path in files
    }
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        write_text(path, text)
    result = validate_plan(plan_dir, only_phase=only_phase)
    if result["errors"]:
        for path, original in originals.items():
            if original is None:
                path.unlink(missing_ok=True)
                try:
                    path.parent.rmdir()
                except OSError:
                    pass
            else:
                write_text(path, original)
        for error in result["errors"]:
            print(f"error: {error}", file=sys.stderr)
        fail("changes rolled back because validation failed")
    return result


def cmd_new(args: argparse.Namespace) -> None:
    slug = args.slug or slugify(args.title)
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        fail("slug must use lowercase letters, digits, and hyphens")
    root_dir = Path(args.root)
    plan_dir = root_dir / slug
    resolved_root = root_dir.resolve()
    resolved_plan = plan_dir.resolve()
    if resolved_plan != resolved_root and resolved_root not in resolved_plan.parents:
        fail(f"{slug} escapes {root_dir}")
    if plan_dir.exists():
        fail(f"{plan_dir} already exists")
    authorized_by = "none"
    if args.mode == "yolo":
        if is_pending(args.authorized_by) or placeholder_findings(args.authorized_by or ""):
            fail('--mode yolo requires --authorized-by "<user>"')
        authorized_by = f"{args.authorized_by}, {date.today().isoformat()}"
    (plan_dir / "phases").mkdir(parents=True)
    template_name = (
        "master-template-small.md" if args.size == "small" else "master-template.md"
    )
    master = render(
        template_name,
        TITLE=args.title,
        SLUG=slug,
        DATE=date.today().isoformat(),
        SIZE=args.size,
        MODE=args.mode,
        MODE_AUTHORIZED_BY=authorized_by,
        PLAN_DIR=plan_dir.as_posix(),
        BRANCH=f"plan/{slug}",
    )
    write_text(plan_dir / "master.md", master)
    print(f"created {plan_dir}/master.md")
    repo = git_root(plan_dir)
    if repo is not None:
        branch = current_branch(plan_dir)
        expected = f"plan/{slug}"
        if branch != expected:
            print(
                f"warning: current branch is {branch}; create or switch to {expected} "
                "before editing the plan"
            )
        dirty = working_tree(plan_dir)
        if dirty:
            print(
                "warning: working tree has uncommitted changes; review them before "
                "committing plan files"
            )
    print(
        f'next: python3 {Path(__file__)} add-phase {plan_dir} "<Phase name>" '
        "--depends none"
    )
    if args.mode == "yolo":
        print(
            "yolo: create the plan branch and open the draft PR before implementation; "
            "auto-approve each checked phase with approve --yolo"
        )


def cmd_add_phase(args: argparse.Namespace) -> None:
    plan_dir = Path(args.plan_dir)
    master_file = plan_dir / "master.md"
    if not master_file.exists():
        fail(f"{master_file} does not exist")
    master = read_text(master_file)
    phase_template = (
        "phase-plan-template-small.md"
        if field(master, "Size") == "small"
        else "phase-plan-template.md"
    )
    rows = phase_rows(master)
    number = max((int(row["id"][1:]) for row in rows), default=0) + 1
    phase_id = f"P{number}"
    version = require_master_version(master)
    new_version = version + 1
    master = set_field(master, "Master version", str(new_version))

    name = _cell(args.name, "phase name")
    outcome = _cell(args.outcome, "phase outcome")
    depends = _cell(args.depends, "depends value")
    plan_cell = "pending"
    updates: dict[Path, str] = {}
    phase_dir = plan_dir / "phases" / f"{number:02d}-{slugify(name)}"
    if not args.outline:
        if phase_dir.exists() and any(phase_dir.iterdir()):
            fail(f"{phase_dir} already exists")
        plan_text = render(
            phase_template,
            PHASE_ID=phase_id,
            PHASE_NAME=name,
            SLUG=plan_dir.name,
            DATE=date.today().isoformat(),
            DEPENDS_ON=depends,
            MASTER_VERSION=new_version,
        )
        updates[phase_dir / "plan.md"] = plan_text
        relative = f"phases/{phase_dir.name}/plan.md"
        plan_cell = f"[plan]({relative})"

    row = (
        f"| {phase_id} | {name} | {outcome} | {depends} "
        f"| planned | {plan_cell} |"
    )
    master = _insert_table_row(master, "Phase map", row, r"P\d+")
    updates[master_file] = master
    _commit_updates(updates, plan_dir, only_phase=phase_id)
    if args.outline:
        print(f"added outline {phase_id} to {master_file}")
        print(f"next: python3 {Path(__file__)} write-plan {plan_dir} {phase_id}")
    else:
        print(f"created {plan_dir / 'phases' / f'{number:02d}-{slugify(name)}'}/plan.md")
        print(f"added {phase_id} to {master_file}")
    _warn_stale_phases(master)


def cmd_write_plan(args: argparse.Namespace) -> None:
    plan_dir = Path(args.plan_dir)
    master, row = _find_phase_row(plan_dir, args.phase)
    if row["status"] != "planned":
        fail(f"phase {args.phase} is {row['status']}; only planned phases get a new plan")
    if str(row["plan"]).strip().lower() not in {"", "pending", "not written", "—", "-"}:
        fail(f"phase {args.phase} already has a plan: {row['plan']}")
    version = require_master_version(master)
    number = int(row["id"][1:])
    name = row["name"]
    phase_dir = plan_dir / "phases" / f"{number:02d}-{slugify(name)}"
    if phase_dir.exists() and any(phase_dir.iterdir()):
        fail(f"{phase_dir} already exists")
    phase_dir.mkdir(parents=True, exist_ok=True)
    phase_template = (
        "phase-plan-template-small.md"
        if field(master, "Size") == "small"
        else "phase-plan-template.md"
    )
    plan_text = render(
        phase_template,
        PHASE_ID=row["id"],
        PHASE_NAME=name,
        SLUG=plan_dir.name,
        DATE=date.today().isoformat(),
        DEPENDS_ON=row["depends"],
        MASTER_VERSION=version,
    )
    plan_file = phase_dir / "plan.md"
    relative = f"phases/{phase_dir.name}/plan.md"
    new_row = (
        f"| {row['id']} | {name} | {row['outcome']} | {row['depends']} "
        f"| planned | [plan]({relative}) |"
    )
    master = master.replace(row["raw"], new_row, 1)
    _commit_updates(
        {plan_file: plan_text, plan_dir / "master.md": master},
        plan_dir,
        only_phase=row["id"],
    )
    print(f"created {plan_file}")
    print(f"next: fill the plan, run check, then approve {row['id']}")


def cmd_approve(args: argparse.Namespace) -> None:
    plan_dir = Path(args.plan_dir)
    if is_pending(args.by):
        fail("--by must name the approving user")
    master, row = _find_phase_row(plan_dir, args.phase)
    if args.yolo:
        if master_mode(master) != "yolo":
            fail("--yolo requires a master plan with '- Mode: yolo'")
        if is_pending(field(master, "Mode authorized by")):
            fail("master records yolo mode without '- Mode authorized by'")
    if row["status"] in {"done", "superseded"}:
        fail(f"phase {args.phase} is already {row['status']}")
    if row["status"] == "in_progress":
        fail(f"phase {args.phase} is already in progress")
    plan_file = _require_plan_file(plan_dir, row)
    plan_text = read_text(plan_file)

    unmet: list[str] = []
    for dependency in sorted(expand_phase_refs(str(row["depends"]))):
        dependency_row = next(
            (item for item in phase_rows(master) if item["id"] == dependency), None
        )
        if dependency_row is None:
            fail(f"phase {args.phase} depends on unknown phase {dependency}")
        if dependency_row["status"] != "done":
            unmet.append(dependency)
    parallel_safe = (field(plan_text, "Parallel safe") or "no").strip().lower()
    if unmet and parallel_safe not in {"yes", "true"}:
        if args.allow_unmet_dependency:
            plan_text = set_field(plan_text, "Parallel safe", "yes")
            parallel_safe = "yes"
        else:
            fail(
                f"phase {args.phase} depends on {', '.join(unmet)}, which are not done; "
                "use --allow-unmet-dependency for intentional parallel work"
            )

    version = master_version(master)
    plan_version = field(plan_text, "Validated against master version")
    try:
        plan_version_int = int(plan_version) if plan_version is not None else None
    except ValueError:
        plan_version_int = None
    if version is not None and plan_version_int != version:
        fail(
            f"phase {args.phase} is validated against master v{plan_version}, "
            f"master is v{version}; revalidate the phase plan first"
        )

    precheck = validate_plan(
        plan_dir, only_phase=args.phase, for_approval=True
    )
    if precheck["errors"]:
        for error in precheck["errors"]:
            print(f"error: {error}", file=sys.stderr)
        fail(f"phase {args.phase} is not ready for approval")

    plan_text = set_field(plan_text, "Status", "ready")
    approved_by = f"{args.by} (yolo)" if args.yolo else args.by
    plan_text = set_field(plan_text, "Approved by", approved_by)
    plan_text = set_field(plan_text, "Approved at", args.when)
    plan_text = set_field(plan_text, "Commit", "pending")
    plan_text = set_field(plan_text, "Implemented by", "pending")
    plan_text = set_field(plan_text, "Implemented at", "pending")
    if field(plan_text, "Implementation mode") != "coordinator-exception":
        plan_text = set_field(plan_text, "Exception approved by", "none")
        plan_text = set_field(plan_text, "Exception reason", "none")

    master = _set_phase_status(master, args.phase, "ready")
    if field(master, "Status") == "draft":
        master = set_field(master, "Status", "active")
    _commit_updates(
        {plan_file: plan_text, plan_dir / "master.md": master},
        plan_dir,
        only_phase=args.phase,
    )
    print(f"approved {args.phase} by {approved_by} on {args.when}")
    print(f"phase plan: {plan_file}")
    print(f"master: {plan_dir / 'master.md'}")


def cmd_reopen(args: argparse.Namespace) -> None:
    plan_dir = Path(args.plan_dir)
    master, row = _find_phase_row(plan_dir, args.phase)
    if row["status"] == "superseded":
        fail(f"phase {args.phase} is superseded")
    plan_file = _require_plan_file(plan_dir, row)
    plan_text = read_text(plan_file)
    plan_text = set_field(plan_text, "Status", "draft")
    plan_text = set_field(plan_text, "Approved by", "pending")
    plan_text = set_field(plan_text, "Approved at", "pending")
    plan_text = set_field(plan_text, "Commit", "pending")
    plan_text = set_field(plan_text, "Implemented by", "pending")
    plan_text = set_field(plan_text, "Implemented at", "pending")
    plan_text = set_field(plan_text, "Exception approved by", "none")
    plan_text = set_field(plan_text, "Exception reason", "none")
    plan_text = bump_int_field(plan_text, "Plan version", 1)
    master = _set_phase_status(master, args.phase, "planned")
    other_active = any(
        item["status"] in {"ready", "in_progress", "done", "blocked", "needs_replan"}
        for item in phase_rows(master)
    )
    master = set_field(master, "Status", "active" if other_active else "draft")
    _commit_updates(
        {plan_file: plan_text, plan_dir / "master.md": master},
        plan_dir,
        only_phase=args.phase,
    )
    print(f"reopened {args.phase} for refinement")
    print(f"phase plan: {plan_file}")


def cmd_record_commit(args: argparse.Namespace) -> None:
    plan_dir = Path(args.plan_dir)
    master, row = _find_phase_row(plan_dir, args.phase)
    if row["status"] not in {"in_progress", "done"}:
        fail(f"phase {args.phase} is {row['status']}; record a commit only for in_progress or done")
    plan_file = _require_plan_file(plan_dir, row)
    repo = _require_repo(plan_dir)

    commit_hash = args.hash
    if not commit_hash:
        commit_hash = git(repo, "rev-parse", "--short", "HEAD")
        if not commit_hash:
            fail(f"could not read HEAD in {repo}")
        subject = commit_subject(repo, commit_hash) or ""
        if not re.match(rf"^{re.escape(args.phase)}:\s", subject):
            fail(
                f"HEAD ({commit_hash}) does not look like the {args.phase} commit "
                f"(subject: {subject!r}); pass --hash with the phase commit"
            )
    _require_commit(repo, commit_hash)

    plan_text = read_text(plan_file)
    plan_text = set_field_all(plan_text, "Commit", commit_hash)
    if args.by:
        plan_text = set_field(plan_text, "Implemented by", args.by)
    plan_text = _set_implemented_at(plan_text, repo, commit_hash)
    write_text(plan_file, plan_text)

    master_text = read_text(plan_dir / "master.md")
    history = section(master_text, "Closeout history")
    history_lines = history.splitlines()
    updated = False
    for index, line in enumerate(history_lines):
        if re.match(rf"^\|\s*{re.escape(args.phase)}\s*\|", line):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) == 5:
                cells.insert(4, commit_hash)
            elif len(cells) >= 6:
                cells[4] = commit_hash
            else:
                continue
            history_lines[index] = "| " + " | ".join(cells) + " |"
            updated = True
            break
    if updated:
        new_history = "\n".join(history_lines)
        if history.endswith("\n"):
            new_history += "\n"
        master_text = master_text.replace(history, new_history, 1)
        write_text(plan_dir / "master.md", master_text)
    else:
        print(
            f"warning: {args.phase} has no closeout-history row; "
            "commit recorded in the phase plan only"
        )

    print(f"recorded commit {commit_hash} for {args.phase}")
    print(f"phase plan: {plan_file}")
    if updated:
        print(f"master: {plan_dir / 'master.md'}")


def _upsert_closeout_history(
    master: str,
    phase_id: str,
    day: str,
    verdict: str,
    criteria: str,
    commit: str,
    report_link: str,
) -> str:
    lines = master.splitlines()
    start, end = _section_bounds(
        lines,
        "Closeout history",
        missing_message="master plan has no Closeout history section",
    )
    header = _table_header_index(
        lines,
        start,
        end,
        r"\|\s*Phase\s*\|",
        missing_message="Closeout history has no table header",
    )
    new_row = (
        f"| {phase_id} | {day} | {verdict} | {criteria} | {commit} | {report_link} |"
    )
    for index in range(header + 1, end):
        if re.match(rf"^\|\s*{re.escape(phase_id)}\s*\|", lines[index]):
            lines[index] = new_row
            return _join_lines(lines)
    indices = _row_indices(lines, header + 1, end, r"^\|\s*P\d+\s*\|")
    insert_at = max(indices) + 1 if indices else header + 2
    lines.insert(insert_at, new_row)
    return _join_lines(lines)


def cmd_close(args: argparse.Namespace) -> None:
    plan_dir = Path(args.plan_dir)
    master, row = _find_phase_row(plan_dir, args.phase)
    if row["status"] != "in_progress":
        fail(f"phase {args.phase} is {row['status']}; close only an in_progress phase")
    plan_file = _require_plan_file(plan_dir, row)
    repo = _require_repo(plan_dir)

    plan_text = read_text(plan_file)
    if args.hash:
        _require_commit(repo, args.hash)
        plan_text = set_field_all(plan_text, "Commit", args.hash)
    commit_hash = field(plan_text, "Commit")
    if is_pending(commit_hash):
        fail(f"phase {args.phase} has no recorded commit; run record-commit first")
    _require_commit(repo, str(commit_hash))
    if args.by:
        plan_text = set_field(plan_text, "Implemented by", args.by)
    if is_pending(field(plan_text, "Implemented by")):
        fail("set Implemented by with --by before closing the phase")
    plan_text = _set_implemented_at(plan_text, repo, str(commit_hash))
    plan_text = set_field(plan_text, "Status", "done")

    verdict = closeout_verdict(plan_text) or ""
    if verdict != "addressed":
        fail(f"phase {args.phase} verdict is '{verdict or 'missing'}'; close requires addressed")
    met = [
        item["criterion"]
        for item in closeout_rows(plan_text)
        if item["verdict"] == "met" and item["criterion"].startswith("A")
    ]
    criteria = ", ".join(met) if met else "none"
    relative = plan_file.relative_to(plan_dir).as_posix()
    report_link = f"[report]({relative})"

    master = _set_phase_status(master, args.phase, "done")
    master = _upsert_closeout_history(
        master,
        args.phase,
        date.today().isoformat(),
        verdict,
        criteria,
        str(commit_hash),
        report_link,
    )
    rows_after = phase_rows(master)
    master = set_field(
        master,
        "Status",
        "complete" if rows_after and all(item["status"] == "done" for item in rows_after) else "active",
    )
    _commit_updates(
        {plan_file: plan_text, plan_dir / "master.md": master}, plan_dir
    )
    print(f"closed {args.phase} with verdict {verdict}")
    print(f"phase plan: {plan_file}")
    print(f"commit: {commit_hash}")


def cmd_archive(args: argparse.Namespace) -> None:
    plan_dir = Path(args.plan_dir)
    master_file = plan_dir / "master.md"
    if not master_file.exists():
        fail(f"{master_file} does not exist")
    rows = phase_rows(read_text(master_file))
    if not rows or not all(row["status"] == "done" for row in rows):
        fail(
            f"{plan_dir} is not complete; "
            "archive only a plan whose phases are all done"
        )
    archive_root = Path(args.dest) if args.dest else plan_dir.parent / "archive"
    target = archive_root / plan_dir.name
    resolved_plan = plan_dir.resolve()
    resolved_target = target.resolve()
    if resolved_target == resolved_plan or resolved_plan in resolved_target.parents:
        fail(f"{target} must not be inside {plan_dir}")
    if target.exists():
        fail(f"{target} already exists")

    archive_root.mkdir(parents=True, exist_ok=True)
    shutil.move(str(plan_dir), str(target))

    repo = git_root(target)
    try:
        display = target.resolve().relative_to(repo.resolve()).as_posix()
    except (AttributeError, ValueError):
        display = target.as_posix()
    master = read_text(target / "master.md")
    master = set_field(master, "Plan directory", f"`{display}`")
    write_text(target / "master.md", master)
    print(f"archived {plan_dir} -> {target}")
    print("next: commit the move and push if a draft PR is open")


def _git_checked(
    repo: Path,
    *args: str,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        input=input_text,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        fail(f"git {' '.join(args)} failed: {detail}")
    return result


def _resolve_commit(repo: Path, value: str, label: str) -> str:
    full = git(repo, "rev-parse", "--verify", f"{value}^{{commit}}")
    if not full:
        fail(f"{label}: unknown commit {value!r}")
    return full


def _condense_base(repo: Path, explicit: str | None) -> str:
    if explicit:
        base = _resolve_commit(repo, explicit, "--base")
    else:
        candidates: list[str] = []
        origin_head = git(repo, "symbolic-ref", "refs/remotes/origin/HEAD")
        if origin_head:
            candidates.append(origin_head)
        candidates.extend(
            [
                "refs/remotes/origin/main",
                "refs/remotes/origin/master",
                "refs/heads/main",
                "refs/heads/master",
            ]
        )
        base = ""
        for ref in candidates:
            if not git_ok(repo, "rev-parse", "--verify", ref):
                continue
            merge_base = git(repo, "merge-base", "HEAD", ref)
            if merge_base:
                base = merge_base
                break
        if not base:
            fail("could not determine the plan base; pass --base <commit>")
    if not commit_is_ancestor(repo, base, "HEAD"):
        fail(f"base {base[:12]} is not an ancestor of HEAD")
    head = _git_checked(repo, "rev-parse", "HEAD").stdout.strip()
    if base == head:
        fail("base equals HEAD; there is nothing to condense")
    return base


def _tree_without_plans(
    repo: Path, commit: str, plan_rel: str | None, index_file: Path
) -> str:
    env = os.environ.copy()
    env["GIT_INDEX_FILE"] = str(index_file)
    _git_checked(repo, "read-tree", f"{commit}^{{tree}}", env=env)
    if plan_rel:
        _git_checked(
            repo,
            "rm",
            "-r",
            "-f",
            "--cached",
            "-q",
            "--ignore-unmatch",
            "--",
            plan_rel,
            env=env,
        )
    return _git_checked(repo, "write-tree", env=env).stdout.strip()


def _commit_identity(repo: Path, commit: str) -> tuple[str, str, str]:
    output = _git_checked(
        repo, "show", "-s", "--format=%an%n%ae%n%aI", commit
    ).stdout.splitlines()
    if len(output) < 3:
        fail(f"could not read author identity from {commit}")
    return output[0], output[1], output[2]


def _write_condensed_commit(
    repo: Path, tree: str, parent: str, message: str, source: str
) -> str:
    name, email, when = _commit_identity(repo, source)
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": name,
            "GIT_AUTHOR_EMAIL": email,
            "GIT_AUTHOR_DATE": when,
            "GIT_COMMITTER_NAME": name,
            "GIT_COMMITTER_EMAIL": email,
            "GIT_COMMITTER_DATE": when,
        }
    )
    return _git_checked(
        repo,
        "commit-tree",
        tree,
        "-p",
        parent,
        env=env,
        input_text=message + "\n",
    ).stdout.strip()


def _condense_subject(repo: Path, entry: dict[str, Any]) -> str:
    if entry["kind"] == "phase":
        row = entry["phase"]
        name = str(row.get("name") or "").strip()
        fallback = commit_subject(repo, entry["commit"]) or entry["commit"][:7]
        return f"{row['id']}: {name or fallback}"
    if entry["kind"] == "keep":
        return commit_subject(repo, entry["commit"]) or "checkpoint"
    return "plan: record final state"


def _rewrite_plan_hashes(
    repo: Path,
    tip: str,
    plan_rel: str,
    mappings: list[tuple[str, str, str]],
    index_file: Path,
    source: str,
) -> str | None:
    replacements: list[tuple[str, str]] = []
    for recorded, old_full, new_full in mappings:
        new_short = git(repo, "rev-parse", "--short", new_full) or new_full[:7]
        for old in {recorded, old_full}:
            if old and old != new_short:
                replacements.append((old, new_short))
    if not replacements:
        return None
    replacements.sort(key=lambda item: len(item[0]), reverse=True)

    env = os.environ.copy()
    env["GIT_INDEX_FILE"] = str(index_file)
    _git_checked(repo, "read-tree", f"{tip}^{{tree}}", env=env)
    paths = _git_checked(
        repo, "ls-tree", "-r", "--name-only", tip, "--", plan_rel
    ).stdout.splitlines()

    changed = False
    for path in paths:
        original = _git_checked(repo, "show", f"{tip}:{path}").stdout
        updated = original
        for old, new in replacements:
            updated = re.sub(
                rf"(?<![0-9a-fA-F]){re.escape(old)}(?![0-9a-fA-F])",
                new,
                updated,
            )
        if updated == original:
            continue
        blob = _git_checked(repo, "hash-object", "-w", "--stdin", input_text=updated)
        _git_checked(
            repo,
            "update-index",
            "--add",
            "--cacheinfo",
            "100644",
            blob.stdout.strip(),
            path,
            env=env,
        )
        changed = True
    if not changed:
        return None
    tree = _git_checked(repo, "write-tree", env=env).stdout.strip()
    return _write_condensed_commit(
        repo, tree, tip, "plan: record condensed commits", source
    )


def cmd_condense(args: argparse.Namespace) -> None:
    plan_dir = Path(args.plan_dir)
    master_file = plan_dir / "master.md"
    if not master_file.exists():
        fail(f"{master_file} does not exist")
    master = read_text(master_file)
    if master_history(master) == "keep" and not args.force:
        fail(
            "master records History: keep; condense would discard the audit trail. "
            "Pass --force only after deciding to rewrite the branch."
        )

    rows = phase_rows(master)
    if not rows:
        fail("master has no phases to condense")
    malformed = [row["id"] for row in rows if row.get("malformed")]
    if malformed:
        fail(f"master phase map is malformed for {', '.join(malformed)}")
    pending = [
        row["id"] for row in rows if row["status"] not in {"done", "superseded"}
    ]
    if pending:
        fail(
            "condense requires every phase to be done or superseded; "
            f"pending: {', '.join(pending)}"
        )

    repo = git_root(plan_dir)
    if repo is None:
        fail("condense requires a git repository")
    if working_tree(plan_dir):
        fail("working tree is not clean; commit or stash changes before condensing")
    try:
        plan_rel = plan_dir.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        fail("plan directory is outside the repository")

    current = current_branch(plan_dir)
    recorded_branch = field(master, "Branch")
    if (
        recorded_branch
        and current
        and current != "HEAD"
        and current != recorded_branch
    ):
        print(
            f"warning: master records branch {recorded_branch}; "
            f"current branch is {current}",
            file=sys.stderr,
        )
    default_branch = (
        f"{current}-condensed" if current and current != "HEAD" else "plan-condensed"
    )
    branch = args.branch or default_branch
    if branch == current:
        fail("the condensed branch must differ from the current branch")
    if git_ok(repo, "rev-parse", "--verify", f"refs/heads/{branch}") and not args.force:
        fail(f"branch {branch} already exists; pass --force to replace it")
    if (
        args.tag
        and git_ok(repo, "rev-parse", "--verify", f"refs/tags/{args.tag}")
        and not args.force
    ):
        fail(f"tag {args.tag} already exists; pass --force to replace it")

    base = _condense_base(repo, args.base)
    head = _git_checked(repo, "rev-parse", "HEAD").stdout.strip()
    rev_list = _git_checked(
        repo, "rev-list", "--reverse", f"{base}..HEAD"
    ).stdout.split()
    position = {commit: index for index, commit in enumerate(rev_list)}

    entries: list[dict[str, Any]] = []
    mappings: list[tuple[str, str]] = []
    for row in rows:
        if row["status"] == "superseded":
            continue
        plan_file = phase_plan_path(plan_dir, row)
        if not plan_file.exists():
            fail(f"{row['id']}: phase plan {plan_file} does not exist")
        recorded = field(read_text(plan_file), "Commit")
        if is_pending(recorded):
            fail(f"{row['id']}: no recorded commit; run record-commit first")
        full = _resolve_commit(repo, recorded or "", row["id"])
        if full not in position:
            fail(f"{row['id']}: commit {recorded} is not between base and HEAD")
        entries.append(
            {"commit": full, "kind": "phase", "phase": row, "recorded": recorded}
        )
        mappings.append((recorded or "", full))

    for value in args.keep:
        full = _resolve_commit(repo, value, "--keep")
        if full not in position:
            fail(f"--keep {value}: commit is not between base and HEAD")
        entries.append({"commit": full, "kind": "keep", "recorded": value})

    entries.append({"commit": head, "kind": "final"})
    priority = {"phase": 0, "keep": 1, "final": 2}
    by_commit: dict[str, dict[str, Any]] = {}
    for entry in entries:
        existing = by_commit.get(entry["commit"])
        if existing is None or priority[entry["kind"]] < priority[existing["kind"]]:
            by_commit[entry["commit"]] = entry
    ordered = sorted(by_commit.values(), key=lambda item: position[item["commit"]])

    drop_plans = args.plans == "drop"
    with tempfile.TemporaryDirectory(prefix="pplan-condense-") as tmp:
        index_file = Path(tmp) / "index"
        expected_tree = _tree_without_plans(
            repo, head, plan_rel if drop_plans else None, index_file
        )
        parent = base
        previous_tree = _tree_without_plans(
            repo, base, plan_rel if drop_plans else None, index_file
        )
        new_commits: list[dict[str, Any]] = []
        new_tip: str | None = None
        hash_rewrite: str | None = None
        phase_new: dict[str, str] = {}
        for entry in ordered:
            tree = _tree_without_plans(
                repo, entry["commit"], plan_rel if drop_plans else None, index_file
            )
            if tree == previous_tree and entry["kind"] != "phase":
                continue
            subject = _condense_subject(repo, entry)
            item = {
                "source": entry["commit"],
                "kind": entry["kind"],
                "subject": subject,
                "phase": entry.get("phase", {}).get("id"),
            }
            if not args.dry_run:
                new = _write_condensed_commit(
                    repo, tree, parent, subject, entry["commit"]
                )
                item["new"] = new
                parent = new
                new_tip = new
                if entry["kind"] == "phase":
                    phase_new[entry["commit"]] = new
            else:
                item["new"] = None
            new_commits.append(item)
            previous_tree = tree

        if previous_tree != expected_tree:
            fail(
                "condensed history does not reproduce the final tree; "
                "the plan commits are stale or out of order"
            )

        if not new_commits:
            fail("nothing to condense; the branch already has one product state")

        if not args.dry_run:
            if not drop_plans:
                replacement_mappings = [
                    (recorded, old, phase_new[old])
                    for recorded, old in mappings
                    if old in phase_new
                ]
                hash_rewrite = _rewrite_plan_hashes(
                    repo,
                    parent,
                    plan_rel,
                    replacement_mappings,
                    index_file,
                    head,
                )
                if hash_rewrite:
                    new_tip = hash_rewrite
                    new_commits.append(
                        {
                            "source": head,
                            "kind": "plan",
                            "subject": "plan: record condensed commits",
                            "phase": None,
                            "new": hash_rewrite,
                        }
                    )
            if new_tip is None:
                fail("condense produced no commits")
            _git_checked(repo, "branch", "-f", branch, new_tip)
            if args.tag:
                if git_ok(repo, "rev-parse", "--verify", f"refs/tags/{args.tag}"):
                    _git_checked(repo, "tag", "-f", args.tag, head)
                else:
                    _git_checked(repo, "tag", args.tag, head)
        else:
            new_tip = None
            if not drop_plans and any(
                item["kind"] == "phase" for item in new_commits
            ):
                new_commits.append(
                    {
                        "source": head,
                        "kind": "plan",
                        "subject": "plan: record condensed commits",
                        "phase": None,
                        "new": None,
                    }
                )

    payload = {
        "branch": branch,
        "current_branch": current,
        "base": base,
        "old_tip": head,
        "new_tip": new_tip,
        "old_count": len(rev_list),
        "new_count": len(new_commits),
        "plans": args.plans,
        "tag": args.tag,
        "dry_run": args.dry_run,
        "commits": new_commits,
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    verb = "would condense" if args.dry_run else "condensed"
    print(f"{verb} {len(rev_list)} commits to {len(new_commits)} on {branch}")
    print(f"base: {base[:12]}  old tip: {head[:12]}")
    if new_tip:
        print(f"new tip: {new_tip[:12]}")
    if args.tag:
        print(f"trail tag: {args.tag} -> {head[:12]}")
    print("product tree unchanged")
    if not drop_plans:
        print(
            "plan files kept; recorded phase hashes rewritten"
            if hash_rewrite
            else "plan files kept"
        )
    else:
        print(f"plan files dropped from the new history: {plan_rel}")
    if args.dry_run:
        print("dry run: no branch, tag, or commit was created")
    else:
        current_name = current if current and current != "HEAD" else None
        print("next:")
        print(f"  git switch {branch}")
        if not drop_plans:
            print(f"  python3 {Path(__file__)} check {plan_dir}")
        print("  run the plan's verification commands")
        if not args.tag:
            print(f"  git tag {current_name or branch}-trail {head}")
        if current_name:
            print(f"  git branch -f {current_name} {branch}")
            print(f"  git switch {current_name}")
            print("  git push --force-with-lease")
        else:
            print(
                f"  git push --force-with-lease origin {branch}:<remote-branch>"
            )
    print("commits:")
    for item in new_commits:
        short = item["new"][:7] if item["new"] else "pending"
        print(f"  {short} {item['subject']}")


def cmd_check(args: argparse.Namespace) -> None:
    plan_dir = Path(args.plan_dir)
    result = validate_plan(plan_dir, strict=args.strict)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for warning in result["warnings"]:
            print(f"warning: {warning}")
        for error in result["errors"]:
            print(f"error: {error}")
        if not result["errors"]:
            master = read_text(plan_dir / "master.md")
            rows = phase_rows(master)
            print(
                f"ok: {plan_dir} ({len(rows)} phase(s), "
                f"master v{master_version(master)})"
            )
    if result["errors"]:
        raise SystemExit(1)


def cmd_discoveries(args: argparse.Namespace) -> None:
    plan_dir = Path(args.plan_dir)
    master = read_text(plan_dir / "master.md")
    rows = phase_rows(master)
    if not any(row["id"] == args.phase for row in rows):
        fail(f"phase {args.phase} is not in the master phase map")
    entries = affecting_ledger(ledger_rows(master), args.phase)
    if not entries:
        print(f"no ledger rows affect {args.phase}")
        return
    print(f"Ledger rows affecting {args.phase}:")
    for entry in entries:
        print(
            f"- {entry['id']} ({entry.get('affects', '')}, {entry.get('type', '')}, "
            f"{entry.get('status', '')}): {entry.get('discovery', '')}"
        )
        print(f"  action: {entry.get('action', '')}")


def _validate_discovery_args(
    master: str, phase: str, affects: str, entry_type: str, status: str, action: str
) -> None:
    phase_ids = {row["id"] for row in phase_rows(master) if not row["malformed"]}
    if phase not in phase_ids and phase != "master":
        fail(f"phase {phase} is not in the master phase map")
    for token in invalid_phase_refs(affects):
        fail(f"invalid Affects value '{token}'")
    refs = expand_phase_refs(affects)
    if not refs:
        fail("Affects must name at least one phase or 'all'")
    for ref in refs:
        if ref != "all" and ref not in phase_ids:
            fail(f"Affects names unknown phase {ref}")
    if entry_type not in VALID_TYPES:
        fail(f"invalid discovery type '{entry_type}'")
    if status not in VALID_LEDGER_STATUSES:
        fail(f"invalid discovery status '{status}'")
    if not action.strip():
        fail("action must not be empty")


def cmd_add_discovery(args: argparse.Namespace) -> None:
    plan_dir = Path(args.plan_dir)
    master_file = plan_dir / "master.md"
    master = read_text(master_file)
    _validate_discovery_args(
        master, args.phase, args.affects, args.type, args.status, args.action
    )
    discovery = _cell(args.discovery, "discovery")
    action = _cell(args.action, "action")
    entries = ledger_rows(master)
    number = max(
        (identifier_number(entry["id"]) for entry in entries), default=0
    ) + 1
    entry_id = f"L{number}"
    row = (
        f"| {entry_id} | {date.today().isoformat()} | {args.phase} | {args.affects} | "
        f"{discovery} | {args.type} | {action} | {args.status} |"
    )
    master = _insert_table_row(master, "Discovery ledger", row, r"[A-Z]\d+")
    if not args.no_bump:
        master, _ = bump_master_version(master)
    write_text(master_file, master)
    print(f"added {entry_id} to {master_file}")
    if not args.no_bump:
        _warn_stale_phases(master)


def cmd_add_decision(args: argparse.Namespace) -> None:
    plan_dir = Path(args.plan_dir)
    master_file = plan_dir / "master.md"
    master = read_text(master_file)
    phase_ids = {row["id"] for row in phase_rows(master) if not row["malformed"]}
    for token in invalid_phase_refs(args.affects):
        fail(f"invalid Affects value '{token}'")
    for ref in expand_phase_refs(args.affects):
        if ref != "all" and ref not in phase_ids:
            fail(f"Affects names unknown phase {ref}")
    decision = _cell(args.decision, "decision")
    reason = _cell(args.reason, "reason")
    rows = decision_rows(master)
    number = max(
        (identifier_number(row["id"]) for row in rows), default=0
    ) + 1
    decision_id = f"C{number}"
    row = (
        f"| {decision_id} | {date.today().isoformat()} | {decision} | "
        f"{reason} | {args.affects} |"
    )
    master = _insert_table_row(master, "Cross-phase decisions", row, r"C\d+")
    master, _ = bump_master_version(master)
    write_text(master_file, master)
    print(f"added {decision_id} to {master_file}")
    _warn_stale_phases(master)


def cmd_status(args: argparse.Namespace) -> None:
    plan_dir = Path(args.plan_dir)
    status = build_status(plan_dir)
    if args.json:
        print(json.dumps(status, indent=2))
    else:
        print(render_status_text(status))
    if status.get("error"):
        raise SystemExit(1)


def _plan_files(plan_text: str) -> set[str]:
    files: set[str] = set()
    in_files = False
    for line in section(plan_text, "Steps").splitlines():
        stripped = line.strip()
        if stripped.startswith("- Files:"):
            in_files = True
            continue
        if in_files:
            if re.match(r"^\s{2,}-\s", line):
                match = re.search(r"`([^`]+)`", line)
                if match:
                    files.add(match.group(1).strip())
            elif stripped.startswith("- "):
                in_files = False
    return files


def _resolve_base(plan_dir: Path, row: dict[str, Any], explicit: str | None) -> str:
    if explicit:
        return explicit
    master = read_text(plan_dir / "master.md")
    rows = phase_rows(master)
    current = int(row["id"][1:])
    previous = sorted(
        (item for item in rows if int(item["id"][1:]) < current),
        key=lambda item: int(item["id"][1:]),
        reverse=True,
    )
    for item in previous:
        if item["status"] != "done":
            continue
        plan_file = phase_plan_path(plan_dir, item)
        if not plan_file.exists():
            continue
        commit = field(read_text(plan_file), "Commit")
        if commit and not is_pending(commit):
            return commit
    repo = git_root(plan_dir)
    if repo is not None:
        for ref in ("origin/HEAD", "main", "master"):
            merge_base = git(repo, "merge-base", "HEAD", ref)
            if merge_base:
                return merge_base
    return "HEAD~1"


def cmd_scope(args: argparse.Namespace) -> None:
    plan_dir = Path(args.plan_dir)
    _master, row = _find_phase_row(plan_dir, args.phase)
    plan_file = _require_plan_file(plan_dir, row)
    expected = _plan_files(read_text(plan_file))
    repo = _require_repo(plan_dir)
    base = _resolve_base(plan_dir, row, args.base)
    changed = git(repo, "diff", "--name-only", f"{base}..HEAD")
    if changed is None:
        fail(f"could not diff {base}..HEAD in {repo}")
    changed_files = [line for line in changed.splitlines() if line.strip()]
    try:
        plan_relative = plan_dir.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        fail(f"{plan_dir} is outside the git repository {repo}")
    out_of_scope = [
        path
        for path in changed_files
        if path not in expected and not path.startswith(plan_relative + "/")
    ]
    result = {
        "phase": args.phase,
        "base": base,
        "expected": sorted(expected),
        "changed": changed_files,
        "out_of_scope": out_of_scope,
    }
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Scope check {args.phase}")
        print(f"Base: {base}")
        print(f"Expected files: {', '.join(sorted(expected)) or 'none parsed'}")
        print(f"Changed files: {len(changed_files)}")
        if expected:
            print(
                "Out of scope: "
                + (", ".join(out_of_scope) if out_of_scope else "none")
            )
        else:
            print("Out of scope: not checked (no Files entries parsed)")
        if not expected:
            print("warning: no phase files parsed; add `Files:` entries to each step")
    if args.strict and out_of_scope:
        raise SystemExit(1)


def cmd_report(args: argparse.Namespace) -> None:
    plan_dir = Path(args.plan_dir)
    status = build_status(plan_dir)
    if args.json:
        print(json.dumps(status, indent=2))
    else:
        print(render_report(plan_dir))
    if status.get("error"):
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    new = sub.add_parser("new", help="create a master plan directory")
    new.add_argument("title")
    new.add_argument("--root", default="docs/plans")
    new.add_argument("--slug")
    new.add_argument("--size", choices=sorted(VALID_SIZES), default="medium")
    new.add_argument(
        "--mode",
        choices=sorted(VALID_MODES),
        default="standard",
        help="execution mode; yolo auto-approves phases under a master authorization",
    )
    new.add_argument(
        "--authorized-by",
        default=None,
        help='user who authorized yolo mode; required when --mode is yolo',
    )
    new.set_defaults(func=cmd_new)

    add = sub.add_parser("add-phase", help="add the next phase to the master")
    add.add_argument("plan_dir")
    add.add_argument("name")
    add.add_argument("--depends", default="none")
    add.add_argument("--outcome", default="TBD")
    add.add_argument("--outline", action="store_true", help="add a row without a plan file")
    add.set_defaults(func=cmd_add_phase)

    write = sub.add_parser("write-plan", help="write a plan for an outline phase")
    write.add_argument("plan_dir")
    write.add_argument("phase")
    write.set_defaults(func=cmd_write_plan)

    approve = sub.add_parser("approve", help="record user approval for a phase plan")
    approve.add_argument("plan_dir")
    approve.add_argument("phase")
    approve.add_argument("--by", required=True)
    approve.add_argument("--when", default=date.today().isoformat())
    approve.add_argument(
        "--yolo",
        action="store_true",
        help="auto-approve under the master's yolo authorization",
    )
    approve.add_argument(
        "--allow-unmet-dependency",
        action="store_true",
        help="allow intentional parallel work before dependencies are done",
    )
    approve.set_defaults(func=cmd_approve)

    reopen = sub.add_parser("reopen", help="reset a phase to draft for refinement")
    reopen.add_argument("plan_dir")
    reopen.add_argument("phase")
    reopen.set_defaults(func=cmd_reopen)

    record_commit = sub.add_parser(
        "record-commit", help="record the phase commit hash in the plan and master"
    )
    record_commit.add_argument("plan_dir")
    record_commit.add_argument("phase")
    record_commit.add_argument("--hash", default=None)
    record_commit.add_argument("--by", default=None, help="worker name or ID")
    record_commit.set_defaults(func=cmd_record_commit)

    close = sub.add_parser("close", help="close an in_progress phase")
    close.add_argument("plan_dir")
    close.add_argument("phase")
    close.add_argument("--by", default=None, help="worker name or ID")
    close.add_argument("--hash", default=None)
    close.set_defaults(func=cmd_close)

    discovery = sub.add_parser("add-discovery", help="append a discovery ledger row")
    discovery.add_argument("plan_dir")
    discovery.add_argument("phase")
    discovery.add_argument("discovery")
    discovery.add_argument("--affects", required=True)
    discovery.add_argument("--type", required=True, choices=sorted(VALID_TYPES))
    discovery.add_argument("--action", required=True)
    discovery.add_argument(
        "--status", default="open", choices=sorted(VALID_LEDGER_STATUSES)
    )
    discovery.add_argument("--no-bump", action="store_true")
    discovery.set_defaults(func=cmd_add_discovery)

    decision = sub.add_parser("add-decision", help="append a cross-phase decision")
    decision.add_argument("plan_dir")
    decision.add_argument("decision")
    decision.add_argument("--reason", required=True)
    decision.add_argument("--affects", default="all")
    decision.set_defaults(func=cmd_add_decision)

    discoveries = sub.add_parser(
        "discoveries", help="list ledger rows that affect a phase"
    )
    discoveries.add_argument("plan_dir")
    discoveries.add_argument("phase")
    discoveries.set_defaults(func=cmd_discoveries)

    scope = sub.add_parser("scope", help="compare changed files with phase file lists")
    scope.add_argument("plan_dir")
    scope.add_argument("phase")
    scope.add_argument("--base", default=None)
    scope.add_argument("--strict", action="store_true")
    scope.add_argument("--json", action="store_true")
    scope.set_defaults(func=cmd_scope)

    report = sub.add_parser("report", help="print a plan or PR report")
    report.add_argument("plan_dir")
    report.add_argument("--json", action="store_true")
    report.set_defaults(func=cmd_report)

    archive = sub.add_parser(
        "archive", help="move a completed plan into the archive directory"
    )
    archive.add_argument("plan_dir")
    archive.add_argument(
        "--dest",
        default=None,
        help="archive root directory (default: <plans-root>/archive)",
    )
    archive.set_defaults(func=cmd_archive)

    condense = sub.add_parser(
        "condense", help="rebuild the branch as one commit per phase"
    )
    condense.add_argument("plan_dir")
    condense.add_argument(
        "--base", default=None, help="base commit (default: merge-base with the default branch)"
    )
    condense.add_argument(
        "--branch", default=None, help="new branch name (default: <current>-condensed)"
    )
    condense.add_argument(
        "--plans",
        choices=("keep", "drop"),
        default="keep",
        help="keep plan files in the new history or drop them",
    )
    condense.add_argument(
        "--keep",
        action="append",
        default=[],
        metavar="HASH",
        help="additional commit to keep as its own commit; repeatable",
    )
    condense.add_argument(
        "--tag", default=None, help="tag the pre-condense tip with this name"
    )
    condense.add_argument(
        "--dry-run", action="store_true", help="print the plan without creating refs"
    )
    condense.add_argument(
        "--force",
        action="store_true",
        help="override History: keep or replace an existing branch or tag",
    )
    condense.add_argument("--json", action="store_true")
    condense.set_defaults(func=cmd_condense)

    check = sub.add_parser("check", help="validate master and phase plans")
    check.add_argument("plan_dir")
    check.add_argument("--strict", action="store_true")
    check.add_argument("--json", action="store_true")
    check.set_defaults(func=cmd_check)

    status = sub.add_parser("status", help="print phases, check, and next action")
    status.add_argument("plan_dir")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=cmd_status)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
