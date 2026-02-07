# Guardrails

This document defines safe operating guidelines for the Repo Monitor Agent.

## Core Principles
- **Least privilege**: Use the minimal required GitHub scopes and local system permissions.
- **No secret leakage**: Never log or echo API keys, tokens, or webhook secrets.
- **Local-first data**: Keep analysis artifacts local unless explicitly shared.
- **Deterministic outputs**: Favor lower temperature for reviews and summaries.

## Operational Safety
- **Webhook validation**: Always verify GitHub webhook signatures.
- **Rate limits**: Respect GitHub API limits and backoff on 403/429.
- **Prompt hygiene**: Strip secrets from prompts and redact tokens in logs.
- **Output sanitation**: Avoid executing or auto-applying code changes without human review.

## LLM Usage
- **Provider control**: Use `LLM_PROVIDER=foundry_local` for local inference.
- **Model pinning**: Pin model names (e.g., `qwen2.5-0.5b`) for reproducibility.
- **Timeouts**: Enforce request timeouts and retry with backoff.

## Data Retention
- **Event logs**: Treat `repo-monitor-events.jsonl` as disposable and exclude from VCS.
- **Vector stores**: Clear local vector DBs when no longer needed.

## Incident Handling
- **Stop on errors**: If review output is malformed or suspicious, stop and retry.
- **Audit**: Keep minimal logs necessary for debugging; purge regularly.
