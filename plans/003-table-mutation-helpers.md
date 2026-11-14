# Plan 003: Consolidate markdown table location and rewrite helpers

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**:
> `git diff --stat 6f887f0..HEAD -- skills/progressive-plan/scripts/progressive_plan.py`
> Plan 001 and plan 002 may have changed this file's imports and closeout
> verdict call. Re-read the three functions named below before editing.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: LOW/MED
- **Depends on**: `plans/001-parser-helpers.md`
- **Category**: tech-debt
- **Planned at**: commit `6f887f0`, 2026-11-14

## Why this matters

Three commands in `progressive_plan.py` implement the same markdown table
mechanics in three slightly different ways:

- `_insert_table_row` (`progressive_plan.py:88-122`) finds a section, finds a
  table header, finds rows with an ID prefix, and inserts a new row after the
  last one.
- `_set_phase_status` (`progressive_plan.py:125-135`) scans for a phase row,
  splits it, requires exactly six cells, replaces the status cell, and joins it
  back.
- `_upsert_closeout_history` (`progressive_plan.py:518-567`) finds a section,
  finds a table header, replaces an existing phase row or inserts a new one.

A table-format change currently needs three coordinated edits, and the
differences are easy to miss. This plan adds shared helpers for section bounds,
header lookup, row indices, cell splitting, and row formatting. It preserves
every failure message, whitespace decision, and insert position.

## Current state

- `skills/progressive-plan/scripts/progressive_plan.py` — CLI commands and the
  three table helpers.
- `tests/test_plans.py` — existing CLI tests that exercise `add-phase`,
  `add-discovery`, `add-decision`, and `close`.

Current helper shapes:

```python
def _insert_table_row(text: str, section_keyword: str, row: str, prefix: str) -> str:
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if re.match(r"^##\s+.*" + re.escape(section_keyword), line, re.IGNORECASE):
            start = index
            break
    if start is None:
        fail(f"master plan has no {section_keyword} section")
    end = next(
        (
            index
            for index in range(start + 1, len(lines))
            if re.match(r"^##\s+", lines[index])
        ),
        len(lines),
    )
    header = next(
        (
            index
            for index in range(start, end)
            if re.match(r"\|\s*ID\s*\|", lines[index])
        ),
        None,
    )
    if header is None:
        fail(f"{section_keyword} has no table header")
    indices = [
        index
        for index in range(header + 1, end)
        if re.match(rf"^\|\s*{prefix}\s*\|", lines[index])
    ]
    insert_at = max(indices) + 1 if indices else header + 2
    lines.insert(insert_at, row)
    return "\n".join(lines) + "\n"
```

`_set_phase_status` uses the same `strip("|").split("|")` and
`"| " + " | ".join(cells) + " |"` pattern, but scans the whole master for the
phase row and fails on any row with a cell count other than 6.

`_upsert_closeout_history` uses the same section/header scan with the header
pattern `r"\|\s*Phase\s*\|"`, replaces an existing `P<n>` row, or inserts after
the last `P<n>` row.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Syntax | `python3 -m compileall -q skills tests` | exit 0, no output |
| Tests | `python3 -m unittest discover -s tests -v` | all tests pass |
| Whitespace | `git diff --check` | exit 0, no output |

## Scope

**In scope**:
- `skills/progressive-plan/scripts/progressive_plan.py`
- `tests/test_plans.py` (add focused CLI tests if needed)

**Out of scope** (do NOT touch):
- `planlib.py` parsers and validation — plans 001 and 002.
- Master version and stale-phase helpers — plan 004.
- Commit preconditions and renderers — plan 005.
- Any template, reference, README, or SKILL.md file.
- The overall `cmd_*` structure or argparse wiring.

## Git workflow

- Branch: `cleanup/clean-code-refactors`.
- Commit after this plan with an imperative subject, for example:
  `Share markdown table helpers between plan commands`.
- Do NOT push or open a PR unless the operator instructs it.

## Steps

### Step 0: Baseline

Run the test command and confirm all existing tests pass.

**Verify**: `python3 -m unittest discover -s tests -v` → all tests pass.

