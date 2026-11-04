---
name: progressive-plan
description: Plan and execute coding work of any size through a master plan and phases, with issue intake, scope sizing, approval gates, subagent implementation, and closeout. Use when starting from a GitHub or Linear issue or a request, when a task needs scoping and acceptance criteria, for a small one-phase task, or for large multi-phase work with just-in-time sub-plans.
---

# Progressive Plan

Start from the source issue or request, size the work, and choose a one-phase plan for small tasks or a multi-phase master for large ones. A master plan states the outcome and splits the work into phases. Each phase gets a detailed sub-plan written just before it starts. No phase implementation begins until the user has seen that phase's plan and explicitly approved it. Every approved phase is implemented by a subagent; the coordinator plans, reviews, and closes out, but does not write product code. At the end of every implementation session, the agent proves what the master plan owed, records what no earlier plan predicted, updates the master plan, commits the phase, and only then calls the phase done.

This skill is the coordinator's operating loop. It works for one agent doing all the work and for a coordinator delegating phases to subagents.

## Artifacts

```
docs/plans/<slug>/
├── master.md
└── phases/
    ├── 01-<name>/plan.md
    └── 02-<name>/plan.md
```

- `master.md` is the contract and the map. The coordinator owns it.
- `phases/NN-<name>/plan.md` is one phase's executable plan plus its closeout record. One phase per file.
- Later phases stay as outlines in the master until their plan is written. Do not write every sub-plan up front; discoveries would invalidate them before use.

Before scaffolding a new plan, create its branch (see Branch and PR gates).

Scaffold and validate:

```bash
python3 <skill-dir>/scripts/progressive_plan.py new "<Title>" --root docs/plans
python3 <skill-dir>/scripts/progressive_plan.py add-phase docs/plans/<slug> "<Phase name>" --depends P1
python3 <skill-dir>/scripts/progressive_plan.py approve docs/plans/<slug> P2 --by "<user>"
python3 <skill-dir>/scripts/progressive_plan.py record-commit docs/plans/<slug> P2
python3 <skill-dir>/scripts/progressive_plan.py discoveries docs/plans/<slug> P3
python3 <skill-dir>/scripts/progressive_plan.py check docs/plans/<slug>
python3 <skill-dir>/scripts/progressive_plan.py status docs/plans/<slug>
```

`<skill-dir>` is the directory containing this `SKILL.md`. Use the repository's existing plans directory if it has one; `docs/plans` is the default.

To resume an existing plan, run `status` first: it prints the phase table and the resume brief. Then read `master.md` and the current phase plan.

## Task intake and sizing

Start here for a new request that changes the repository. Answer questions and do read-only investigation directly; do not scaffold a plan for them. For repository work, do not write a plan from the prompt alone. Read the source, scope it against the repository, ask about gaps, and size the work before choosing the plan shape. See `references/issue-intake.md` for source recipes, a scoping brief, sizing examples, and escalation rules.

### Read the source

Identify where the requirement lives and read all of it:

- **GitHub issue or PR:** `gh issue view <number> --comments` or `gh pr view <number> --comments`.
- **Linear, Jira, Notion, or another tracker:** use the connected MCP tools. In prime-agent, discover them with `mcp.list_connections` and `mcp.search_tools` and inspect a schema with `mcp.describe_tool`; in Claude Code or Pi, use the configured MCP servers and search their tools. Then call the read tool. If no connection exists, ask the user to paste the issue.
- **Local file, URL, or conversation:** read the file or ask for the text. Do not invent details from a title.

Read the body, every comment, linked specs or designs, acceptance criteria, labels, priority, dependencies, and attachments. Record the source and issue ID in the master.

### Scope against the repository

Before asking questions, inspect what already exists:

- `AGENTS.md`, `CLAUDE.md`, `README.md`, and the current plans.
- The code, tests, and git history the change touches.
- The current branch and working tree.
- Existing behavior that the request would replace.

State what you found as evidence. Never assume a path, symbol, flag, or behavior.

### Ask about gaps

