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
- Parallel safe: no
- Depends on: {{DEPENDS_ON}}
- Written: {{DATE}}
- Master plan: [master.md](../../master.md)

Keep this phase to one outcome. Every criterion must trace to a master D item.

## 1. Phase objective

<What this phase delivers, in one or two sentences.>

## 2. Master traceability

| Master item | How this phase advances it | Phase criterion |
|---|---|---|
| D1 | <contribution> | A1 |

## Prior discoveries applied

| Ledger | Discovery | Effect on this phase |
|---|---|---|
| <L-id or None> | <discovery, or none> | <effect, or no ledger rows affect this phase> |

## 3. Scope

In scope:
- <change this phase delivers>

Out of scope:
- <work excluded or deferred>

## 4. Entry conditions

- [ ] <state that must be true before the first edit> — verify: `<command or check>`
- [x] Phase plan revalidated against current master version
- [x] User approved this phase plan — verify: `Approved by` is set

## 5. Steps

### S1 — <imperative title>

- Depends on: none
- Files:
  - `path/to/file` (modify) — <symbol or area>
- Change: <precise change>
- Acceptance:
  - [ ] <falsifiable result>
- Verification: `<command>` — expected: <condition>
- Rollback: <how to undo this step>

## 6. Phase acceptance criteria

- [ ] A1 — <observable result> — verify: `<command or observation>`

## 7. Code standards check

- [ ] The diff is the smallest change that meets the acceptance criteria
- [ ] Existing helpers are reused where they fit
- [ ] Names and structure state intent
- [ ] Tests assert observable behavior
- [ ] Master standards commands pass: `<format>`, `<lint>`, `<type check>`, `<tests>`

## 8. Risks and unknowns

| Risk | Likelihood | Impact | Mitigation or check |
|---|---|---|---|
| <risk> | low | low | <check> |

## 9. Deviations and working notes

None.

## 10. Closeout

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

**Master updates written:** <version bump, ledger rows, or none>
**Next-phase updates written:** <phase ID and sections, or none>
**Remaining work and handoff:** <what the next session must do first>
