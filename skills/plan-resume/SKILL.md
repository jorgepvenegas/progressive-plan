---
name: plan-resume
description: Resume an in-progress progressive-plan master plan in a new coding session. Use when starting fresh against an existing docs/plans master and phase plans, when the user says resume or continue the plan, or when a session was interrupted and the next agent must reconstruct state without re-planning.
---

# Plan Resume

Use this skill at the start of a new session against an existing `progressive-plan` plan. The goal is to reconstruct the exact state, verify it against the repository and git history, and continue from the next legal action. Do not re-plan from scratch and do not redo completed phases.

The execution rules remain in `progressive-plan`: approval gate, subagent implementation, commit gate, and discovery propagation. This skill only gets the new session to the correct entry point.

## Quick start

At the first turn of the new session, do not ask the user to re-explain the task. Run the resume script against the plan directory and read its report:

```bash
python3 <skill-dir>/scripts/resume_status.py docs/plans/<slug>
```

Use `--json` when another tool needs the state, and `--phase P<n>` to inspect a specific phase.

`<skill-dir>` is this skill's directory. `<progressive-plan-dir>` is its sibling directory, next to this skill in the installed skills folder.

## 1. Inspect before touching code

Run these commands from the repository root, using the absolute plan directory:

```bash
python3 <skill-dir>/scripts/resume_status.py docs/plans/<slug>
python3 <progressive-plan-dir>/scripts/progressive_plan.py check docs/plans/<slug>
python3 <progressive-plan-dir>/scripts/progressive_plan.py status docs/plans/<slug>
```

Then read, in full:

1. `master.md`
2. the resume brief
3. the current phase plan
4. `git status`, `git log --oneline -10`, and the recorded phase commit

Do not rely on the previous session's conversation summary when the files disagree with it. The files and the repository are the source of truth.

## 2. Reconcile the state

`resume_status.py` prints the master version, phase table, current phase, approval, implementation mode, commit record, closeout verdict, acceptance progress, affected discoveries, git branch/HEAD, and uncommitted files. Use it as the first pass, then verify manually.

Reconcile these pairs:

| Plan says | Check |
|---|---|
| Current phase `in_progress` | Is there a worker, changed files, a phase closeout, and a commit? |
| Phase `ready` | Is `Approved by` set, and is the plan validated against the current master version? |
| Phase `done` | Does the recorded commit exist? Is it an ancestor of HEAD? Is the closeout verdict valid? |
| Working tree clean | Does `git status` agree? If dirty, identify which phase the changes belong to. |
| Tests pass | Run the phase verification before trusting old evidence. |
| Standards check clean | Run the master's standards commands and read the phase plan's `Code standards check`. |
| Discoveries applied | Does the phase plan list every ledger row whose `Affects` includes it? |
| Commit recorded | Does `Commit:` name a real commit, and does `Implemented by` name the worker or a recorded exception? |
| Plan branch | Does `git branch --show-current` match the master `Branch:` field? If the master has no `Branch:` field, report the current branch; do not create a branch mid-plan without asking. |

Never discard uncommitted work to make the state look clean. If the dirty files belong to the current phase, treat them as in-progress work. If they belong to a later phase, stop and report the out-of-order change.

### Upgrade an older master before acting

`resume_status.py` runs `progressive_plan.py check`. If the check fails because an older master is missing a current required section, repair the master before choosing the next action.

The required sections and their order are in `../progressive-plan/references/master-template.md`. For a missing `Goal flow`:

1. Add the section after `Objective`, with a fenced `mermaid` diagram of the plan's user-visible outcome.
2. Fill the diagram from the objective and definition of done. Keep it to the main path; no phase IDs or internal component names.
3. Bump `Master version` by 1.
4. Set `Validated against master version` to the new version in every `ready` or `in_progress` phase plan.
5. Add a `master-amend` discovery row with `Affects: all` and the reason.
6. Re-run `check`.

