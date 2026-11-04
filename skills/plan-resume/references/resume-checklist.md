# Resume checklist

Use this with `scripts/resume_status.py`. Tick every item before the first edit.

## Plan state

- [ ] `master.md` read in full.
- [ ] Resume brief read; current phase matches the phase map.
- [ ] Master version matches every `ready`/`in_progress` phase plan's `Validated against master version`.
- [ ] Current phase plan read in full.
- [ ] `progressive_plan.py check` passes.
- [ ] `progressive_plan.py discoveries <plan-dir> <phase>` run; every affecting ledger row appears in `Prior discoveries applied`.

## Approval and implementation

- [ ] `Approved by` and `Approved at` are set for the current phase.
- [ ] `Implementation mode` is `subagent`, or a coordinator exception has an approving user.
- [ ] The current phase is `in_progress` only after approval.
- [ ] If not approved, the next action is to ask the user, not to implement.

## Repository state

- [ ] `git status` reviewed; uncommitted files identified and preserved.
- [ ] `git log --oneline -10` reviewed.
- [ ] The current phase's recorded commit exists and is an ancestor of HEAD (or no commit is expected yet).
- [ ] The working tree is clean, or the dirty files are current-phase work.
- [ ] No secrets, database files, build output, or `node_modules` are staged.

## Verification

- [ ] The phase verification commands run in this session.
- [ ] The full test suite result is recorded.
- [ ] The web/server build result is recorded.
- [ ] A silent worker's files and closeout were inspected, not assumed failed.

## Handoff

- [ ] The resume report states the next legal action.
- [ ] If the phase is done, the next phase plan is written and the session stops at the approval gate.
- [ ] If the phase is blocked, the blocker, owner, and unblocking condition are written in the phase plan and master.
