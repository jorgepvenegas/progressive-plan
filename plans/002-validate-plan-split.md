# Plan 002: Split `validate_plan` into focused validation passes

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**:
> `git diff --stat 6f887f0..HEAD -- skills/progressive-plan/scripts/planlib.py tests/test_plans.py`
> If either file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition. Plan 001 is expected to have changed
> `planlib.py`; that is not drift, but re-read the helpers it added before
> refactoring `validate_plan`.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: LOW
- **Depends on**: `plans/001-parser-helpers.md`
- **Category**: tech-debt
- **Planned at**: commit `6f887f0`, 2026-11-14

## Why this matters

`validate_plan` is 610 lines (`planlib.py:554-1163`). It validates the master
header, definition of done, phase map, discovery ledger, decisions, dependency
graph, active-master content, every phase plan, done-phase closeouts, and the
final definition-of-done sweep. Every rule change edits one function with many
shared locals and deeply nested branches. The recent validation commits all
touched this function, and a future change can easily append an error in the
wrong place or miss an earlier rule.

This plan moves each coherent block into a named helper and leaves
`validate_plan` as a short orchestrator. **This is a pure move-only refactor.**
Every error and warning must be appended in exactly the same order, with
exactly the same text and the same `None`/`""` semantics.

## Current state

- `skills/progressive-plan/scripts/planlib.py` — contains the 610-line
  `validate_plan` and all parsed-row helpers.
- `tests/test_plans.py` — 26 tests. Most assert return codes and substrings;
  they do not assert exact error order. Add characterization tests before the
  refactor.

`validate_plan` currently has this top-level order:

1. Lines 566-579: read `master.md`; check `Master version`; check every
   `MASTER_HEADINGS` entry.
2. Lines 581-596: validate `Status`, `Size`, and the `Goal flow` Mermaid
   diagram.
3. Lines 598-608: parse and validate `D` items (none, duplicate IDs, missing
   description, missing verify clause).
4. Lines 610-635: parse phase rows; warn if empty; validate malformed rows,
   duplicate IDs, statuses; compute `active`.
5. Lines 637-683: parse and validate discovery ledger rows.
6. Lines 685-712: parse and validate cross-phase decisions.
7. Lines 714-734: build the dependency graph; validate unknown dependencies,
   self-dependencies, and cycles.
8. Lines 736-774: active-master content checks (placeholders, Source, Owner,
   D items, empty Objective/Goal flow, template diagram), the draft warning,
   and the `complete`-requires-all-phases-done error.
9. Lines 776-1120: per-phase plan checks, including approval, dependencies,
   ledger coverage, placeholders, steps, acceptance criteria, traceability,
   standards, and the done-phase closeout.
10. Lines 1122-1128: `master_status == "complete"` requires every D item
    checked.
11. Lines 1130-1157: when every phase is done, require every D item checked
    and require the final phase closeout to cover every D item.
12. Lines 1159-1163: convert warnings to errors under `strict`; return
    `{"errors": errors, "warnings": warnings}`.

The function signature and return must not change:

```python
def validate_plan(
    plan_dir: Path,
    *,
    strict: bool = False,
    only_phase: str | None = None,
    for_approval: bool = False,
) -> dict[str, Any]:
```

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Syntax | `python3 -m compileall -q skills tests` | exit 0, no output |
| Tests | `python3 -m unittest discover -s tests -v` | all tests pass |
| Whitespace | `git diff --check` | exit 0, no output |

## Scope

**In scope**:
- `skills/progressive-plan/scripts/planlib.py` — extract helpers and rewrite
  `validate_plan` as an orchestrator.
- `tests/test_plans.py` — add characterization tests for exact validation
  output.

**Out of scope** (do NOT touch):
- The validation rules themselves. Do not add, remove, reorder, or reword any
  error or warning.
- Parser helpers added by plan 001. Use them; do not rewrite them.
- `build_status`, `build_resume_report`, and renderers.
- CLI command behavior, templates, references, README, or SKILL.md files.

## Git workflow

- Branch: `cleanup/clean-code-refactors`.
- Commit after this plan with an imperative subject, for example:
  `Split plan validation into focused helpers`.
- Do NOT push or open a PR unless the operator instructs it.

## Steps

### Step 0: Baseline and characterization tests