Ask only questions that change scope, behavior, acceptance, risk, or priority. Give two or three options and a recommended default. Ask at most three to five questions per round.

Good questions:
- "Should this apply to all accounts or only the selected one?"
- "When the file has an invalid row, should the import fail completely or skip that row?"

Bad questions:
- "Can you tell me more?"
- "What do you want me to do?"

If the source has no acceptance criteria, propose two or three and ask the user to confirm. If the source is too vague to size, stop and ask. Record every answer in the master.

### Size the task

| Size | Signals | Plan shape |
|---|---|---|
| Small | One outcome, up to about three files, no schema/API/contract change, one verification command, no cross-phase dependency, fits one session | Master with one phase and one to three steps; keep each required section short and write `none` where empty |
| Medium | One subsystem, several files, tests, one or two user-visible behaviors | Master with one phase and three to seven steps |
| Large | Several subsystems, a user-visible contract, migrations, dependencies, or several sessions | Full master and multi-phase map with just-in-time phase plans |

A small task still gets the plan, approval, subagent, and commit gates. The gates protect the work; the plan shape only removes unnecessary phases. Do not invent future phases for a small task.

If a small task grows past its plan, stop and add a phase or convert it to a larger plan. Do not expand scope silently.

### Record the intake

Add these lines to the master or the phase plan:

```text
Source: <issue URL, ticket ID, or "user request">
Problem: <one or two sentences>
Outcome: <what the user can do or see afterward>
Acceptance: <the initial A criteria>
Constraints: <time, files, compatibility, data>
Non-goals: <what is explicitly excluded>
Unknowns: <open questions and answers>
Size: small | medium | large
```

For a small task, keep the intake to a few lines. Link to the issue instead of copying the whole thread.

## Code standards

The repository owns its standards. Read `AGENTS.md`/`CLAUDE.md`, contributor docs, tooling config, and nearby code; record the exact checks in the master. Do not restate a style guide in the plan.

Every phase and every step follows these rules:

- **Smallest change.** Add only what the acceptance criteria require. No speculative abstraction, extension point, configuration, or dependency (YAGNI).
- **Reuse before writing.** Use an existing helper or pattern when it fits. Remove duplication the change creates, but do not build a framework for two similar lines (DRY).
- **Expressive code.** Names state intent and units; a function or module does one job. No dead code, commented-out code, or unused exports.
- **Comments explain why.** Write a comment only for a non-obvious constraint, workaround, or trade-off that the code cannot show. Do not narrate what the code does, restate a name, or keep a changelog in comments.
- **Tests are evidence.** A test asserts observable behavior or a failure the requirements name. Do not add a test that restates the implementation, repeats another test's assertion, or would still pass if the behavior broke. Test behavior, not internal calls.
- **No drive-by cleanup.** Leave unrelated code, formatting, names, and dependencies alone. Report the problem instead.

Enforcement:

- The master records the project's standards commands (format, lint, type check, tests). Each phase verification includes the commands that cover the changed code.
- The worker runs those commands, records the result in the phase plan's `Code standards check`, and reports any rule it cannot meet. It does not weaken the rule.
- The coordinator reviews the diff for duplicated logic, speculative abstraction, dead code, comment noise, and tautological tests. A green test suite does not excuse a violation.

## Branch and PR gates

Every plan gets its own branch. All plan and phase commits land on it. When the final phase is done and the definition of done is met, offer a draft PR. Never push or open a PR without explicit approval.

### Start of plan

Create the branch before writing `master.md`:

1. Confirm the working tree is clean with `git status --short`. If it is dirty, stop and ask what to do with the changes.
2. Detect the default branch:
   ```bash
   git symbolic-ref refs/remotes/origin/HEAD --short
   ```
   Strip the `origin/` prefix. If that fails, use `main`, then `master`.
3. Create `plan/<slug>` from the default branch:
   ```bash
   git switch -c plan/<slug> <default-branch>
   ```
   If the branch already exists, switch to it. Do not recreate it.
