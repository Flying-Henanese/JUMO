# Harness Guide

`.harness/` is the project-local operating manual for coding agents. It should help
an agent understand how to work in this repository before it edits code, docs,
configuration, or deployment files.

## Directory Roles

- `context/`: Stable project facts, architecture maps, runtime assumptions, and service boundaries.
- `checklists/`: Reusable checks that should be applied before edits, before completion, and for riskier areas.
- `designs/`: Design notes for architecture or behavior changes that need durable rationale.
- `plans/`: Implementation plans derived from accepted designs or concrete tasks.
- `prompts/`: Prompt templates for delegating recurring work to Codex or another agent.
- `runs/`: Dated execution notes for important investigations, migrations, or verification runs.

## How Agents Should Use This

1. Start from `AGENTS.md` at the repository root.
2. Read the files under `context/` that match the task.
3. Apply the relevant checklist before editing.
4. For substantial changes, create or update a design and plan before changing code.
5. Record durable run evidence only when it will help future agents avoid rediscovery.

## Source Of Truth

The current code, `pyproject.toml`, Docker Compose files, and tests override older
README content. When documentation and code disagree, inspect the code path and
update the documentation if the task requires it.

