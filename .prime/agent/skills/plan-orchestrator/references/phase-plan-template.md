# Phase {{PHASE_ID}} — {{PHASE_NAME}}

- Plan ID: `{{SLUG}}`
- Phase: {{PHASE_ID}}
- Plan version: 1
- Validated against master version: {{MASTER_VERSION}}
- Status: draft
- Approved by: pending
- Approved at: pending
- Commit: pending
- Implementation mode: subagent
- Implemented by: pending
- Implemented at: pending
- Exception approved by: none
- Exception reason: none
- Depends on: {{DEPENDS_ON}}
- Written: {{DATE}}
- Master plan: [master.md](../../master.md)

> Read `master.md` first. Every phase acceptance criterion must trace to a master definition-of-done item.

## 1. Phase objective

<What this phase delivers and how it moves the master objective forward. One paragraph.>

## 2. Master traceability

| Master item | How this phase advances it | Phase criterion |
|---|---|---|
| D1 | <contribution> | A1 |

## Prior discoveries applied

| Ledger | Discovery | Effect on this phase |
|---|---|---|
| <L-id or None> | <discovery from the master ledger> | <how it changes a step or acceptance criterion> |

Write `None` with a one-line reason when no ledger row affects this phase.

## 3. Scope

In scope:
- <change this phase delivers>

Out of scope:
- <adjacent work deferred to another phase or excluded>

## 4. Entry conditions

- [ ] <state that must be true before the first edit> — verify: `<command or check>`
- [ ] Phase plan revalidated against current master version
- [ ] User approved this phase plan — verify: `Approved by` is set and status is `ready`

## 5. Steps

### S1 — <imperative title>

- Depends on: none
- Files:
  - `path/to/file` (modify) — <symbol or area>
  - `path/to/new_file` (create) — <purpose>
- Change: <precise change; outcomes and interfaces, not local mechanics>
- Acceptance:
  - [ ] <falsifiable result>
- Verification: `<command>` — expected: <condition or exact output>
- Rollback: <how to undo this step alone>

## 6. Phase acceptance criteria

- [ ] A1 — <observable result> — verify: `<command or observation>`
- [ ] A2 — <observable result> — verify: `<command or observation>`

## 7. Risks and unknowns

| Risk | Likelihood | Impact | Mitigation or check |
|---|---|---|---|

## 8. Deviations and working notes

Append during implementation. One line per deviation: date, step, what changed, why, approval if needed.

## 9. Closeout

Fill at the end of every implementation session. Do not mark the phase done until this section is complete and the master is updated.

- Date:
- Session:
- Verdict: pending
- Steps complete:
- Verification run:

| Criterion | Verdict | Evidence |
|---|---|---|
| A1 | met / partial / not met / deferred | `<command>` — <result> |
| D1 (master) | met / partial / not met / deferred | `<command>` — <result> |

**Discoveries no earlier plan predicted:**

| ID | Discovery | Type | Applies to | Action written |
|---|---|---|---|---|

**Master updates written:** <version bump, ledger rows, phase map changes, or none>
**Next-phase updates written:** <phase ID, plan version, sections changed, or none>
**Remaining work and handoff:** <what the next session must do first>