4. Record `- Branch: plan/<slug>` in the master header.
5. If the repository is not a git repository, record that and continue without a branch. A missing remote does not block a local branch; it only blocks the draft PR at the end.

Do not create a plan branch in the middle of an existing plan. If a plan is already in progress and the current branch does not match the recorded branch, stop and report.

### End of plan

After the final phase is `done`, every definition-of-done item is met, any `record-commit` metadata is committed, and the working tree is clean:

1. Confirm the branch and the remote:
   ```bash
   git branch --show-current
   git remote -v
   gh auth status
   ```
2. Offer, do not act: "The plan is complete on `plan/<slug>`. Create a draft PR to `<default-branch>`?"
3. Only after explicit approval, push and create the draft PR:
   ```bash
   git push -u origin plan/<slug>
   gh pr create --draft --base <default-branch> --head plan/<slug> \
     --title "<plan title>" --body-file <temp-file>
   ```
4. Write the PR body from the master, not from conversation. Include the objective, the definition-of-done checklist with verdicts, the phase table, verification commands and results, known issues and risks, and the plan directory path.
5. Record the PR URL in the master resume brief and report it.

If `gh` is missing, unauthenticated, or there is no remote, report the limitation and leave the branch pushed or local as the user prefers. Do not fail the plan closeout.

**Plans that predate this rule.** If the master has no `Branch:` field and work already landed on the default branch, do not push the default branch or open a PR from it. Report the state and ask whether to create a retrospective branch. Do not rewrite history.

## The loop

### 1. Intake, size, then write the plan

Run Task intake and sizing first. Read the source, inspect the repository, ask gap questions, and choose the small/medium/large plan shape. Then create the plan branch (see Branch and PR gates).

For every task, write the master plan after the intake. Small and medium tasks use a one-phase master; large tasks use the full phase map. Read `AGENTS.md`/`CLAUDE.md`, the README, contributor docs, and the code and tests the work touches. Run the baseline build or tests. Record exact commands and results.

Ask the user only questions that change scope, behavior, acceptance, or risk. Give each question two or three options and a recommended default. If the user delegates a choice, record the chosen default in the master plan and continue. Never invent paths, symbols, flags, or behavior.

The master plan must contain:

- **Objective** — the user-visible outcome, not an activity.
- **Goal flow** — a high-level Mermaid diagram of the user-visible outcome, for the person approving phases. Keep it to the main path; implementation detail belongs in the phase plans.
- **Definition of done** — numbered `D1..Dn`, each observable and each with a verification command or observation.
- **Non-goals** — adjacent work explicitly excluded.
- **Current state** — evidence from the repository: files, symbols, baseline results, assumptions, unknowns.
- **Phase map** — phases ordered by dependency, each with a one-line outcome, exit criteria, and status.
- **Cross-phase decisions** — append-only decisions that constrain more than one phase.

Phase sizing:

- A phase is a coherent increment that leaves the repository in a verifiable state and fits roughly one focused session.
- A phase has one outcome, not a bucket of unrelated steps. If it touches unrelated subsystems or needs more than about seven steps, split it.
- Phases are ordered by dependency. Mark phases that are safe to run in parallel and name the shared files that make them unsafe.
- A phase is not a step. Steps live in the phase sub-plan.

Check the master before moving on: can a new agent tell why the plan exists, when the whole task is done, which phase is next, and what each phase owes? If not, rewrite it.

### 2. Write the phase sub-plan just in time

Before starting phase `Pn`, write `phases/NN-<name>/plan.md`. Do not start implementation from the master outline.

- Read the master plan fresh, not from memory.
- Apply every discovery-ledger row that affects this phase before writing steps. Run `progressive_plan.py discoveries <plan-dir> <phase-id>`, then list every returned row in `Prior discoveries applied` with how it changes a step or acceptance criterion. Write `None` only when the command returns none.
- Trace every phase acceptance criterion to a master definition-of-done item, and every step to a phase criterion.
- Give each step exact files, the intended change, falsifiable acceptance, a verification command, and rollback.
- State entry conditions and verify them before the first edit.
- If a previous closeout marked the phase `needs_replan`, rewrite the affected sections. Do not patch around a plan that no longer holds.
- Keep local mechanics open: variable names, helper layout, and test organization are the implementer's choice.

