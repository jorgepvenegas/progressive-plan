# Plan 005: Share repository, commit, and renderer helpers

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**:
> `git diff --stat 6f887f0..HEAD -- skills/progressive-plan/scripts/planlib.py skills/progressive-plan/scripts/progressive_plan.py`
> Plans 001-004 may have changed these files. Re-read the cited functions
> before editing.

## Status

- **Priority**: P3
- **Effort**: S
- **Risk**: LOW
- **Depends on**: `plans/001-parser-helpers.md`, `plans/004-master-maintenance-helpers.md`
- **Category**: tech-debt
- **Planned at**: commit `6f887f0`, 2026-11-14

## Why this matters

`record-commit` and `close` repeat the same repository check and the same
commit-exists/ancestor checks. `close` also repeats the closeout-verdict regex
that plan 001 moved into `planlib.closeout_verdict`. `git()` and `git_ok()`
invoke the same subprocess separately. The status and resume text renderers
repeat the same phase-map and resume-brief formatting. This plan centralizes
these small pieces. It is a pure refactor: same messages, same output, same
exit codes.

## Current state

- `skills/progressive-plan/scripts/planlib.py` — git wrappers and renderers.
- `skills/progressive-plan/scripts/progressive_plan.py` — `record-commit` and
  `close` command handlers.
- `tests/test_plans.py` — `CommitAndCloseTests`, `ResumeAndReportTests`.

The repeated repository block is:

```python
repo = git_root(plan_dir)
if repo is None:
    fail(f"{plan_dir} is not inside a git repository")
```

It appears in `cmd_record_commit` (`progressive_plan.py:451-455`),
`cmd_close` (`575-578`), and `cmd_scope` (`848-850`).

The repeated commit checks are:

```python
if not commit_exists(repo, commit_hash):
    fail(f"commit {commit_hash} does not exist in {repo}")
if not commit_is_ancestor(repo, commit_hash):
    fail(f"commit {commit_hash} is not an ancestor of HEAD")
```

They appear in `cmd_record_commit` (`467-470`) and `cmd_close` (`588-591`).
`cmd_close` also checks `args.hash` with `commit_exists` at `582-583`.

The repeated implemented-at block is:

```python
if is_pending(field(plan_text, "Implemented at")):
    plan_text = set_field(
        plan_text,
        "Implemented at",
        commit_date(repo, str(commit_hash)) or date.today().isoformat(),
    )
```

It appears in `cmd_record_commit` (`476-481`) and `cmd_close` (`596-601`).

`cmd_close` extracts the verdict with the same regex plan 001 moved into
`planlib.closeout_verdict` (`progressive_plan.py:604-608`).

`git()` and `git_ok()` (`planlib.py:504-521`) both call
`subprocess.run([...], capture_output=True, text=True, encoding="utf-8")`.

`render_resume_text` (`planlib.py:1397-1408`) and `render_status_text`
(`planlib.py:1484-1494`) both format the phase map and resume brief the same
way.

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
- `tests/test_plans.py` (add a focused commit test)

**Out of scope** (do NOT touch):
- Parsers, `validate_plan`, table mutation helpers, master-version helpers.
- The commit gate's rules or messages.
- Output text, spacing, or section order.
- Any template, reference, README, or SKILL.md file.

## Git workflow

- Branch: `cleanup/clean-code-refactors`.
- Commit after this plan with an imperative subject, for example:
  `Share repository, commit, and renderer helpers`.
- Do NOT push or open a PR unless the operator instructs it.

## Steps

### Step 0: Baseline

Run the test command and confirm all existing tests pass.

### Step 1: Share the git subprocess runner

In `planlib.py`, replace the bodies of `git` and `git_ok` with a shared
runner:

```python
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
```

Do not change the return conditions. In particular, `git()` still returns
`None` for a failed command and `""` for a successful command with empty
stdout, because it preserves the current `result.stdout.strip()` expression.

**Verify**: `python3 -m unittest discover -s tests -v` → all tests pass.

### Step 2: Add repository and commit preconditions

In `progressive_plan.py`, add near the other private helpers:

```python
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
```

Replace the repository block in `cmd_record_commit`, `cmd_close`, and
`cmd_scope` with `repo = _require_repo(plan_dir)`.

Replace the commit checks:

- `cmd_record_commit`: after the subject check, call
  `_require_commit(repo, commit_hash)`.
- `cmd_close`: when `args.hash` is provided, call
  `_require_commit(repo, args.hash)` (this replaces the current exists-only
  check and adds the ancestor check at the same point). For the recorded
  commit, call `_require_commit(repo, str(commit_hash))`.

If calling `_require_commit` twice for the same hash bothers you, keep a local
`checked` set or skip the second call only when the hashes are equal. The
observable behavior must stay the same: a missing commit and a non-ancestor
commit both fail with the same messages.

