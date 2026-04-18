---
name: resolve-github-issue-tdd
description: Resolve a GitHub issue end-to-end using Test Driven Development. Picks up issues labelled agent-ready, implements them, and opens a PR for review.
---

# Resolve GitHub Issue (TDD)

This workflow resolves a GitHub issue end-to-end. It is designed to be flexible and adaptable to different types of issues. Use your understanding of the issue, project context, and available tools to adjust the workflow as needed.

The resolve agent is triggered by issues carrying the `agent-ready` label — the same label applied by the **create-github-issue** skill after the user approves the draft.

Start by creating a TODO list to track all steps below.

## Steps

### 1. Fetch the issue

Use the `gh` CLI to read the issue details:

```bash
gh issue view <issue-number> --json title,body,labels,assignees,milestone
```

If no issue number is supplied, list open issues with the `agent-ready` label and pick the oldest unassigned one:

```bash
gh issue list --label "agent-ready" --state open --json number,title,createdAt | jq 'sort_by(.createdAt)'
```

Self-assign the issue so other agents don't pick it up concurrently:

```bash
gh issue edit <issue-number> --add-assignee "@me"
```

### 2. Ensure main is up to date

Work directly on `main`:

```bash
git checkout main && git pull
```

### 3. Investigate & plan (Plan agent)

Spawn a **Plan agent** to investigate the issue and generate a Test-Driven Development implementation plan.

Instruct the agent to:

- Read the full issue body (title, summary, acceptance criteria, scope).
- Search the codebase for relevant files, functions, and patterns.
- Review related recent commits: `git log --oneline -20`.
- Identify which tests need to be written first (TDD: red → green → refactor).
- Produce a step-by-step plan: failing tests → implementation → passing tests.

The plan must respect the project rules in `CLAUDE.md` (financial precision, audit trail, tenant isolation, no floats for money, etc.).

### 4. Implement (General agent)

Spawn a **General agent** to execute the plan using TDD:

1. Write failing tests for each acceptance criterion first.
2. Implement the minimum code to make tests pass.
3. Refactor while keeping tests green.
4. Run the full test suite and ensure it passes:
   ```bash
   make test
   make lint
   make typecheck
   ```
5. Apply any database migrations and verify they apply cleanly:
   ```bash
   make migrate
   alembic check
   ```
6. Confirm `make build` (or equivalent) completes without errors.

The agent must not modify code outside the scope defined in the issue.

### 5. Commit & push directly to main

Commit changes with a Conventional Commit message referencing the issue and push straight to `main`:

```bash
git add <specific files>
git commit -m "feat(<scope>): <description>

Closes #<issue-number>

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git push origin main
```

Remove the `agent-ready` label and close the issue (it is resolved by the direct push — no PR needed):

```bash
gh issue edit <issue-number> --remove-label "agent-ready"
gh issue close <issue-number>
```

### 6. Update the issue

Add a comment summarising the implementation before closing:

```bash
gh issue comment <issue-number> --body "..."
```

### 7. Monitor CI on main (background task)

Poll until the latest CI run on `main` completes:

```bash
gh run list --branch main --limit 1
gh run view <run-id>
```

If any check fails (ignore Vercel permission errors), spawn a **General agent** to:

- Read the failed output: `gh run view <run-id> --log-failed`
- Fix the failures.
- Commit and push the fix to `main`.

### 8. Clean up

- Kill any background polling tasks.
- Confirm the commit SHA and that the issue is closed.
