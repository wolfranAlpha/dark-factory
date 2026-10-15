# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

M0 (foundations) in progress. [PRD.md](PRD.md) is the approved spec and the source of truth; [docs/plan.md](docs/plan.md) gives the build order, the step specs and the design decisions (D-numbers). Read the relevant section before implementing anything.

Toolchain (PRD 5.7): Python 3.14 (plan D14), `temporalio`, `pydantic`, `httpx`, `pyyaml`; ruff, mypy (strict), pytest with `pytest-asyncio`, `respx` and the Temporal test environment (time skipping). Later: Terraform 1.10+, Docker Compose for local runs, `gh webhook forward` for local webhooks.

## Setup

- Create the venv with Python 3.14: `py -3.14 -m venv .venv` (Windows) or `python3.14 -m venv .venv`
- Activate it before running anything: `.venv\Scripts\activate` (Windows) or `source .venv/bin/activate` (Linux/macOS, Git Bash: `source .venv/Scripts/activate`)
- Install from the lockfile: `pip install --require-hashes -r requirements-dev.lock` then `pip install -e . --no-deps`
- Copy `.env.example` to `.env` for local development. `.env` is git-ignored

## Commands

- `pytest` — run all tests
- `pytest tests/test_package.py::test_version_matches_installed_metadata -v` — run a single test
- `ruff check .` — lint
- `ruff format .` — format
- `mypy src/` — type check (strict)
- `uv pip compile pyproject.toml --extra dev --universal --generate-hashes --python-version 3.14 -o requirements-dev.lock` — regenerate the lockfile after changing dependencies in `pyproject.toml` (add `--upgrade` to bump all pins). Commit both files together; CI fails if the lock is stale

Full check, required before every commit (and what CI runs from M0.2):

```
ruff check . && ruff format --check . && mypy src/ && pytest
```

## Project structure

- `src/dark_factory/` — the single import root. Subpackages are added as steps need them (plan D1): `config`, `ingress`, `workflows`, `activities`, `github`, `llm`, `sandbox`, `policy`, `telemetry`, `storage`
- `tests/` — mirrors the package: `tests/test_config/`, `tests/test_workflows/`, etc.
- `docs/plan.md` — development plan; `PRD.md` — requirements

## Coding conventions

- `from __future__ import annotations` at the top of every module (enforced by ruff)
- Type hints on all function signatures; mypy runs in strict mode
- Pydantic models for data that crosses a boundary (workflow and activity inputs/outputs, config files, external APIs) — never raw dicts
- `pathlib.Path`, not `os.path`; f-strings for formatting
- Google-style docstrings on public functions, classes and methods
- No `print()` — use `logging`. No `*` imports
- Telemetry DB (M2): `psycopg` 3 with numbered plain-SQL migration files and a small runner. No ORM, no Alembic (plan D2)
- [Conventional Commits](https://www.conventionalcommits.org/): `<type>: <summary>`, with `!` after the type for breaking changes. PR titles follow the same format. Types:
  - `feat:` — new capability
  - `fix:` — bug fix
  - `docs:` — documentation only
  - `style:` — formatting, no behaviour change
  - `refactor:` — code change that neither fixes a bug nor adds a feature
  - `perf:` — performance improvement
  - `test:` — tests only
  - `build:` — packaging, dependencies, lockfile, Dockerfiles
  - `ci:` — GitHub Actions workflows
  - `chore:` — maintenance that fits none of the above
  - `revert:` — reverts an earlier commit

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
- **In the factory, the reviewer is never the same vendor as the implementer.** (The manual loop has a temporary exception until M0.5; see `docs/ai-workflow.md`.)
- **Protected paths** (`infra/`, `.github/`, system prompts, routing policy, registry, gate code) always force `gate:merge` and can never use `gate:none`. `gate:none` and auto-merge are out of MVP scope.
- **Unauthorised trigger/gate labels** (sender not on owner allowlist) are removed, commented on, alerted via SNS and recorded; no run starts or advances.
- **Cost caps:** $5 hard cap per run; the run stops and comments when hit. Raising a cap needs owner approval.

## Infrastructure conventions (PRD 5.6, 9)

- Terraform lives in `infra/`: `infra/bootstrap` (applied once by hand), `infra/modules/*`, `infra/envs/prod`. S3 backend with native lockfile locking.
- GitOps via GitHub Actions with OIDC: PRs run `fmt`, `validate`, `tflint`, read-only `plan`; merges to `main` build/push images tagged with the commit SHA and `apply`.
- Cost traps to avoid: no NAT Gateway, no ALB (use API Gateway HTTP API + Lambda), no VPC interface endpoints, no Temporal Cloud. Set CloudWatch log retention (14 days). Everything must scale to zero via `session-up` / `session-down`.

## Repo conventions

- LF line endings enforced by `.gitattributes` (`* text=auto eol=lf`).
- Every issue runs through the manual agent loop in [docs/ai-workflow.md](docs/ai-workflow.md) until M1.10: branch `<type>/m<x.y>-<slug>`, PR with `Closes #<n>`, cross-vendor review (until M0.5 is merged, the default is a same-vendor automatic review by a fresh-context subagent, unless the owner asks for cross-vendor; see step 5 and plan D15), owner merges. Each closing PR adds a log entry there (what worked, what failed, model mistakes, `routing.yaml` changes with reasons).
- New issues use the template `.github/ISSUE_TEMPLATE/agent-task.md`. Never apply `agent` to a `manual` issue.
