---
name: plan-orchestrator
description: Orchestrate a large coding task through a master plan, phases, and a just-in-time sub-plan per phase. Use when a task is too large for one plan or one session, when the user asks for a master plan with phases and sub-plans, or when each phase must close out by proving the master plan was addressed and folding new discoveries into the master plan and the next phase.
---

# Plan Orchestrator

A master plan states the outcome and splits the work into phases. Each phase gets a detailed sub-plan written just before it starts. No phase implementation begins until the user has seen that phase's plan and explicitly approved it. Every approved phase is implemented by a subagent; the coordinator plans, reviews, and closes out, but does not write product code. At the end of every implementation session, the agent proves what the master plan owed, records what no earlier plan predicted, updates the master plan, commits the phase, and only then calls the phase done.

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

Scaffold and validate:

```bash
python3 <skill-dir>/scripts/plan_orchestrator.py new "<Title>" --root docs/plans
python3 <skill-dir>/scripts/plan_orchestrator.py add-phase docs/plans/<slug> "<Phase name>" --depends P1
python3 <skill-dir>/scripts/plan_orchestrator.py approve docs/plans/<slug> P2 --by "<user>"
python3 <skill-dir>/scripts/plan_orchestrator.py record-commit docs/plans/<slug> P2
python3 <skill-dir>/scripts/plan_orchestrator.py discoveries docs/plans/<slug> P3
python3 <skill-dir>/scripts/plan_orchestrator.py check docs/plans/<slug>
python3 <skill-dir>/scripts/plan_orchestrator.py status docs/plans/<slug>
```

`<skill-dir>` is the directory containing this `SKILL.md`. Use the repository's existing plans directory if it has one; `docs/plans` is the default.

To resume an existing plan, run `status` first: it prints the phase table and the resume brief. Then read `master.md` and the current phase plan.

## The loop

### 1. Research, then write the master plan

Do not write the master plan from the request alone. Read `AGENTS.md`/`CLAUDE.md`, the README, contributor docs, and the code and tests the work touches. Run the baseline build or tests. Record exact commands and results.

Ask the user only questions that change scope, behavior, acceptance, or risk. Give each question two or three options and a recommended default. If the user delegates a choice, record the chosen default in the master plan and continue. Never invent paths, symbols, flags, or behavior.

The master plan must contain:

- **Objective** — the user-visible outcome, not an activity.
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

Check the master before moving on: can a new agent tell when the whole task is done, which phase is next, and what each phase owes? If not, rewrite it.

### 2. Write the phase sub-plan just in time

Before starting phase `Pn`, write `phases/NN-<name>/plan.md`. Do not start implementation from the master outline.

- Read the master plan fresh, not from memory.
- Apply every discovery-ledger row that affects this phase before writing steps. Run `plan_orchestrator.py discoveries <plan-dir> <phase-id>`, then list every returned row in `Prior discoveries applied` with how it changes a step or acceptance criterion. Write `None` only when the command returns none.
- Trace every phase acceptance criterion to a master definition-of-done item, and every step to a phase criterion.
- Give each step exact files, the intended change, falsifiable acceptance, a verification command, and rollback.
- State entry conditions and verify them before the first edit.
- If a previous closeout marked the phase `needs_replan`, rewrite the affected sections. Do not patch around a plan that no longer holds.
- Keep local mechanics open: variable names, helper layout, and test organization are the implementer's choice.

Leave the phase status `draft` and the master row `planned` while the plan is being written. A completed plan is **not** approval to implement.

### Approval gate (required before every phase)

A phase may move to `ready` only after the user has seen its plan and explicitly approved it. This gate applies to every phase, including phases that look small or obvious.

1. Finish the phase plan and run `check`. Keep the phase `draft` / master `planned`.
2. Send the user a short review request: absolute plan path, phase outcome, acceptance criteria, and the top risks. Ask directly: "Approve implementation of phase Pn?"
3. Wait. Do not edit implementation files, set `in_progress`, or spawn a worker for that phase.
4. On explicit approval, run `plan_orchestrator.py approve <plan-dir> <phase-id> --by "<user>"`. This writes `Approved by` and `Approved at`, sets the phase and master row to `ready`, and validates the plan.
5. Only then set the phase `in_progress` in the master and start step 1.
6. Approval of one phase does not approve any later phase. Repeat the gate for every phase.

Silence, a prior "keep going", approval of the master plan, or approval of an earlier phase is **not** approval of the current phase. Do not infer it. If the user asks to skip review, record that instruction in the phase plan and master before starting.

### 3. Implement inside the phase by delegation

**Mandatory:** an approved phase is implemented by a subagent, not by the coordinator. The coordinator may edit plans, the master, and review artifacts; it must not edit product code for the phase.

1. Confirm the approval gate passed: the phase plan has `Approved by` and `Approved at`, and both the phase and master are `ready`.
2. Set the phase `in_progress` in the master and in the phase plan before spawning.
3. Spawn one subagent for the phase with the prompt from `references/worker-prompt-template.md`, filled with absolute paths, the phase ID, the scope fence, and the approval record. In prime-agent:
   ```python
   handle = await rlm.spawn(prompt, name="p3-dashboard-ui")
   ```
   Admission returns a handle, not the answer. Keep the handle.
4. Wait for the worker's reply. Do not implement the phase while waiting. Do not start a second worker on the same phase or the same shared files.
5. Review the worker's output yourself: read the changed files, run the phase verification, inspect the commit, and read the closeout. A silent worker is not a failed worker; verify before deciding.
6. If the worker is blocked or wrong, send it a correction or spawn a replacement. Do not take over the implementation.

