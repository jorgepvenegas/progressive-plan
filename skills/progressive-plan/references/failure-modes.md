# Failure modes to avoid

## Planning

- **Plan theater** — phases with no observable exit; the project can never be declared done.
- **Big-design-up-front** — writing every sub-plan before the first phase. Later plans are fiction.
- **Empty approval** — approving a phase plan that still contains template placeholders. `approve` must run content validation.
- **Outline mismatch** — treating a `planned` row with no plan as if it were ready, or requiring a plan before the phase starts. Use `add-phase --outline` and `write-plan`.
- **Silent replan** — rewriting the master during implementation to match what was built instead of recording the discovery and its cause.
- **Discovery dump** — listing observations without a type, action, or owner.
- **Discovery loss** — writing a phase plan without the ledger rows that affect it, or leaving `Affects` blank.

## Execution

- **Unauthorized start** — implementing a phase whose plan the user has not explicitly approved.
- **Approval by assumption** — treating silence, a prior "keep going", or approval of an earlier phase as approval of the current phase.
- **Coordinator implementation** — writing product code in the coordinator instead of delegating an approved phase. Exceptions need explicit user approval and a recorded reason.
- **Phase drift** — doing the next phase's work early because it is convenient.
- **Scope creep** — accepting unrelated work or opportunistic fixes into an approved phase.
- **New-work absorption** — doing a later phase's work inside the current phase instead of adding a new phase and planning it separately.
- **Malformed rows** — a phase or ledger row with the wrong column count. The scripts flag these instead of skipping them.

## Closeout

- **Coverage by assertion** — marking a criterion met without a command, test, or file evidence.
- **Optimistic closeout** — `addressed` with deferred criteria and no user approval.
- **Open standards check** — marking a phase done while a code-standards checkbox is open.
- **Uncommitted closeout** — marking a phase done with no commit, no recorded hash, or no `Implemented by`/`Implemented at`.
- **Stale plans** — a master version bump that leaves a `ready` or `in_progress` phase validated against an older version.
- **Stale resume brief** — a brief that names a different current phase than the phase map.
- **Branch mismatch** — implementing on the default branch while the master records `plan/<slug>`.
- **PR without consent** — pushing a branch or opening a draft PR before the user explicitly agrees.

## Code quality

- **Speculative abstraction** — a helper, layer, option, or dependency built for a caller that does not exist.
- **Copy-paste duplication** — a second copy of logic where the existing helper or a small extraction fits.
- **Comment narration** — comments that repeat what the code says or record the change instead of explaining why.
- **Test theater** — tautological tests that restate the implementation, repeat another test's assertion, or pass when the behavior breaks.
