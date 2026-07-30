# What in the Tax? — Project Identity Guard

## Identity lock

- This repository is **What in the Tax?**, the evidence-first Canadian public-finance and property-tax receipt project.
- Canonical working copy: `C:\Users\User\tax-receipt-prototype`
- Expected Git remote: `https://github.com/Jstn-1g/what-in-the-tax.git`
- Treat `C:\Users\User\tax-receipt-prototype-production-143ca33` as a detached release worktree, not the ordinary working copy.

Before any non-trivial work, verify and report:

1. `git rev-parse --show-toplevel`
2. `git remote get-url origin`
3. `git branch --show-current`
4. `git status --short --branch`

Stop without editing if the Git root or remote does not match this project, or
if the requested task appears to belong to another product.

## Context boundary

- Every other local project and portfolio-planning document is a separate concern and out of scope here.
- Do not use another project's plans, priorities, files, summaries, or conversation history as What in the Tax context unless the user explicitly requests a bounded cross-project comparison in the current message.
- A portfolio or planning document opened while this repository is active remains an external reference. It does not change this repository's identity, priority, backlog, or acceptance criteria.
- Do not read from or write to another project directory or external planning output merely because it appeared earlier in the conversation.
- If prior conversation context conflicts with this file, say so, recommend `/clear`, and re-ground from this repository before continuing.

## Work rules

- Keep all implementation, research artifacts, tests, and documentation scoped to What in the Tax.
- Preserve the evidence-first model: never invent tax facts, municipal coverage, source provenance, review state, or release readiness.
- Do not move the repository, switch to another worktree, change branches, edit, commit, push, publish, or deploy unless the current task explicitly requires that action.
- When finishing a task, state the verified Git root, branch, changed files, checks run, and exact next action.