Leave the phase status `draft` and the master row `planned` while the plan is being written. A completed plan is **not** approval to implement.

### Approval gate (required before every phase)

A phase may move to `ready` only after the user has seen its plan and explicitly approved it. This gate applies to every phase, including phases that look small or obvious.

1. Finish the phase plan and run `check`. Keep the phase `draft` / master `planned`. If `check` reports a missing master section, repair the master from `references/master-template.md` before asking for approval. Do not mark the phase ready while `check` fails.
2. Send the user a short review request: absolute plan path, phase outcome, acceptance criteria, and the top risks. Ask directly: "Approve implementation of phase Pn?"
3. Wait. Do not edit implementation files, set `in_progress`, or spawn a worker for that phase. If the user asks for changes instead of approving, use the `refine-phase` skill (sibling directory); keep the phase `draft` and return to this gate after the refinement.
4. On explicit approval, run `progressive_plan.py approve <plan-dir> <phase-id> --by "<user>"`. This writes `Approved by` and `Approved at`, sets the phase and master row to `ready`, and validates the plan.
5. Only then set the phase `in_progress` in the master and start step 1.
6. Approval of one phase does not approve any later phase. Repeat the gate for every phase.

Silence, a prior "keep going", approval of the master plan, or approval of an earlier phase is **not** approval of the current phase. Do not infer it. If the user asks to skip review, record that instruction in the phase plan and master before starting.

### 3. Implement inside the phase by delegation

**Mandatory:** an approved phase is implemented by a subagent, not by the coordinator. The coordinator may edit plans, the master, and review artifacts; it must not edit product code for the phase.

1. Confirm the approval gate passed: the phase plan has `Approved by` and `Approved at`, and both the phase and master are `ready`.
2. Set the phase `in_progress` in the master and in the phase plan before spawning.
3. Spawn one subagent for the phase with the prompt from `references/worker-prompt-template.md`, filled with absolute paths, the phase ID, the scope fence, and the approval record. Use your harness's subagent mechanism: in prime-agent, `await rlm.spawn(prompt, name="p3-dashboard-ui")`; in Claude Code, the Task tool; in Pi, the `pi-subagents` tools. Keep the handle or task ID.
4. Wait for the worker's reply. Do not implement the phase while waiting. Do not start a second worker on the same phase or the same shared files.
5. Review the worker's output yourself: read the changed files against the phase plan's file lists, run the phase verification and the master's standards commands, inspect the commit, and read the closeout. Check the diff for duplicated logic, speculative abstraction, dead code, comment noise, and tautological tests. A silent worker is not a failed worker; verify before deciding.
6. If the worker is blocked or wrong, send it a correction or spawn a replacement. Do not take over the implementation.

### Scope discipline and new work

The approved phase plan is the only work authorization. The worker must not absorb unrelated work, opportunistic fixes, refactors, features, or a later phase's scope.

When implementation discovers more work, classify it before touching code:

| Discovery | Example | Handling |
|---|---|---|
| Required to meet this phase's acceptance criteria | A helper or migration the approved steps missed | `phase-amend`: the worker stops and reports; the coordinator updates the phase plan (files, steps, or acceptance as needed), revalidates, and sends the worker back. |
| A separate outcome or feature | "We should also add CSV export" found while building import | `new-phase`: the worker reports it and continues the approved steps unless it blocks them; the coordinator adds a `planned` phase to the master and ledger; do not implement it in this phase. |
| Invalidates the phase premise | The API cannot support the approved behavior | Stop; mark the phase `blocked` or `needs_replan`; ask the user. |

New-phase procedure:

