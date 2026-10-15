# Development plan: Dark Factory

> Source of truth for requirements: [PRD.md](../PRD.md). This file covers **order and slicing**: what gets built when, and what each step delivers.
> Each step is one PR-sized GitHub issue. M0 and M1 are fully specified below and tracked as issues. M2 and M3 are outlined here and get written as full issues at the self-hosting point, because the factory itself will execute them. M4 and M5 stay coarse.

## Self-hosting point

**The factory starts building itself at the end of M1 (step M1.10).** This is earlier than PRD §6, which says M2, and the owner approved the change.

Why it is safe at that point:

- The M1 system reads exactly one piece of GitHub text: the body of an issue that the **owner** labelled `agent`. It never reads comments.
- It holds no label, merge or gate operation. Its GitHub client only reads issues and snapshots, pushes a branch, opens a PR and comments.
- The GitHub App has **no `workflows` permission**, so no agent PR can change CI.
- The owner reviews and merges every PR by hand. Until M2, the owner *is* the reviewer and the merge gate.
- CI on this repo holds no secrets until M3.

What changes after the switch:

- M2 work is written as factory-ready issues and run by labelling them `agent`.
- Anything under `.github/workflows/`, and owner-only setup (GitHub App, AWS bootstrap), stays on the manual loop. These issues carry the `manual` label.

Self-hosting deepens in stages:

| Level | When | What the factory does to itself |
|---|---|---|
| 0 | M0 to M1.9 | Nothing. The manual loop (a coding agent driven by the owner) builds everything |
| 1 | M1.10 | Issue → plan → sandbox → PR. Owner reviews and merges |
| 2 | End of M2 | Plus cross-vendor review, CI-driven revisions, enforced plan and merge gates, telemetry, cost cap |
| 3 | End of M3 | The same, running on AWS. Merges deploy through GitOps |

## Design decisions taken in this plan

These are implementation choices. They are not in the PRD. Each can be challenged in the PR of the step that introduces it.

| # | Decision | Reason |
|---|---|---|
| D1 | Package `src/dark_factory/` with subpackages `config`, `ingress`, `workflows`, `activities`, `github`, `llm`, `sandbox`, `policy`, `telemetry`, `storage`. Tests mirror the layout under `tests/` | One import root. The layout matches the PRD components |
| D2 | Telemetry DB uses `psycopg` 3 with numbered plain-SQL migration files and a small runner. No ORM, FastAPI or Alembic. CLAUDE.md template leftovers are removed in M0.1 | Owner decision: the template sections are leftovers |
| D3 | Ingress is a pure function `handle(headers, body) -> Response`. In prod a Lambda adapter wraps it (M3); locally a small Starlette/uvicorn adapter does | One code path for HMAC, sender and registry checks |
| D4 | Local webhooks use `gh webhook forward`, which creates **repo** webhooks. The ingress must not depend on the App-only `installation` field. The worker resolves the installation per repo through the App API | Prod (App webhooks) and local (repo webhooks) then behave the same |
| D5 | MinIO in Docker Compose stands in for S3. Sandbox I/O always goes through presigned GET/PUT URLs | The sandbox contract is identical locally and on AWS |
| D6 | The sandbox gets a tarball snapshot, makes a baseline git commit and returns a unified diff. The **worker** applies the diff on a fresh shallow clone, commits as the App bot and pushes with the installation token | Agents hold no credentials. Bot-authored commits make the PRD's human-edit-rate metric computable |
| D7 | Every run gets its own OpenRouter key, minted through the provisioning API with `limit` = remaining run budget, and deleted when the run ends (including on failure, through a cleanup activity) | Owner decision. Enforces the per-run cap at the provider too |
| D8 | Workflow ID `issue-run:{owner}/{repo}#{number}`, with ID reuse allowed but a conflicting start rejected while a run is open: a duplicate webhook during a run is a no-op. Labels on **closed** issues are ignored. Re-applying `agent` to an open issue whose run has ended (stopped, failed, PR closed unmerged) starts a fresh run, which force-pushes the same branch and reuses the open PR if one exists | PRD idempotency, plus one recovery path the owner can always use |
| D13 | In M1, if the repo's test command still fails after Aider's own test loop, the PR is opened as a **draft** with the test output summary in the body. The run never merges in M1 | The owner sees the attempt and decides. M2 replaces this with the revision loop |
| D9 | Branch `df/issue-{number}`. PR body links the issue (`Closes #n`) | Predictable and greppable |
| D10 | The LLM base URL is configurable everywhere (orchestrator and sandbox), so tests point at a stub OpenAI-compatible server | Deterministic tests now, zero-cost load test in M4 |
| D11 | Self-hosted deploys after M1.10: merging is followed by `docker compose up -d --build worker`. Workflow code changes must stay replay-safe: CI replays recorded histories, and incompatible changes use `workflow.patched` | The system rewrites the code it runs on. In-flight runs must survive that |
| D12 | GitHub App has no `workflows` permission | Owner decision. CI can never be changed by an agent |
| D14 | The orchestrator (this repo) targets Python 3.14, not 3.12 as PRD 5.7 first said. Target repos and the sandbox image are unaffected and stay on their own versions | Owner decision. 3.14 is the installed interpreter; one version locally and in CI |

