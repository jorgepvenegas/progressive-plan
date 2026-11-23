#!/usr/bin/env python3
"""Shared parsing, state, and validation helpers for progressive-plan."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Any

VALID_MASTER_STATUSES = {"draft", "active", "complete", "blocked"}
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
VALID_TYPES = {
    "note",
    "phase-amend",
    "next-phase-amend",
    "master-amend",
    "new-phase",
    "scope-change",
    "plan-defect",
}
VALID_LEDGER_STATUSES = {"open", "applied", "superseded", "wontfix"}
VALID_SIZES = {"small", "medium", "large"}
VALID_MODES = {"standard", "yolo"}
VALID_HISTORY = {"per-phase", "keep"}

# master status -> phase plan status
PHASE_STATUS_MAP = {
    "planned": "draft",
    "ready": "ready",
    "in_progress": "in_progress",
    "done": "done",
    "blocked": "blocked",
    "needs_replan": "needs_replan",
    "superseded": "superseded",
}

MASTER_HEADINGS = [
    "Objective",
    "Goal flow",
    "Definition of done",
    "Non-goals",
    "Code standards",
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
    "Code standards check",
    "Risks and unknowns",
    "Deviations and working notes",
    "Closeout",
]

PENDING_VALUES = {"", "pending", "tbd", "none", "n/a", "-", "—"}


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def read_text(path: Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "plan"


def section(text: str, keyword: str) -> str:
    """Return the body of the first level-2 section whose heading contains keyword."""
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


def has_heading(text: str, keyword: str) -> bool:
    pattern = r"^##\s+.*" + re.escape(keyword)
    return re.search(pattern, text, re.MULTILINE | re.IGNORECASE) is not None


def field(text: str, name: str) -> str | None:
    match = re.search(
        r"^-\s*" + re.escape(name) + r":\s*(.+)$", text, re.MULTILINE
    )
    if not match:
        return None
    value = match.group(1).strip()
    if len(value) >= 2 and value.startswith("`") and value.endswith("`"):
        value = value[1:-1].strip()
    return value


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


def bump_int_field(text: str, name: str, amount: int = 1) -> str:
    current = field(text, name)
    try:
        value = int(current) if current is not None else 0
    except ValueError:
        value = 0
    return set_field(text, name, str(value + amount))


def master_mode(text: str) -> str:
    return (field(text, "Mode") or "standard").strip().lower()


def master_history(text: str) -> str:
    return (field(text, "History") or "per-phase").strip().lower()


def master_version(text: str) -> int | None:
    match = re.search(r"^-\s*Master version:\s*(\d+)", text, re.MULTILINE)
    return int(match.group(1)) if match else None


def require_master_version(master: str) -> int:
    version = master_version(master)
    if version is None:
        fail("master plan has no '- Master version: N' line")
    return version


def bump_master_version(master: str) -> tuple[str, int]:
    version = require_master_version(master)
    new_version = version + 1
    return set_field(master, "Master version", str(new_version)), new_version


def stale_phase_ids(master: str) -> list[str]:
    return [
        item["id"]
        for item in phase_rows(master)
        if item["status"] in {"ready", "in_progress"}
    ]


def closeout_verdict(plan_text: str) -> str | None:
    match = re.search(
        r"^-\s*Verdict:\s*(\S+)", section(plan_text, "Closeout"), re.MULTILINE
    )
    return match.group(1).strip().lower() if match else None


def identifier_number(value: str) -> int:
    digits = re.sub(r"\D", "", value)
    return int(digits) if digits else 0


def link_target(cell: str) -> str:
    match = re.search(r"\(([^)]+)\)", cell)
    return match.group(1).strip() if match else cell.strip()


def is_pending(value: str | None) -> bool:
    return value is None or value.strip().lower() in PENDING_VALUES


def strip_code_fences(text: str) -> str:
    return re.sub(r"```.*?```", "", text, flags=re.DOTALL)


def placeholder_findings(text: str) -> list[str]:
    """Return template placeholders found outside fenced code blocks."""
    clean = strip_code_fences(text)
    findings: list[str] = []
    findings.extend(match.group(0) for match in re.finditer(r"<[^>\n]{2,}>", clean))
    findings.extend(
        match.group(0) for match in re.finditer(r"\{\{[^}\n]+\}\}", clean)
    )
    findings.extend(
        match.group(0)
        for match in re.finditer(r"\b(?:TBD|TODO)\b|\?\?", clean)
    )
    return findings


def _table_rows(
    text: str,
    section_keyword: str,
    row_pattern: str,
    columns: tuple[str, ...],
    *,
    keep_raw: bool = False,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in section(text, section_keyword).splitlines():
        if not re.match(row_pattern, line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        malformed = len(cells) != len(columns)
        padded = cells + [""] * (len(columns) - len(cells))
        row = {name: padded[index] for index, name in enumerate(columns)}
        row["malformed"] = malformed
        if keep_raw:
            row["raw"] = line
        rows.append(row)
    return rows


def phase_rows(master_text: str) -> list[dict[str, Any]]:
    return _table_rows(
        master_text,
        "Phase map",
        r"^\|\s*P\d+\s*\|",
        ("id", "name", "outcome", "depends", "status", "plan"),
        keep_raw=True,
    )


def ledger_rows(master_text: str) -> list[dict[str, Any]]:
    return _table_rows(
        master_text,
        "Discovery ledger",
        r"^\|\s*[A-Z]\d+\s*\|",
        ("id", "date", "phase", "affects", "discovery", "type", "action", "status"),
        keep_raw=True,
    )


def decision_rows(master_text: str) -> list[dict[str, Any]]:
    return _table_rows(
        master_text,
        "Cross-phase decisions",
        r"^\|\s*C\d+\s*\|",
        ("id", "date", "decision", "reason", "affects"),
        keep_raw=True,
    )


def closeout_history_rows(master_text: str) -> list[dict[str, Any]]:
    return _table_rows(
        master_text,
        "Closeout history",
        r"^\|\s*P\d+\s*\|",
        ("phase", "date", "verdict", "criteria", "commit", "report"),
    )


def expand_phase_refs(value: str) -> set[str]:
    refs: set[str] = set()
    for part in re.split(r"[,\s]+", (value or "").strip()):
        part = part.strip(",;")
        if not part:
            continue
        if part.lower() == "all":
            refs.add("all")
            continue
        if part.lower() == "none":
            continue
        match = re.fullmatch(r"P(\d+)\s*[–-]\s*P?(\d+)", part)
        if match:
            start, end = int(match.group(1)), int(match.group(2))
            if start <= end:
                refs.update(f"P{index}" for index in range(start, end + 1))
            continue
        if re.fullmatch(r"P\d+", part):
            refs.add(part)
    return refs


def invalid_phase_refs(value: str) -> list[str]:
    invalid: list[str] = []
    for part in re.split(r"[,\s]+", (value or "").strip()):
        part = part.strip(",;")
        if not part or part.lower() in {"all", "none"}:
            continue
        if re.fullmatch(r"P\d+", part):
            continue
        match = re.fullmatch(r"P(\d+)\s*[–-]\s*P?(\d+)", part)
        if match and int(match.group(1)) <= int(match.group(2)):
            continue
        invalid.append(part)
    return invalid


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
            match = re.fullmatch(r"([A-Z])(\d+)\s*[–-]\s*\1?(\d+)", part)
            if match:
                prefix = match.group(1)
                start, end = int(match.group(2)), int(match.group(3))
                ids.update(f"{prefix}{index}" for index in range(start, end + 1))
            elif re.fullmatch(r"[A-Z]\d+", part):
                ids.add(part)
    return ids


def _checklist_items(
    text: str, section_keyword: str, id_pattern: str
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    pattern = (
        r"^\s*-\s*\[([ xX])\]\s*("
        + id_pattern
        + r")\s*(?:[—:-]\s*)?(.*)$"
    )
    for line in section(text, section_keyword).splitlines():
        match = re.match(pattern, line)
        if not match:
            continue
        item_text = match.group(3).strip()
        verify = ""
        verify_match = re.search(r"verify:\s*(.+)$", item_text, re.IGNORECASE)
        if verify_match:
            verify = verify_match.group(1).strip()
        items.append(
            {
                "id": match.group(2),
                "checked": match.group(1).lower() == "x",
                "text": item_text,
                "verify": verify,
            }
        )
    return items


def definition_items(master_text: str) -> list[dict[str, Any]]:
    return _checklist_items(master_text, "Definition of done", r"D\d+")


def acceptance_items(plan_text: str) -> list[dict[str, Any]]:
    return _checklist_items(plan_text, "Phase acceptance criteria", r"A\d+")


def step_items(plan_text: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for match in re.finditer(
        r"^###\s*(S\d+)\s*[—:-]?\s*(.*)$",
        section(plan_text, "Steps"),
        re.MULTILINE,
    ):
        items.append({"id": match.group(1), "title": match.group(2).strip()})
    return items


def traceability_rows(plan_text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in section(plan_text, "Master traceability").splitlines():
        if not re.match(r"^\|\s*D\d+\s*\|", line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        rows.append(
            {
                "d": cells[0],
                "how": cells[1],
                "criteria": re.findall(r"A\d+", cells[2]),
            }
        )
    return rows


def closeout_rows(plan_text: str) -> list[dict[str, Any]]:
    lines = section(plan_text, "Closeout").splitlines()
    start: int | None = None
    for index, line in enumerate(lines):
        if line.strip().startswith("|") and "Criterion" in line and "Verdict" in line:
            start = index + 1
            break
    if start is None:
        return []
    rows: list[dict[str, Any]] = []
    for line in lines[start:]:
        if not line.strip().startswith("|"):
            break
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        if set(cells[0]) <= set("-: "):
            continue
        match = re.match(r"^(A\d+|D\d+)", cells[0])
        if not match:
            continue
        rows.append(
            {
                "criterion": match.group(1),
                "raw": cells[0],
                "verdict": cells[1].strip().lower(),
                "evidence": cells[2].strip(),
            }
        )
    return rows


def standards_check_items(plan_text: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for line in section(plan_text, "Code standards check").splitlines():
        match = re.match(r"^\s*-\s*\[([ xX])\]\s*(.+)$", line)
        if not match:
            continue
        items.append({"checked": match.group(1).lower() == "x", "text": match.group(2).strip()})
    return items


def affecting_ledger(entries: list[dict[str, Any]], phase_id: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for entry in entries:
        if entry.get("malformed") or entry.get("status") == "superseded":
            continue
        refs = expand_phase_refs(str(entry.get("affects", "")))
        if "all" in refs or phase_id in refs:
            result.append(entry)
    return result


def phase_plan_path(plan_dir: Path, row: dict[str, Any]) -> Path:
    target = link_target(str(row.get("plan", "")))
    path = Path(target)
    return path if path.is_absolute() else plan_dir / path


def _cycle_nodes(graph: dict[str, set[str]]) -> list[str]:
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []
    cycles: list[str] = []

    def visit(node: str) -> None:
        if node in visited:
            return
        if node in visiting:
            try:
                start = stack.index(node)
            except ValueError:
                start = 0
            cycle = stack[start:] + [node]
            cycles.append(" -> ".join(cycle))
            return
        visiting.add(node)
        stack.append(node)
        for neighbour in sorted(graph.get(node, set())):
            visit(neighbour)
        stack.pop()
        visiting.remove(node)
        visited.add(node)

    for node in sorted(graph):
        visit(node)
    return cycles


def _run_git(plan_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(plan_dir), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def git(plan_dir: Path, *args: str) -> str | None:
    result = _run_git(plan_dir, *args)
    return result.stdout.strip() if result.returncode == 0 else None


def git_ok(plan_dir: Path, *args: str) -> bool:
    return _run_git(plan_dir, *args).returncode == 0


def git_root(plan_dir: Path) -> Path | None:
    output = git(plan_dir, "rev-parse", "--show-toplevel")
    return Path(output) if output else None


def commit_exists(repo: Path, commit_hash: str) -> bool:
    return git_ok(repo, "cat-file", "-e", f"{commit_hash}^{{commit}}")


def commit_is_ancestor(repo: Path, commit_hash: str, ref: str = "HEAD") -> bool:
    return git_ok(repo, "merge-base", "--is-ancestor", commit_hash, ref)


def commit_subject(repo: Path, commit_hash: str) -> str | None:
    return git(repo, "show", "-s", "--format=%s", commit_hash)


def commit_date(repo: Path, commit_hash: str) -> str | None:
    return git(repo, "show", "-s", "--format=%cs", commit_hash)


def current_branch(plan_dir: Path) -> str | None:
    return git(plan_dir, "rev-parse", "--abbrev-ref", "HEAD")


def working_tree(plan_dir: Path) -> list[str]:
    output = git(plan_dir, "status", "--porcelain") or ""
    return [line for line in output.splitlines() if line.strip()]


def _validate_master_header(
    master: str, errors: list[str]
) -> tuple[int | None, str | None, str]:
    """Validate version, headings, status, size, and Goal flow.

    Returns (version, master_status, goal_flow). Appends errors in the current
    order.
    """
    version = master_version(master)
    if version is None:
        errors.append("master: missing '- Master version: N'")
    for keyword in MASTER_HEADINGS:
        if not has_heading(master, keyword):
            errors.append(f"master: missing section '{keyword}'")

    master_status = field(master, "Status")
    if master_status not in VALID_MASTER_STATUSES:
        errors.append(
            f"master: invalid status '{master_status or 'missing'}'; "
            f"expected one of {', '.join(sorted(VALID_MASTER_STATUSES))}"
        )
    size = field(master, "Size")
    if size not in VALID_SIZES:
        errors.append(
            f"master: Size must be one of {', '.join(sorted(VALID_SIZES))}; "
            f"found '{size or 'missing'}'"
        )

    mode = master_mode(master)
    if mode not in VALID_MODES:
        errors.append(
            f"master: Mode must be one of {', '.join(sorted(VALID_MODES))}; "
            f"found '{mode}'"
        )
    elif mode == "yolo":
        authorized_by = field(master, "Mode authorized by")
        if is_pending(authorized_by) or (
            authorized_by and placeholder_findings(authorized_by)
        ):
            errors.append(
                "master: Mode is yolo but '- Mode authorized by' is missing or pending"
            )

    history = field(master, "History")
    if history is not None and history.strip().lower() not in VALID_HISTORY:
        errors.append(
            f"master: History must be one of {', '.join(sorted(VALID_HISTORY))}; "
            f"found '{history}'"
        )

    goal_flow = section(master, "Goal flow")
    if goal_flow and "```mermaid" not in goal_flow:
        errors.append("master: Goal flow has no Mermaid diagram")

    return version, master_status, goal_flow


def _validate_definition_items(
    master: str, errors: list[str]
) -> list[dict[str, Any]]:
    dod = definition_items(master)
    if not dod:
        errors.append("master: Definition of done has no D items")
    dod_id_list = [item["id"] for item in dod]
    if len(dod_id_list) != len(set(dod_id_list)):
        errors.append("master: Definition of done has duplicate D ids")
    for item in dod:
        if not item["text"]:
            errors.append(f"master: {item['id']} has no description")
        if not item["verify"]:
            errors.append(f"master: {item['id']} has no verify clause")
    return dod


def _validate_phase_map(
    master: str, errors: list[str], warnings: list[str]
) -> tuple[list[dict[str, Any]], set[str]]:
    rows = phase_rows(master)
    if not rows:
        warnings.append("master: phase map is empty")

    seen_ids: set[str] = set()
    phase_ids: set[str] = set()
    for row in rows:
        phase_id = row["id"]
        if row["malformed"]:
            errors.append(
                f"master: malformed phase row for {phase_id or '?'}; "
                "expected 6 columns (ID, Phase, Outcome, Depends on, Status, Plan)"
            )
        if phase_id in seen_ids:
            errors.append(f"master: duplicate phase id {phase_id}")
        seen_ids.add(phase_id)
        if not row["malformed"]:
            phase_ids.add(phase_id)
        if row["status"] not in VALID_STATUSES:
            errors.append(f"master: {phase_id} has invalid status '{row['status']}'")

    return rows, phase_ids


def _validate_ledger_rows(
    master: str,
    errors: list[str],
    phase_ids: set[str],
    active: bool,
) -> list[dict[str, Any]]:
    entries = ledger_rows(master)
    for entry in entries:
        if entry["malformed"]:
            errors.append(
                f"master: malformed ledger row {entry['id'] or '?'}; "
                "expected 8 columns (ID, Date, Phase, Affects, Discovery, Type, Action taken, Status)"
            )
            continue
        placeholders = [
            name
            for name in ("date", "phase", "affects", "discovery", "type", "action", "status")
            if placeholder_findings(str(entry[name]))
        ]
        if placeholders:
            if active:
                errors.append(
                    f"master: ledger {entry['id']} still has template placeholders in "
                    + ", ".join(placeholders)
                )
            continue
        if not entry["affects"]:
            errors.append(f"master: ledger {entry['id']} is missing the Affects column")
        for token in invalid_phase_refs(str(entry["affects"])):
            errors.append(
                f"master: ledger {entry['id']} has invalid Affects value '{token}'"
            )
        for ref in expand_phase_refs(str(entry["affects"])):
            if ref != "all" and ref not in phase_ids:
                errors.append(
                    f"master: ledger {entry['id']} affects unknown phase {ref}"
                )
        if entry["type"] not in VALID_TYPES:
            errors.append(
                f"master: ledger {entry['id']} has invalid type '{entry['type']}'"
            )
        if entry["status"] not in VALID_LEDGER_STATUSES:
            errors.append(
                f"master: ledger {entry['id']} has invalid status '{entry['status']}'"
            )
        if not entry["discovery"]:
            errors.append(f"master: ledger {entry['id']} has no discovery text")
        if not entry["action"]:
            errors.append(f"master: ledger {entry['id']} has no action taken")
        if entry["phase"] not in phase_ids and entry["phase"] != "master":
            errors.append(
                f"master: ledger {entry['id']} names unknown phase '{entry['phase']}'"
            )
    return entries


def _validate_decision_rows(
    master: str,
    errors: list[str],
    phase_ids: set[str],
    active: bool,
) -> None:
    for decision in decision_rows(master):
        if decision["malformed"]:
            errors.append(
                f"master: malformed decision row {decision['id'] or '?'}; "
                "expected 5 columns (ID, Date, Decision, Reason, Affects)"
            )
            continue
        placeholders = [
            name
            for name in ("date", "decision", "reason", "affects")
            if placeholder_findings(str(decision[name]))
        ]
        if placeholders:
            if active:
                errors.append(
                    f"master: decision {decision['id']} still has template placeholders in "
                    + ", ".join(placeholders)
                )
            continue
        for token in invalid_phase_refs(str(decision["affects"])):
            errors.append(
                f"master: decision {decision['id']} has invalid Affects value '{token}'"
            )
        for ref in expand_phase_refs(str(decision["affects"])):
            if ref != "all" and ref not in phase_ids:
                errors.append(
                    f"master: decision {decision['id']} affects unknown phase {ref}"
                )


def _validate_dependency_graph(
    rows: list[dict[str, Any]],
    phase_ids: set[str],
    active: bool,
    errors: list[str],
) -> None:
    graph: dict[str, set[str]] = {}
    for row in rows:
        if row["malformed"]:
            continue
        if placeholder_findings(str(row["depends"])):
            if active:
                errors.append(
                    f"master: {row['id']} still has a placeholder dependency"
                )
            continue
        deps = expand_phase_refs(str(row["depends"]))
        graph[row["id"]] = deps
        for dependency in deps:
            if dependency not in phase_ids:
                errors.append(
                    f"master: {row['id']} depends on unknown phase {dependency}"
                )
            elif dependency == row["id"]:
                errors.append(f"master: {row['id']} depends on itself")
    for cycle in _cycle_nodes(graph):
        errors.append(f"master: dependency cycle: {cycle}")


def _validate_active_master_content(
    master: str,
    goal_flow: str,
    dod: list[dict[str, Any]],
    active: bool,
    errors: list[str],
) -> None:
    if active:
        for name, text in [
            ("Objective", section(master, "Objective")),
            ("Goal flow", goal_flow),
            ("Code standards", section(master, "Code standards")),
            ("Current state and assumptions", section(master, "Current state")),
            ("Non-goals", section(master, "Non-goals")),
            ("Resume brief", section(master, "Resume brief")),
        ]:
            for finding in placeholder_findings(text):
                errors.append(f"master: {name} still contains placeholder {finding}")
        source = field(master, "Source")
        if source is None or placeholder_findings(source):
            errors.append("master: Source is not filled")
        owner = field(master, "Owner")
        if owner is None or placeholder_findings(owner):
            errors.append("master: Owner is not filled")
        for item in dod:
            for finding in placeholder_findings(item["text"]):
                errors.append(
                    f"master: {item['id']} still contains placeholder {finding}"
                )
            for finding in placeholder_findings(item["verify"]):
                errors.append(
                    f"master: {item['id']} verify still contains placeholder {finding}"
                )
        if not section(master, "Objective").strip():
            errors.append("master: Objective is empty")
        if not goal_flow.strip():
            errors.append("master: Goal flow is empty")
        template_markers = ["Current situation", "Main step", "Desired outcome"]
        if all(marker in goal_flow for marker in template_markers):
            errors.append("master: Goal flow still contains the template diagram")


def _validate_master_status_rules(
    master_status: str | None,
    rows: list[dict[str, Any]],
    active: bool,
    errors: list[str],
    warnings: list[str],
) -> None:
    if active and master_status == "draft":
        warnings.append("master: status is draft but work has started; set Status: active")
    if master_status == "complete":
        if not rows or not all(row["status"] == "done" for row in rows):
            errors.append("master: status is complete but not every phase is done")


def _validate_phase_plans(
    plan_dir: Path,
    master: str,
    rows: list[dict[str, Any]],
    version: int | None,
    dod: list[dict[str, Any]],
    entries: list[dict[str, Any]],
    only_phase: str | None,
    for_approval: bool,
    errors: list[str],
) -> dict[str, Path]:
    phase_plan_files: dict[str, Path] = {}
    for row in rows:
        if row["malformed"]:
            continue
        phase_id = row["id"]
        if only_phase is not None and phase_id != only_phase:
            continue
        plan_cell = str(row["plan"]).strip()
        if row["status"] == "planned" and plan_cell.lower() in {
            "",
            "pending",
            "not written",
            "n/a",
            "—",
            "-",
        }:
            continue
        plan_file = phase_plan_path(plan_dir, row)
        phase_plan_files[phase_id] = plan_file
        if not plan_file.exists():
            errors.append(f"master: {phase_id} plan is missing ({plan_file})")
            continue

        plan = read_text(plan_file)
        for keyword in PHASE_HEADINGS:
            if not has_heading(plan, keyword):
                errors.append(f"{plan_file}: missing section '{keyword}'")

        effective_status = "ready" if for_approval and phase_id == only_phase else row["status"]
        approval_ready = not (for_approval and phase_id == only_phase)
        expected_plan_status = PHASE_STATUS_MAP.get(effective_status)
        plan_status = field(plan, "Status")
        if (
            approval_ready
            and expected_plan_status
            and plan_status != expected_plan_status
        ):
            errors.append(
                f"{plan_file}: phase status is '{plan_status or 'missing'}', "
                f"master says '{effective_status}' (expected '{expected_plan_status}')"
            )

        plan_id = field(plan, "Plan ID")
        if plan_id is not None and plan_id != plan_dir.name:
            errors.append(
                f"{plan_file}: Plan ID is '{plan_id}', expected '{plan_dir.name}'"
            )
        plan_phase = field(plan, "Phase")
        if plan_phase is not None and plan_phase != phase_id:
            errors.append(
                f"{plan_file}: Phase is '{plan_phase}', master says '{phase_id}'"
            )
        plan_depends = field(plan, "Depends on")
        if plan_depends is not None:
            if expand_phase_refs(plan_depends) != expand_phase_refs(str(row["depends"])):
                errors.append(
                    f"{plan_file}: Depends on '{plan_depends}' does not match "
                    f"master '{row['depends']}'"
                )
        master_link = field(plan, "Master plan")
        if master_link:
            target = Path(link_target(master_link))
            if not target.is_absolute():
                target = plan_file.parent / target
            if not target.exists():
                errors.append(
                    f"{plan_file}: Master plan link does not exist ({target})"
                )

        plan_number = field(plan, "Plan version")
        if plan_number is None:
            errors.append(f"{plan_file}: missing 'Plan version'")
        else:
            try:
                int(plan_number)
            except ValueError:
                errors.append(f"{plan_file}: invalid Plan version '{plan_number}'")

        plan_version = field(plan, "Validated against master version")
        if plan_version is None:
            errors.append(f"{plan_file}: missing 'Validated against master version'")
        elif version is not None:
            try:
                behind = int(plan_version) < version
            except ValueError:
                behind = False
                errors.append(
                    f"{plan_file}: invalid master version '{plan_version}'"
                )
            if behind and effective_status in {"ready", "in_progress"}:
                errors.append(
                    f"{plan_file}: validated against master v{plan_version}, "
                    f"master is v{version}; revalidate the phase plan"
                )

        if effective_status in {"ready", "in_progress", "done"}:
            approved_by = field(plan, "Approved by")
            approved_at = field(plan, "Approved at")
            if approval_ready and is_pending(approved_by):
                errors.append(
                    f"{plan_file}: {phase_id} is {effective_status} without user approval; "
                    f"run approve {plan_dir} {phase_id} --by <user>"
                )
            if approval_ready and is_pending(approved_at):
                errors.append(
                    f"{plan_file}: {phase_id} is {effective_status} without an approval date"
                )

            implementation_mode = field(plan, "Implementation mode")
            if implementation_mode not in {"subagent", "coordinator-exception"}:
                errors.append(
                    f"{plan_file}: {phase_id} needs 'Implementation mode: subagent' "
                    "or 'coordinator-exception'"
                )
            if implementation_mode == "coordinator-exception":
                exception_by = field(plan, "Exception approved by")
                exception_reason = field(plan, "Exception reason")
                if is_pending(exception_by):
                    errors.append(
                        f"{plan_file}: coordinator-exception for {phase_id} "
                        "has no approving user"
                    )
                if is_pending(exception_reason):
                    errors.append(
                        f"{plan_file}: coordinator-exception for {phase_id} "
                        "has no reason"
                    )

            parallel_safe = (field(plan, "Parallel safe") or "no").strip().lower()
            for dependency in sorted(expand_phase_refs(str(row["depends"]))):
                dependency_row = next(
                    (item for item in rows if item["id"] == dependency), None
                )
                if (
                    dependency_row is not None
                    and dependency_row["status"] != "done"
                    and effective_status in {"ready", "in_progress"}
                    and parallel_safe not in {"yes", "true"}
                ):
                    errors.append(
                        f"{plan_file}: {phase_id} is {effective_status} but depends on "
                        f"{dependency}, which is {dependency_row['status']}; "
                        "finish the dependency or set Parallel safe: yes"
                    )

            mentioned = mentioned_ledger_ids(plan)
            known_ledger = {
                entry["id"] for entry in entries if not entry.get("malformed")
            }
            for mentioned_id in sorted(mentioned):
                if mentioned_id not in known_ledger:
                    errors.append(
                        f"{plan_file}: 'Prior discoveries applied' names unknown "
                        f"ledger row {mentioned_id}"
                    )
            for entry in affecting_ledger(entries, phase_id):
                if entry["id"] not in mentioned:
                    errors.append(
                        f"{plan_file}: missing ledger {entry['id']} in "
                        f"'Prior discoveries applied' (affects {entry.get('affects', '')})"
                    )

            for name in [
                "Phase objective",
                "Master traceability",
                "Prior discoveries applied",
                "Scope",
                "Entry conditions",
                "Steps",
                "Phase acceptance criteria",
                "Code standards check",
                "Risks and unknowns",
            ]:
                for finding in placeholder_findings(section(plan, name)):
                    errors.append(
                        f"{plan_file}: {name} still contains placeholder {finding}"
                    )

            steps = step_items(plan)
            if not steps:
                errors.append(f"{plan_file}: Steps has no S items")
            acceptance = acceptance_items(plan)
            if not acceptance:
                errors.append(
                    f"{plan_file}: Phase acceptance criteria has no A items"
                )
            acceptance_ids = [item["id"] for item in acceptance]
            if len(acceptance_ids) != len(set(acceptance_ids)):
                errors.append(
                    f"{plan_file}: Phase acceptance criteria has duplicate A ids"
                )
            for criterion in acceptance:
                if not criterion["verify"]:
                    errors.append(
                        f"{plan_file}: {criterion['id']} has no verify clause"
                    )
            trace = traceability_rows(plan)
            if not trace:
                errors.append(
                    f"{plan_file}: Master traceability has no D rows"
                )
            dod_ids = {item["id"] for item in dod}
            for item in trace:
                if item["d"] not in dod_ids:
                    errors.append(
                        f"{plan_file}: Master traceability references unknown {item['d']}"
                    )
                if not item["criteria"]:
                    errors.append(
                        f"{plan_file}: Master traceability row {item['d']} names no A criterion"
                    )
            for criterion in acceptance:
                if not any(
                    criterion["id"] in item["criteria"] for item in trace
                ):
                    errors.append(
                        f"{plan_file}: {criterion['id']} is not traced to a master D item"
                    )

            standards = standards_check_items(plan)
            if not standards:
                errors.append(
                    f"{plan_file}: Code standards check has no checklist items"
                )

        if effective_status == "done":
            implemented_by = field(plan, "Implemented by")
            implemented_at = field(plan, "Implemented at")
            if is_pending(implemented_by):
                errors.append(
                    f"{plan_file}: done phase has no 'Implemented by' record"
                )
            if is_pending(implemented_at):
                errors.append(
                    f"{plan_file}: done phase has no 'Implemented at' record"
                )

            commit_hash = field(plan, "Commit")
            if is_pending(commit_hash):
                errors.append(
                    f"{plan_file}: done phase has no commit; run record-commit "
                    f"{plan_dir} {phase_id}"
                )
            else:
                repo = git_root(plan_dir)
                if repo is not None:
                    if not commit_exists(repo, str(commit_hash)):
                        errors.append(
                            f"{plan_file}: commit {commit_hash} does not exist in {repo}"
                        )
                    elif not commit_is_ancestor(repo, str(commit_hash)):
                        errors.append(
                            f"{plan_file}: commit {commit_hash} is not an ancestor of HEAD"
                        )

            verdict = closeout_verdict(plan) or ""
            if verdict not in VALID_VERDICTS:
                errors.append(
                    f"{plan_file}: done phase has no valid closeout verdict "
                    f"(found '{verdict or 'none'}')"
                )
            elif verdict != "addressed":
                errors.append(
                    f"{plan_file}: done phase verdict must be 'addressed', "
                    f"found '{verdict}'"
                )

            coverage = closeout_rows(plan)
            by_criterion = {row["criterion"]: row for row in coverage}
            for criterion in acceptance_items(plan):
                row = by_criterion.get(criterion["id"])
                if row is None:
                    errors.append(
                        f"{plan_file}: closeout has no row for {criterion['id']}"
                    )
                elif row["verdict"] != "met":
                    errors.append(
                        f"{plan_file}: {criterion['id']} is not met "
                        f"(found '{row['verdict'] or 'missing'}')"
                    )
                elif not row["evidence"]:
                    errors.append(
                        f"{plan_file}: {criterion['id']} has no evidence"
                    )
            traced_d = {
                item["d"] for item in traceability_rows(plan)
            }
            for item in dod:
                if item["id"] not in traced_d:
                    continue
                row = by_criterion.get(item["id"])
                if row is None:
                    errors.append(
                        f"{plan_file}: closeout has no row for {item['id']} (master)"
                    )
                elif row["verdict"] != "met":
                    errors.append(
                        f"{plan_file}: {item['id']} is not met "
                        f"(found '{row['verdict'] or 'missing'}')"
                    )
                elif not row["evidence"]:
                    errors.append(
                        f"{plan_file}: {item['id']} has no evidence"
                    )

            standards = standards_check_items(plan)
            for index, item in enumerate(standards, start=1):
                if not item["checked"]:
                    errors.append(
                        f"{plan_file}: code standards check item {index} is not checked"
                    )

            history_row = next(
                (
                    row
                    for row in closeout_history_rows(master)
                    if row["phase"] == phase_id
                ),
                None,
            )
            if history_row is None:
                errors.append(
                    f"master: done phase {phase_id} is missing from Closeout history"
                )
            else:
                if history_row["malformed"]:
                    errors.append(
                        f"master: Closeout history row for {phase_id} is malformed"
                    )
                if history_row["verdict"] != "addressed":
                    errors.append(
                        f"master: Closeout history for {phase_id} is not addressed"
                    )
                if is_pending(history_row["commit"]):
                    errors.append(
                        f"master: Closeout history for {phase_id} has no commit"
                    )
                if not history_row["criteria"]:
                    errors.append(
                        f"master: Closeout history for {phase_id} has no criteria met"
                    )

    return phase_plan_files


def _validate_master_completion(
    master_status: str | None,
    rows: list[dict[str, Any]],
    dod: list[dict[str, Any]],
    errors: list[str],
) -> None:
    if master_status == "complete":
        unchecked = [item["id"] for item in dod if not item["checked"]]
        if unchecked:
            errors.append(
                "master: status is complete but definition-of-done is unchecked: "
                + ", ".join(unchecked)
            )


def _validate_final_closeout(
    rows: list[dict[str, Any]],
    dod: list[dict[str, Any]],
    phase_plan_files: dict[str, Path],
    errors: list[str],
) -> None:
    if rows and all(row["status"] == "done" for row in rows):
        unchecked = [item["id"] for item in dod if not item["checked"]]
        if unchecked:
            errors.append(
                "master: all phases are done but definition-of-done is unchecked: "
                + ", ".join(unchecked)
            )
        final_row = max(rows, key=lambda row: identifier_number(row["id"]))
        final_file = phase_plan_files.get(final_row["id"])
        if final_file and final_file.exists():
            final_plan = read_text(final_file)
            coverage = {
                row["criterion"]: row for row in closeout_rows(final_plan)
            }
            for item in dod:
                row = coverage.get(item["id"])
                if row is None:
                    errors.append(
                        f"{final_file}: final closeout has no row for {item['id']} (master)"
                    )
                elif row["verdict"] != "met":
                    errors.append(
                        f"{final_file}: final closeout does not mark {item['id']} met"
                    )
                elif not row["evidence"]:
                    errors.append(
                        f"{final_file}: final closeout has no evidence for {item['id']}"
                    )


def validate_plan(
    plan_dir: Path,
    *,
    strict: bool = False,
    only_phase: str | None = None,
    for_approval: bool = False,
) -> dict[str, Any]:
    """Validate a master plan and its phase plans.

    only_phase limits per-phase checks to one phase. for_approval applies the
    ready-phase content checks to that phase before its status is changed.
    """
    plan_dir = Path(plan_dir)
    errors: list[str] = []
    warnings: list[str] = []
    master_file = plan_dir / "master.md"
    if not master_file.exists():
        return {"errors": [f"{master_file} does not exist"], "warnings": []}

    master = read_text(master_file)
    version, master_status, goal_flow = _validate_master_header(master, errors)
    dod = _validate_definition_items(master, errors)
    rows, phase_ids = _validate_phase_map(master, errors, warnings)
    active = any(
        row["status"] in {"ready", "in_progress", "done"} for row in rows
    ) or master_status in {"active", "complete"} or (
        for_approval and only_phase is not None
    )
    entries = _validate_ledger_rows(master, errors, phase_ids, active)
    _validate_decision_rows(master, errors, phase_ids, active)
    _validate_dependency_graph(rows, phase_ids, active, errors)
    _validate_active_master_content(master, goal_flow, dod, active, errors)
    _validate_master_status_rules(master_status, rows, active, errors, warnings)
    phase_plan_files = _validate_phase_plans(
        plan_dir,
        master,
        rows,
        version,
        dod,
        entries,
        only_phase,
        for_approval,
        errors,
    )
    _validate_master_completion(master_status, rows, dod, errors)
    _validate_final_closeout(rows, dod, phase_plan_files, errors)

    if strict and warnings:
        errors.extend(f"warning treated as error: {warning}" for warning in warnings)
        warnings = []

    return {"errors": errors, "warnings": warnings}


def current_phase_id(
    master: str, rows: list[dict[str, Any]], override: str | None = None
) -> str | None:
    if override:
        return override
    for wanted in ("in_progress", "ready", "blocked", "needs_replan", "planned"):
        for row in rows:
            if row["status"] == wanted:
                return row["id"]
    if rows:
        done = [row for row in rows if row["status"] == "done"]
        if done:
            return max(done, key=lambda row: identifier_number(row["id"]))["id"]
    brief = section(master, "Resume brief")
    match = re.search(r"^-\s*Current phase:\s*(P\d+)", brief, re.MULTILINE)
    return match.group(1) if match else None


def build_status(plan_dir: Path, phase_override: str | None = None) -> dict[str, Any]:
    plan_dir = Path(plan_dir)
    master_file = plan_dir / "master.md"
    if not master_file.exists():
        return {
            "error": f"{master_file} does not exist",
            "errors": [f"{master_file} does not exist"],
            "warnings": [],
        }
    master = read_text(master_file)
    version = master_version(master)
    status = field(master, "Status")
    mode = master_mode(master)
    rows = phase_rows(master)
    check = validate_plan(plan_dir)
    current = current_phase_id(master, rows, phase_override)
    if phase_override and not any(row["id"] == phase_override for row in rows):
        check["errors"].append(
            f"phase {phase_override} is not in the master phase map"
        )
    current_row = next((row for row in rows if row["id"] == current), None)
    brief = section(master, "Resume brief").strip()
    brief_phase_match = re.search(
        r"^-\s*Current phase:\s*(P\d+)", brief, re.MULTILINE
    )
    brief_phase = brief_phase_match.group(1) if brief_phase_match else None
    warnings = list(check["warnings"])
    if brief_phase and current and brief_phase != current:
        warnings.append(
            f"resume brief says current phase {brief_phase}, plan state says {current}"
        )

    yolo = mode == "yolo"
    next_action = (
        "Write the next phase plan, check it, auto-approve it, and continue."
        if yolo
        else "Write the next phase plan from the master and stop for approval."
    )
    if check["errors"]:
        next_action = "Fix the plan validation errors before any implementation."
    elif not rows:
        next_action = "Add the first phase to the master phase map."
    elif all(row["status"] == "done" for row in rows):
        history_step = (
            "condense the branch with the condense gate, "
            if master_history(master) == "per-phase"
            else ""
        )
        next_action = (
            "All phases are done. Run the final definition-of-done sweep, "
            + (
                f"then {history_step}archive the plan files, update the PR title "
                "and body, and leave the draft PR for review."
                if yolo
                else "then offer a draft PR, ask whether to keep or remove "
                f"the plan files, {history_step}and update the PR title and body."
            )
        )
    elif current_row is not None:
        if current_row["status"] == "in_progress":
            next_action = (
                "Inspect the worker's files, verification, closeout, and commit. "
                "Do not reimplement. Finish the coordinator review and close the phase."
            )
        elif current_row["status"] == "ready":
            next_action = (
                "Set the phase in_progress and spawn one implementation subagent "
                "with references/worker-prompt-template.md."
            )
        elif current_row["status"] == "blocked":
            next_action = "Report the blocker, owner, and unblocking condition."
        elif current_row["status"] == "needs_replan":
            next_action = (
                "Rewrite the phase plan against the current master, then "
                + ("auto-approve it with --yolo and continue." if yolo else "ask for approval.")
            )
        elif current_row["status"] == "planned":
            next_action = (
                "Write or complete the phase plan, run check, then "
                + (
                    "auto-approve it with approve --yolo and start implementation."
                    if yolo
                    else "ask for approval."
                )
            )

    title = master.splitlines()[0].lstrip("# ").strip() if master.splitlines() else plan_dir.name
    title = re.sub(r"^Master Plan\s*[—-]\s*", "", title)
    return {
        "title": title,
        "plan_dir": str(plan_dir),
        "master_version": version,
        "master_status": status,
        "mode": mode,
        "mode_authorized_by": field(master, "Mode authorized by"),
        "size": field(master, "Size"),
        "branch": field(master, "Branch"),
        "resume_brief": brief.splitlines(),
        "phases": rows,
        "current_phase": current,
        "next_action": next_action,
        "check": check,
        "warnings": warnings,
        "errors": check["errors"],
    }


def build_resume_report(
    plan_dir: Path, phase_override: str | None = None
) -> dict[str, Any]:
    plan_dir = Path(plan_dir).resolve()
    status = build_status(plan_dir, phase_override)
    if "error" in status:
        return status
    master = read_text(plan_dir / "master.md")
    rows = status["phases"]
    current = status["current_phase"]
    current_row = next((row for row in rows if row["id"] == current), None)
    warnings = list(status["warnings"])
    errors = list(status["errors"])

    repo = git_root(plan_dir)
    branch = current_branch(plan_dir) if repo else None
    head = git(plan_dir, "rev-parse", "--short", "HEAD") if repo else None
    dirty = working_tree(plan_dir) if repo else []
    branch_field = field(master, "Branch")
    if branch_field and branch and branch_field.strip("` ") != branch:
        warnings.append(
            f"master records branch '{branch_field.strip('` ')}', current branch is '{branch}'"
        )

    phase: dict[str, Any] | None = None
    checks: list[str] = []
    if current_row is not None:
        plan_file = phase_plan_path(plan_dir, current_row)
        plan = read_text(plan_file) if plan_file.exists() else ""
        approved_by = field(plan, "Approved by")
        approved_at = field(plan, "Approved at")
        commit = field(plan, "Commit")
        verdict = closeout_verdict(plan)
        acceptance = acceptance_items(plan)
        met = [item["id"] for item in acceptance if item["checked"]]
        pending = [item["id"] for item in acceptance if not item["checked"]]
        mentioned = mentioned_ledger_ids(plan)
        affecting = affecting_ledger(ledger_rows(master), current_row["id"])
        missing = [entry["id"] for entry in affecting if entry["id"] not in mentioned]
        if commit and not is_pending(commit) and repo is not None:
            checks.append(
                f"recorded commit {commit} exists: {commit_exists(repo, commit)}"
            )
            checks.append(
                f"recorded commit {commit} is an ancestor of HEAD: "
                f"{commit_is_ancestor(repo, commit)}"
            )
        phase = {
            "id": current_row["id"],
            "name": current_row["name"],
            "master_status": current_row["status"],
            "plan_file": str(plan_file),
            "plan_status": field(plan, "Status"),
            "approved_by": approved_by,
            "approved_at": approved_at,
            "approved": not is_pending(approved_by) and not is_pending(approved_at),
            "implementation_mode": field(plan, "Implementation mode"),
            "implemented_by": field(plan, "Implemented by"),
            "implemented_at": field(plan, "Implemented at"),
            "commit": None if is_pending(commit) else commit,
            "verdict": verdict,
            "validated_against": field(plan, "Validated against master version"),
            "acceptance": {"met": met, "pending": pending, "total": len(acceptance)},
            "prior_discoveries": sorted(mentioned),
            "affecting_discoveries": [
                {"id": entry["id"], "affects": entry["affects"], "discovery": entry["discovery"]}
                for entry in affecting
            ],
            "missing_discoveries": missing,
            "verification": verification_lines(plan),
        }

    gate = "NO ACTIVE PHASE"
    if errors:
        gate = "PLAN CHECK FAILED"
    elif rows and all(row["status"] == "done" for row in rows):
        gate = "ALL PHASES DONE"
    elif current_row is not None:
        gate = {
            "in_progress": "IN PROGRESS",
            "ready": "READY TO SPAWN" if phase and phase["approved"] else "APPROVAL REQUIRED",
            "blocked": "BLOCKED",
            "needs_replan": "REPLAN REQUIRED",
            "planned": "PLAN REQUIRED",
            "done": "DONE",
        }.get(current_row["status"], "UNKNOWN")

    return {
        "title": status["title"],
        "plan_dir": str(plan_dir),
        "master_version": status["master_version"],
        "master_status": status["master_status"],
        "mode": status["mode"],
        "mode_authorized_by": status["mode_authorized_by"],
        "resume_brief": status["resume_brief"],
        "phases": rows,
        "current_phase": phase,
        "git": {
            "repository": str(repo) if repo else None,
            "branch": branch,
            "head": head,
            "working_tree": dirty,
            "checks": checks,
        },
        "check": status["check"],
        "gate": gate,
        "next_action": status["next_action"],
        "warnings": warnings,
        "errors": errors,
    }


def verification_lines(plan: str) -> list[str]:
    lines: list[str] = []
    for line in plan.splitlines():
        stripped = line.strip()
        for prefix in ("- Verification:", "- Verification run:"):
            if stripped.startswith(prefix):
                value = stripped[len(prefix):].strip().replace("`", "").strip().rstrip(".;")
                if value and value not in lines:
                    lines.append(value)
    return lines[:10]


def _phase_map_lines(rows: list[dict[str, Any]]) -> list[str]:
    return [
        f"  {row['id']:<3} {row['status']:<12} {row['name']} "
        f"(depends: {row['depends']})"
        for row in rows
    ]


def _brief_lines(brief: list[str]) -> list[str]:
    return [f"  {line.strip()}" for line in brief if line.strip()]


def render_resume_text(report: dict[str, Any]) -> str:
    if "error" in report:
        return f"error: {report['error']}"
    lines: list[str] = []
    lines.append(f"Resume — {report['title']}")
    lines.append(f"Plan directory: {report['plan_dir']}")
    lines.append(
        f"Master: v{report['master_version']}, status {report['master_status']}, "
        f"mode {report['mode']}"
    )
    lines.append("")
    lines.append("Phase map:")
    lines.extend(_phase_map_lines(report["phases"]))
    if report["resume_brief"]:
        lines.append("")
        lines.append("Resume brief:")
        lines.extend(_brief_lines(report["resume_brief"]))
    lines.append("")
    phase = report["current_phase"]
    if phase is None:
        lines.append("Current phase: none")
    else:
        lines.append(f"Current phase: {phase['id']} — {phase['name']}")
        lines.append(f"  Master status: {phase['master_status']}")
        lines.append(f"  Plan status: {phase['plan_status']}")
        approval = (
            f"approved by {phase['approved_by']} on {phase['approved_at']}"
            if phase["approved"]
            else f"pending (Approved by: {phase['approved_by'] or 'none'})"
        )
        lines.append(f"  Approval: {approval}")
        lines.append(
            f"  Implementation: {phase['implementation_mode'] or 'missing'} / "
            f"implemented by {phase['implemented_by'] or 'pending'}"
        )
        lines.append(f"  Commit: {phase['commit'] or 'none recorded'}")
        lines.append(f"  Closeout verdict: {phase['verdict'] or 'none'}")
        criteria = phase["acceptance"]
        lines.append(
            f"  Acceptance: {len(criteria['met'])}/{criteria['total']} met"
            + (
                f"; pending: {', '.join(criteria['pending'])}"
                if criteria["pending"]
                else ""
            )
        )
        lines.append(
            "  Prior discoveries: "
            + (", ".join(phase["prior_discoveries"]) or "none")
        )
        lines.append(
            "  Missing affecting discoveries: "
            + (", ".join(phase["missing_discoveries"]) or "none")
        )
        if phase["verification"]:
            lines.append("  Verification commands:")
            for value in phase["verification"]:
                lines.append(f"    {value}")
    lines.append("")
    lines.append("Git:")
    lines.append(f"  Repository: {report['git']['repository'] or 'not a git repository'}")
    lines.append(f"  Branch: {report['git']['branch'] or 'unknown'}")
    lines.append(f"  HEAD: {report['git']['head'] or 'unknown'}")
    dirty = report["git"]["working_tree"]
    lines.append(
        f"  Working tree: {'clean' if not dirty else f'{len(dirty)} uncommitted file(s)'}"
    )
    for value in dirty:
        lines.append(f"    {value}")
    for value in report["git"]["checks"]:
        lines.append(f"  {value}")
    lines.append("")
    lines.append(f"Plan check: {'ok' if not report['errors'] else 'FAILED'}")
    for error in report["errors"]:
        lines.append(f"  error: {error}")
    if report["warnings"]:
        lines.append("")
        lines.append("Warnings:")
        for warning in report["warnings"]:
            lines.append(f"  - {warning}")
    lines.append("")
    lines.append(f"Gate: {report['gate']}")
    lines.append(f"Next action: {report['next_action']}")
    return "\n".join(lines)


def render_status_text(status: dict[str, Any]) -> str:
    if "error" in status:
        return f"error: {status['error']}"
    lines = [
        f"{status['title']} — master v{status['master_version']} "
        f"({status['master_status']}, {status['mode']})"
    ]
    lines.extend(_phase_map_lines(status["phases"]))
    if status["resume_brief"]:
        lines.append("")
        lines.append("Resume brief")
        lines.extend(_brief_lines(status["resume_brief"]))
    lines.append("")
    lines.append(f"Plan check: {'ok' if not status['errors'] else 'FAILED'}")
    for error in status["errors"]:
        lines.append(f"  error: {error}")
    for warning in status["warnings"]:
        lines.append(f"  warning: {warning}")
    lines.append(f"Next action: {status['next_action']}")
    return "\n".join(lines)


def render_report(plan_dir: Path) -> str:
    plan_dir = Path(plan_dir)
    status = build_status(plan_dir)
    if "error" in status:
        return f"error: {status['error']}"
    master = read_text(plan_dir / "master.md")
    rows = status["phases"]
    lines: list[str] = []
    lines.append(f"# {status['title']}")
    lines.append("")
    lines.append(
        f"- Master version: {status['master_version']}\n"
        f"- Status: {status['master_status']}\n"
        f"- Mode: {status['mode']}\n"
        f"- Size: {status['size']}\n"
        f"- Branch: {status['branch']}\n"
        f"- Plan directory: `{plan_dir}`"
    )
    lines.append("")
    lines.append("## Issue")
    source = field(master, "Source")
    lines.append(f"Source: {source or '_missing_'}")
    lines.append("")
    lines.append("## Objective")
    lines.append(section(master, "Objective").strip() or "_missing_")
    dod_items = definition_items(master)
    lines.append("")
    lines.append("## Definition of done")
    for item in dod_items:
        mark = "x" if item["checked"] else " "
        lines.append(f"- [{mark}] {item['id']} — {item['text']}")
    done_rows = [row for row in rows if row["status"] == "done"]
    if done_rows:
        final_row = max(
            done_rows, key=lambda row: identifier_number(row["id"])
        )
        final_file = phase_plan_path(plan_dir, final_row)
        if final_file.exists():
            final_coverage = {
                row["criterion"]: row
                for row in closeout_rows(read_text(final_file))
            }
            lines.append("")
            lines.append("### Definition of done verdicts")
            lines.append("| Item | Verdict | Evidence |")
            lines.append("|---|---|---|")
            for item in dod_items:
                row = final_coverage.get(item["id"])
                if row is None:
                    lines.append(f"| {item['id']} | not covered | - |")
                else:
                    lines.append(
                        f"| {item['id']} | {row['verdict'] or 'missing'} | "
                        f"{row['evidence'] or '-'} |"
                    )
    lines.append("")
    lines.append("## What was done")
    if rows:
        for row in rows:
            plan_file = phase_plan_path(plan_dir, row)
            commit = ""
            if plan_file.exists():
                value = field(read_text(plan_file), "Commit")
                if value and not is_pending(value):
                    commit = f" — commit `{value}`"
            lines.append(
                f"- {row['id']} — {row['name']}: {row['outcome']} "
                f"({row['status']}){commit}"
            )
    else:
        lines.append("_none_")
    lines.append("")
    lines.append("## Decisions")
    decisions = decision_rows(master)
    if decisions:
        lines.append("| ID | Date | Decision | Reason | Affects |")
        lines.append("|---|---|---|---|---|")
        for decision in decisions:
            lines.append(
                f"| {decision['id']} | {decision['date']} | "
                f"{decision['decision']} | {decision['reason']} | "
                f"{decision['affects']} |"
            )
    else:
        lines.append("_none_")
    lines.append("")
    lines.append("## Phase map")
    lines.append("| ID | Phase | Outcome | Depends on | Status | Plan |")
    lines.append("|---|---|---|---|---|---|")
    for row in rows:
        lines.append(
            f"| {row['id']} | {row['name']} | {row['outcome']} | "
            f"{row['depends']} | {row['status']} | {row['plan']} |"
        )
    lines.append("")
    lines.append("## Closeout history")
    history = closeout_history_rows(master)
    if history:
        lines.append("| Phase | Date | Verdict | Criteria met | Commit | Report |")
        lines.append("|---|---|---|---|---|---|")
        for row in history:
            lines.append(
                f"| {row['phase']} | {row['date']} | {row['verdict']} | "
                f"{row['criteria']} | {row['commit']} | {row['report']} |"
            )
    else:
        lines.append("_none_")
    lines.append("")
    lines.append("## Verification")
    verification_rows: list[str] = []
    for row in rows:
        plan_file = phase_plan_path(plan_dir, row)
        if not plan_file.exists():
            continue
        for command in verification_lines(read_text(plan_file)):
            verification_rows.append(f"- {row['id']}: {command}")
    lines.extend(verification_rows or ["_none recorded_"])
    lines.append("")
    lines.append("## Open questions, risks, and blockers")
    open_items = section(master, "Open questions").strip()
    lines.append(open_items or "_none_")
    lines.append("")
    lines.append("## Validation")
    if status["errors"]:
        for error in status["errors"]:
            lines.append(f"- error: {error}")
    else:
        lines.append("- ok")
    if status["warnings"]:
        for warning in status["warnings"]:
            lines.append(f"- warning: {warning}")
    return "\n".join(lines)
