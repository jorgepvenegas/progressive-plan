"""Fixtures shared by the progressive-plan tests."""

from __future__ import annotations

import subprocess
from pathlib import Path


def valid_master(
    plan_dir: Path,
    phase_status: str,
    *,
    discovery_row: str = "",
    dod_checked: bool = False,
    brief_phase: str = "P1",
) -> str:
    dod_mark = "x" if dod_checked else " "
    discovery_block = discovery_row or ""
    return f"""# Master Plan — Valid Plan

- Plan ID: `valid-plan`
- Master version: 1
- Status: active
- Created: 2026-11-14
- Source: user request
- Size: small
- Owner: coordinator
- Plan directory: `{plan_dir.as_posix()}`
- Branch: `plan/valid-plan`

## 1. Objective

Add a small, verified behavior.

## 2. Goal flow

```mermaid
flowchart LR
    A["User starts"] --> B["Runs the command"]
    B --> C["Sees the result"]
```

## 3. Definition of done

- [{dod_mark}] D1 — The command prints the expected result — verify: `python3 -c "print('ok')"`

## 4. Code standards

| Topic | Rule or command |
|---|---|
| Source of truth | AGENTS.md |
| Format | none |
| Lint | none |
| Type check | none |
| Tests | python3 -m unittest |
| Project rules | none |

## 5. Non-goals

- No new dependency.

## 6. Current state and assumptions

| Area | Evidence | Constraint or surprise |
|---|---|---|
| Request | user request | none |
| Baseline | `python3 -m unittest` — passes | none |

**Assumptions:** none.
**Unknowns:** none.

## 7. Phase map

| ID | Phase | Outcome | Depends on | Status | Plan |
|---|---|---|---|---|---|
| P1 | Build | Add the behavior | none | {phase_status} | [plan](phases/01-build/plan.md) |

Status: `planned`, `ready`, `in_progress`, `done`, `blocked`, `needs_replan`, `superseded`.

## 8. Cross-phase decisions

| ID | Date | Decision | Reason | Affects |
|---|---|---|---|---|

## 9. Discovery ledger

| ID | Date | Phase | Affects | Discovery | Type | Action taken | Status |
|---|---|---|---|---|---|---|---|
{discovery_block}

## 10. Open questions, risks, and blockers

| ID | Question or risk | Owner | Needed by | Status |
|---|---|---|---|---|

## 11. Closeout history

| Phase | Date | Verdict | Criteria met | Commit | Report |
|---|---|---|---|---|---|

## 12. Resume brief

- Current phase: {brief_phase}
- Last verdict: none
- Next action: implement P1
- Open decisions: none
- PR: none
- Last updated: 2026-11-14
"""


def valid_plan(
    phase_status: str,
    *,
    commit_hash: str = "abc1234",
    discovery_row: str = "",
) -> str:
    plan_status = {
        "planned": "draft",
        "ready": "ready",
        "in_progress": "in_progress",
        "done": "done",
    }.get(phase_status, phase_status)
    done = phase_status == "done"
    checked = "x" if done else " "
    verdict = "addressed" if done else "pending"
    evidence = '`python3 -c "print(\'ok\')"` — ok' if done else "pending"
    coverage = "met" if done else "pending"
    implemented_by = "worker-1" if done else "pending"
    implemented_at = "2026-11-14" if done else "pending"
    commit = commit_hash if done else "pending"
    approved = "Jorge" if phase_status in {"ready", "in_progress", "done"} else "pending"
    approved_at = "2026-11-14" if phase_status in {"ready", "in_progress", "done"} else "pending"
    prior = "| None | none | No ledger rows affect this phase. |"
    if discovery_row:
        cells = [cell.strip() for cell in discovery_row.strip().strip("|").split("|")]
        prior = f"| {cells[0]} | {cells[4]} | Applied to this phase. |"
    return f"""# Phase P1 — Build

- Plan ID: `valid-plan`
- Phase: P1
- Plan version: 1
- Validated against master version: 1
- Status: {plan_status}
- Approved by: {approved}
- Approved at: {approved_at}
- Commit: {commit}
- Implementation mode: subagent
- Implemented by: {implemented_by}
- Implemented at: {implemented_at}
- Exception approved by: none
- Exception reason: none
- Parallel safe: no
- Depends on: none
- Written: 2026-11-14
- Master plan: [master.md](../../master.md)

## 1. Phase objective

Add the behavior.

## 2. Master traceability

| Master item | How this phase advances it | Phase criterion |
|---|---|---|
| D1 | Implements the result | A1 |

## Prior discoveries applied

| Ledger | Discovery | Effect on this phase |
|---|---|---|
{prior}

## 3. Scope

In scope:
- Add the behavior.

Out of scope:
- Nothing.

## 4. Entry conditions

- [ ] Repository is on the plan branch — verify: `git branch --show-current`
- [x] Phase plan revalidated against current master version
- [x] User approved this phase plan — verify: `Approved by` is set

## 5. Steps

### S1 — Add the behavior

- Depends on: none
- Files:
  - `app.py` (create) — the behavior
- Change: add a command that prints ok.
- Acceptance:
  - [x] The command prints ok.
- Verification: `python3 -c "print('ok')"` — expected: ok
- Rollback: delete app.py.

## 6. Phase acceptance criteria

- [{"x" if done else " "}] A1 — The command prints ok — verify: `python3 -c "print('ok')"`

## 7. Code standards check

- [{checked}] The diff is the smallest change that meets the acceptance criteria
- [{checked}] Existing helpers are reused where they fit
- [{checked}] Names and structure state intent
- [{checked}] Tests assert observable behavior
- [{checked}] Master standards commands pass: none, none, none, python3 -m unittest

## 8. Risks and unknowns

| Risk | Likelihood | Impact | Mitigation or check |
|---|---|---|---|
| None | low | low | none |

## 9. Deviations and working notes

None.

## 10. Closeout

- Date: 2026-11-14
- Session: test
- Verdict: {verdict}
- Steps complete: S1
- Verification run: python3 -c "print('ok')" — ok

| Criterion | Verdict | Evidence |
|---|---|---|
| A1 | {coverage} | {evidence} |
| D1 (master) | {coverage} | {evidence} |

**Discoveries no earlier plan predicted:**

| ID | Discovery | Type | Applies to | Action written |
|---|---|---|---|---|

**Master updates written:** none
**Next-phase updates written:** none
**Remaining work and handoff:** none
"""


def make_valid_plan(
    tmp: Path,
    phase_status: str,
    *,
    commit_hash: str = "abc1234",
    discovery_row: str = "",
    dod_checked: bool = False,
    brief_phase: str = "P1",
) -> Path:
    plan_dir = tmp / "plans" / "valid-plan"
    (plan_dir / "phases" / "01-build").mkdir(parents=True, exist_ok=True)
    (plan_dir / "master.md").write_text(
        valid_master(
            plan_dir,
            phase_status,
            discovery_row=discovery_row,
            dod_checked=dod_checked or phase_status == "done",
            brief_phase=brief_phase,
        ),
        encoding="utf-8",
    )
    (plan_dir / "phases" / "01-build" / "plan.md").write_text(
        valid_plan(phase_status, commit_hash=commit_hash, discovery_row=discovery_row),
        encoding="utf-8",
    )
    return plan_dir


def init_git(tmp: Path) -> str:
    subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp, check=True)
    (tmp / "base.txt").write_text("base", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp, check=True)
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=tmp,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()