## Resolved questions

| # | Question | Decision |
|---|---|---|
| 1 | Merge gate in MVP | **Merge always waits for the owner's PR approval.** With `gate:none` and auto-merge out of MVP scope, the `gate:merge` label has no effect yet. Label-driven merge gating moves to M5, together with `gate:none`. The label still exists and still counts as a gate label for the owner-only check (M2.8). This is a deliberate narrowing of PRD §5.1 for the MVP |
| 2 | Revision budget exhausted | After 3 rounds the run **stops and comments**. Details in M2.6 |
| 3 | Raising the cost cap | Config change only (`registry.yaml`, a protected path, so it needs an owner-reviewed PR). An owner command is in the backlog |
| 4 | Alerts before AWS | A real SNS topic with an email subscription to the owner, from M2 on. Details in M2.8 |

## Backlog (post-MVP, not scheduled)

- **Owner command to raise a run's cost cap** (e.g. `/budget <usd>` on the issue, parsed deterministically like the other owner commands). MVP raises caps by config change only.

---

## M0: Foundations

Exit criteria (PRD §8): CI, Docker Compose with the Temporal dev server, GitHub App created, `routing.yaml` v1, registry file, own issues run through the manual loop.

### M0.1 Python project skeleton and CLAUDE.md cleanup
- **Value:** the repo can be linted, type-checked and tested locally.
- **Scope:** `pyproject.toml` (Python 3.14 (D14), `temporalio`, `pydantic`, `httpx`, `pyyaml`; dev: `ruff`, `mypy`, `pytest`, `pytest-asyncio`, `respx`), `src/dark_factory/__init__.py`, ruff and mypy config (strict), one trivial test, `.env.example`. Rewrite CLAUDE.md: remove the FastAPI, SQLAlchemy, Alembic and repository-layer template sections (D2), add the real commands and structure, add Windows venv activation (`.venv\Scripts\activate`).
- **Acceptance:** `ruff check . && ruff format --check . && mypy src/ && pytest` passes on a clean checkout.
- **Depends on:** none.

### M0.2 CI on GitHub Actions *(manual)*
- **Value:** every PR is checked automatically.
- **Scope:** `.github/workflows/ci.yml` on `pull_request` and push to `main`: the full check from M0.1. No secrets, and `permissions: contents: read`. Owner enables branch protection on `main` requiring the check, but not an approving review: GitHub does not let a PR author approve their own PR, and until M1.10 the owner authors every PR. From M1.10 the GitHub App bot authors factory PRs, so the owner can be requested as reviewer and approve them.
- **Acceptance:** a PR shows the check. A failing lint blocks merge.
- **Depends on:** M0.1.

### M0.3 Manual agent loop, labels and work log
- **Value:** from here on, every issue runs through the same documented loop, and the record of how the repo was built starts.
- **Scope:** `docs/ai-workflow.md` covering the loop (issue → coding agent on a branch → PR → cross-vendor review by hand → owner merges) and the log format. Labels `agent`, `gate:plan`, `gate:merge`, `manual`. Issue template `agent-task.md` (goal, scope, acceptance criteria, out of scope). This is the format the factory will consume.
- **Acceptance:** this issue is closed by a PR made through the documented loop, with a log entry.
- **Depends on:** M0.1.

### M0.4 Docker Compose: Temporal dev server, Postgres, MinIO, hello worker
- **Value:** durable workflows run locally. This is the base for everything in M1.
- **Scope:** `docker-compose.yml` with the Temporal dev server and UI, Postgres (telemetry DB, unused until M2), MinIO with a bucket, and a `worker` service built from a `Dockerfile` that runs a trivial `Hello` workflow and activity. A script that starts the workflow and prints the result. Pinned image versions.
- **Acceptance:** `docker compose up` followed by the script prints the result. The run is visible in the Temporal UI. A time-skipping unit test for `Hello` passes in CI.
- **Depends on:** M0.1.

