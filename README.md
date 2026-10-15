# Dark Factory

A human-gated dark factory on Temporal: GitHub issues go in, reviewed and merged pull requests come out.

Each issue starts a durable Temporal workflow that plans the change, implements it in an isolated sandbox, opens a PR, has it reviewed by a model from a different vendor, waits for CI, and pauses at the human gates the issue requires before merging. Model choice per task is routed through OpenRouter, and every run records duration, tokens, cost and outcome.

## Status

Pre-M0. The design is in [PRD.md](PRD.md).

## Stack

Python, Temporal, Aider, OpenRouter, AWS (ECS Fargate, Lambda, API Gateway, RDS, S3), Terraform, GitHub Actions.

## Principles

- Human gates are enforced in code, not by convention. Only the owner can trigger runs or approve gates.
- No text from GitHub is ever treated as an instruction. Agents hold no credentials.
- Infrastructure is code, deployed through GitOps.
- The project is built with itself.