For a missing `Code standards`, add the table from the master template and record the project's real format, lint, type-check, and test commands; write `none` only for a check the project does not have.

Do not present a phase for approval or spawn a worker while `check` fails.

## 3. Choose the next action from the state

| Current phase state | Next action |
|---|---|
| No phase plan yet | Write the next phase plan from the master; keep it `draft`/`planned`. |
| Plan written, not approved | Present the plan to the user and ask for approval. If the user requests changes, use the `refine-phase` skill; do not implement. |
| Approved and `ready` | Set `in_progress`, spawn the implementation subagent, and wait. |
| `in_progress` | Inspect the worker's files, verification, closeout, and commit; do not reimplement. Finish the coordinator review. |
| `partial` closeout | Continue the remaining steps with a subagent, or close the session with a partial verdict and a handoff. |
| `done` | Write the next phase plan and stop at the approval gate. |
| `blocked` | Report the blocker, owner, and unblocking condition. Do not start a different phase without approval. |
| `needs_replan` | Rewrite the phase plan against the current master, then ask for approval. |

If the current phase is already implemented but not committed, finish the closeout and commit gate before starting anything new. If it is committed but the master is stale, update the master before writing the next phase.

## 4. Resume the progressive-plan loop

Once the state is reconciled:

- **Never implement an unapproved phase.** Ask: "The P<n> plan is ready at `<path>. Approve implementation?"
- **Never write product code in the coordinator.** Spawn a subagent with `../progressive-plan/references/worker-prompt-template.md`, including the approval record.
- **Never mark a phase done without evidence.** Run the verification commands; do not trust a stale closeout.
- **Never skip the commit gate.** A `done` phase needs a real commit hash recorded in the phase plan and master.
- **Never implement on the default branch.** Work on `plan/<slug>` when the master records it. If the plan predates the branch field and work is already in progress, report the current branch instead of rebranching silently.
- **Never drop discoveries.** Run `progressive_plan.py discoveries <plan-dir> <phase>` and compare it with the phase plan's `Prior discoveries applied` table.
- **Keep the phase focused.** If a closeout reports a `new-phase` discovery, verify the master phase map has that phase as `planned` and that the current phase did not implement it. Do not absorb new work into the current phase.
- **Do not start the next phase because it looks easy.** Close the current phase and stop at the next approval gate.

## 5. Report the resume state

Before the first implementation action, send a short report:

```text
Resume — <plan title>
Master: v<n>, <status>
Current phase: P<n> — <name> (<status>)
Approval: approved by <user> on <date> | pending
Commit: <hash> | none
Branch: plan/<slug> | <current branch> | none
Working tree: clean | <n> files (list)
Verification from this session: <command> — <result>
Next legal action: <one action>
Blocker: <none or specific>
```

Lead with whether the phase is approved, in progress, or done. Do not bury a pending approval under a list of completed work.

## Failure modes to avoid

- **Re-planning from scratch** — ignoring an existing master and phase plans.
- **Stale-state trust** — believing a closeout without running its verification.
- **Dirty-tree amnesia** — resetting or overwriting uncommitted work from the previous session.
- **Skipping the approval gate** — continuing into implementation because the plan already exists.
- **Skipping the subagent mandate** — the coordinator implementing the phase itself.
- **Skipping the commit gate** — marking a phase done without a real recorded commit.
- **Discovery loss** — starting the next phase without checking the master ledger and `Prior discoveries applied`.
- **Default-branch implementation** — resuming work on the default branch when the plan records a `plan/<slug>` branch.
- **Scope absorption** — letting a worker's out-of-scope discovery become part of the current phase instead of a new phase.

## Files

- `scripts/resume_status.py` — prints the plan state, git state, gates, and next action as text or JSON.
- `references/resume-checklist.md` — the manual checklist to run alongside the script.
- `../progressive-plan/` — the execution skill and its templates.