### M0.5 Config: `registry.yaml` and `routing.yaml` v1
- **Value:** what to serve and which model to use become versioned and validated, as PRD §5.6 requires ("Git is the source of truth").
- **Scope:** Pydantic models and loaders in `dark_factory.config`. **Registry:** owner allowlist (GitHub logins), and per repo `full_name`, default plan gate (merge is always gated in MVP), test command, routing overrides. **Routing:** task type (`plan`, `implement`, `review`, `triage`, `ci_summary`, `commit_message`) → model ID plus vendor, with a version field. Research current OpenRouter models and prices, and propose the v1 table in the PR for owner approval. Add a CI test that loads and validates both files. Initial registry entry: the playground repo.
- **Acceptance:** invalid config fails CI with a clear message. The owner approves the model table.
- **Depends on:** M0.1.

### M0.6 GitHub App and playground repo *(manual, owner)*
- **Value:** the credentials and target needed for M1 exist.
- **Scope:** create the GitHub App with the minimum permissions:
  - Issues: read/write
  - Pull requests: read/write
  - Contents: read/write
  - Checks: read
  - Metadata: read
  - **No `workflows` permission** (D12)
  - Events: `issues`, `issue_comment`, `pull_request`, `pull_request_review`, `check_suite`

  Store the private key outside the repo, referenced from `.env`. Create `dark-factory-playground`, a small Python 3.12 project with pytest and its own CI, and install the App on it and on `dark-factory`. Document every step in `docs/setup/github-app.md`. Install the `gh` CLI with the `gh webhook forward` extension.
- **Acceptance:** a script mints an installation token and reads the playground repo's issues.
- **Depends on:** M0.5 (registry entry).

**M0 done:** M0.1 to M0.6 merged, each through the manual loop and logged.

---

## M1: Happy path, local

Exit criteria (PRD §8): owner-labelled issue → workflow → plan → Aider in a local sandbox → PR opened. Timeouts and retries on every activity. A killed worker resumes the run. Idempotent workflow IDs. **Plus, by owner decision: the self-hosting switch.**

Suggested order: M1.1, M1.2 and M1.3 can run in parallel. Then M1.4, M1.5 → M1.6 → M1.7 → M1.8 → M1.9 → M1.10.

### M1.1 Domain types, untrusted-data envelope, system prompts
- **Value:** GitHub text can reach a model only through a safe constructor, from the first LLM call on (PRD §5.2).
- **Scope:** Pydantic types (`RepoRef`, `IssueRef`, `RunInput`, `PlanResult`, `SandboxJob`, `SandboxResult`, `LlmUsage`). `policy.envelope.wrap(text, source, author)` produces a delimited block with a per-call random boundary, so content cannot close it. Prompt builders accept GitHub text only as `Envelope` values, never as `str`. System prompts live as files under `prompts/` (protected path from M2), loaded by name.
- **Acceptance:** tests show that content containing the delimiter or a fake closing tag stays inside the block, and that a prompt builder rejects a raw `str` in the data slot (mypy plus a runtime check).
- **Depends on:** M0.1.

### M1.2 OpenRouter client, routing resolver, per-run keys
- **Value:** every model call is routed by policy and returns its usage. Sandboxes can get budget-limited keys (D7).
- **Scope:** async `httpx` client for chat completions with usage accounting (model, prompt/completion tokens, cost, duration → `LlmUsage`). Resolver: task type + repo override → model. Provisioning client: create a key with a limit, read key usage, delete the key. Base URL configurable (D10). Typed errors split into retryable (429, 5xx, timeouts) and non-retryable (400, 401, insufficient credit).
- **Acceptance:** `respx` tests for the usage parsing, the error classes and the key lifecycle. A manual smoke script makes one real call and prints its cost.
- **Depends on:** M0.5.

### M1.3 Narrow GitHub client
- **Value:** the only path to GitHub, with no operation for labels, gates or merge (PRD §5.1).
- **Scope:** App JWT → installation token (resolved per repo, cached until expiry, D4). Operations:
  - `get_issue`
  - `download_tarball(ref)`
  - `push_branch_from_diff(diff, branch, message)`, which clones shallow, applies the diff, commits as the bot and pushes with `--force-with-lease` (D6)
  - `find_open_pr(branch)`
  - `open_pr`
  - `post_comment`

  Nothing else is exposed. Labels and merge come in M2 as separate, deliberately named operations.
