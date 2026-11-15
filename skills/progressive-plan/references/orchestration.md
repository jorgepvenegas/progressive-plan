# Orchestrating subagents

Subagent implementation is mandatory for every approved phase. The coordinator handles planning, approval, review, and master updates.

- The coordinator owns `master.md`. A worker owns one phase plan at a time and the implementation files listed in that plan.
- Never let two agents write `master.md`, claim the same phase, or edit the same shared files.
- Spawn the worker only after approval. The prompt must include absolute paths to `master.md` and the phase plan, the phase ID, the scope fence, the approval record (`Approved by`, `Approved at`), and the instruction to implement, verify, write the phase-plan closeout, commit, and report verdict plus discoveries.
- Use `worker-prompt-template.md`. Do not improvise a shorter prompt that omits the approval or the scope fence.
- Use the harness's own delegation API: in prime-agent, `rlm.spawn(prompt, name=...)` returns a handle and the worker replies through `agent_message`; in Claude Code, spawn a Task; in Pi, use `pi-subagents`. Keep whatever handle, task ID, or result channel the harness returns, and recover it after a restart or compaction.
- The worker may update its phase plan but not `master.md`. It reports master-level changes to the coordinator; the coordinator applies them and marks the phase done.
- The worker commits the phase after closeout and reports the short hash. When a draft PR is open, the worker pushes the phase commit immediately before reporting. The coordinator verifies the hash and the push, runs `record-commit`, then runs `close`, commits the metadata, and pushes it.
- Run phases in parallel only when the master marks them independent (`Parallel safe: yes`) and their file sets do not collide.
- Verify a silent worker's output before assuming failure: read the phase plan, changed files, commit, and test output, then decide.
