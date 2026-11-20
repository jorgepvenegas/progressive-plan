# Shared gates

Use these rules with `progressive-plan`, `plan-resume`, and `refine-phase`. The main skill owns the operating loop; this file is the single description of the gates the sibling skills must preserve.

## Approval gate

A phase may move to `ready` only after the user has seen its plan and explicitly approved it.

- Keep the phase `draft` and the master row `planned` while writing or refining the plan.
- Run `progressive_plan.py check <plan-dir>`. A `ready`, `in_progress`, or `done` phase must have no template placeholders in its required sections.
- Ask directly: "Approve implementation of phase Pn?"
- Silence, a prior "keep going", approval of the master, or approval of an earlier phase is not approval.
- On explicit approval, run:

  ```bash
  python3 <progressive-plan-dir>/scripts/progressive_plan.py approve <plan-dir> P<n> --by "<user>"
  ```

  `approve` validates the phase, refuses an unfilled plan, resets stale implementation fields, records the approver and date, and sets the master to `active`.
- Do not implement, set `in_progress`, or spawn a worker before approval.
- Approval of one phase does not approve a later phase.
- A phase that must run before its dependencies are done needs `Parallel safe: yes` or `approve --allow-unmet-dependency` for intentional parallel work.

## Yolo mode gate

A master with `- Mode: yolo` and `- Mode authorized by: <user>, <date>` replaces the per-phase approval question. It replaces no other gate.

- The user opts in before the plan starts. `check` fails a yolo master without the authorization line, and `approve --yolo` refuses a master that is not in yolo mode.
- Write each phase plan and run `check` as usual. Auto-approve it with `approve <plan-dir> P<n> --by "<user>" --yolo`; the phase plan records `Approved by: <user> (yolo)`.
- Open the draft PR before implementation. The yolo authorization includes that draft PR. If `gh`, authentication, or a remote is missing, stop before implementation.
- Keep the delegation, scope, closeout, commit, discovery, and push rules unchanged.
- The plan ends with a draft PR, archived or removed plan files, and a report. It never merges, deploys, releases, or marks the PR ready.
- Stop and report at the conditions listed in the `progressive-plan` Yolo mode section: a blocked or `needs_replan` phase, a contract or scope change, a product decision, standards that cannot pass honestly, a repeated worker failure, missing credentials, or an exhausted budget.

## Delegation and scope fence

An approved phase is implemented by a subagent, not the coordinator.

- The coordinator may edit plans, the master, and review artifacts. It must not edit product code for the phase.
- Spawn one worker per phase with `references/worker-prompt-template.md`, absolute paths, the phase ID, the scope fence, and the approval record.
- The worker changes only the files listed in the phase plan and reports anything else.
- New work is classified, not absorbed:
  - required to meet this phase's acceptance criteria: amend the phase plan and send the worker back;
  - a separate outcome: add a `planned` phase and do not implement it now;
  - invalidates the phase premise: stop, mark `blocked` or `needs_replan`, and ask the user.

## Closeout and evidence

Run the closeout at the end of every implementation session, and always before a phase is marked done.

- Re-read `master.md` and the phase plan.
- Cover every phase acceptance criterion and every master definition-of-done item this phase advances.
- Evidence is a command and result, a test name, or `path:line`. "Looks correct" is not evidence.
- Run the phase verification, the master's standards commands, and the available definition-of-done commands.
- Record discoveries with a type, `Affects`, action, and status.
- A `done` phase needs `Verdict: addressed`, a row for every A and claimed D with `met` and evidence, every code-standards box checked, `Implemented by`, `Implemented at`, a real commit, and a closeout-history row.
- On the final phase, every master definition-of-done item must be checked and covered by the final closeout. `check` fails otherwise.
- Verdicts:
  - `addressed`: every criterion met, standards clean, no unapproved scope change.
  - `partial`: something unmet or the session ended early; the phase stays `in_progress`.
  - `blocked`: an external dependency or unresolved decision; name the owner and unblocking condition.

## Commit gate

