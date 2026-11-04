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
Do not start if the phase plan is not approved or the approval fields are missing. Report the missing approval instead.

Scope fence:
- Implement exactly the steps in the phase plan, in order.
- Change only the files listed in each step. Log any extra file change as a deviation in the phase plan.
- Do not edit master.md; the coordinator owns it.
- Do not change public interfaces, schemas, or acceptance criteria without reporting the gap first.
- Do not refactor, rename, reformat, upgrade dependencies, or fix unrelated issues.
- Do not weaken or delete tests or acceptance criteria.

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
   - discoveries no earlier plan predicted, each with a type
   - commit hash
   - remaining work or blocker

If a step is wrong or impossible, stop and report the exact gap with the evidence. Do not invent a new design.
```

The coordinator must verify the worker's files, tests, closeout, and commit before marking the phase done. A silent worker is not a failed worker; inspect the output first.