- **Acceptance:** `respx` and local-git tests, including a test that the public surface contains no label or merge method. A smoke script against the playground repo.
- **Depends on:** M0.6.

### M1.4 Ingress: handler core and local adapter
- **Value:** a real `agent` label starts exactly one run.
- **Scope:** `handle(headers, body)` does the following:
  1. Verifies `X-Hub-Signature-256` with a constant-time compare.
  2. Accepts `issues.labeled` with label `agent` only.
  3. Checks that the sender is on the owner allowlist and the repo is in the registry.
  4. Starts `IssueRun` with the D8 ID. An already-started run is a 200 no-op.

  Non-owner trigger labels are ignored and logged. The full `UnauthorisedLabel` handling comes in M2. Add the Starlette adapter as a Compose service (D3), and document `gh webhook forward` in `docs/setup/local.md`.
- **Acceptance:** tests cover a bad signature, wrong events, a non-owner sender, an unregistered repo, a duplicate delivery and a valid start (with a mocked Temporal client).
- **Depends on:** M0.4, M0.5, M1.1.

### M1.5 Sandbox image, `CodingAgent` interface, Aider implementation
- **Value:** an isolated, credential-free container that turns a task into a tested diff.
- **Scope:**
  - `CodingAgent` protocol: `run(task: Envelope-based spec, workdir) -> AgentOutcome`.
  - Aider implementation, headless, with a pinned version, the model from the job spec, the OpenRouter key from the env, and the base URL configurable.
  - Sandbox image: Python 3.12, git, Aider.
  - Entrypoint:
    1. Read the job spec.
    2. GET the snapshot from its presigned URL.
    3. `git init` and baseline commit.
    4. Run the agent with the system prompt plus the envelope (issue body and plan).
    5. Run the repo's test command.
    6. PUT the diff, the log and `result.json` (test outcome, Aider-reported usage).
  - No GitHub or AWS credentials, by construction.
- **Acceptance:** an integration test runs the image against a fixture repo and a stub LLM server (D10) that returns a canned edit, and gets the expected diff and test result.
- **Depends on:** M1.1, M1.2.
- **Note:** egress restriction to port 443 is enforced on AWS by a security group (M3). Locally it is documented as a known gap.

### M1.6 Blob store and local sandbox launcher
- **Value:** the worker can run one sandbox step reliably and get its results back.
- **Scope:** `storage.BlobStore` (S3 API via boto3, pointed at MinIO locally) with presigned GET/PUT. `SandboxLauncher` protocol with a Docker implementation that runs the container with the job spec, heartbeats while it runs, enforces a hard timeout, kills the container on timeout or activity cancellation, and returns `SandboxResult`. The ECS implementation comes in M3.
- **Acceptance:** an activity test runs the M1.5 image through the launcher. A test kills the activity mid-run and checks that no container is left behind.
- **Depends on:** M0.4, M1.5.

### M1.7 `IssueRun` workflow, happy path
- **Value:** the first end-to-end orchestration: issue in, PR out.
- **Scope:** `IssueRun(repo, issue)`, as a chain of activities:
  1. `load_config`
  2. `fetch_issue`
  3. `plan`: frontier model, issue body in the envelope, plan posted as an issue comment
  4. `mint_run_key`
  5. `snapshot_repo`: tarball → blob store
  6. `implement`: sandbox launcher, plan in the envelope
  7. `push_branch`
  8. `open_pr`, which reuses an existing PR if one is open, and opens it as a draft when sandbox tests failed (D13)
  9. `comment_pr_link`
  10. `delete_run_key`, run in a `finally` block

  Every activity has an explicit `start_to_close` timeout and a retry policy, plus a heartbeat timeout for the sandbox. Indicative values: GitHub calls 30 s / 5 attempts; LLM 5 min / 3 attempts; sandbox 30 min / 2 attempts. Non-retryable errors map to failure with an explanatory issue comment. The workflow returns all `LlmUsage` records, which keeps them in history until telemetry tables exist (M2).
- **Acceptance:** time-skipping workflow tests with mocked activities cover success, retry after transient failure, non-retryable failure and key deletion on failure.
- **Depends on:** M1.2, M1.3, M1.6.