Run the test command. Confirm all existing tests pass.

Add a `ValidationCharacterizationTests` class to `tests/test_plans.py`. It must
assert the **entire** `validate_plan` result, including `errors` order and
`warnings` order, for at least these scenarios:

1. A brand-new small plan from `self.new_plan()` (draft, empty phase map).
2. `make_valid_plan(self.tmp, "ready")`.
3. `make_valid_plan(self.tmp, "in_progress")`.
4. A malformed phase row inserted into a new plan, using the same setup as
   `StructureTests.test_malformed_phase_row_is_error`.
5. A malformed ledger row, using the same setup as
   `StructureTests.test_invalid_ledger_row_is_error`.

For each scenario, call `planlib.validate_plan(plan_dir)` and assert equality
with a literal dict of expected errors and warnings. Generate the expected
values by running the **unmodified** code. Commit these tests before refactoring
if that helps you keep the baseline clear.

Do not weaken the tests to substrings. The point is to catch reordered or
reworded output.

**Verify**: `python3 -m unittest discover -s tests -v` → all tests pass,
including the new characterization class.

### Step 1: Add `_validate_master_header`

Move lines 566-596 into:

```python
def _validate_master_header(
    master: str, errors: list[str]
) -> tuple[int | None, str | None, str]:
    """Validate version, headings, status, size, and Goal flow.

    Returns (version, master_status, goal_flow). Appends errors in the current
    order.
    """
```

It must:

