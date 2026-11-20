---
name: plan-resume
description: Resume an in-progress progressive-plan master in a new session. Use when continuing an existing docs/plans plan or reconstructing state after an interruption without re-planning.
---

# Plan Resume

Use this skill at the start of a new session against an existing `progressive-plan` plan. The goal is to reconstruct the exact state, verify it against the repository and git history, and continue from the next legal action. Do not re-plan from scratch and do not redo completed phases.

The execution rules remain in `progressive-plan` and its `references/gates.md`: approval gate, subagent implementation, closeout evidence, commit gate, and discovery propagation. This skill only gets the new session to the correct entry point.

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

`resume_status.py` prints the master version, status, mode, phase table, current phase, approval, implementation mode, commit record, closeout verdict, acceptance progress, affected discoveries, git branch/HEAD, and uncommitted files. Use it as the first pass, then verify manually.

Reconcile these pairs:

| Plan says | Check |
|---|---|
| Current phase `in_progress` | Is there a worker, changed files, a phase closeout, and a commit? |
| Phase `ready` | Is `Approved by` set, and is the plan validated against the current master version? |
| Phase `done` | Does the recorded commit exist and is it an ancestor of HEAD? Is the verdict `addressed`? Does every A and claimed D have a `met` closeout row with evidence? Are all code-standards boxes checked? |
| Working tree clean | Does `git status` agree? If dirty, identify which phase the changes belong to. |
| Mode `yolo` | Does `Mode authorized by` name the user and date? Is the draft PR open and its head `plan/<slug>`? If either is missing, stop before continuing; do not auto-approve. |
| Tests pass | Run the phase verification before trusting old evidence. |
| Standards check clean | Run the master's standards commands and read the phase plan's `Code standards check`. |
| Discoveries applied | Does the phase plan list every ledger row whose `Affects` includes it? |
| Commit recorded | Does `Commit:` name a real commit, and does `Implemented by` name the worker or a recorded exception? |
| Resume brief | Does `Current phase` match the actual phase map? `resume_status.py` warns when it does not. |
| Plan branch | Does `git branch --show-current` match the master `Branch:` field? `resume_status.py` warns on a mismatch. If the master has no `Branch:` field, report the current branch; do not create a branch mid-plan without asking. |
| Draft PR | If the resume brief records `- PR: <url>`, run `gh pr view <url>` (or the harness equivalent) and confirm the PR is open and its head is the plan branch. Run `git status -sb`; push any commits that exist only locally. If it records `PR: declined (<date>)`, do not open one without asking. If it records `PR: none`, ask at the next plan review. |

Never discard uncommitted work to make the state look clean. If the dirty files belong to the current phase, treat them as in-progress work. If they belong to a later phase, stop and report the out-of-order change.

### Upgrade an older master before acting

`resume_status.py` runs `progressive_plan.py check`. If the check fails because an older master is missing a current required section, repair the master before choosing the next action.

The required sections and their order are in `../progressive-plan/references/master-template.md`. For a missing `Goal flow`:

1. Add the section after `Objective`, with a fenced `mermaid` diagram of the plan's user-visible outcome.
2. Fill the diagram from the objective and definition of done. Keep it to the main path; no phase IDs or internal component names.
3. Record the schema repair with `add-discovery <plan-dir> <phase> "Added the required section" --affects all --type master-amend --action "Repaired the master schema"`. It bumps `Master version`.
4. Set `Validated against master version` to the new version in every `ready` or `in_progress` phase plan.
5. Re-run `check`.

For a missing `Code standards`, add the table from the master template and record the project's real format, lint, type-check, and test commands; write `none` only for a check the project does not have.

If an older phase plan is missing a required section such as `Risks and unknowns`, add the section from `../progressive-plan/references/phase-plan-template.md` before continuing. Keep the existing content and status. Do not present a phase for approval or spawn a worker while `check` fails.

Legacy done phases may lack `Implemented by`, `Implemented at`, checked code-standards items, or a `met` closeout row. Do not invent evidence. Record a `plan-defect`, keep the original closeout and commit visible, and ask the user whether to accept the gap, add a corrective phase, or mark the plan `needs_replan`.