- Work on `plan/<slug>`, not the default branch.
- Commit plan files with a `plan:` subject: `plan: <slug> master`, `plan: P<n> <name>`, `plan: P<n> approval`, or `plan: record draft PR`.
- Commit the phase as `P<n>: <phase name>`.
- Record the commit with `record-commit <plan-dir> P<n> --by <worker>`. The command rejects a `HEAD` whose subject does not start with `P<n>:`; pass `--hash` when the phase commit is not `HEAD`.
- Run `check` after recording. A `done` phase without a real recorded commit fails.
- Close the phase with `close <plan-dir> P<n> --by <worker>`. `close` sets the phase and master to `done`, writes the closeout history, and validates the result. It is the only transition that should mark a phase done.
- Commit the metadata change separately as `P<n>: record closeout`; never amend the phase commit.
- If a draft PR is open for `plan/<slug>`, push every commit as it is created with `git push`. This includes plan commits, phase commits, approval and closeout metadata, and the final plan-file disposition commit. Do not batch pushes until the end. A commit that stays local is not reviewable on GitHub.

## Discovery propagation

- Every ledger row has `Affects`: `all`, one phase ID, or a list/range such as `P3–P5`.
- Before approval, run `discoveries <plan-dir> P<n>` and list every returned row in `Prior discoveries applied`.
- `check` fails a `ready`, `in_progress`, or `done` phase that does not mention every affecting row.
- If a row truly does not apply, list it with "not applicable" and the reason. Do not drop it.
- A master version bump makes `ready` and `in_progress` phase plans stale; revalidate them before continuing.

## Branch and PR gate

- Every plan gets its own branch, recorded in the master.
- Do not create a plan branch in the middle of an existing plan.
- When the master or a phase plan is drafted, checked, and about to be presented for review, ask whether to open a draft PR so the user can read the plan on GitHub. Ask once per branch; skip the offer when the master resume brief records `- PR: declined (<date>)` or a draft PR already exists.
- Do not push or open a PR without explicit approval. Approval to open the review draft PR authorizes later pushes to that same branch.
- In yolo mode, the master authorization covers creating the draft PR before implementation and every later push to `plan/<slug>`. It does not cover merging, deploying, or marking the PR ready.
- Before an approval request, commit the plan with a `plan:` subject. If a draft PR is open, push it first.
- Record the PR URL in the master resume brief as `- PR: <url>`.
- At the end, offer a draft PR if none exists; do not push or open it without explicit approval.
- Write the initial PR body from `report <plan-dir>`, not from conversation. Include the objective, definition-of-done verdicts, phase table, verification commands, risks, and plan directory.
- After the whole plan is implemented, update the PR title and body. The title uses a conventional-commit prefix (`feat:`, `fix:`, `docs:`, `refactor:`, `perf:`, `test:`, `build:`, `ci:`, or `chore:`) chosen from the delivered outcome. The body covers the issue, what was done, the decisions, and verification. Apply it with `gh pr edit <number> --title "<conventional title>" --body-file <temp-file>`.
- Leave the PR as a draft unless the user asks to mark it ready.

## Completed-plan file gate

After the final phase is `done` and every definition-of-done item is met, ask whether to keep the plan files or remove them from the PR.

- **Remove:** `git rm -r <plan-dir>`, commit `plan: remove completed plan files`, and push when a draft PR is open. The PR body must not point at the removed directory.
- **Keep:** ask whether to leave the files at `<plan-dir>` or archive them under `<plans-root>/archive/<slug>/`. Recommend archive so a new master plan can use the same slug. Run `archive <plan-dir>`, commit `plan: archive <slug>`, and push when a draft PR is open.
- If the user keeps the files in place, say that the slug stays occupied.
- After the decision, update the PR title to a conventional-commit title and rewrite the body with the issue, what was done, the decisions, and verification.
- Record the decision in the final report.
- In yolo mode, do not ask: archive the plan files, update the PR title and body, and leave the PR as a draft. Remove the plan files instead only when the user asked for a product-only PR.