- append the missing-version error if `master_version(master)` is `None`;
- check every `MASTER_HEADINGS` entry in order;
- validate `Status` and `Size` with the current messages;
- read `goal_flow = section(master, "Goal flow")` and append the Mermaid error
  if `goal_flow` is non-empty and does not contain ` ```mermaid `;
- return `(version, master_status, goal_flow)`.

### Step 2: Add `_validate_definition_items`

Move lines 598-608 into:

```python
def _validate_definition_items(
    master: str, errors: list[str]
) -> list[dict[str, Any]]:
```

It must preserve the current order: no D items, duplicate IDs, then for each
item missing description and missing verify clause. Return `dod`.

### Step 3: Add `_validate_phase_map`

Move lines 610-635 into:

```python
def _validate_phase_map(
    master: str, errors: list[str], warnings: list[str]
) -> tuple[list[dict[str, Any]], set[str]]:
```

It must preserve the exact per-row order: `malformed` error, duplicate-ID
error, add to `seen_ids`, add to `phase_ids` only when not malformed, then
invalid-status error. Return `(rows, phase_ids)`.

### Step 4: Add `_validate_ledger_rows`

Move lines 637-683 into:

```python
def _validate_ledger_rows(
    master: str,
    errors: list[str],
    phase_ids: set[str],
    active: bool,
) -> list[dict[str, Any]]:
```

Preserve the `continue` behavior for malformed rows and for rows with
placeholders. Do not move the placeholder check into a different order.

### Step 5: Add `_validate_decision_rows`

Move lines 685-712 into:

```python
def _validate_decision_rows(
    master: str,
    errors: list[str],
    phase_ids: set[str],
    active: bool,
) -> None:
```

Preserve the same `continue` behavior.

### Step 6: Add `_validate_dependency_graph`

Move lines 714-734 into:

```python
def _validate_dependency_graph(
    rows: list[dict[str, Any]],
    phase_ids: set[str],
    active: bool,
    errors: list[str],
) -> None:
```

Preserve the placeholder-dependency `continue`, the `graph[row["id"]] = deps`
assignment, unknown/self dependency checks, and `_cycle_nodes`.

### Step 7: Add `_validate_active_master_content` and `_validate_master_status_rules`

Move lines 736-769 into:

```python
def _validate_active_master_content(
    master: str,
    goal_flow: str,
    dod: list[dict[str, Any]],
    errors: list[str],
) -> None:
```

This includes the section-placeholder loop in the current order,
`Source`, `Owner`, D-item text/verify placeholders, empty Objective, empty Goal
flow, and the template-diagram check.

Move lines 770-774 into:

```python
def _validate_master_status_rules(
    master_status: str | None,
    rows: list[dict[str, Any]],
    errors: list[str],
    warnings: list[str],
) -> None:
```

This includes the draft warning and the `complete`-requires-all-phases-done
error. Call it immediately after `_validate_active_master_content` so error
order is unchanged.

### Step 8: Add `_validate_phase_plans`

Move lines 776-1120 into:

```python
def _validate_phase_plans(
    plan_dir: Path,
    rows: list[dict[str, Any]],
    version: int | None,
    dod: list[dict[str, Any]],
    entries: list[dict[str, Any]],
    only_phase: str | None,
    for_approval: bool,
    errors: list[str],
) -> dict[str, Path]:
```

It returns `phase_plan_files` for the final closeout sweep. Keep the per-phase
loop body verbatim. Do not split the done-phase block into another helper in
this plan; moving it as one unit keeps the risk low. Keep every `f"{plan_file}: ..."`
message exactly as it is.

### Step 9: Add the completion helpers

Move lines 1122-1128 into:

```python
def _validate_master_completion(
    master_status: str | None,
    rows: list[dict[str, Any]],
    dod: list[dict[str, Any]],
    errors: list[str],
) -> None:
```

Move lines 1130-1157 into:

```python
def _validate_final_closeout(
    rows: list[dict[str, Any]],
    dod: list[dict[str, Any]],
    phase_plan_files: dict[str, Path],
    errors: list[str],
) -> None:
```

Preserve both D-item checkbox errors and the final closeout row checks.

### Step 10: Rewrite `validate_plan` as the orchestrator

The new body should be approximately:

```python
def validate_plan(
    plan_dir: Path,
    *,
    strict: bool = False,
    only_phase: str | None = None,
    for_approval: bool = False,
) -> dict[str, Any]:
    """Validate a master plan and its phase plans. ..."""
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
    _validate_active_master_content(master, goal_flow, dod, errors)
    _validate_master_status_rules(master_status, rows, errors, warnings)
    phase_plan_files = _validate_phase_plans(
        plan_dir,
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
```

Keep the docstring's meaning; you may keep the existing wording.

**Verify**: `python3 -m unittest discover -s tests -v` → all tests pass,
including the characterization class. If any exact-output test fails, the
refactor changed behavior; fix the refactor, not the test.

### Step 11: Full verification

Run:

```bash
python3 -m compileall -q skills tests
python3 -m unittest discover -s tests -v
git diff --check
```

Also inspect `validate_plan` and confirm its body is under roughly 100 lines
and contains only orchestration. The helpers may be longer.

## Test plan

- New `ValidationCharacterizationTests` with exact `errors` and `warnings`
  lists for the five scenarios listed in Step 0.
- Existing 26 tests continue to pass. Pay particular attention to
  `ApprovalTests`, `StructureTests`, `DiscoveryTests`, and
  `CommitAndCloseTests` because they exercise validation through the CLI.
- Verification: `python3 -m unittest discover -s tests -v` → all pass.

## Done criteria

- [ ] `python3 -m compileall -q skills tests` exits 0.
- [ ] `python3 -m unittest discover -s tests -v` exits 0; all tests pass.
- [ ] `ValidationCharacterizationTests` exists and passes against the
  refactored code.
- [ ] `validate_plan` calls the extracted helpers in the exact order above and
  its body is under roughly 100 lines.
- [ ] No error or warning text, order, or `None`/`""` semantics changed.
- [ ] `git diff --check` exits 0.
- [ ] No files outside the in-scope list are modified (`git status --short`).
- [ ] `plans/README.md` status row for plan 002 is `DONE`.

## STOP conditions

Stop and report back (do not improvise) if:

- The code at the cited line ranges does not match the described order.
- An exact-output characterization test fails and you cannot make it pass by
  moving code without changing behavior.
- A helper would need a new parameter that changes a message, an order, or a
  branch condition.
- The refactor requires touching a file outside the in-scope list.
- You cannot preserve the `for_approval`/`only_phase` behavior for
  `effective_status` and `approval_ready`.

## Maintenance notes

- New validation rules should go into the helper that owns the relevant
  section, in the position that matches the desired error order. The
  orchestrator order is the contract.
- The characterization tests are intentionally exact. When a rule changes,
  update the expected list and the rule together in one commit so the output
  change is visible.
- `_validate_phase_plans` is still the largest helper. If it grows further,
  split the done-phase block into its own helper as a follow-up, not as part of
  this behavior-preserving plan.