### Step 1: Add shared table scanning helpers

Add these private helpers near `_insert_table_row`:

```python
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
```

The `missing_message` parameters exist to preserve the current failure text.
Do not replace them with generic messages.

### Step 2: Rewrite `_insert_table_row`

Use the helpers but keep the current messages and insert position:

```python
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
```

**Verify**: `python3 -m unittest discover -s tests -v` → all tests pass.
The relevant tests are `ScaffoldTests.test_draft_and_outline_pass`,
`ScaffoldTests.test_write_plan_for_outline`, and all `DiscoveryTests`.

### Step 3: Rewrite `_upsert_closeout_history`

Replace its section/header/row scan with the helpers. Preserve the existing
replace-or-insert behavior and messages:

```python
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
```

**Verify**: `python3 -m unittest discover -s tests -v` → all tests pass,
especially `CommitAndCloseTests.test_close_sets_done_and_history` and
`CommitAndCloseTests.test_close_rejects_unchecked_standards`.

### Step 4: Rewrite `_set_phase_status`

Keep the whole-file scan and the exact 6-cell failure. Use `_split_row`,
`_format_row`, and `_join_lines`:

```python
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
```

Do not switch this function to `_section_bounds`; it currently finds the first
matching phase row anywhere in the file. Keep that behavior.

**Verify**: `python3 -m unittest discover -s tests -v` → all tests pass.

### Step 5: Add focused tests for insertion order and replacement

If the existing tests do not already cover it, add a test that:

1. Creates a new plan.
2. Adds phase P1 as an outline.
3. Adds phase P2 as an outline.
4. Adds phase P3 as an outline.
5. Asserts the master's phase map order is P1, P2, P3.

This locks the `insert_at = max(indices) + 1` behavior.

Also assert that closing a phase updates an existing Closeout history row
instead of appending a duplicate when the row already exists. If this is hard
to set up through the CLI, skip it and note that the existing close test covers
the normal path.

**Verify**: `python3 -m unittest discover -s tests -v` → all tests pass,
including the new test.

### Step 6: Full verification

Run:

```bash
python3 -m compileall -q skills tests
python3 -m unittest discover -s tests -v
git diff --check
```

Inspect `_insert_table_row`, `_upsert_closeout_history`, and
`_set_phase_status` and confirm they no longer contain their own section/header
scan or cell split/join logic.

## Test plan

- Existing CLI tests cover all three helpers indirectly.
- New test for phase-map insertion order (P1, P2, P3).
- If feasible, a test for Closeout history replacement rather than duplicate
  insertion.
- Verification: `python3 -m unittest discover -s tests -v` → all pass.

## Done criteria

- [ ] `_section_bounds`, `_table_header_index`, `_row_indices`, `_split_row`,
  `_format_row`, and `_join_lines` are defined and used.
- [ ] `_insert_table_row`, `_upsert_closeout_history`, and `_set_phase_status`
  no longer duplicate the scan/split/join logic.
- [ ] Failure messages are unchanged.
- [ ] Insert positions and newline handling are unchanged.
- [ ] `python3 -m compileall -q skills tests` exits 0.
- [ ] `python3 -m unittest discover -s tests -v` exits 0; all tests pass.
- [ ] `git diff --check` exits 0.
- [ ] No files outside the in-scope list are modified (`git status --short`).
- [ ] `plans/README.md` status row for plan 003 is `DONE`.

## STOP conditions

Stop and report back (do not improvise) if:

- The functions' current code does not match the excerpts.
- A test fails because the inserted row lands one line earlier or later than
  before.
- Preserving a failure message requires adding a new parameter that makes the
  helper awkward; report the exact message instead of changing it.
- The change requires touching `planlib.py` or any out-of-scope file.

## Maintenance notes

- If the table format changes, update `_section_bounds`, `_table_header_index`,
  and `_row_indices` together. The callers should stay small.
- `_set_phase_status` intentionally scans the whole file; do not "simplify" it
  to a section-only scan without checking malformed-row behavior.
- Closeout history rows are matched by phase ID; a duplicate phase ID in the
  table still replaces the first match, as before.
