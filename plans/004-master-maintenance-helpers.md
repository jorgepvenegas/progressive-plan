# Plan 004: Extract master version and stale-phase maintenance helpers

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**:
> `git diff --stat 6f887f0..HEAD -- skills/progressive-plan/scripts/planlib.py skills/progressive-plan/scripts/progressive_plan.py`
> Plans 001-003 may have changed these files. Re-read the call sites before
> editing.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: `plans/001-parser-helpers.md`, `plans/003-table-mutation-helpers.md`
- **Category**: tech-debt
- **Planned at**: commit `6f887f0`, 2026-11-14

## Why this matters

Four commands repeat the same missing-master-version failure, and three
commands repeat the same "bump the master version, then warn about ready or
in-progress phases" block. A new command that edits the master can easily
forget the warning or use a different error text. This plan centralizes the
version read, the bump, and the stale-phase warning. It is a pure refactor:
same messages, same exit codes, same bump conditions.

## Current state

- `skills/progressive-plan/scripts/planlib.py` — has `master_version`,
  `set_field`, `phase_rows`, and `fail`.
- `skills/progressive-plan/scripts/progressive_plan.py` — command handlers with
  the repeated blocks.

The repeated missing-version block is:

```python
version = master_version(master)
if version is None:
    fail("master plan has no '- Master version: N' line")
```

It appears in:

- `cmd_add_phase` (`progressive_plan.py:241-245`)
- `cmd_write_plan` (`progressive_plan.py:301-303`)
- `cmd_add_discovery` (`progressive_plan.py:726-729`)
- `cmd_add_decision` (`progressive_plan.py:767-770`)

The repeated stale-phase warning is:

```python
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
```

It appears in `cmd_add_phase` (`282-291`), `cmd_add_discovery` (`732-742`),
and `cmd_add_decision` (`773-782`).

The bump block is:

```python
version = master_version(master)
if version is None:
    fail("master plan has no '- Master version: N' line")
master = set_field(master, "Master version", str(version + 1))
```

It appears in `cmd_add_phase` (before inserting the row), `cmd_add_discovery`
(after inserting the row, unless `--no-bump`), and `cmd_add_decision` (after
inserting the row).

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Syntax | `python3 -m compileall -q skills tests` | exit 0, no output |
| Tests | `python3 -m unittest discover -s tests -v` | all tests pass |
| Whitespace | `git diff --check` | exit 0, no output |

## Scope

**In scope**:
- `skills/progressive-plan/scripts/planlib.py`
- `skills/progressive-plan/scripts/progressive_plan.py`
- `tests/test_plans.py` (add focused tests)

**Out of scope** (do NOT touch):
- Table mutation helpers (plan 003).
- Commit preconditions, git wrappers, or renderers (plan 005).
- The `--no-bump` flag's existence or meaning.
- Any template, reference, README, or SKILL.md file.

## Git workflow

- Branch: `cleanup/clean-code-refactors`.
- Commit after this plan with an imperative subject, for example:
  `Centralize master version and stale-phase updates`.
- Do NOT push or open a PR unless the operator instructs it.

## Steps

### Step 0: Baseline

Run the test command and confirm all existing tests pass.

### Step 1: Add planlib helpers

In `planlib.py`, add after `master_version`:

```python
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
```

`require_master_version` must call the existing `fail`, so the stderr text and
`SystemExit(1)` behavior stay identical.

### Step 2: Add a local warning helper

In `progressive_plan.py`, add near the other private helpers:

```python
def _warn_stale_phases(master: str) -> None:
    stale = stale_phase_ids(master)
    if stale:
        print(
            "warning: master version bumped; revalidate these phases: "
            + ", ".join(stale)
        )
```

Add `require_master_version`, `bump_master_version`, and `stale_phase_ids` to
the `from planlib import (...)` list.

### Step 3: Replace the missing-version checks

- `cmd_add_phase`: replace the `master_version`/`None` block with
  `version = require_master_version(master)`. Keep the existing
  `new_version = version + 1` and `set_field` logic, or use
  `master, new_version = bump_master_version(master)` and then use
  `new_version` for the template and row. Choose the version that keeps the
  diff smallest and the order unchanged.