1. Record a ledger row with type `new-phase` and `Affects` set to the new phase ID (or the phase that will own it).
2. Add the phase to the phase map with a one-line outcome and dependencies, status `planned`. Use `progressive_plan.py add-phase` when available, then bump the master version and set the new plan's `Validated against master version` to the new value.
3. Do not write its detailed plan until the current phase is closed, unless it must run first; in that case stop and ask the user about order.
4. Keep the current phase's closeout scoped to its own acceptance criteria. Note the new phase ID under remaining work.
5. Review the current diff for scope drift: changed files must match the phase plan's file lists. If the worker added out-of-scope code, stop and remove it or ask.

The coordinator must not let a worker expand the phase. If the worker already made out-of-scope changes, do not accept the commit; revert the out-of-scope files and re-run verification.

**Coordinator exception.** The user may explicitly approve coordinator implementation for a specific phase. Record `Implementation mode: coordinator-exception`, `Exception approved by`, and `Exception reason` in the phase plan; otherwise the phase is invalid. Approval of the plan alone is not approval of this exception.

The worker follows the phase plan one step at a time, changes only the listed files, runs each verification, records evidence and deviations in the phase plan, and reports the closeout. If the plan is wrong or incomplete, the worker stops and reports the gap; the coordinator amends the plan, revalidates, and sends the worker back. If the change affects the user-visible contract, stop and ask the user.

### 4. Close out before ending the session

Run this at the end of every session that touched implementation, and always before marking a phase done. The worker writes the phase-plan closeout; the coordinator reviews it, proves coverage, and writes the master updates. A session that ends mid-phase still gets a closeout: verdict `partial`, partial evidence, discoveries, and the next action.

**A. Re-read the plans.** Open `master.md` and the phase plan. Do not reconstruct them from memory.

**B. Prove coverage.** Build a table with one row for every phase acceptance criterion and every master definition-of-done item this phase claims to advance. Verdicts: `met`, `partial`, `not met`, `deferred`. Evidence is a command and result, a test name, or `path:line`. "Looks correct" is not evidence.

On the final phase, cover every definition-of-done item in the master. Any unaddressed item forces verdict `partial`; the project is not done.

**C. Run the verification.** Execute the phase verification, the master's standards commands, and any master definition-of-done commands that are available now. Record exact commands and results.

**D. Sweep for discoveries.** Answer each prompt in writing. Write "none" only after answering all five:

1. What did implementation learn that the master plan or phase plan assumed wrong?
2. What coupling, constraint, or requirement appeared that no earlier plan predicted?
3. What was built that no plan asked for, or what plan item proved unnecessary?
4. What will bite the next phase if it is not written down now?
5. Which earlier phase's evidence is now suspect because of what was learned?

**E. Classify every discovery.** Do not leave a finding as an observation; give it a type and an action.

| Type | Meaning | Where it is written |
|---|---|---|
| `note` | Worth keeping; no plan change | Master discovery ledger |
| `phase-amend` | Changes the current phase plan | Phase plan, then master ledger |
| `next-phase-amend` | Changes the following phase's scope or steps | Following phase plan, then master ledger |
| `master-amend` | Changes the objective, definition of done, constraints, or phase map | Master plan, then affected phase plans |
| `new-phase` | Work no existing phase covers | Master phase map and discovery ledger |
| `scope-change` | Changes the user-visible contract | Stop and ask the user before proceeding |
| `plan-defect` | An earlier plan missed a fact it should have found | Master discovery ledger; name the missed fact |

`new-phase` discoveries are added to the master phase map in the same closeout with status `planned`. They are not implemented in the current phase.

**Propagation rule.** Every ledger row must record `Affects`: `all`, one phase ID, or a comma-separated list/range such as `P3–P5`. When a discovery appears, set `Affects` immediately; do not leave it blank.

- Before approving a phase, run `progressive_plan.py discoveries <plan-dir> <phase-id>` and put every returned row in that phase plan's `Prior discoveries applied` table.
- `check` fails a `ready`, `in_progress`, or `done` phase that does not mention every ledger row affecting it. This is the guard against losing a discovery between phases.
- If a returned row truly does not apply, list it with "not applicable" and the reason. Do not silently drop it.
- When a new discovery changes the next phase, update that phase plan's table in the same closeout that records the ledger row.

