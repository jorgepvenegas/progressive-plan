# Plan 001: Consolidate plan parsing and identifier helpers

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**:
> `git diff --stat 6f887f0..HEAD -- skills/progressive-plan/scripts/planlib.py skills/progressive-plan/scripts/progressive_plan.py tests/test_plans.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S/M
- **Risk**: LOW
- **Depends on**: none
- **Category**: tech-debt
- **Planned at**: commit `6f887f0`, 2026-11-14

## Why this matters

The plan parser repeats the same markdown table row logic in four functions,
the same checklist parser in two functions, and the same closeout-verdict regex
in two files. It also parses phase and ledger numbers with the same expression
in several places. A change to a row shape, malformed-row handling, or an ID
rule currently requires edits in four or more places, and the copies can drift.
This plan consolidates the copies behind small internal helpers while keeping
every public function's return value exactly the same.

This is a pure refactor. It must not change validation rules, error messages,
command output, row dict keys, key order, or exit codes.

## Current state

- `skills/progressive-plan/scripts/planlib.py` — shared parser, validation,
  status, and report helpers. The duplicated parsers are here.
- `skills/progressive-plan/scripts/progressive_plan.py` — CLI commands. It
  contains a second closeout-verdict regex and two ID-number expressions.
- `tests/test_plans.py` — existing CLI/integration tests. It imports `planlib`
  and the fixtures in `tests/fixtures.py`.

The four table parsers follow this shape (`planlib.py:188-277`):

```python
def phase_rows(master_text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in section(master_text, "Phase map").splitlines():
        if not re.match(r"^\|\s*P\d+\s*\|", line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        malformed = len(cells) != 6
        padded = cells + [""] * (6 - len(cells))
        rows.append(
            {
                "id": padded[0],
                "name": padded[1],
                "outcome": padded[2],
                "depends": padded[3],
                "status": padded[4],
                "plan": padded[5],
                "malformed": malformed,
                "raw": line,
            }
        )
    return rows
```

`ledger_rows` uses 8 columns, `decision_rows` uses 5, and
`closeout_history_rows` uses 6. `phase_rows`, `ledger_rows`, and
`decision_rows` include `"raw"`; `closeout_history_rows` does not.

The checklist parsers are nearly identical (`planlib.py:338-383`):
`definition_items` matches `D\d+` and `acceptance_items` matches `A\d+`.
Both produce `{"id", "checked", "text", "verify"}` in that order.

The closeout verdict is extracted twice:
`planlib.py:1032-1035` inside `validate_plan`, and
`progressive_plan.py:604-608` inside `cmd_close`.
Both use the same regex:
`r"^-\s*Verdict:\s*(\S+)"` over `section(plan_text, "Closeout")`.

The same cell split appears seven times:
`planlib.py:193, 216, 241, 263, 322, 402, 428`.
The same numeric-ID expression
`int(re.sub(r"\D", "", ...) or 0)` appears at
`planlib.py:1137, 1178, 1534` and `progressive_plan.py:717, 759`.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Syntax | `python3 -m compileall -q skills tests` | exit 0, no output |
| Tests | `python3 -m unittest discover -s tests -v` | 26 tests pass before this plan; more after |
| Whitespace | `git diff --check` | exit 0, no output |

Run all commands from the worktree root.

## Scope

**In scope** (the only files you should modify):
- `skills/progressive-plan/scripts/planlib.py`
- `skills/progressive-plan/scripts/progressive_plan.py`
- `tests/test_plans.py` (add parser tests; remove the unused assignment)

**Out of scope** (do NOT touch):
- `validate_plan` control flow and its error ordering — that is plan 002.
- `_insert_table_row`, `_set_phase_status`, `_upsert_closeout_history` — that
  is plan 003.
- Master version and stale-phase helpers — that is plan 004.
- Any template, reference, README, or SKILL.md file.
- The plan-cell pending-value sets. They currently differ between
  `planlib.py:784-791` and `progressive_plan.py:299`; resolving that would
  change behavior and needs an explicit decision.

## Git workflow

- Branch: `cleanup/clean-code-refactors` (already checked out in this worktree).
- Commit after this plan with an imperative subject, for example:
  `Consolidate plan parsers into shared helpers`.
- Do NOT push or open a PR unless the operator instructs it.

## Steps

### Step 0: Baseline

Run the syntax and test commands above. Confirm all 26 existing tests pass and
record the count in your final report.

**Verify**: `python3 -m unittest discover -s tests -v` → `Ran 26 tests` and `OK`.

### Step 1: Add characterization tests before refactoring

Add a `ParserTests` class to `tests/test_plans.py`. Use the existing
`PlanTestCase` only if you need temporary directories; most parser tests can be
plain `unittest.TestCase` methods with inline markdown.

Cover at least these cases:

1. `planlib.phase_rows` on a well-formed row and on a row with too few cells.
   Assert the exact list of dicts, including key order, `malformed`, and
   `raw`.
2. `planlib.ledger_rows` on a well-formed row and a malformed row.
3. `planlib.decision_rows` on a well-formed row and a malformed row.
4. `planlib.closeout_history_rows` on a well-formed row and a malformed row.
5. `planlib.definition_items` and `planlib.acceptance_items` on checked,
   unchecked, and `verify:` lines.
6. `planlib.closeout_verdict` on a plan with a verdict and on a plan without
   one. The expected result is the lowercased verdict string or `None`.
7. `planlib.identifier_number("P12") == 12`, `identifier_number("L7") == 7`,
   and `identifier_number("master") == 0` (after you add the helper in Step 5).

Write the expected values from the current code. Run the tests **before** the
refactor and confirm they pass. If a test fails, fix the test to match current
behavior; do not change production code in this step.

Remove the unused `head = init_git(self.tmp)` assignment at
`tests/test_plans.py:313`; the later `head = subprocess.run(...)` assignment
replaces it.

**Verify**: `python3 -m unittest discover -s tests -v` → all tests pass,
including the new `ParserTests`.

### Step 2: Add `_table_rows` and rewrite the four table parsers

In `planlib.py`, add this internal helper above `phase_rows`:

```python
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
```

Rewrite the four functions as thin wrappers. Keep the exact field order shown
below, because JSON output and tests can depend on it.

```python
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
```

Do not change the `malformed` definition: it is `len(cells) != len(columns)`,
and extra cells beyond the expected columns are ignored.

**Verify**: `python3 -m unittest discover -s tests -v` → all tests pass,
including `ParserTests`.

### Step 3: Add `_checklist_items` and rewrite the D/A parsers

Add this helper above `definition_items`:

```python
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
```

Rewrite `definition_items` as
`return _checklist_items(master_text, "Definition of done", r"D\d+")` and
`acceptance_items` as
`return _checklist_items(plan_text, "Phase acceptance criteria", r"A\d+")`.
Keep the returned key order `id`, `checked`, `text`, `verify`.

**Verify**: `python3 -m unittest discover -s tests -v` → all tests pass.

### Step 4: Add `closeout_verdict` and use it in all three call sites

In `planlib.py`, add:

```python
def closeout_verdict(plan_text: str) -> str | None:
    match = re.search(
        r"^-\s*Verdict:\s*(\S+)", section(plan_text, "Closeout"), re.MULTILINE
    )
    return match.group(1).strip().lower() if match else None
```

Update the call sites without changing their current `None` vs `""` behavior:

- In `validate_plan` (around `planlib.py:1032`), replace the local regex with:
  `verdict = closeout_verdict(plan) or ""`
- In `build_resume_report` (around `planlib.py:1294`), replace the local regex
  with: `verdict = closeout_verdict(plan)`
- In `progressive_plan.py` `cmd_close` (around line 604), replace the local
  regex with: `verdict = closeout_verdict(plan_text) or ""`
- Add `closeout_verdict` to the `from planlib import (...)` list in
  `progressive_plan.py`.

**Verify**: `python3 -m unittest discover -s tests -v` → all tests pass. Also
run `python3 -m compileall -q skills tests` → exit 0.

### Step 5: Add `identifier_number` and replace only the matching expressions

In `planlib.py`, add:

```python
def identifier_number(value: str) -> int:
    digits = re.sub(r"\D", "", value)
    return int(digits) if digits else 0
```

Replace only the expressions that use `int(re.sub(r"\D", "", ... ) or 0)`:

- `planlib.py:1137` → `max(rows, key=lambda row: identifier_number(row["id"]))`
- `planlib.py:1178` → same pattern for `done`
- `planlib.py:1534` → same pattern for `done_rows`
- `progressive_plan.py:717` →
  `max((identifier_number(entry["id"]) for entry in entries), default=0) + 1`
- `progressive_plan.py:759` →
  `max((identifier_number(row["id"]) for row in rows), default=0) + 1`

Add `identifier_number` to the `from planlib import (...)` list in
`progressive_plan.py`.

**Do NOT replace** `int(row["id"][1:])` at `progressive_plan.py:239, 304,
819-822`. Those sites assume a valid `P<n>` ID and have different failure
behavior; changing them is outside this plan.

**Verify**: `python3 -m unittest discover -s tests -v` → all tests pass.

### Step 6: Remove dead parser code

Delete `placeholder_count` from `planlib.py` (around lines 184-185). It is not
called anywhere. Do not remove `placeholder_findings` or `strip_code_fences`;
they are used.

**Verify**: `grep -rn "placeholder_count" skills tests` → no matches.

### Step 7: Full verification

Run all three commands from "Commands you will need". Also run:

```bash
grep -c 'strip("|").split("|")' skills/progressive-plan/scripts/planlib.py
```

Expected: `1` — only `_table_rows` contains the cell-split expression.

```bash
grep -rn "re.sub(r\"\\\\D\", \"\", " skills/progressive-plan/scripts
```

Expected: only the definition inside `identifier_number`, and the
`int(...[1:])` sites are unaffected. If the shell quoting is awkward, inspect
the two files directly.

## Test plan

- New `ParserTests` in `tests/test_plans.py` covering exact parser output for
  well-formed and malformed rows, checklist items, closeout verdicts, and
  identifier numbers.
- Existing 26 tests continue to pass. In particular:
  `test_add_phase_bumps_master_version`, `test_add_discovery_appends_and_bumps`,
  `test_add_decision_appends`, `test_close_sets_done_and_history`, and
  `test_report_contains_sections` exercise the rewritten parsers through the
  CLI.
- Verification: `python3 -m unittest discover -s tests -v` → all pass.

## Done criteria

- [ ] `python3 -m compileall -q skills tests` exits 0.
- [ ] `python3 -m unittest discover -s tests -v` exits 0; all tests pass.
- [ ] `ParserTests` exists and passes.
- [ ] The four table parsers call `_table_rows`; `definition_items` and
  `acceptance_items` call `_checklist_items`.
- [ ] `closeout_verdict` is defined once and used by `validate_plan`,
  `build_resume_report`, and `cmd_close`.
- [ ] `identifier_number` is used at the five listed sites; the `[1:]` sites
  are unchanged.
- [ ] `grep -rn "placeholder_count" skills tests` returns no matches.
- [ ] `grep -c 'strip("|").split("|")' skills/progressive-plan/scripts/planlib.py`
  returns `1`.
- [ ] `git diff --check` exits 0.
- [ ] No files outside the in-scope list are modified (`git status --short`).
- [ ] `plans/README.md` status row for plan 001 is `DONE`.

## STOP conditions

Stop and report back (do not improvise) if:

- The code at the cited locations does not match the excerpts.
- A parser test fails against the unmodified code. Do not "fix" the test by
  changing production behavior.
- Any existing test fails after a refactor step twice after a reasonable fix
  attempt.
- A change appears to require touching an out-of-scope file.
- The refactor would change a returned dict's key order, a `malformed` value,
  an error message, or a `None` vs `""` result.
- The `closeout_verdict` helper cannot preserve the three call sites' current
  behavior.

## Maintenance notes

- Adding a column to a table now means editing one field tuple in the wrapper,
  not four parser bodies. Keep the field order stable because JSON output can
  expose it.
- If a new table parser is added, use `_table_rows` and keep the
  `malformed`/`raw` conventions.
- The plan-cell pending-value drift is deliberately not fixed here. If a
  maintainer wants `n/a` treated the same way in `validate_plan` and
  `write-plan`, that is a separate behavior decision.