**Coordinator exception.** The user may explicitly approve coordinator implementation for a specific phase. Record `Implementation mode: coordinator-exception`, `Exception approved by`, and `Exception reason` in the phase plan; otherwise the phase is invalid. Approval of the plan alone is not approval of this exception.

The worker follows the phase plan one step at a time, changes only the listed files, runs each verification, records evidence and deviations in the phase plan, and reports the closeout. If the plan is wrong or incomplete, the worker stops and reports the gap; the coordinator amends the plan, revalidates, and sends the worker back. If the change affects the user-visible contract, stop and ask the user.

### 4. Close out before ending the session

Run this at the end of every session that touched implementation, and always before marking a phase done. The worker writes the phase-plan closeout; the coordinator reviews it, proves coverage, and writes the master updates. A session that ends mid-phase still gets a closeout: verdict `partial`, partial evidence, discoveries, and the next action.

**A. Re-read the plans.** Open `master.md` and the phase plan. Do not reconstruct them from memory.

**B. Prove coverage.** Build a table with one row for every phase acceptance criterion and every master definition-of-done item this phase claims to advance. Verdicts: `met`, `partial`, `not met`, `deferred`. Evidence is a command and result, a test name, or `path:line`. "Looks correct" is not evidence.

On the final phase, cover every definition-of-done item in the master. Any unaddressed item forces verdict `partial`; the project is not done.

**C. Run the verification.** Execute the phase verification and any master definition-of-done commands that are available now. Record exact commands and results.

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

**Propagation rule.** Every ledger row must record `Affects`: `all`, one phase ID, or a comma-separated list/range such as `P3–P5`. When a discovery appears, set `Affects` immediately; do not leave it blank.

- Before approving a phase, run `plan_orchestrator.py discoveries <plan-dir> <phase-id>` and put every returned row in that phase plan's `Prior discoveries applied` table.
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

- `addressed` — every phase criterion met, every relevant master definition-of-done item met, and no unapproved scope change. Only now may the phase become `done` in the master.
- `partial` — a criterion is unmet or deferred, or the session ended early. The phase stays `in_progress`. Record what remains and the next action.
- `blocked` — an external dependency or unresolved decision stops work. Set the phase `blocked` and name the owner and the unblocking condition.

A phase is not done because its steps are done. It is done when the master plan says what the phase owed and evidence proves it.

### 5. Commit the phase

A phase is not wrapped up until its work is committed. Do this after the closeout updates are written and verified, and before any next-phase work.

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
   python3 <skill-dir>/scripts/plan_orchestrator.py record-commit docs/plans/<slug> P<n>
   python3 <skill-dir>/scripts/plan_orchestrator.py check docs/plans/<slug>
   ```
4. Put the short hash in the master closeout-history row. `check` fails a `done` phase with no recorded commit.
5. `record-commit` edits the plan files after the commit. Commit that small metadata change separately (`P<n>: record closeout commit`) or include it in the next phase's commit. Never amend the phase commit, because amending changes the hash.
6. Do not start the next phase until the commit exists and is recorded.

If the session ends `partial` or `blocked`, commit a WIP checkpoint with the same message plus `[WIP]`, record the hash, and state what remains. If the user explicitly forbids commits, record that exemption in the phase plan and master before proceeding; the gate is otherwise mandatory.

### 6. Hand off cleanly

Update the resume brief in the master: current phase, last verdict, next action, open decisions. Write the next phase plan only when the previous phase is closed, then stop at the approval gate and ask the user. The next session starts with the `plan-resume` skill, which reads the master plan, the current phase plan, the git state, and the recorded commit; do not rely on conversation history that a later session will not have.

## User-facing closeout report

End every closeout with a short report in this shape:

```text
Phase P2 closeout — <phase name>
Verdict: addressed | partial | blocked
Master coverage: D1 met (<evidence>), D2 partial (<gap>), D3 not started
Discoveries no earlier plan predicted: <one line each, or "none">
Plan updates: master v3 (<rows/sections changed>); P3 plan v2 (<sections changed>)
Commit: <short hash>
Next action: <one concrete action>
```

Lead with the verdict and the coverage result. Do not bury a partial verdict under a list of completed steps.

## Orchestrating subagents

Subagent implementation is mandatory for every approved phase. The coordinator handles planning, approval, review, and master updates.

- The coordinator owns `master.md`. A worker owns one phase plan at a time and the implementation files listed in that plan.
- Never let two agents write `master.md`, claim the same phase, or edit the same shared files.
- Spawn the worker only after approval. The prompt must include absolute paths to `master.md` and the phase plan, the phase ID, the scope fence, the approval record (`Approved by`, `Approved at`), and the instruction to implement, verify, write the phase-plan closeout, commit, and report verdict plus discoveries.
- Use the `references/worker-prompt-template.md` file. Do not improvise a shorter prompt that omits the approval or the scope fence.
- In prime-agent, `rlm.spawn(prompt, name=...)` returns immediately with a handle. Results arrive through `agent_message`; the worker replies with `await agent_message.send(message, receiver_role='parent')`. Recover handles with `await rlm.list_subagents()` after a restart or compaction.
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

## Files

- `references/master-template.md` — master plan structure.
- `references/phase-plan-template.md` — phase sub-plan and closeout structure.
- `references/worker-prompt-template.md` — required prompt for the subagent that implements an approved phase.
- `scripts/plan_orchestrator.py` — `new`, `add-phase`, `approve`, `record-commit`, `discoveries`, `check`, `status`.
- `../plan-resume/` — the new-session resume skill; use it before editing an existing plan.
