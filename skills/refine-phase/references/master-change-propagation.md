# Master change propagation

Use this reference when refinement feedback changes the master plan, not just one phase plan.

## Decide whether the master must change

The master changes when the feedback changes any of these:

- the objective, the goal flow, or the definition of done;
- a non-goal;
- the phase map, phase order, or phase dependencies;
- a cross-phase decision;
- a constraint that more than one phase must honor.

If the feedback only changes a step, file list, acceptance wording, or risk inside one phase, keep the master unchanged and edit the phase plan.

## Order of edits

1. Edit `master.md`.
2. Record the change with `add-discovery` or `add-decision`; both bump `Master version` and validate `Affects`.
3. Update the phase map and, when relevant, the closeout history.
4. Revalidate every affected phase plan.
5. Run `progressive_plan.py check`.
6. Re-present the current phase for approval.

Doing the phase plans before the master leaves them validated against the wrong version.

## Revalidate affected phases

For each phase whose plan is affected:

- Update `Validated against master version` to the new master version.
- Bump `Plan version` by 1.
- Apply the changed master item in `Master traceability`.
- Add the ledger row to `Prior discoveries applied` and adjust the step or acceptance it changes.
- Run `progressive_plan.py discoveries <plan-dir> <phase>` and confirm every returned row is present.
- If the change is too large for a targeted edit, set the phase `needs_replan` and state what must be rewritten.
- Never leave a `ready` phase validated against an older master version.

## New phase from feedback

If the feedback adds a separate outcome, add a phase instead of expanding the current one:

- Add a phase-map row with `add-phase <plan-dir> "<name>" --depends <deps> --outcome "<outcome>" --outline`; it bumps `Master version` and leaves the plan unwritten.
- Do not add the new outcome as steps in the current phase.
- Write the new phase plan with `write-plan` after the current phase closes, then stop at its approval gate. In yolo mode, write and auto-approve it and continue.

## Status rules

| Affected phase status | Action |
|---|---|
| `planned` or `draft` | Update the plan and keep it unapproved. |
| `ready` | Run `reopen <plan-dir> P<n>`, update the plan, then re-request approval; in yolo mode, revalidate and run `approve --yolo`. |
| `in_progress` | Stop implementation, record the change, update the plan, and report the interruption to the user before continuing. In yolo mode, a plan-local change may continue after the amendment; a contract change stops the run. |
| `done` | Do not rewrite its closeout evidence. Prefer a new phase or an added step. If its result is invalid, set the master row to `needs_replan`, keep the closeout, and write a new plan version for the corrective work. |
| `blocked` | Update the blocker or plan only after the blocking condition is resolved or the user changes direction. |

## Discovery row

Every master-level change produces a ledger row unless an existing row already covers it.

```text
| <ID> | <date> | <phase> | <Affects> | <what changed and why> | <type> | <action taken> | <status> |
```

Types: `note`, `phase-amend`, `next-phase-amend`, `master-amend`, `new-phase`, `scope-change`, `plan-defect`.
Statuses: `open`, `applied`, `superseded`, `wontfix`.

For a user-requested scope change, use `scope-change` and confirm the user-visible contract before editing. For a defect in an earlier plan, use `plan-defect` and name the missed fact.

## Done phases and history

Completed phases are evidence. Do not edit their acceptance results to fit a new plan.

- If the new work is additive, add a phase or extend the phase that owns it.
- If the change invalidates a done phase's result, record the discovery, mark the master row `needs_replan`, and plan the corrective work.
- Keep the original closeout and commit hash visible.

## Final check

Before re-presenting:

- `Master version` is higher than before.
- Every affected phase names the new master version.
- Every ledger row has `Affects`, an action, and a status.
- `progressive_plan.py check --strict` passes.
- The current phase is still `draft` and unapproved until the user says otherwise, unless the master records `Mode: yolo`; then auto-approve it with `--yolo`.