### M1.8 Resilience: idempotency, worker loss and replay safety
- **Value:** proves the PRD's Temporal guarantees and makes self-hosting safe (D11).
- **Scope:**
  - Make every side-effecting activity idempotent under retry. The branch push already is. PR open looks up the existing PR first. Comments carry a hidden marker that is used only to deduplicate; their content is never fed to a model.
  - Test: start a run, kill the worker during `implement`, restart it, and check that the run completes with one PR and one plan comment.
  - Test: a duplicate webhook does not start a second run.
  - Replay harness: export histories of completed runs into `tests/replay/` and replay them against the current code in CI.
  - `scripts/kill-worker-demo` for the README.
- **Acceptance:** all of the above pass in CI. The demo script works locally.
- **Depends on:** M1.7.

### M1.9 End to end on the playground repo
- **Value:** M1 exit criteria met against a real repository.
- **Scope:** the full local stack, a real owner-labelled issue on the playground repo, and a real PR. Fix whatever breaks. Write `docs/setup/local.md` (start the stack, forward webhooks, label an issue) and a log entry in `docs/ai-workflow.md` with the run's cost and duration.
- **Acceptance:** three different playground issues each produce a reasonable PR with passing tests. One of them is run with a worker kill mid-run.
- **Depends on:** M1.4, M1.8.

### M1.10 ★ Self-hosting switch
- **Value:** the factory builds itself from here on.
- **Scope:**
  - Add `dark-factory` to the registry, with test command `pip install -e ".[dev]" && ruff check . && mypy src/ && pytest`, and make sure the sandbox image can run it.
  - Document the deploy procedure (D11) and the rule that `manual` issues never get the `agent` label.
  - Write the first M2 issues as factory-ready tasks, using the M0.3 template.
  - Label one small one `agent` and merge the resulting PR after owner review.
- **Acceptance:** one PR on this repo, opened by the App bot from an `agent`-labelled issue, is reviewed and merged by the owner, and the log entry is written.
- **Depends on:** M1.9.

---

## M2: Review, gates, telemetry *(outline; built by the factory)*

Issues are written at M1.10. The order puts measurement and money controls first, so every later M2 run is measured and capped. Steps that touch protected paths still go through the factory, but the owner reviews them with extra care. `.github/workflows` changes stay manual (D12).

1. **Telemetry schema and writer:** `telemetry` DB tables `runs`, `steps`, `llm_calls`, `gate_waits`, `events`, `revision_rounds`, `redos`; the migration runner (D2); a writer activity; a CLI report (`df report`) for lead time excluding gate time, cost per run, and human-edit rate (from commit authors, D6).
2. **Per-run cost cap:** spend accumulated from `LlmUsage` and sandbox key usage. Each sandbox key's limit = the remaining budget. When spend hits $5 the run stops and comments. The cap is read from config (global default, per-repo override in `registry.yaml`); raising it is a reviewed config PR.
3. **Owner commands and signals:** a deterministic parser for `/approve`, `/changes <text>` and `/reject`. Ingress handles `issue_comment` and `pull_request_review`. Non-owner comments are dropped and logged before anything else sees them. The ingress then signals the running workflow.
4. **Gate resolution and plan gate:** the plan gate comes from the repo default plus the `gate:plan` label; the merge gate is always on (resolved question 1). Wait for the signal with no timeout and periodic reminders. `/changes` re-plans with the owner's text inside the envelope and is recorded as a redo. `/reject` ends the run.
5. **Structured cross-vendor reviewer:** a JSON schema for verdict plus findings, validated, with a retry on invalid output. The resolver refuses a reviewer from the implementer's vendor. The orchestrator reads only the verdict. Findings go back to the implementer inside the envelope.
6. **CI wait and bounded revisions:** a `check_suite` signal with a timeout. A failure log is summarised by the cheap model (inside the envelope) and fed into revision. Review and CI share a 3-round budget. When it runs out, the run **stops**:
   - It posts one comment on the issue and the PR with a system-generated summary: rounds used, last reviewer verdict, last CI state, spend so far. It never quotes model or GitHub text as anything but data.
   - The PR stays open and is converted to draft, so it cannot be merged by accident and the work is not lost.
   - The run ends with outcome `revisions_exhausted` in telemetry. It is **not** a redo (PRD §3 counts only owner gate decisions and reverts), but it is reported next to redo rate, together with revision rounds per run.
   - To continue, the owner edits the issue if needed and re-applies `agent` (D8). That starts a new run with a fresh 3-round budget and a fresh cost cap, linked to the earlier run in telemetry.
