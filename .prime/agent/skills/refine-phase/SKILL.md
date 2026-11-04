---
name: refine-phase
description: Refine an unapproved plan-orchestrator phase plan after the user rejects it or requests changes, then re-present it for approval and continue into delegated implementation once approved. Use when the user says no to a phase plan, asks for plan changes before approving, or wants scope, steps, acceptance criteria, files, or risks revised after plan review.
---

# Refine Phase

Use this skill when a `plan-orchestrator` phase plan is written but the user does not approve it. The goal is to turn the feedback into a precise, revalidated plan, obtain explicit approval, and then hand the approved phase to a subagent.

Do not implement product code during refinement. The approval gate stays closed until the user explicitly approves the revised plan.

## Quick start

Run these from the repository root:

```bash
python3 <plan-orchestrator-dir>/scripts/plan_orchestrator.py status docs/plans/<slug>
python3 <plan-orchestrator-dir>/scripts/plan_orchestrator.py check docs/plans/<slug>
```

Then read the current phase plan and `master.md` fresh. `<plan-orchestrator-dir>` is the sibling directory of this skill.

## 1. Protect the approval gate

- Keep the phase `draft` and the master row `planned`.
- Do not edit product code, tests, or configuration.
- Do not set `in_progress`.
- Do not spawn a worker.

If the phase was already marked `ready` or has approval fields, reset it before refining:

- `Status: draft`
- `Approved by: pending`
- `Approved at: pending`
- `Commit: pending`
- master phase row: `planned`

If the phase is already `in_progress` or `done`, this is no longer a plan refinement. Stop and handle it as a scope change: use the master amendment and discovery rules in `references/master-change-propagation.md`.

## 2. Understand the requested change

Restate the request as a concrete plan change. Ask only questions that change scope, acceptance, behavior, or risk. Give two or three options and a recommended default.

Classify the feedback:

| Level | Examples | Where it lands |
|---|---|---|
| Phase-local | steps, file list, acceptance wording, test plan, risks, step order, rollback | the phase plan |
| Master | objective, definition of done, non-goals, phase map, cross-phase decision | `master.md`, then every affected phase plan |
| Contract | user-visible feature behavior, CSV format, API shape, data model | stop and confirm with the user before editing |

If the feedback points out a defect in the current plan, record it as a plan defect. Do not silently rewrite the history that produced it.

## 3. Rewrite the plan

Read `master.md` and the phase plan before editing. Apply targeted edits; do not re-plan from scratch when one section is enough.

### Phase-local changes

- Update only the affected sections: objective, traceability, scope, entry conditions, steps, acceptance criteria, test plan, or risks.
- Keep every phase acceptance criterion traced to a master definition-of-done item.
- If an acceptance criterion changes, update the traceability table and any master coverage claim it supports.
- Add new constraints from the user to scope, entry conditions, or risks, so the implementer sees them.
- Bump `Plan version` by 1 for a material change. Leave it unchanged for a typo or formatting-only edit.
- Set `Validated against master version` to the current master version.
- Keep `Status: draft`, `Approved by: pending`, and `Approved at: pending`.
- If the feedback reveals a new discovery, add a master ledger row first, then list it in `Prior discoveries applied`.

### Master-level changes

Edit `master.md` first, then propagate. Follow `references/master-change-propagation.md` for the order, version bump, affected phases, done-phase exceptions, and discovery rows.

### Do not

- re-plan the whole phase to avoid a targeted edit;
- drop or reorder ledger rows without an action;
- weaken acceptance criteria just to make approval easier;
- change user-visible behavior without confirmation;
- edit `master.md` for a phase-local change that does not alter it.

## 4. Record the refinement round

Add a short entry to the phase plan's `Deviations and working notes` section:

```text
**Refinement round <n> — <YYYY-MM-DD>**
- User request: <one line>
- Level: phase-local | master
- Sections changed: <list>
- Versions: plan v<a> -> v<b>; master v<c> -> v<d> | master unchanged
- Product code: none
- Outcome: re-presented for approval
```

Increment `<n>` on every round. Keep the log factual; do not narrate the conversation.

## 5. Revalidate and re-present

Run:

```bash
python3 <plan-orchestrator-dir>/scripts/plan_orchestrator.py check docs/plans/<slug>
python3 <plan-orchestrator-dir>/scripts/plan_orchestrator.py status docs/plans/<slug>
```

Present a delta, not the whole plan again:

```text
Refined P<n> — v<m>
Changed: <what changed, section by section>
Unchanged: <what the user might worry about but did not change>
Acceptance now: <the current A1..An, one line each>
Top risks: <one or two>
Path: <absolute phase plan path>
Approve implementation of phase P<n>?
```

Do not infer approval from silence, "keep going", approval of the master, or approval of an earlier phase. If the user requests more changes, return to step 2 and increment the round.

## 6. Continue after approval

Only after the user explicitly approves:

1. Run the approval command:

   ```bash
   python3 <plan-orchestrator-dir>/scripts/plan_orchestrator.py approve docs/plans/<slug> P<n> --by "<user>"
   ```

2. Verify the plan branch. `git branch --show-current` must match the master `Branch:` field (`plan/<slug>`). If the master has no `Branch:` field and the plan has no implementation commits, create or switch to `plan/<slug>` now. If work is already in progress, report the current branch and ask before rebranching.
3. Set `Status: in_progress` in the phase plan and the master row to `in_progress`.
4. Run `check` again.
5. Spawn one subagent with `plan-orchestrator/references/worker-prompt-template.md`, filled with:
   - absolute paths to `master.md` and the phase plan,
   - the phase ID, plan branch, and scope fence,
   - the approval record (`Approved by`, `Approved at`),
   - the instruction to implement, verify, write the phase closeout, commit on the plan branch, and report the hash.
6. Keep the handle. Do not implement the phase in the coordinator.
7. Report the handoff, then follow the normal `plan-orchestrator` closeout loop: review the worker's files, tests, closeout, and commit; update the master; record the commit. When the final phase is done and all D items are met, follow the plan-orchestrator End of plan gate and offer a draft PR.

If the user pauses or rejects without actionable feedback, keep the phase `draft`, record the round, and ask one focused question. If the user abandons the phase, set it `blocked` and name the reason.

## Guardrails

- **No approval by assumption.** A revised plan is still unapproved.
- **No implementation during refinement.** The coordinator may edit plans and the master only.
- **No silent scope change.** Confirm user-visible behavior before changing it.
- **No stale phase plans.** Any master version bump revalidates every affected phase.
- **No dropped discoveries.** Run `discoveries` for the current phase after ledger changes.
- **No full rewrite for a small change.** Keep the diff reviewable.
- **No version inflation.** Bump versions for semantic changes, not typos.
- **No default-branch implementation.** Work on `plan/<slug>`; do not switch branches silently.
- **No PR without consent.** At plan completion, offer the draft PR; do not push or open it without explicit approval.

## Files

- `references/master-change-propagation.md` — how to change the master and propagate to affected phases.
- `../plan-orchestrator/SKILL.md` — approval gate, phase loop, and closeout.
- `../plan-orchestrator/scripts/plan_orchestrator.py` — `check`, `status`, `approve`, `discoveries`.
- `../plan-orchestrator/references/worker-prompt-template.md` — required subagent prompt.