- `cmd_write_plan`: replace the `master_version`/`None` block with
  `version = require_master_version(master)`.
- `cmd_add_discovery`: inside `if not args.no_bump:`, replace the block with
  `master, _ = bump_master_version(master)`.
- `cmd_add_decision`: replace the block with
  `master, _ = bump_master_version(master)`.

Do not change the order of operations in `cmd_add_phase`: the master version
must still be readable before the new row is inserted, and the new version is
used in the template and the row.

### Step 4: Replace the stale-phase warning blocks

In `cmd_add_phase`, `cmd_add_discovery`, and `cmd_add_decision`, replace the
three copies of the stale list/warning with `_warn_stale_phases(master)`.
Keep the `if not args.no_bump:` guard in `cmd_add_discovery`.

**Verify**: `python3 -m unittest discover -s tests -v` → all tests pass.

### Step 5: Add focused tests

Add tests in `tests/test_plans.py`:

1. `test_add_discovery_no_bump_skips_version_and_warning`:
   - create a valid plan with `make_valid_plan(self.tmp, "ready")`;
   - run `add-discovery` with `--no-bump`;
   - assert `Master version: 1` is still present;
   - assert the output does not contain `warning: master version bumped`.
2. `test_missing_master_version_fails`:
   - create a new plan;
   - remove the `- Master version:` line from `master.md`;
   - run `add-phase ... --outline`;
   - assert a non-zero exit and the exact error text
     `master plan has no '- Master version: N' line`.

Use `run_cli` from the existing test module. Match the style of
`ApprovalTests.test_add_phase_bumps_master_version` and
`DiscoveryTests.test_add_discovery_appends_and_bumps`.

**Verify**: `python3 -m unittest discover -s tests -v` → all tests pass,
including the two new tests.

### Step 6: Full verification

Run:

```bash
python3 -m compileall -q skills tests
python3 -m unittest discover -s tests -v
git diff --check
```

Also run:

```bash
grep -rn "master plan has no '- Master version: N' line" skills/progressive-plan/scripts
```

Expected: exactly one match, inside `require_master_version`.

```bash
grep -rn "warning: master version bumped; revalidate these phases" skills/progressive-plan/scripts
```

Expected: exactly one match, inside `_warn_stale_phases`.

## Test plan

- Existing tests:
  `test_add_phase_bumps_master_version`,
  `test_add_discovery_appends_and_bumps`,
  `test_add_decision_appends`.
- New tests: `test_add_discovery_no_bump_skips_version_and_warning` and
  `test_missing_master_version_fails`.
- Verification: `python3 -m unittest discover -s tests -v` → all pass.

## Done criteria

- [ ] `require_master_version`, `bump_master_version`, and
  `stale_phase_ids` are defined in `planlib.py`.
- [ ] `_warn_stale_phases` is defined once in `progressive_plan.py`.
- [ ] The four missing-version call sites use `require_master_version` or
  `bump_master_version`.
- [ ] The three stale-warning call sites use `_warn_stale_phases`.
- [ ] `--no-bump` still skips both the bump and the warning.
- [ ] `python3 -m compileall -q skills tests` exits 0.
- [ ] `python3 -m unittest discover -s tests -v` exits 0; all tests pass.
- [ ] `git diff --check` exits 0.
- [ ] No files outside the in-scope list are modified (`git status --short`).
- [ ] `plans/README.md` status row for plan 004 is `DONE`.

## STOP conditions

Stop and report back (do not improvise) if:

- A call site's operation order differs from the description.
- `cmd_add_phase` cannot use the helper without changing the new version used
  in the template or row.
- `--no-bump` behavior would change.
- The error text or exit code would change.
- The change requires touching an out-of-scope file.

## Maintenance notes

- Any new command that edits the master should call `require_master_version`
  when it reads the version and `_warn_stale_phases` after a bump.
- `stale_phase_ids` is the single source of truth for which statuses need
  revalidation. Keep `ready` and `in_progress` there unless the lifecycle rules
  change.
- `bump_master_version` returns the new version so callers do not have to
  re-read the field.