## 3. Choose the next action from the state

| Current phase state | Next action |
|---|---|
| No phase plan yet | Write the plan with `write-plan <plan-dir> P<n>`; keep it `draft`/`planned`. |
| Plan written, not approved | Present the plan to the user and ask for approval. If the user requests changes, use `refine-phase`; if it was already ready, run `reopen` first. In yolo mode, run `approve --yolo` and continue instead. |
| Approved and `ready` | Set `in_progress`, spawn the implementation subagent, and wait. |
| `in_progress` | Inspect the worker's files, verification, closeout, and commit; run `scope`; do not reimplement. Finish the coordinator review. |
| `partial` closeout | Continue the remaining steps with a subagent, or leave the phase `in_progress` with a handoff. |
| `done` | Write the next phase plan and stop at the approval gate. In yolo mode, write it, auto-approve it, and continue. |
| `blocked` | Report the blocker, owner, and unblocking condition. Do not start a different phase without approval. |
| `needs_replan` | Rewrite the phase plan against the current master, then ask for approval. In yolo mode, revalidate and auto-approve it. |

If the current phase is already implemented but not committed, finish the closeout and commit gate before starting anything new. If it is committed but the master is stale, update the master before writing the next phase.

## 4. Resume the progressive-plan loop

Once the state is reconciled, follow `../progressive-plan/references/gates.md`. The resume-specific rules are:

- Do not implement an unapproved phase. Ask: "The P<n> plan is ready at `<path>. Approve implementation?" In yolo mode, run `approve --yolo` instead; the master authorization replaces this question.
- Use `reopen` when a ready or done phase needs plan changes; do not edit approval fields by hand.
- Use `record-commit` and `close`; do not mark a phase done by editing the status fields.
- Run `scope <plan-dir> <phase>` before accepting a worker's commit.
- If a draft PR is open, push every commit as it is created, including plan, approval, and closeout metadata commits.
- Before presenting a plan for approval, commit it with a `plan:` subject and push it when a draft PR is open. If no draft PR exists and the master records no decline, offer one first (see `../progressive-plan/references/gates.md`).
- When the master is complete, follow the completed-plan file gate: ask whether to keep or remove the plan files, archive them under `<plans-root>/archive/<slug>/` when kept, push the disposition commit, and update the PR title and body for the implemented outcome. The title uses a conventional-commit prefix; the body covers the issue, what was done, the decisions, and verification. In yolo mode, archive them, update the PR, and leave it as a draft without asking.
- If a closeout reports a `new-phase` discovery, verify the master phase map has that phase as `planned` and that the current phase did not implement it.
- Do not start the next phase because it looks easy. Close the current phase and stop at the next approval gate, unless the master records `Mode: yolo`.
- In yolo mode, stop only at the Yolo mode stop conditions in `../progressive-plan/SKILL.md`. Push every commit, keep the PR a draft, and archive the plan files at the end without asking.

## 5. Report the resume state

Before the first implementation action, send a short report:

```text
Resume — <plan title>
Master: v<n>, <status>, mode <standard|yolo>
Current phase: P<n> — <name> (<status>)
Approval: approved by <user> on <date> | pending
Commit: <hash> | none
Branch: plan/<slug> | <current branch> | none
PR: <draft URL> | declined (<date>) | none
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
- **Stale resume brief** — following a `Current phase` that disagrees with the phase map.
- **Skipping the approval or commit gate** — see `../progressive-plan/references/failure-modes.md`.
- **Scope absorption** — letting a worker's out-of-scope discovery become part of the current phase instead of a new phase.
- **Unpushed review PR** — resuming while plan or closeout commits stay local and the draft PR shows stale content.
- **Plan leftovers** — completing a master without deciding whether to archive or remove its plan files.
- **Yolo without its guardrails** — resuming a yolo master without the recorded authorization or the draft PR, or asking for per-phase approval the mode already replaced.

## Files

- `scripts/resume_status.py` — prints the plan state, git state, gates, and next action as text or JSON.
- `references/resume-checklist.md` — the manual checklist to run alongside the script.
- `../progressive-plan/` — the execution skill and its templates.
