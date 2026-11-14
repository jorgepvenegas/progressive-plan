#!/usr/bin/env python3
"""Scaffold, validate, and close master/phase plans.

Commands:
    new <title> [--root docs/plans] [--slug name] [--size small|medium|large]
    add-phase <plan-dir> <name> [--depends P1] [--outcome text] [--outline]
    write-plan <plan-dir> <phase>
    approve <plan-dir> <phase> --by <user> [--when YYYY-MM-DD]
    reopen <plan-dir> <phase>
    record-commit <plan-dir> <phase> [--hash HASH] [--by WORKER]
    close <plan-dir> <phase> [--by WORKER] [--hash HASH]
    add-discovery <plan-dir> <phase> <discovery> --affects P2 --type note --action text
    add-decision <plan-dir> <decision> --reason text [--affects all]
    discoveries <plan-dir> <phase>
    scope <plan-dir> <phase> [--base REF] [--strict] [--json]
    report <plan-dir> [--json]
    check <plan-dir> [--strict] [--json]
    status <plan-dir> [--json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

from planlib import (
    VALID_LEDGER_STATUSES,
    VALID_SIZES,
    VALID_TYPES,
    affecting_ledger,
    build_status,
    bump_int_field,
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
    git_root,
    identifier_number,
    invalid_phase_refs,
    is_pending,
    ledger_rows,
    master_version,
    phase_plan_path,
    phase_rows,
    read_text,
    render_report,
    render_status_text,
    section,
    set_field,
    set_field_all,
    slugify,
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
    version = master_version(master)
    if version is None:
        fail("master plan has no '- Master version: N' line")
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
    stale = [
        item["id"]
        for item in rows
        if item["status"] in {"ready", "in_progress"}
    ]
    if stale:
        print(
            "warning: master version bumped; revalidate these phases: "
            + ", ".join(stale)
        )


def cmd_write_plan(args: argparse.Namespace) -> None:
    plan_dir = Path(args.plan_dir)
    master, row = _find_phase_row(plan_dir, args.phase)
    if row["status"] != "planned":
        fail(f"phase {args.phase} is {row['status']}; only planned phases get a new plan")
    if str(row["plan"]).strip().lower() not in {"", "pending", "not written", "—", "-"}:
        fail(f"phase {args.phase} already has a plan: {row['plan']}")
    version = master_version(master)
    if version is None:
        fail("master plan has no '- Master version: N' line")
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
    plan_text = set_field(plan_text, "Approved by", args.by)
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
    print(f"approved {args.phase} by {args.by} on {args.when}")
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
    repo = git_root(plan_dir)
    if repo is None:
        fail(f"{plan_dir} is not inside a git repository")

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
    if not commit_exists(repo, commit_hash):
        fail(f"commit {commit_hash} does not exist in {repo}")
    if not commit_is_ancestor(repo, commit_hash):
        fail(f"commit {commit_hash} is not an ancestor of HEAD")

    plan_text = read_text(plan_file)
    plan_text = set_field_all(plan_text, "Commit", commit_hash)
    if args.by:
        plan_text = set_field(plan_text, "Implemented by", args.by)
    if is_pending(field(plan_text, "Implemented at")):
        plan_text = set_field(
            plan_text,
            "Implemented at",
            commit_date(repo, commit_hash) or date.today().isoformat(),
        )
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
    repo = git_root(plan_dir)
    if repo is None:
        fail(f"{plan_dir} is not inside a git repository")

    plan_text = read_text(plan_file)
    if args.hash:
        if not commit_exists(repo, args.hash):
            fail(f"commit {args.hash} does not exist in {repo}")
        plan_text = set_field_all(plan_text, "Commit", args.hash)
    commit_hash = field(plan_text, "Commit")
    if is_pending(commit_hash):
        fail(f"phase {args.phase} has no recorded commit; run record-commit first")
    if not commit_exists(repo, str(commit_hash)):
        fail(f"commit {commit_hash} does not exist in {repo}")
    if not commit_is_ancestor(repo, str(commit_hash)):
        fail(f"commit {commit_hash} is not an ancestor of HEAD")
    if args.by:
        plan_text = set_field(plan_text, "Implemented by", args.by)
    if is_pending(field(plan_text, "Implemented by")):
        fail("set Implemented by with --by before closing the phase")
    if is_pending(field(plan_text, "Implemented at")):
        plan_text = set_field(
            plan_text,
            "Implemented at",
            commit_date(repo, str(commit_hash)) or date.today().isoformat(),
        )
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
        version = master_version(master)
        if version is None:
            fail("master plan has no '- Master version: N' line")
        master = set_field(master, "Master version", str(version + 1))
    write_text(master_file, master)
    print(f"added {entry_id} to {master_file}")
    if not args.no_bump:
        stale = [
            item["id"]
            for item in phase_rows(master)
            if item["status"] in {"ready", "in_progress"}
        ]
        if stale:
            print(
                "warning: master version bumped; revalidate these phases: "
                + ", ".join(stale)
            )


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
    version = master_version(master)
    if version is None:
        fail("master plan has no '- Master version: N' line")
    master = set_field(master, "Master version", str(version + 1))
    write_text(master_file, master)
    print(f"added {decision_id} to {master_file}")
    stale = [
        row["id"]
        for row in phase_rows(master)
        if row["status"] in {"ready", "in_progress"}
    ]
    if stale:
        print(
            "warning: master version bumped; revalidate these phases: "
            + ", ".join(stale)
        )


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
    repo = git_root(plan_dir)
    if repo is None:
        fail(f"{plan_dir} is not inside a git repository")
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