### Step 3: Share the implemented-at update

Add a helper in `progressive_plan.py`:

```python
def _set_implemented_at(plan_text: str, repo: Path, commit_hash: str) -> str:
    if is_pending(field(plan_text, "Implemented at")):
        return set_field(
            plan_text,
            "Implemented at",
            commit_date(repo, commit_hash) or date.today().isoformat(),
        )
    return plan_text
```

Use it in `cmd_record_commit` and `cmd_close` with the same `commit_hash`
value each currently uses (`commit_hash` in the first, `str(commit_hash)` in
the second).

### Step 4: Use the shared closeout verdict

Use `planlib.closeout_verdict` from plan 001 in `cmd_close`:

```python
verdict = closeout_verdict(plan_text) or ""
```

Remove the local regex. Do not change the failure text.

**Verify**: `python3 -m unittest discover -s tests -v` → all tests pass.

### Step 5: Share the status/resume text fragments

In `planlib.py`, add:

```python
def _phase_map_lines(rows: list[dict[str, Any]]) -> list[str]:
    return [
        f"  {row['id']:<3} {row['status']:<12} {row['name']} "
        f"(depends: {row['depends']})"
        for row in rows
    ]


def _brief_lines(brief: list[str]) -> list[str]:
    return [f"  {line.strip()}" for line in brief if line.strip()]
```

Use `_phase_map_lines` in `render_resume_text` and `render_status_text` in
place of the duplicated f-string loop. Use `_brief_lines` in both places in
place of the duplicated resume-brief loop. Keep the surrounding headings and
blank lines exactly as they are: `render_resume_text` prints a `Phase map:`
heading before the rows; `render_status_text` does not.

**Verify**: `python3 -m unittest discover -s tests -v` → all tests pass.

### Step 6: Add a non-ancestor commit test

Add a test to `CommitAndCloseTests`:

1. Initialize a temp git repository with `init_git(self.tmp)`.
2. Create a branch `side`, commit a file on it, and capture the short hash.
3. Switch back to the original branch.
4. Create a valid in-progress plan with `make_valid_plan(self.tmp, "in_progress")`.
5. Run `record-commit ... --hash <side-hash>`.
6. Assert a non-zero exit and `is not an ancestor of HEAD` in the output.

Use `subprocess.run` with `check=True` as the existing tests do. If the
repository setup becomes unreliable, stop and report instead of weakening the
test.

**Verify**: `python3 -m unittest discover -s tests -v` → all tests pass,
including the new test.

### Step 7: Full verification

Run:

```bash
python3 -m compileall -q skills tests
python3 -m unittest discover -s tests -v
git diff --check
```

Inspect `cmd_record_commit` and `cmd_close` and confirm they no longer contain
their own repository/commit preconditions or implemented-at block.

## Test plan

- Existing `CommitAndCloseTests` and `ResumeAndReportTests` cover the normal
  paths.
- New `test_record_commit_rejects_non_ancestor_commit` locks the shared commit
  gate.
- Verification: `python3 -m unittest discover -s tests -v` → all pass.

## Done criteria

- [ ] `_run_git` is defined once; `git` and `git_ok` call it.
- [ ] `_require_repo` and `_require_commit` are defined once and used by the
  three and two call sites respectively.
- [ ] `_set_implemented_at` is defined once and used by both commands.
- [ ] `cmd_close` uses `closeout_verdict`.
- [ ] `_phase_map_lines` and `_brief_lines` are defined once and used by both
  renderers.
- [ ] All messages, output text, and exit codes are unchanged.
- [ ] `python3 -m compileall -q skills tests` exits 0.
- [ ] `python3 -m unittest discover -s tests -v` exits 0; all tests pass.
- [ ] `git diff --check` exits 0.
- [ ] No files outside the in-scope list are modified (`git status --short`).
- [ ] `plans/README.md` status row for plan 005 is `DONE`.

## STOP conditions

Stop and report back (do not improvise) if:

- `cmd_close`'s current double check of `args.hash` and the recorded commit
  makes the helper change ambiguous; report the exact current sequence and
  ask before changing it.
- A message or exit code would change.
- The renderer output differs by a space, blank line, or heading.
- The non-ancestor test requires touching production code to pass.
- The change requires touching an out-of-scope file.

## Maintenance notes

- New commands that need git should call `_require_repo`; new commit gates
  should call `_require_commit` so missing and non-ancestor commits stay
  consistent.
- If the status and resume reports diverge intentionally, split the shared
  renderer helpers rather than changing one report's text.
- `_run_git` returns the full `CompletedProcess`; if a future caller needs
  stderr or the exit code, use it directly instead of adding another wrapper.