**F. Write the updates, in this order:**

1. **Phase plan** — step status and evidence, deviations, and the complete `Closeout` section with the verdict and discovery table.
2. **Master plan** — phase status, discovery-ledger rows, decisions, definition-of-done changes, phase-map changes, closeout-history row, and the resume brief. Bump `Master version` on any semantic change.
3. **Following phase** — apply the amendment and every relevant discovery-ledger row now. Bump its `Plan version`, update `Prior discoveries applied`, and set `Validated against master version` to the new master version. If the change is too large for a targeted edit, set the phase `needs_replan` and state what must be rewritten.
4. **Any other phase** whose assumptions the discovery invalidated. Update it or mark it `needs_replan`; never leave a stale plan marked `ready`.

Do not update a future plan from memory. Open the file and edit it.

**G. Decide the verdict.**

- `addressed` — every phase criterion met, every relevant master definition-of-done item met, the code standards check is clean, and no unapproved scope change. Only now may the phase become `done` in the master.
- `partial` — a criterion is unmet or deferred, or the session ended early. The phase stays `in_progress`. Record what remains and the next action.
- `blocked` — an external dependency or unresolved decision stops work. Set the phase `blocked` and name the owner and the unblocking condition.

A phase is not done because its steps are done. It is done when the master plan says what the phase owed and evidence proves it.

### 5. Commit the phase

A phase is not wrapped up until its work is committed. Do this after the closeout updates are written and verified, and before any next-phase work. Confirm you are on `plan/<slug>` with `git branch --show-current`; never commit phase work to the default branch.

1. Review the diff and the ignored files:
   ```bash
   git status --short
   git diff --stat
   ```
   Confirm `node_modules`, the local database, build output, and secrets are ignored.
2. Commit the phase:
   ```bash
   git add -A
   git commit -m "P<n>: <phase name>"
   ```
3. Record the commit hash in the phase plan and validate:
   ```bash
   python3 <skill-dir>/scripts/progressive_plan.py record-commit docs/plans/<slug> P<n>
   python3 <skill-dir>/scripts/progressive_plan.py check docs/plans/<slug>
   ```
4. Put the short hash in the master closeout-history row. `check` fails a `done` phase with no recorded commit.
5. `record-commit` edits the plan files after the commit. Commit that small metadata change separately (`P<n>: record closeout commit`) or include it in the next phase's commit. Never amend the phase commit, because amending changes the hash.
6. Do not start the next phase until the commit exists and is recorded.

If the session ends `partial` or `blocked`, commit a WIP checkpoint with the same message plus `[WIP]`, record the hash, and state what remains. If the user explicitly forbids commits, record that exemption in the phase plan and master before proceeding; the gate is otherwise mandatory.

### 6. Hand off cleanly

Update the resume brief in the master: current phase, last verdict, next action, open decisions. Write the next phase plan only when the previous phase is closed, then stop at the approval gate and ask the user. The next session starts with the `plan-resume` skill, which reads the master plan, the current phase plan, the git state, and the recorded commit; do not rely on conversation history that a later session will not have.

When the final phase is `done` and every definition-of-done item is met, follow the End of plan gate in Branch and PR gates: ask whether to push and open a draft PR. Record the answer and the PR URL in the master.

## User-facing closeout report

End every closeout with a short report in this shape:

```text
Phase P2 closeout — <phase name>
Verdict: addressed | partial | blocked
Master coverage: D1 met (<evidence>), D2 partial (<gap>), D3 not started
Discoveries no earlier plan predicted: <one line each, or "none">
Plan updates: master v3 (<rows/sections changed>); P3 plan v2 (<sections changed>)
Standards: passed | <unmet rule and reason>
Commit: <short hash>
Branch: plan/<slug>
Next action: <one concrete action>
```

Lead with the verdict and the coverage result. Do not bury a partial verdict under a list of completed steps.

## Orchestrating subagents