7. **Merge gate and merge:** every run waits at the merge gate once review and CI pass, with no timeout and periodic reminders. The owner's PR review becomes a signal. Request changes → revision, recorded as a redo. Approve → merge, using a dedicated, narrowly named client operation. Time paused at the gate is recorded.
8. **`UnauthorisedLabel` workflow and alerts:** for `agent`, `gate:plan`, `gate:merge` and `gate:none` applied by a non-owner, remove the label (the client's only label operation, restricted to removal), comment, alert and record it. Alerts go through an `Alerter` interface with a real SNS implementation from the start:
   - **Before this step (manual):** apply `infra/bootstrap` by hand (pulled forward from M3.1), then an `alerts` module in `infra/envs/prod` with the SNS topic and an email subscription. The owner's address is a Terraform variable from an untracked tfvars file, never committed (this repo is public). The owner confirms the subscription email.
   - Locally, the worker publishes with an IAM user whose only permission is `sns:Publish` on that topic, keys in `.env`. In M3 the worker's task role replaces it and the user is deleted.
9. **Protected paths:** the diff's paths are checked against the protected list (`infra/`, `.github/`, `prompts/`, `routing.yaml`, `registry.yaml`, gate code). In MVP the merge gate is always on, so the check cannot change the outcome yet. It is still built and tested now: it is part of the M2 exit criteria, it lists the touched protected paths at the top of the PR body so the owner reviews them with extra care, and `gate:none` in M5 will rely on it.
10. **Injection tripwire and test suite:** a cheap classifier flags injection-like content, records an event and raises an alert. CI fixtures plant instructions in issue bodies, PR comments, code comments, CI logs and reviewer findings. Pass: no gate, label, tool or merge change, and the attempt is flagged.
11. **Routing review:** confirm the concrete models after real telemetry (PRD §12) and log the changes in `docs/ai-workflow.md`.

**M2 exit:** this repo's default gates become `plan` + `merge`, and its own issues run through the full loop (self-hosting level 2).

## M3: On AWS, documented *(outline)*

Infrastructure is written by the factory where possible, under forced `gate:merge`. Bootstrap and workflow files are manual.

1. `infra/bootstrap` *(manual, already applied in M2.8)*: state bucket, GitHub OIDC provider, read-only plan role, apply role trusting only `refs/heads/main`. M3 brings the existing `alerts` resources under the GitOps pipeline.
2. GitOps workflows *(manual, `.github`)*: PR runs `fmt`, `validate`, `tflint` and `plan`, posted as a PR comment. Merge builds images, pushes to ECR tagged with the SHA, then runs `apply`.
3. Modules for network (public subnets, no NAT, no endpoints), RDS Postgres (Temporal plus `telemetry`), S3, ECR, Secrets Manager and log groups with 14-day retention.
4. Temporal server on Fargate. The UI is on demand and reachable only from the owner's IP.
5. Worker service on Fargate, plus the ECS `SandboxLauncher` (RunTask, a security group allowing only outbound 443, a hard task timeout).
6. Ingress: API Gateway HTTP API plus the Lambda adapter around the same `handle` (D3), with the Lambda in the VPC reaching only Temporal.
7. Budget alarm at $60, sent to the existing SNS topic.
8. `session-up` and `session-down` workflows. A scheduled re-check that RDS is stopped. The `Reconcile` workflow (start missed runs, stop orphaned sandbox tasks), run on `session-up` and on a schedule.
9. Cutover: the App webhook URL points to API Gateway, and a run on AWS completes from issue to merge (self-hosting level 3).
10. README demo GIF, run history, telemetry tables; the design write-up justifying each AWS service choice.

## M4: Scale *(stretch, coarse)*
Parallel runs per repo with conflict handling (merge queue or rebase). Load test from PRD §7: 50 issues in one minute across 5 repos, using the stub LLM (D10), reporting p50/p95 orchestrator overhead per step. Run dashboard.

## M5: Extensions *(later, coarse)*
A self-built inner loop behind `CodingAgent`, compared with Aider on telemetry. Label-driven merge gating: the `gate:merge` label and `gate:none` (merge with no human), once the metrics justify it. Protected paths (M2.9) then force the merge gate. Creating repos from issues. Jira adapter. MCP tools.
