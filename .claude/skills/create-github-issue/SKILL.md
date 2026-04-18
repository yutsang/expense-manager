---
name: create-github-issue
description: Create a well-defined GitHub issue through collaborative conversation, then hand off to the resolve agent via a GitHub label
---

# Create GitHub Issue

## Goal

Create issues that an AI coding agent can pick up and implement without needing to ask clarifying questions. Focus on **what** needs to be done and **why**, not **how** to implement it.

After creating the issue, apply the label `agent-ready` so the resolve agent can detect and pick it up automatically.

## Principles

- **Describe intent, not implementation** - Let the implementing agent figure out which files to modify
- **Be specific about outcomes** - Vague requirements lead to misaligned implementations
- **Define boundaries clearly** - What's in scope matters as much as what's out of scope
- **Keep issues small** - If it has >3 acceptance criteria, it should probably be split

## Workflow

1. **Understand what the user wants** - Ask clarifying questions about the problem, desired behavior, and priority
    - If the issue is a bug:
        - Ask about the steps to reproduce.
        - Perform a root cause analysis by searching relevant code paths, recent commits, and error patterns.
2. **Draft the issue** - Write it up using the template below
3. **Review with user** - Present the draft and adjust based on feedback
4. **Create in GitHub** - Use the `gh` CLI to create the issue, then apply the `agent-ready` label

## Issue Template

```markdown
## Summary
[1-2 sentences: what this accomplishes and why it matters]

## Current vs Expected Behavior
**Current:** [What happens now, or "N/A" for new features]
**Expected:** [What should happen after this is implemented]

## Acceptance Criteria
- [ ] [Specific, testable outcome 1]
- [ ] [Specific, testable outcome 2]
- [ ] [Specific, testable outcome 3 - max 3, split if more needed]

## Scope
**In scope:** [What this issue covers]
**Out of scope:** [What this issue explicitly does NOT cover]

## Additional Context
[Optional: logs, screenshots, error messages, links to designs, related issues, or hints about existing patterns to follow - only include if genuinely helpful]
```

### Issue-Specific Template Sections (REQUIRED)

#### Bugs

```markdown
## Reproduction Steps
1. [Specific step 1]
2. [Specific step 2]
3. [Specific step 3]

## Root Cause Analysis

### Evidence Gathered
[Summarize what was found in logs, code review, git history]

### Possible Root Causes
1. **[Most likely cause]** - [Evidence supporting this]
2. **[Alternative cause]** - [Evidence supporting this]

### Relevant Code Paths
- [File/function involved]
- [File/function involved]
```

## Writing Tips

**Titles** should complete "This issue will...":
- Good: "Add Google OAuth login to signup flow"
- Bad: "Google login" or "Auth improvements"

**Acceptance criteria** should be pass/fail testable:
- Good: "User sees error message when email is already registered"
- Bad: "Handle duplicate emails gracefully"

**Scope boundaries** prevent misunderstandings:
- Good: "In scope: Add login button. Out of scope: Forgot password flow"
- Bad: Omitting the section entirely

**Reproduction steps** must be specific and repeatable:
- Good: "1. Log in as admin 2. Navigate to /settings 3. Click 'Save' without changes"
- Bad: "Sometimes the settings page doesn't work"

## Priority & Labels

**Priority** (ask user if unclear):
- **P0**: Production broken, security issue
- **P1**: Blocking other work, significant user impact
- **P2**: Normal feature work (default)
- **P3**: Nice-to-have, can wait

**Type labels**: `feature` | `improvement` | `bug`

**Agent handoff label**: Always apply `agent-ready` after issue creation — this signals the resolve agent to pick it up.

## Creating the Issue

Use `gh issue create` with the body from the template above:

```bash
gh issue create \
  --title "..." \
  --body "$(cat <<'EOF'
[issue body here]
EOF
)" \
  --label "bug,P2,agent-ready"   # adjust labels to match issue type and priority
```

After creation, confirm the issue URL and number to the user.
