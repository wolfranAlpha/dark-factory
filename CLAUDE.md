# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

- Virtual environment: `source .venv/bin/activate` (always activate before running commands)
- Install deps: `pip install -e ".[dev]"`
- Environment variables: copy `.env.example` to `.env` for local development

## Commands

- `pytest` — run all tests
- `pytest tests/test_items.py::test_create_item -v` — run a single test
- `pytest --cov=src --cov-report=term-missing` — run tests with coverage
- `ruff check .` — lint
- `ruff format .` — format code
- `mypy src/` — type checking
- `uvicorn src.main:app --reload` — start dev server

Run `ruff check . && mypy src/` before committing.

## Project Structure

- `src/` — application source code
- `tests/` — mirrors src/ structure: `tests/test_routers/`, `tests/test_services/`, etc.

structure to be updated after planning.


## Coding Conventions

- Type hints on all function signatures — parameters and return types
- Use `from __future__ import annotations` at the top of every module
- Pydantic models for all API input/output — never pass raw dicts across boundaries
- Use `pathlib.Path` instead of `os.path`
- f-strings for string formatting (no .format() or % formatting)
- Docstrings on public functions using Google style

```python
def get_item(item_id: int, db: Session) -> Item:
    """Fetch a single item by ID.

    Args:
        item_id: The item's primary key.
        db: Database session.

    Returns:
        The matching Item.

    Raises:
        NotFoundError: If no item matches the ID.
    """
```

## Testing

- Use pytest with fixtures defined in `conftest.py`
- Test database: use an in-memory SQLite or test-specific PostgreSQL database — never touch the dev database
- Use `httpx.AsyncClient` with `app` for API integration tests
- Factory fixtures for creating test data (see `tests/factories.py`)
- Aim for >80% coverage on business logic in `src/services/`

## Database

- SQLAlchemy 2.0 style (use `select()` not `session.query()`)
- All schema changes go through Alembic migrations — never modify tables manually
- New migration: `alembic revision --autogenerate -m "description"`
- Apply migrations: `alembic upgrade head`

## Error Handling

- Use custom exception classes in `src/exceptions.py`
- Routers should not catch generic exceptions — let the global exception handler deal with unexpected errors
- Service layer raises domain exceptions (NotFoundError, ValidationError, etc.)
- Never return error details from unhandled exceptions in production responses

## Git

- Conventional commits: feat:, fix:, chore:
- Run the full check before committing: `ruff check . && ruff format --check . && mypy src/ && pytest`

## Do NOT

- Do not use `import *`
- Do not use `objects.raw()` or raw SQL — use the repository layer
- Do not use `print()` — use the configured `logging` module
- Do not use `*` imports

## Status

Pre-M0: the repository holds only the design. There is no code, build, lint or test setup yet. [PRD.md](PRD.md) is the approved spec and the source of truth; read the relevant section before implementing anything, and update this file once real commands exist.

Planned toolchain (PRD 5.7): Python 3.12, `temporalio`, ruff, mypy, pytest with the Temporal test environment (time skipping), Terraform 1.10+, Docker Compose for local runs, `gh webhook forward` for local webhooks.

## What the system is

A Temporal-based pipeline that turns an owner-labelled GitHub issue into a merged PR: plan → implement in a sandbox (Aider behind a `CodingAgent` interface) → open PR → cross-vendor automated review → CI wait → bounded revisions (max 3 rounds) → human gates → merge. Every LLM call goes through OpenRouter per `routing.yaml` and records model, tokens, cost and duration. Repositories register via the GitHub App plus an entry in the registry file in this repo.

Components (PRD 5.3): ingress Lambda (HMAC check, sender check, start/signal workflow; talks only to Temporal), self-hosted Temporal server, orchestrator worker (all workflows and activities: GitHub client, OpenRouter client, sandbox launcher, telemetry, alerts), per-step sandbox task, RDS Postgres (Temporal persistence + separate `telemetry` DB), S3 for snapshots/diffs/logs.

Workflows (PRD 5.4): `IssueRun(repo, issue)`, `UnauthorisedLabel(event)`, `Reconcile()`. Workflow IDs derive from `repo#issue` so duplicate webhooks cannot start a second run. Every external call is an activity with a timeout and retry policy; human waits have no timeout but send reminders.

## Invariants that code must preserve

These are security and design guarantees, enforced by capabilities rather than prompt wording. Do not weaken them.

- **No GitHub text is ever an instruction** (PRD 5.2). Issue bodies, comments, reviews, code, CI logs and other agents' output reach models only inside the untrusted-data envelope (delimited, with source and author). The issue body is the task description only.
- **Agents hold no credentials.** Sandboxes get a repo snapshot via presigned URL and a scoped OpenRouter key, and return a diff. Only orchestrator activities talk to GitHub, through a narrow client that has no operation for trigger or gate labels.
- **Decisions are code.** Gate transitions, labels and merges are driven only by typed signals: owner labels, deterministically parsed owner commands (`/approve`, `/changes <text>`, `/reject`), and owner PR reviews. Non-owner comments are dropped before any model sees them; the system never reads its own comments back.
- **Reviewer output is structured**: verdict enum (`approve` | `changes` | `reject`) plus findings, schema-validated. The orchestrator reads only the verdict; findings go to the implementer inside the data envelope.
- **Reviewer is never the same vendor as the implementer.**
- **Protected paths** (`infra/`, `.github/`, system prompts, routing policy, registry, gate code) always force `gate:merge` and can never use `gate:none`. `gate:none` and auto-merge are out of MVP scope.
- **Unauthorised trigger/gate labels** (sender not on owner allowlist) are removed, commented on, alerted via SNS and recorded; no run starts or advances.
- **Cost caps:** $5 hard cap per run; the run stops and comments when hit. Raising a cap needs owner approval.

## Infrastructure conventions (PRD 5.6, 9)

- Terraform lives in `infra/`: `infra/bootstrap` (applied once by hand), `infra/modules/*`, `infra/envs/prod`. S3 backend with native lockfile locking.
- GitOps via GitHub Actions with OIDC: PRs run `fmt`, `validate`, `tflint`, read-only `plan`; merges to `main` build/push images tagged with the commit SHA and `apply`.
- Cost traps to avoid: no NAT Gateway, no ALB (use API Gateway HTTP API + Lambda), no VPC interface endpoints, no Temporal Cloud. Set CloudWatch log retention (14 days). Everything must scale to zero via `session-up` / `session-down`.

## Repo conventions

- LF line endings enforced by `.gitattributes` (`* text=auto eol=lf`).
- `docs/ai-workflow.md` (to be created) logs what worked, what failed, model mistakes, and `routing.yaml` changes with reasons.
