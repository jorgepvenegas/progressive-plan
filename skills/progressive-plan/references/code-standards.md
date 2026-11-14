# Code standards

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
- `approve` requires a `Code standards check` section with checklist items. `close` requires every item checked.
