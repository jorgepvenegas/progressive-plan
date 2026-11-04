#!/usr/bin/env python3
"""Scaffold and validate a master/phase plan directory.

Commands:
    new <title> [--root docs/plans] [--slug name]
    add-phase <plan-dir> <name> [--depends P1] [--outcome text]
    approve <plan-dir> <phase-id> --by <user> [--when YYYY-MM-DD]
    record-commit <plan-dir> <phase-id> [--hash HASH]
    discoveries <plan-dir> <phase-id>
    check <plan-dir>
    status <plan-dir>
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
REFERENCES = SKILL_DIR / "references"

VALID_STATUSES = {
    "planned",
    "ready",
    "in_progress",
    "done",
    "blocked",
    "needs_replan",
    "superseded",
}
VALID_VERDICTS = {"addressed", "partial", "blocked"}

MASTER_HEADINGS = [
    "Objective",
    "Goal flow",
    "Definition of done",
    "Non-goals",
    "Current state",
    "Phase map",
    "Cross-phase decisions",
    "Discovery ledger",
    "Open questions",
    "Closeout history",
    "Resume brief",
]

PHASE_HEADINGS = [
    "Phase objective",
    "Master traceability",
    "Prior discoveries applied",
    "Scope",
    "Entry conditions",
    "Steps",
    "Phase acceptance criteria",
    "Deviations and working notes",
    "Closeout",
]


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "plan"


def render(template_name: str, **values: object) -> str:
    text = (REFERENCES / template_name).read_text()
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text


def has_heading(text: str, keyword: str) -> bool:
    pattern = r"^##\s+.*" + re.escape(keyword)
    return re.search(pattern, text, re.MULTILINE | re.IGNORECASE) is not None


def phase_rows(master_text: str) -> list[dict[str, str]]:
    rows = []
    for line in section(master_text, "Phase map").splitlines():
        if not re.match(r"\|\s*P\d+\s*\|", line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 6:
            continue
        rows.append(
            {
                "id": cells[0],
                "name": cells[1],
                "outcome": cells[2],
                "depends": cells[3],
                "status": cells[4],
                "plan": cells[5],
            }
        )
    return rows


def ledger_rows(master_text: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in section(master_text, "Discovery ledger").splitlines():
        if not re.match(r"^\|\s*[A-Z]\d+\s*\|", line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 8:
            rows.append(
                {
                    "id": cells[0],
                    "affects": "",
                    "discovery": cells[3] if len(cells) > 3 else "",
                    "action": "",
                    "status": cells[-1] if cells else "",
                    "malformed": True,
                }
            )
            continue
        rows.append(
            {
                "id": cells[0],
                "date": cells[1],
                "phase": cells[2],
                "affects": cells[3],
                "discovery": cells[4],
                "type": cells[5],
                "action": cells[6],
                "status": cells[7],
                "malformed": False,
            }
        )
    return rows


def expand_phase_refs(value: str) -> set[str]:
    refs: set[str] = set()
    for part in re.split(r"[,\s]+", value.strip()):
        part = part.strip(",;")
        if not part:
            continue
        if part.lower() == "all":
            refs.add("all")
            continue
        match = re.match(r"^P(\d+)[–-]P?(\d+)$", part)
        if match:
            start, end = int(match.group(1)), int(match.group(2))
            refs.update(f"P{index}" for index in range(start, end + 1))
            continue
        if re.fullmatch(r"P\d+", part):
            refs.add(part)
    return refs


def mentioned_ledger_ids(plan_text: str) -> set[str]:
    ids: set[str] = set()
    for line in section(plan_text, "Prior discoveries applied").splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        first = cells[0] if cells else ""
        if not first or first.lower() in {"ledger", "---", "—"}:
            continue
        for part in re.split(r"[,\s]+", first):
            part = part.strip(",;")
            match = re.match(r"^([A-Z])(\d+)[–-]\1?(\d+)$", part)
            if match:
                prefix = match.group(1)
                start, end = int(match.group(2)), int(match.group(3))
                ids.update(f"{prefix}{index}" for index in range(start, end + 1))
            elif re.fullmatch(r"[A-Z]\d+", part):
                ids.add(part)
    return ids


def link_target(cell: str) -> str:
    match = re.search(r"\(([^)]+)\)", cell)
    return match.group(1) if match else cell


def master_version(master_text: str) -> int | None:
    match = re.search(r"^-\s*Master version:\s*(\d+)", master_text, re.MULTILINE)
    return int(match.group(1)) if match else None


def field(text: str, name: str) -> str | None:
    match = re.search(
        r"^-\s*" + re.escape(name) + r":\s*(.+)$", text, re.MULTILINE
    )
    return match.group(1).strip() if match else None


def set_field_all(text: str, name: str, value: str) -> str:
    pattern = re.compile(r"^-\s*" + re.escape(name) + r":.*$", re.MULTILINE)
    return pattern.sub(lambda _match: f"- {name}: {value}", text)

def set_field(text: str, name: str, value: str) -> str:
    pattern = re.compile(r"^-\s*" + re.escape(name) + r":.*$", re.MULTILINE)
    if pattern.search(text):
        return pattern.sub(lambda _match: f"- {name}: {value}", text, count=1)
    status = re.compile(r"^-\s*Status:.*$", re.MULTILINE)
    if status.search(text):
        return status.sub(lambda match: f"{match.group(0)}\n- {name}: {value}", text, count=1)
    return text


def section(text: str, keyword: str) -> str:
    pattern = re.compile(
        r"^##\s+.*" + re.escape(keyword) + r".*$", re.MULTILINE | re.IGNORECASE
    )
    match = pattern.search(text)
    if not match:
        return ""
    start = match.end()
    next_heading = re.search(r"^##\s+", text[start:], re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(text)
    return text[start:end]


def cmd_new(args: argparse.Namespace) -> None:
    plan_dir = Path(args.root) / (args.slug or slugify(args.title))
    if plan_dir.exists():
        fail(f"{plan_dir} already exists")
    (plan_dir / "phases").mkdir(parents=True)
    master = render(
        "master-template.md",
        TITLE=args.title,
        SLUG=plan_dir.name,
        DATE=date.today().isoformat(),
    )
    (plan_dir / "master.md").write_text(master)
    print(f"created {plan_dir}/master.md")
    print(f"next: python3 {Path(__file__)} add-phase {plan_dir} \"<Phase name>\"")


def cmd_add_phase(args: argparse.Namespace) -> None:
    plan_dir = Path(args.plan_dir)
    master_file = plan_dir / "master.md"
    if not master_file.exists():
        fail(f"{master_file} does not exist")

    master_text = master_file.read_text()
    rows = phase_rows(master_text)
    number = max((int(row["id"][1:]) for row in rows), default=0) + 1
    phase_id = f"P{number}"
    phase_dir = plan_dir / "phases" / f"{number:02d}-{slugify(args.name)}"
    if phase_dir.exists():
        fail(f"{phase_dir} already exists")

    version = master_version(master_text)
    if version is None:
        fail("master plan has no '- Master version: N' line")

    phase_dir.mkdir(parents=True)
    plan_text = render(
        "phase-plan-template.md",
        PHASE_ID=phase_id,
        PHASE_NAME=args.name,
        SLUG=plan_dir.name,
        DATE=date.today().isoformat(),
        DEPENDS_ON=args.depends,
        MASTER_VERSION=version,
    )
    (phase_dir / "plan.md").write_text(plan_text)

    relative = f"phases/{phase_dir.name}/plan.md"
    row = (
        f"| {phase_id} | {args.name} | {args.outcome} | {args.depends} "
        f"| planned | [plan]({relative}) |"
    )
    lines = master_text.splitlines()
    map_start = next(
        (
            index
            for index, line in enumerate(lines)
            if re.match(r"^##\s+.*Phase map", line, re.IGNORECASE)
        ),
        None,
    )
    if map_start is None:
        fail("master plan has no phase map section")
    map_end = next(
        (
            index
            for index in range(map_start + 1, len(lines))
            if re.match(r"^##\s+", lines[index])
        ),
        len(lines),
    )
    header_index = next(
        (
            index
            for index in range(map_start, map_end)
            if re.match(r"\|\s*ID\s*\|\s*Phase\s*\|", lines[index])
        ),
        None,
    )
    if header_index is None:
        fail("master plan has no phase map table header")
    if rows:
        last_row_index = max(
            index
            for index in range(header_index, map_end)
            if re.match(r"\|\s*P\d+\s*\|", lines[index])
        )
        insert_at = last_row_index + 1
    else:
        insert_at = header_index + 2
    lines.insert(insert_at, row)
    master_file.write_text("\n".join(lines) + "\n")

    print(f"created {phase_dir}/plan.md")
    print(f"added {phase_id} to {master_file}")


def git_root(plan_dir: Path) -> Path | None:
    result = subprocess.run(
        ["git", "-C", str(plan_dir), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip())


def commit_exists(repo: Path, commit_hash: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", f"{commit_hash}^{{commit}}"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def cmd_record_commit(args: argparse.Namespace) -> None:
    plan_dir = Path(args.plan_dir)
    master_file = plan_dir / "master.md"
    if not master_file.exists():
        fail(f"{master_file} does not exist")

    master_text = master_file.read_text()
    rows = phase_rows(master_text)
    row = next((item for item in rows if item["id"] == args.phase), None)
    if row is None:
        fail(f"phase {args.phase} is not in the master phase map")

    plan_file = plan_dir / link_target(row["plan"])
    if not plan_file.exists():
        fail(f"{plan_file} does not exist")

    repo = git_root(plan_dir)
    if repo is None:
        fail(f"{plan_dir} is not inside a git repository")

    commit_hash = args.hash
    if not commit_hash:
        result = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            fail(f"could not read HEAD in {repo}")
        commit_hash = result.stdout.strip()

    if not commit_exists(repo, commit_hash):
        fail(f"commit {commit_hash} does not exist in {repo}")

    plan_text = set_field_all(plan_file.read_text(), "Commit", commit_hash)
    plan_file.write_text(plan_text)

    closeout_history = section(master_text, "Closeout history")
    history_lines = closeout_history.splitlines()
    updated_history = False
    for index, line in enumerate(history_lines):
        if re.match(r"^\|\s*" + re.escape(args.phase) + r"\s*\|", line):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) == 5:
                cells.insert(4, commit_hash)
            elif len(cells) >= 6:
                cells[4] = commit_hash
            else:
                continue
            history_lines[index] = "| " + " | ".join(cells) + " |"
            updated_history = True
            break
    if updated_history:
        new_history = "\n".join(history_lines)
        if closeout_history.endswith("\n"):
            new_history += "\n"
        master_file.write_text(master_text.replace(closeout_history, new_history, 1))
    else:
        print(f"warning: {args.phase} has no closeout-history row; commit recorded in the phase plan only")

    print(f"recorded commit {commit_hash} for {args.phase}")
    print(f"phase plan: {plan_file}")
    if updated_history:
        print(f"master: {master_file}")


def cmd_approve(args: argparse.Namespace) -> None:
    plan_dir = Path(args.plan_dir)
    master_file = plan_dir / "master.md"
    if not master_file.exists():
        fail(f"{master_file} does not exist")

    master_text = master_file.read_text()
    rows = phase_rows(master_text)
    row = next((item for item in rows if item["id"] == args.phase), None)
    if row is None:
        fail(f"phase {args.phase} is not in the master phase map")
    if row["status"] in {"done", "superseded"}:
        fail(f"phase {args.phase} is already {row['status']}")
    if row["status"] == "in_progress":
        fail(f"phase {args.phase} is already in progress")

    plan_file = plan_dir / link_target(row["plan"])
    if not plan_file.exists():
        fail(f"{plan_file} does not exist")

    for dependency in re.findall(r"P\d+", row["depends"]):
        dependency_row = next((item for item in rows if item["id"] == dependency), None)
        if dependency_row and dependency_row["status"] != "done":
            print(
                f"warning: {args.phase} depends on {dependency}, "
                f"which is {dependency_row['status']}"
            )

    plan_text = plan_file.read_text()
    plan_text = set_field(plan_text, "Status", "ready")
    plan_text = set_field(plan_text, "Approved by", args.by)
    plan_text = set_field(plan_text, "Approved at", args.when)
    plan_file.write_text(plan_text)

    phase_map = section(master_text, "Phase map")
    lines = phase_map.splitlines()
    updated = False
    for index, line in enumerate(lines):
        if re.match(r"^\|\s*" + re.escape(row["id"]) + r"\s*\|", line):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) < 6:
                fail(f"master row for {args.phase} is malformed")
            cells[4] = "ready"
            lines[index] = "| " + " | ".join(cells) + " |"
            updated = True
            break
    if not updated:
        fail(f"could not update the master row for {args.phase}")
    replacement = "\n".join(lines) + ("\n" if phase_map.endswith("\n") else "")
    master_file.write_text(master_text.replace(phase_map, replacement, 1))

    print(f"approved {args.phase} by {args.by} on {args.when}")
    print(f"phase plan: {plan_file}")
    print(f"master: {master_file}")


def cmd_check(args: argparse.Namespace) -> None:
    plan_dir = Path(args.plan_dir)
    master_file = plan_dir / "master.md"
    if not master_file.exists():
        fail(f"{master_file} does not exist")

    errors: list[str] = []
    warnings: list[str] = []
    master_text = master_file.read_text()
    version = master_version(master_text)

    if version is None:
        errors.append("master: missing '- Master version: N'")
    for keyword in MASTER_HEADINGS:
        if not has_heading(master_text, keyword):
            errors.append(f"master: missing section '{keyword}'")

    goal_flow = section(master_text, "Goal flow")
    if goal_flow and "```mermaid" not in goal_flow:
        errors.append("master: Goal flow has no Mermaid diagram")

    rows = phase_rows(master_text)
    if not rows:
        warnings.append("master: phase map is empty")

    for entry in ledger_rows(master_text):
        if entry.get("malformed") or not entry.get("affects"):
            errors.append(
                f"master: ledger {entry['id']} is missing the Affects column; "
                "add a phase list, range, or all"
            )

    seen_ids: set[str] = set()
    dependencies: list[tuple[str, str]] = []
    done_phases: set[str] = set()
    for row in rows:
        phase_id = row["id"]
        if phase_id in seen_ids:
            errors.append(f"master: duplicate phase id {phase_id}")
        seen_ids.add(phase_id)
        if row["status"] not in VALID_STATUSES:
            errors.append(
                f"master: {phase_id} has invalid status '{row['status']}'"
            )
        if row["status"] == "done":
            done_phases.add(phase_id)
        for dependency in re.findall(r"P\d+", row["depends"]):
            dependencies.append((phase_id, dependency))

        plan_file = plan_dir / link_target(row["plan"])
        if not plan_file.exists():
            errors.append(f"master: {phase_id} plan is missing ({plan_file})")
            continue

        plan_text = plan_file.read_text()
        for keyword in PHASE_HEADINGS:
            if not has_heading(plan_text, keyword):
                errors.append(f"{plan_file}: missing section '{keyword}'")

        plan_version = field(plan_text, "Validated against master version")
        if plan_version is None:
            errors.append(f"{plan_file}: missing 'Validated against master version'")
        elif version is not None and row["status"] in {"ready", "in_progress"}:
            try:
                behind = int(plan_version) < version
            except ValueError:
                behind = False
                errors.append(f"{plan_file}: invalid master version '{plan_version}'")
            if behind:
                errors.append(
                    f"{plan_file}: validated against master v{plan_version}, "
                    f"master is v{version}; revalidate the phase plan"
                )

        approved_by = field(plan_text, "Approved by")
        approved_at = field(plan_text, "Approved at")
        phase_status = field(plan_text, "Status")
        if row["status"] in {"ready", "in_progress", "done"}:
            if not approved_by or approved_by.strip().lower() in {
                "",
                "pending",
                "tbd",
                "none",
            }:
                errors.append(
                    f"{plan_file}: {phase_id} is {row['status']} without user approval; "
                    f"run approve {plan_dir} {phase_id} --by <user>"
                )
            if not approved_at or approved_at.strip().lower() in {
                "",
                "pending",
                "tbd",
                "none",
            }:
                errors.append(
                    f"{plan_file}: {phase_id} is {row['status']} without an approval date"
                )
        if row["status"] in {"ready", "in_progress", "done"}:
            expected = "done" if row["status"] == "done" else row["status"]
            if phase_status != expected:
                errors.append(
                    f"{plan_file}: phase status is '{phase_status or 'missing'}', "
                    f"master says '{row['status']}'"
                )

        if row["status"] in {"ready", "in_progress", "done"}:
            mentioned = mentioned_ledger_ids(plan_text)
            for entry in ledger_rows(master_text):
                if entry.get("malformed"):
                    continue
                if entry.get("status") == "superseded":
                    continue
                refs = expand_phase_refs(str(entry.get("affects", "")))
                if "all" in refs or phase_id in refs:
                    if entry["id"] not in mentioned:
                        errors.append(
                            f"{plan_file}: missing ledger {entry['id']} in "
                            f"'Prior discoveries applied' (affects {entry.get('affects', '')})"
                        )

        implementation_mode = field(plan_text, "Implementation mode")
        if row["status"] in {"ready", "in_progress", "done"}:
            if implementation_mode not in {"subagent", "coordinator-exception"}:
                errors.append(
                    f"{plan_file}: {phase_id} needs 'Implementation mode: subagent' "
                    "or 'coordinator-exception'"
                )
            if implementation_mode == "coordinator-exception":
                exception_by = field(plan_text, "Exception approved by")
                if not exception_by or exception_by.strip().lower() in {
                    "",
                    "pending",
                    "tbd",
                    "none",
                }:
                    errors.append(
                        f"{plan_file}: coordinator-exception for {phase_id} "
                        "has no approving user"
                    )
        if row["status"] == "done":
            implemented_by = field(plan_text, "Implemented by")
            implemented_at = field(plan_text, "Implemented at")
            if not implemented_by or implemented_by.strip().lower() in {
                "",
                "pending",
                "tbd",
                "none",
            }:
                errors.append(f"{plan_file}: done phase has no 'Implemented by' record")
            if not implemented_at or implemented_at.strip().lower() in {
                "",
                "pending",
                "tbd",
                "none",
            }:
                errors.append(f"{plan_file}: done phase has no 'Implemented at' record")

        commit_hash = field(plan_text, "Commit")
        if row["status"] == "done":
            if not commit_hash or commit_hash.strip().lower() in {
                "",
                "pending",
                "tbd",
                "none",
            }:
                errors.append(
                    f"{plan_file}: done phase has no commit; run record-commit "
                    f"{plan_dir} {phase_id}"
                )
            else:
                repo = git_root(plan_dir)
                if repo is not None and not commit_exists(repo, commit_hash):
                    errors.append(
                        f"{plan_file}: commit {commit_hash} does not exist in {repo}"
                    )

        if row["status"] == "done":
            closeout = section(plan_text, "Closeout")
            verdict = re.search(
                r"^-\s*Verdict:\s*(\S+)", closeout, re.MULTILINE
            )
            value = verdict.group(1).strip().lower() if verdict else ""
            if value not in VALID_VERDICTS:
                errors.append(
                    f"{plan_file}: done phase has no valid closeout verdict "
                    f"(found '{value or 'none'}')"
                )
            closeout_history = section(master_text, "Closeout history")
            if not re.search(
                r"^\|\s*" + re.escape(phase_id) + r"\s*\|",
                closeout_history,
                re.MULTILINE,
            ):
                errors.append(
                    f"master: done phase {phase_id} is missing from Closeout history"
                )

    for phase_id, dependency in dependencies:
        if dependency not in seen_ids:
            errors.append(
                f"master: {phase_id} depends on unknown phase {dependency}"
            )
        elif dependency == phase_id:
            errors.append(f"master: {phase_id} depends on itself")

    if rows and done_phases == seen_ids:
        definition = section(master_text, "Definition of done")
        unchecked = re.findall(r"^-\s*\[ \]", definition, re.MULTILINE)
        if unchecked:
            warnings.append(
                f"master: all phases are done but {len(unchecked)} "
                "definition-of-done item(s) are unchecked"
            )

    for warning in warnings:
        print(f"warning: {warning}")
    for error in errors:
        print(f"error: {error}")
    if errors:
        raise SystemExit(1)
    print(f"ok: {plan_dir} ({len(rows)} phase(s), master v{version})")


def cmd_discoveries(args: argparse.Namespace) -> None:
    plan_dir = Path(args.plan_dir)
    master_file = plan_dir / "master.md"
    if not master_file.exists():
        fail(f"{master_file} does not exist")
    entries = [
        entry
        for entry in ledger_rows(master_file.read_text())
        if not entry.get("malformed")
        and entry.get("status") != "superseded"
        and (
            "all" in expand_phase_refs(str(entry.get("affects", "")))
            or args.phase in expand_phase_refs(str(entry.get("affects", "")))
        )
    ]
    if not entries:
        print(f"no ledger rows affect {args.phase}")
        return
    print(f"Ledger rows affecting {args.phase}:")
    for entry in entries:
        print(f"- {entry['id']} ({entry.get('affects', '')}): {entry.get('discovery', '')}")
        print(f"  action: {entry.get('action', '')}")


def cmd_status(args: argparse.Namespace) -> None:
    plan_dir = Path(args.plan_dir)
    master_file = plan_dir / "master.md"
    if not master_file.exists():
        fail(f"{master_file} does not exist")
    master_text = master_file.read_text()
    rows = phase_rows(master_text)
    title = master_text.splitlines()[0].lstrip("# ").strip()
    print(f"{title} — master v{master_version(master_text)}")
    for row in rows:
        print(
            f"  {row['id']:<3} {row['status']:<12} {row['name']} "
            f"(depends: {row['depends']})"
        )
    resume = section(master_text, "Resume brief").strip()
    if resume:
        print("\nResume brief")
        for line in resume.splitlines():
            if line.strip():
                print("  " + line.strip())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    new = sub.add_parser("new", help="create a master plan directory")
    new.add_argument("title")
    new.add_argument("--root", default="docs/plans")
    new.add_argument("--slug")
    new.set_defaults(func=cmd_new)

    add = sub.add_parser("add-phase", help="create the next phase plan")
    add.add_argument("plan_dir")
    add.add_argument("name")
    add.add_argument("--depends", default="none")
    add.add_argument("--outcome", default="TBD")
    add.set_defaults(func=cmd_add_phase)

    approve = sub.add_parser("approve", help="record user approval for a phase plan")
    approve.add_argument("plan_dir")
    approve.add_argument("phase")
    approve.add_argument("--by", required=True)
    approve.add_argument("--when", default=date.today().isoformat())
    approve.set_defaults(func=cmd_approve)

    discoveries = sub.add_parser(
        "discoveries", help="list ledger rows that affect a phase"
    )
    discoveries.add_argument("plan_dir")
    discoveries.add_argument("phase")
    discoveries.set_defaults(func=cmd_discoveries)

    record_commit = sub.add_parser(
        "record-commit", help="record the phase commit hash in the plan and master"
    )
    record_commit.add_argument("plan_dir")
    record_commit.add_argument("phase")
    record_commit.add_argument("--hash", default=None)
    record_commit.set_defaults(func=cmd_record_commit)

    check = sub.add_parser("check", help="validate master and phase plans")
    check.add_argument("plan_dir")
    check.set_defaults(func=cmd_check)

    status = sub.add_parser("status", help="print phases and resume brief")
    status.add_argument("plan_dir")
    status.set_defaults(func=cmd_status)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
