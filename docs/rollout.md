# Staged rollout

## Phase 1: explicitly launched issue work

Acceptance:
- Private dotfiles repository, issue template, and linked infrastructure test PR.
- Nix-managed launchers and declared GitHub CLI.
- Isolated issue workspace, durable session identity, checkpoint and explicit GitHub sync.
- One local worker and quota preflight; no automatic retries or paid fallback.
- Local recovery tests and a minimal live issue smoke test.

The operator owns issue creation, launch, publication, pause, and acceptance. Status is descriptive (`prepared`, `running`, `paused`, `interrupted`, `time-limit`, `needs-review`); a successful agent turn is not a correctness verdict.

## Phase 2: unattended dispatch, separately authorized

Do not implement or start a daemon in Phase 1. Before choosing an implementation, compare existing GitHub-capable runners with adding a tracker adapter to Symphony. Avoid maintaining a new orchestration framework without a demonstrated gap.

Required before unattended use:
- Explicit repository allowlist and eligible issue label.
- Durable issue ownership/lease across processes and hosts.
- Continuous pause and human-feedback reconciliation with acknowledgment.
- Persisted quota wait/reset policy; no repeated model-driven polling.
- Graceful checkpoint requests before quota depletion, crash reconciliation, and session recovery tests.
- Per-task accounting and budget policy, including interrupted attempts.
- Verification tied to the exact proposed commit and human merge authority.
- Test restart, API outage, missing session, quota exhaustion, and concurrent claim scenarios.

Increase to two independent implementation workers only after these contracts are tested. Do not apply the workflow to Vocabularium during infrastructure setup.

## Authorized Phase 2 scope adjustment

The user approved the smaller single-Mac scheduler on 2026-09-07 after comparison with Symphony v0.0.2. Official Symphony has a GitHub adapter, but its worker attempts start new threads, failures retry automatically, and blocked state is in memory. Reusing it unchanged would weaken the desired recovery/cost controls.

This rollout replaces cross-host leases with one fixed local lock domain, including a worker-inherited lock. Cross-host operation is unsupported. It provides checkpoint stop requests and periodic quota reads, not guaranteed graceful completion or a hard token cap. Missing interrupted-attempt usage is explicitly unknown. Automatic code/PR publication is deferred; therefore exact-commit validation remains a human publication gate. A second worker and Vocabularium remain excluded.

Source comparison: [official release README](https://github.com/openai/symphony/blob/v0.0.2/elixir/README.md), [orchestrator](https://github.com/openai/symphony/blob/v0.0.2/elixir/lib/symphony_elixir/orchestrator.ex), [Codex session creation](https://github.com/openai/symphony/blob/v0.0.2/elixir/lib/symphony_elixir/codex/app_server.ex). GitHub-native alternatives reviewed included symphony-ts and agent-orchestrator; they add a separate runtime/framework, while extending the already-tested launcher preserves our saved-session behavior with no new dependencies.
