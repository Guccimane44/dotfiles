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
