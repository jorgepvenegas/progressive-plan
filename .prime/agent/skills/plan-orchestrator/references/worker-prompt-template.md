# Worker prompt template

Fill every angle-bracket field. Send the result as the `prompt` argument to `rlm.spawn`. Do not shorten it by reference; the worker may not have the coordinator's context.

```text
You are implementing phase <Pn> — <phase name> for <project>.

Read these files first, in this order:
1. <absolute path to master.md>
2. <absolute path to phases/NN-<name>/plan.md>
3. <absolute path to AGENTS.md / CLAUDE.md / README, if present>

Approval record:
- Approved by: <user>
- Approved at: <YYYY-MM-DD>
- Phase status: ready
- Branch: plan/<slug>
Do not start if the phase plan is not approved or the approval fields are missing. Report the missing approval instead. Work and commit on the branch above; do not create, switch, or merge branches.

Scope fence:
- Implement exactly the steps in the phase plan, in order.
- Change only the files listed in each step. If another file is needed, stop and report it; the coordinator must amend the plan first. Do not add out-of-scope files.
- Do not edit master.md; the coordinator owns it.
- Do not change public interfaces, schemas, or acceptance criteria without reporting the gap first.
- Do not refactor, rename, reformat, upgrade dependencies, or fix unrelated issues.
- Do not weaken or delete tests or acceptance criteria.
- If you discover work that is not required to meet this phase's acceptance criteria, report it as a discovery and continue the approved steps; do not implement it, do not add files for it, and do not count it as done work in this phase. If it blocks this phase, stop and report the gap.

Work:
1. Read the master plan, phase plan, and prior discoveries applied table.
2. Implement one step at a time. Run that step's verification and record the command and a one-line result in the phase plan.
3. Run the phase verification and the relevant full test suite.
4. Fill the phase plan's Closeout section: verdict, steps complete, verification run, coverage table, discoveries, and remaining work.
5. Commit the phase:
   git add -A
   git commit -m "P<n>: <phase name>"
6. Do not run record-commit or edit master.md; report the short hash to the coordinator.
7. Reply with `await agent_message.send(message, receiver_role='parent')` containing:
   - verdict: addressed / partial / blocked
   - phase criteria met and evidence
   - master DoD items advanced (partial is expected until the final phase)
   - discoveries no earlier plan predicted, each with a type: `phase-amend` (required for this phase), `next-phase-amend`, `new-phase` (separate outcome), or `note`
   - commit hash
   - remaining work or blocker

If a step is wrong or impossible, stop and report the exact gap with the evidence. Do not invent a new design. If the gap is a separate outcome or feature, report it as a `new-phase` discovery and continue the approved steps if they are still valid; do not implement it in this phase.
```

The coordinator must verify the worker's files, tests, closeout, and commit before marking the phase done. A silent worker is not a failed worker; inspect the output first.
