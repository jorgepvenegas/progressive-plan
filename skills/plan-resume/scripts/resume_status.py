#!/usr/bin/env python3
"""Print a resume report for an in-progress progressive-plan master plan."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

PRINTABLE = True


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


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


def field(text: str, name: str) -> str | None:
    match = re.search(
        r"^-\s*" + re.escape(name) + r":\s*(.+)$", text, re.MULTILINE
    )
    return match.group(1).strip() if match else None


def is_pending(value: str | None) -> bool:
    return not value or value.strip().lower() in {"", "pending", "tbd", "none", "n/a", "-"}


def master_version(master: str) -> int | None:
    match = re.search(r"^-\s*Master version:\s*(\d+)", master, re.MULTILINE)
    return int(match.group(1)) if match else None


def link_target(cell: str) -> str:
    match = re.search(r"\(([^)]+)\)", cell)
    return match.group(1) if match else cell


def phase_rows(master: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in section(master, "Phase map").splitlines():
        if not re.match(r"^\|\s*P\d+\s*\|", line):
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


def ledger_rows(master: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in section(master, "Discovery ledger").splitlines():
        if not re.match(r"^\|\s*[A-Z]\d+\s*\|", line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 8:
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
            }
        )
    return rows


def expand_refs(value: str) -> set[str]:
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
            refs.update(
                f"P{index}" for index in range(int(match.group(1)), int(match.group(2)) + 1)
            )
            continue
        if re.fullmatch(r"P\d+", part):
            refs.add(part)
    return refs


def mentioned_ledger_ids(plan: str) -> set[str]:
    ids: set[str] = set()
    for line in section(plan, "Prior discoveries applied").splitlines():
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
                ids.update(
                    f"{prefix}{index}"
                    for index in range(int(match.group(2)), int(match.group(3)) + 1)
                )
            elif re.fullmatch(r"[A-Z]\d+", part):
                ids.add(part)
    return ids


def acceptance(plan: str) -> dict[str, object]:
    text = section(plan, "Phase acceptance criteria")
    met = re.findall(r"^-\s*\[x\]\s*(A\d+)", text, re.MULTILINE | re.IGNORECASE)
    pending = re.findall(r"^-\s*\[ \]\s*(A\d+)", text, re.MULTILINE)
    return {"met": met, "pending": pending, "total": len(met) + len(pending)}


def closeout_verdict(plan: str) -> str | None:
    closeout = section(plan, "Closeout")
    match = re.search(r"^-\s*Verdict:\s*(\S+)", closeout, re.MULTILINE)
    return match.group(1).strip() if match else None


def verification_lines(plan: str) -> list[str]:
    lines: list[str] = []
    for line in plan.splitlines():
        stripped = line.strip()
        for prefix in ("- Verification:", "- Verification run:"):
            if stripped.startswith(prefix):
                value = stripped[len(prefix):].strip()
                value = value.replace("`", "").strip().rstrip(".;")
                if value and value not in lines:
                    lines.append(value)
    return lines[:10]


def placeholder_count(plan: str) -> int:
    return len(re.findall(r"<[^>\n]{2,}>|\bTBD\b|\?\?", plan))


def git(plan_dir: Path, *args: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(plan_dir), *args],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def progressive_plan_check(plan_dir: Path) -> dict[str, object]:
    script = (
        Path(__file__).resolve().parents[2]
        / "progressive-plan"
        / "scripts"
        / "progressive_plan.py"
    )
    if not script.exists():
        return {"ok": False, "output": f"progressive_plan.py not found at {script}"}
    result = subprocess.run(
        [sys.executable, str(script), "check", str(plan_dir)],
        capture_output=True,
        text=True,
    )
    return {
        "ok": result.returncode == 0,
        "output": (result.stdout + result.stderr).strip(),
    }


def current_phase_id(
    master: str, rows: list[dict[str, str]], override: str | None = None
) -> str | None:
    if override:
        return override
    resume = section(master, "Resume brief")
    match = re.search(r"^-\s*Current phase:\s*(P\d+)", resume, re.MULTILINE)
    if match:
        return match.group(1)
    for wanted in ("in_progress", "ready", "blocked", "needs_replan", "planned"):
        for row in rows:
            if row["status"] == wanted:
                return row["id"]
    return None


def build_report(plan_dir: Path, phase_override: str | None = None) -> dict[str, object]:
    master_file = plan_dir / "master.md"
    if not master_file.exists():
        fail(f"{master_file} does not exist")
    master = master_file.read_text()
    rows = phase_rows(master)
    version = master_version(master)
    title = master.splitlines()[0].lstrip("# ").strip() if master.splitlines() else plan_dir.name
    title = re.sub(r"^Master Plan\s*[—-]\s*", "", title)
    resume = section(master, "Resume brief").strip()
    phase_id = current_phase_id(master, rows, phase_override)
    row = next((item for item in rows if item["id"] == phase_id), None)

    warnings: list[str] = []
    check = progressive_plan_check(plan_dir)
    if not check["ok"]:
        warnings.append(f"progressive_plan.py check failed: {check['output']}")

    repo_root = git(plan_dir, "rev-parse", "--show-toplevel")
    branch = git(plan_dir, "rev-parse", "--abbrev-ref", "HEAD")
    head = git(plan_dir, "rev-parse", "--short", "HEAD")
    status_lines = (git(plan_dir, "status", "--porcelain") or "").splitlines()
    status_lines = [line for line in status_lines if line.strip()]

    phase: dict[str, object] | None = None
    git_checks: list[str] = []
    if row is not None:
        plan_file = plan_dir / link_target(row["plan"])
        if not plan_file.exists():
            warnings.append(f"{row['id']} phase plan is missing: {plan_file}")
        plan = plan_file.read_text() if plan_file.exists() else ""
        plan_status = field(plan, "Status")
        approved_by = field(plan, "Approved by")
        approved_at = field(plan, "Approved at")
        commit = field(plan, "Commit")
        implementation_mode = field(plan, "Implementation mode")
        implemented_by = field(plan, "Implemented by")
        implemented_at = field(plan, "Implemented at")
        validated = field(plan, "Validated against master version")
        verdict = closeout_verdict(plan)
        criteria = acceptance(plan)
        mentioned = mentioned_ledger_ids(plan)
        affecting = [
            entry
            for entry in ledger_rows(master)
            if entry["status"] != "superseded"
            and (
                "all" in expand_refs(entry["affects"])
                or row["id"] in expand_refs(entry["affects"])
            )
        ]
        missing = [entry["id"] for entry in affecting if entry["id"] not in mentioned]
        approved = not is_pending(approved_by) and not is_pending(approved_at)

        if row["status"] in {"ready", "in_progress", "done"} and not approved:
            warnings.append(f"{row['id']} is {row['status']} without an approval record")
        if row["status"] in {"ready", "in_progress", "done"} and implementation_mode not in {
            "subagent",
            "coordinator-exception",
        }:
            warnings.append(f"{row['id']} has no valid Implementation mode")
        if row["status"] == "done" and is_pending(commit):
            warnings.append(f"{row['id']} is done without a recorded commit")
        if row["status"] == "done" and is_pending(verdict):
            warnings.append(f"{row['id']} is done without a closeout verdict")
        if missing:
            warnings.append(
                f"{row['id']} plan does not list affecting discoveries: {', '.join(missing)}"
            )
        if (
            row["status"] in {"ready", "in_progress"}
            and validated is not None
            and version is not None
        ):
            try:
                if int(validated) < version:
                    warnings.append(
                        f"{row['id']} plan is validated against v{validated}, master is v{version}"
                    )
            except ValueError:
                warnings.append(f"{row['id']} has an invalid master version '{validated}'")
        if plan_status != row["status"] and row["status"] in {"ready", "in_progress", "done"}:
            warnings.append(
                f"{row['id']} plan status is '{plan_status}', master says '{row['status']}'"
            )

        if commit and not is_pending(commit):
            exists = git(plan_dir, "cat-file", "-e", f"{commit}^{{commit}}") is not None
            ancestor = git(plan_dir, "merge-base", "--is-ancestor", commit, "HEAD") is not None
            git_checks.append(f"recorded commit {commit} exists: {exists}")
            git_checks.append(f"recorded commit {commit} is an ancestor of HEAD: {ancestor}")
            if not exists:
                warnings.append(f"recorded commit {commit} does not exist")
            elif not ancestor:
                warnings.append(f"recorded commit {commit} is not in the current history")

        phase = {
            "id": row["id"],
            "name": row["name"],
            "master_status": row["status"],
            "plan_file": str(plan_file),
            "plan_status": plan_status,
            "approved_by": approved_by,
            "approved_at": approved_at,
            "approved": approved,
            "implementation_mode": implementation_mode,
            "implemented_by": implemented_by,
            "implemented_at": implemented_at,
            "commit": None if is_pending(commit) else commit,
            "verdict": verdict,
            "validated_against": validated,
            "acceptance": criteria,
            "prior_discoveries": sorted(mentioned, key=lambda value: (value[0], int(value[1:]))),
            "affecting_discoveries": [
                {"id": entry["id"], "affects": entry["affects"], "discovery": entry["discovery"]}
                for entry in affecting
            ],
            "missing_discoveries": missing,
            "verification": verification_lines(plan),
        }

    gate = "NO ACTIVE PHASE"
    next_action = "Write the next phase plan from the master and stop for approval."
    if rows and all(item["status"] == "done" for item in rows):
        gate = "ALL PHASES DONE"
        next_action = (
            "All phases are done. Run the final definition-of-done sweep, then stop; do not start "
            "new work without user approval."
        )
    if phase is not None:
        master_status = str(phase["master_status"])
        if master_status == "done":
            gate = "DONE"
            next_action = (
                "The current phase is done. Write the next phase plan and present it for approval; "
                "do not implement it yet."
            )
        elif master_status == "blocked":
            gate = "BLOCKED"
            next_action = "Report the blocker, owner, and unblocking condition before any new work."
        elif master_status == "needs_replan":
            gate = "REPLAN REQUIRED"
            next_action = "Rewrite the phase plan against the current master, then ask for approval."
        elif master_status == "in_progress":
            gate = "IN PROGRESS"
            next_action = (
                "Inspect the worker's files, verification, closeout, and commit. Do not reimplement. "
                "Finish the coordinator review and the commit gate."
            )
            if phase["verdict"] not in {None, "pending"}:
                next_action = (
                    "The phase has a closeout verdict. Re-run its verification, check the commit, "
                    "then update the master and mark it done."
                )
        elif master_status == "ready":
            if phase["approved"]:
                gate = "READY TO SPAWN"
                next_action = (
                    "Set the phase in_progress and spawn one implementation subagent with "
                    "references/worker-prompt-template.md. The coordinator must not implement."
                )
            else:
                gate = "APPROVAL REQUIRED"
                next_action = (
                    "Present the phase plan to the user and ask for explicit approval. "
                    "Do not implement or spawn a worker yet."
                )
        else:
            if placeholder_count(plan) > 0:
                gate = "PLAN REQUIRED"
                next_action = (
                    "Complete the phase plan, run check, then present it for approval. "
                    "Do not implement yet."
                )
            else:
                gate = "APPROVAL REQUIRED"
                next_action = (
                    "The phase plan is complete but unapproved. Present it to the user and ask "
                    "for explicit approval. Do not implement or spawn a worker yet."
                )

    if not check["ok"]:
        gate = "PLAN CHECK FAILED"
        next_action = (
            "Fix the master or phase plan until `progressive_plan.py check` passes. "
            "Do not approve a phase or spawn a worker."
        )

    return {
        "title": title,
        "plan_dir": str(plan_dir),
        "master_version": version,
        "master_status": field(master, "Status"),
        "resume_brief": resume.splitlines(),
        "phases": rows,
        "current_phase": phase,
        "git": {
            "repository": repo_root,
            "branch": branch,
            "head": head,
            "working_tree": status_lines,
            "checks": git_checks,
        },
        "check": check,
        "gate": gate,
        "next_action": next_action,
        "warnings": warnings,
    }


def render_text(report: dict[str, object]) -> str:
    lines: list[str] = []
    lines.append(f"Resume — {report['title']}")
    lines.append(f"Plan directory: {report['plan_dir']}")
    lines.append(f"Master: v{report['master_version']}, status {report['master_status']}")
    lines.append("")
    lines.append("Phase map:")
    for row in report["phases"]:
        lines.append(
            f"  {row['id']:<3} {row['status']:<12} {row['name']} "
            f"(depends: {row['depends']})"
        )
    if report["resume_brief"]:
        lines.append("")
        lines.append("Resume brief:")
        for line in report["resume_brief"]:
            if line.strip():
                lines.append(f"  {line.strip()}")

    phase = report["current_phase"]
    lines.append("")
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
            + (f"; pending: {', '.join(criteria['pending'])}" if criteria["pending"] else "")
        )
        lines.append(
            "  Prior discoveries: "
            + (", ".join(phase["prior_discoveries"]) or "none")
        )
        if phase["missing_discoveries"]:
            lines.append(
                "  Missing affecting discoveries: "
                + ", ".join(phase["missing_discoveries"])
            )
        else:
            lines.append("  Missing affecting discoveries: none")
        if phase["verification"]:
            lines.append("  Verification commands:")
            for value in phase["verification"]:
                lines.append(f"    {value}")

    lines.append("")
    lines.append("Git:")
    lines.append(f"  Repository: {report['git']['repository'] or 'not a git repository'}")
    lines.append(f"  Branch: {report['git']['branch'] or 'unknown'}")
    lines.append(f"  HEAD: {report['git']['head'] or 'unknown'}")
    dirty = [line.strip() for line in report["git"]["working_tree"]]
    lines.append(f"  Working tree: {'clean' if not dirty else f'{len(dirty)} uncommitted file(s)'}")
    for value in dirty:
        lines.append(f"    {value}")
    for value in report["git"]["checks"]:
        lines.append(f"  {value}")

    lines.append("")
    lines.append(f"Plan check: {'ok' if report['check']['ok'] else 'FAILED'}")
    if not report["check"]["ok"]:
        lines.append(f"  {report['check']['output']}")
    if report["warnings"]:
        lines.append("")
        lines.append("Warnings:")
        for warning in report["warnings"]:
            lines.append(f"  - {warning}")
    lines.append("")
    lines.append(f"Gate: {report['gate']}")
    lines.append(f"Next action: {report['next_action']}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan_dir")
    parser.add_argument("--phase", help="inspect a specific phase ID instead of the resume brief")
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = parser.parse_args()
    plan_dir = Path(args.plan_dir).resolve()
    report = build_report(plan_dir, args.phase)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render_text(report))


if __name__ == "__main__":
    main()
