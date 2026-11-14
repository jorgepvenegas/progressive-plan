---
name: refine-phase
description: Refine an unapproved progressive-plan phase plan after rejection or requested changes, then re-present it for approval. Use when the user says no to a plan or wants its scope, steps, acceptance, files, or risks revised.
---

# Refine Phase

Use this skill when a `progressive-plan` phase plan is written but the user does not approve it. The goal is to turn the feedback into a precise, revalidated plan, obtain explicit approval, and then hand the approved phase to a subagent.

Do not implement product code during refinement. The approval gate stays closed until the user explicitly approves the revised plan.

## Quick start

Run these from the repository root:

```bash
python3 <progressive-plan-dir>/scripts/progressive_plan.py status docs/plans/<slug>
python3 <progressive-plan-dir>/scripts/progressive_plan.py check docs/plans/<slug>
```

Then read the current phase plan and `master.md` fresh. `<progressive-plan-dir>` is the sibling directory of this skill.

## 1. Protect the approval gate

- Keep the phase `draft` and the master row `planned`.
- Do not edit product code, tests, or configuration.
- Do not set `in_progress`.
- Do not spawn a worker.

If the phase was already marked `ready` or has approval fields, reset it with:

```bash
python3 <progressive-plan-dir>/scripts/progressive_plan.py reopen docs/plans/<slug> P<n>
```

`reopen` sets the phase `draft`, the master row `planned`, clears approval and implementation fields, and bumps `Plan version`.

If the phase is already `in_progress` or `done`, this is no longer a plan refinement. Stop and handle it as a scope change: use the master amendment and discovery rules in `references/master-change-propagation.md`. If the plan itself is wrong, `reopen` is still the first step; then treat the change as a new plan revision, not a rewrite of completed evidence.

## 2. Understand the requested change

Restate the request as a concrete plan change. Ask only questions that change scope, acceptance, behavior, or risk. Give two or three options and a recommended default.

Classify the feedback:

| Level | Examples | Where it lands |
|---|---|---|
| Phase-local | steps, file list, acceptance wording, verification, code standards check, risks, step order, rollback | the phase plan |
| Master | objective, goal flow, definition of done, non-goals, code standards, phase map, cross-phase decision | `master.md`, then every affected phase plan |
| Contract | user-visible feature behavior, CSV format, API shape, data model | stop and confirm with the user before editing |

If the feedback points out a defect in the current plan, record it as a plan defect. Do not silently rewrite the history that produced it.

## 3. Rewrite the plan

Read `master.md` and the phase plan before editing. Apply targeted edits; do not re-plan from scratch when one section is enough.

If `check` fails because the master predates a required section such as `Goal flow`, add it from `../progressive-plan/references/master-template.md` first, bump the master version, and revalidate affected phases. This is a schema repair, not a refinement of the current phase.

### Phase-local changes

- Update only the affected sections: objective, traceability, scope, entry conditions, steps, acceptance criteria, code standards check, or risks.
- Keep every phase acceptance criterion traced to a master definition-of-done item.
- If an acceptance criterion changes, update the traceability table and any master coverage claim it supports.
- Add new constraints from the user to scope, entry conditions, or risks, so the implementer sees them.
- Bump `Plan version` by 1 for a material change. Leave it unchanged for a typo or formatting-only edit.
- Set `Validated against master version` to the current master version.
- Keep `Status: draft`, `Approved by: pending`, and `Approved at: pending`.
- If the feedback reveals a new discovery, append it with `add-discovery` first, then list it in `Prior discoveries applied`.

### Master-level changes

Edit `master.md` first, then propagate. Follow `references/master-change-propagation.md` for the order, version bump, affected phases, done-phase exceptions, and discovery rows.

### Do not

- re-plan the whole phase to avoid a targeted edit;
- drop or reorder ledger rows without an action;
- weaken acceptance criteria just to make approval easier;
- change user-visible behavior without confirmation;
- add a new outcome or feature as extra steps in the current phase; new outcomes become new phases;
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
python3 <progressive-plan-dir>/scripts/progressive_plan.py check docs/plans/<slug>
python3 <progressive-plan-dir>/scripts/progressive_plan.py status docs/plans/<slug>
```

`check` now validates content, not just headings: no template placeholders, at least one step and acceptance criterion, traceability for every criterion, and every affecting discovery. Fix every error before re-presenting.

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
   python3 <progressive-plan-dir>/scripts/progressive_plan.py approve docs/plans/<slug> P<n> --by "<user>"
   ```

2. Verify the plan branch. `git branch --show-current` must match the master `Branch:` field (`plan/<slug>`). If the master has no `Branch:` field and the plan has no implementation commits, create or switch to `plan/<slug>` now. If work is already in progress, report the current branch and ask before rebranching.
3. Set `Status: in_progress` in the phase plan and the master row to `in_progress`.
4. Run `check` again.
5. Spawn one subagent with your harness's delegation mechanism and `../progressive-plan/references/worker-prompt-template.md`, filled with:
   - absolute paths to `master.md` and the phase plan,
   - the phase ID, plan branch, and scope fence,
   - the approval record (`Approved by`, `Approved at`),
   - the instruction to implement, verify, write the phase closeout, commit on the plan branch, and report the hash.
6. Keep the handle. Do not implement the phase in the coordinator.
7. Report the handoff, then follow the normal `progressive-plan` closeout loop: review the worker's files, tests, closeout, and commit; run `scope`; record the commit with `record-commit --by`; close the phase with `close`. When the final phase is done and all D items are met, run `report` and offer a draft PR.

If the user pauses or rejects without actionable feedback, keep the phase `draft`, record the round, and ask one focused question. If the user abandons the phase, set it `blocked` and name the reason.

## Guardrails

- **No approval by assumption.** A revised plan is still unapproved.
- **No implementation during refinement.** The coordinator may edit plans and the master only.
- **No silent scope change.** Confirm user-visible behavior before changing it.
- **No stale phase plans.** Any master version bump revalidates every affected phase.
- **No dropped discoveries.** Run `discoveries` for the current phase after ledger changes.
- **No full rewrite for a small change.** Keep the diff reviewable.
- **No version inflation.** Bump versions for semantic changes, not typos.
- **No weakened quality gates.** Do not drop standards checks, tests, or acceptance criteria to make a plan approvable.

The shared approval, delegation, closeout, commit, and PR gates are in `../progressive-plan/references/gates.md`.

## Files

- `references/master-change-propagation.md` — how to change the master and propagate to affected phases.
- `../progressive-plan/SKILL.md` — the full loop.
- `../progressive-plan/references/gates.md` — shared approval, delegation, closeout, commit, and PR gates.
- `../progressive-plan/scripts/progressive_plan.py` — `check`, `status`, `approve`, `reopen`, `record-commit`, `close`, `add-discovery`, `scope`, `report`.
- `../progressive-plan/references/worker-prompt-template.md` — required subagent prompt.
