# Issue intake and task sizing

Use this reference with the Task intake and sizing section in `SKILL.md`.

## Source recipes

### GitHub

```bash
gh issue view <number> --comments
gh issue view <url> --comments
gh pr view <number> --comments
```

If `gh` is unavailable or unauthenticated, ask the user to paste the issue body and comments. Do not infer requirements from the title.

### Linear, Jira, Notion, and other MCP-connected trackers

Use the MCP tools configured in your agent:

- prime-agent: discover connections with `mcp.list_connections()`, search with `mcp.search_tools(...)`, inspect a schema with `mcp.describe_tool(...)`, and read with `mcp.call_tool(...)`.
- Claude Code and Pi: use the MCP server tools exposed by the session. List or search the available tools if your client provides discovery.

Read the issue, comments, and linked documents. If there is no connection, ask the user to paste the issue or export it. Do not guess field names.

### Local files, URLs, and pasted text

Read the file directly, or ask the user to paste the text. If a URL is not readable through a connector, ask for a paste or an export. Do not summarize from a search result.

## Extraction checklist

Record each item; write `unknown` when the source does not say:

- Problem: what is broken or missing, and for whom.
- Desired outcome: what the user can do or see afterward.
- Acceptance: how the outcome will be checked.
- Constraints: compatibility, data, time, files, dependencies, priority.
- Non-goals: what is explicitly excluded.
- Affected areas: screens, endpoints, schemas, jobs, docs.
- Related work: linked issues, PRs, designs, prior attempts.
- Unknowns: missing decisions that change scope, behavior, acceptance, or risk.

## Repository inspection

Before asking gap questions, check:

- `AGENTS.md`, `CLAUDE.md`, and `README.md`.
- The current `master.md`, phase plans, and discovery ledger.
- The code and tests that the issue would change.
- Recent git history and the current branch.
- Existing behavior, not just the issue's description of it.

State what you verified. Never invent a path, symbol, flag, or behavior.

## Gap questions

Ask only what changes a decision. Format each question with options and a default:

```text
1. <decision> — A: <option> (recommended), B: <option>, C: <option>.
```

Ask at most three to five questions per round. Group related decisions. If the user delegates a choice, record the default and continue.

If the issue has no acceptance criteria, propose two or three and ask the user to confirm them. If the issue is too vague to size, stop and ask for the missing decision.

## Sizing examples

| Example | Size | Why |
|---|---|---|
| Fix a typo in the README | Small | One file, one verification (read it), no behavior change |
| Add a filter to one list endpoint and its UI | Medium | Several files, API + UI + tests, one subsystem |
| Add import support for a second bank format | Large | Parser, schema, API, UI, fixtures, tests, docs, migration risk |

Small tasks still use the approval, subagent, and commit gates. The plan is shorter, not absent.

## Scoping brief

Paste this into the master's intake note or the phase plan:

```text
Source:
Problem:
Outcome:
Acceptance:
Constraints:
Non-goals:
Affected:
Unknowns:
Size:
Plan shape:
```

Keep the brief to a few lines for a small task. Link to the issue instead of copying the whole thread.

## Escalation

- A small task that grows past three files or changes an API/schema: stop and expand the plan or split it.
- An issue that hides several outcomes: propose phases and ask the user to confirm the split.
- A requirement that changes the user-visible contract: stop and ask before planning implementation.
- A source that keeps changing: re-read it, record a discovery, and update the plan before continuing.