Subagent implementation is mandatory for every approved phase. The coordinator handles planning, approval, review, and master updates.

- The coordinator owns `master.md`. A worker owns one phase plan at a time and the implementation files listed in that plan.
- Never let two agents write `master.md`, claim the same phase, or edit the same shared files.
- Spawn the worker only after approval. The prompt must include absolute paths to `master.md` and the phase plan, the phase ID, the scope fence, the approval record (`Approved by`, `Approved at`), and the instruction to implement, verify, write the phase-plan closeout, commit, and report verdict plus discoveries.
- Use the `references/worker-prompt-template.md` file. Do not improvise a shorter prompt that omits the approval or the scope fence.
- Use the harness's own delegation API: in prime-agent, `rlm.spawn(prompt, name=...)` returns a handle and the worker replies through `agent_message`; in Claude Code, spawn a Task; in Pi, use `pi-subagents`. Keep whatever handle, task ID, or result channel the harness returns, and recover it after a restart or compaction.
- The worker may update its phase plan but not `master.md`. It reports master-level changes to the coordinator; the coordinator applies them and marks the phase done.
- The worker commits the phase after closeout and reports the short hash. The coordinator verifies the hash and runs `record-commit` while updating the master.
- Run phases in parallel only when the master says they are independent and their file sets do not collide.
- Verify a silent worker's output before assuming failure: read the phase plan, changed files, commit, and test output, then decide.

## Failure modes to avoid

- **Plan theater** — phases with no observable exit; the project can never be declared done.
- **Big-design-up-front** — writing every sub-plan before the first phase. The later plans are fiction.
- **Silent replan** — rewriting the master during implementation to match what was built instead of recording the discovery and its cause.
- **Discovery dump** — listing observations without a type, an action, or an owner.
- **Coverage by assertion** — marking a criterion met without a command, test, or file evidence.
- **Phase drift** — doing the next phase's work early because it is convenient.
- **Optimistic closeout** — `addressed` with deferred criteria and no user approval.
- **Stale plans** — a master version bump that leaves the next phase marked `ready` against an older version.
- **Discovery loss** — writing a phase plan without carrying forward the ledger rows that affect it, or leaving a ledger row without an `Affects` value.
- **Unauthorized start** — implementing a phase whose plan the user has not explicitly approved.
- **Coordinator implementation** — writing product code in the coordinator instead of delegating an approved phase to a subagent. Exceptions require explicit user approval and a recorded exception.
- **Approval by assumption** — treating silence, a prior "keep going", approval of the master plan, or approval of an earlier phase as approval of the current phase.
- **Approval theater** — marking a phase `ready` without running the approval command and recording who approved it.
- **Uncommitted closeout** — marking a phase done with no commit or no recorded commit hash.
- **Default-branch implementation** — implementing a plan on the default branch instead of its `plan/<slug>` branch.
- **PR without consent** — pushing a branch or opening a draft PR before the user explicitly agrees.
- **Scope creep** — accepting unrelated work or opportunistic fixes into an approved phase.
- **New-work absorption** — doing a later phase's work inside the current phase instead of adding a new phase and planning it separately.
- **Speculative abstraction** — a helper, layer, option, or dependency built for a caller that does not exist.
- **Copy-paste duplication** — a second copy of logic where the existing helper or a small extraction fits.
- **Comment narration** — comments that repeat what the code says or record the change instead of explaining why.
- **Test theater** — tautological tests that restate the implementation, repeat another test's assertion, or pass when the behavior breaks.

## Files

- `references/master-template.md` — master plan structure.
- `references/phase-plan-template.md` — phase sub-plan and closeout structure.
- `references/worker-prompt-template.md` — required prompt for the subagent that implements an approved phase.
- `references/issue-intake.md` — reading GitHub/Linear/tracker issues, extraction checklist, gap questions, and sizing examples.
- `scripts/progressive_plan.py` — `new`, `add-phase`, `approve`, `record-commit`, `discoveries`, `check`, `status`.
- `../plan-resume/` — the new-session resume skill; use it before editing an existing plan.
