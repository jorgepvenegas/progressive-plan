# Resume checklist

Use this with `scripts/resume_status.py`. Tick every item before the first edit.

## Plan state

- [ ] `master.md` read in full.
- [ ] Resume brief read; current phase matches the phase map.
- [ ] Master `Mode` read. For `yolo`, `Mode authorized by` names the user and date, and the draft PR is open.
- [ ] Master version matches every `ready`/`in_progress` phase plan's `Validated against master version`.
- [ ] Current phase plan read in full.
- [ ] `progressive_plan.py check` passes.
- [ ] `progressive_plan.py discoveries <plan-dir> <phase>` run; every affecting ledger row appears in `Prior discoveries applied`.

## Approval and implementation

- [ ] `Approved by` and `Approved at` are set for the current phase.
- [ ] `Implementation mode` is `subagent`, or a coordinator exception has an approving user and a reason.
- [ ] The current phase is `in_progress` only after approval.
- [ ] If not approved, the next action is to ask the user, not to implement; in `yolo` mode, auto-approve with `--yolo` and continue.
- [ ] For a done phase, `Implemented by` and `Implemented at` are set.
- [ ] For a done phase, every A and claimed D has a `met` closeout row with evidence, and every code-standards box is checked.

## Repository state

- [ ] `git status` reviewed; uncommitted files identified and preserved.
- [ ] `git log --oneline -10` reviewed.
- [ ] The current phase's recorded commit exists and is an ancestor of HEAD (or no commit is expected yet).
- [ ] The current branch matches the master `Branch:` field.
- [ ] The resume brief `PR:` field is checked. An open draft PR is confirmed, and commits that exist only locally are pushed.
- [ ] If no draft PR exists and the brief records no decline, the next plan review offers one.
- [ ] `scope <plan-dir> <phase>` reports no out-of-scope changed files, or each exception is reported.
- [ ] The working tree is clean, or the dirty files are current-phase work.
- [ ] No secrets, database files, build output, or `node_modules` are staged.

## Verification

- [ ] The phase verification commands run in this session.
- [ ] The full test suite result is recorded.
- [ ] The web/server build result is recorded.
- [ ] A silent worker's files and closeout were inspected, not assumed failed.

## Handoff

- [ ] The resume report states the next legal action.
- [ ] If the phase is done, the next phase plan is written, committed with a `plan:` subject, pushed when a draft PR is open, and the session stops at the approval gate; in `yolo` mode, it auto-approves and continues.
- [ ] If the phase is blocked, the blocker, owner, and unblocking condition are written in the phase plan and master.
- [ ] If the master is complete, the plan-file decision is recorded: files removed from the PR, archived under `<plans-root>/archive/<slug>/`, or kept in place. In `yolo` mode, archive them without asking.
- [ ] If the master is complete, the PR title uses a conventional-commit prefix and the body covers the issue, what was done, the decisions, and verification.
