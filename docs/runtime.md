# Stable runtime and recovery

The scheduler and normal `agent-work` commands use the tested, committed release
selected at `~/.local/share/agent-work/current`. Editing or switching the dotfiles
checkout does not change that release. Each invocation verifies its file hashes;
these detect accidental modifications, not attacks by the same macOS account.
Releases include pinned skills and their lock. No new runtime dependency is needed.

## Operate

```sh
agent-work release health
agent-work release build ~/.dotfiles
agent-work release activate ~/.local/share/agent-work/releases/COMMIT
agent-work release rollback
```

Build requires a clean committed checkout and reruns the test suite in the archived
package. Activation and rollback refuse while a scheduler or worker holds its lock.
They preserve all task/session state and the enabled flag. Failed service installation
restores the prior selection/configuration where possible; run health after any failure.
Rollback requires a previous successfully selected release. The initial deployment has
no predecessor. Only state-schema-compatible releases may share this rollback process;
a future schema migration needs an explicit migration and rollback design.

The Nix wrapper prefers the stable launcher; an already installed older wrapper also
routes through it via the source launcher. `AGENT_WORK_SOURCE=1 python3
scripts/agent-work.py ...` explicitly runs checkout code for development. It must not
be used as the service entry point. Nix activation is needed to remove that older
wrapper's remaining dependency on the source launcher existing at its original path.

Health checks inspect local integrity, tool availability, launchd registration, task
status and a controller heartbeat. They do not call a model or prove GitHub access,
account quota availability, or task correctness. During work the heartbeat updates
at control checks. A fresh heartbeat and loaded service are required when enabled.
A dedicated source clone is created lazily for new scheduled issues; existing issue
worktrees and saved session IDs remain in place.

## Persistence and limits

State replacements flush their file and directory before proceeding. Every attempt
gets a durable `running` history entry before process launch, then a final outcome
when the controller can finish. Usage stays unknown after an abrupt loss unless a
completion event supplied it; unknown does not mean free. Checkpoint copies are saved
before and after attempts outside the editable worktree. They complement the live
checkpoint and saved session; they cannot recover reasoning never written to disk.

On restart, a reserved dispatch stops for supervising-agent review. The inherited
worker lock prevents a second worker while an orphaned child is still running.
There is no automatic retry of a started attempt. Review the worktree, logs, session
and checkpoint before granting one bounded retry.

Service logs rotate after controller invocations at 2 MiB, keeping two backups.
This is a retention threshold, not a hard disk cap during a running attempt. Task
logs, checkpoints and session records are retained; deletion is a separate policy.
The scheduler retains a 25% five-hour reserve and a **3% weekly reserve**, with
20-minute attempts and one worker. Polling and stop grace periods mean these are
protective thresholds, not exact spend caps.

Tests cover failed writes, integrity changes, activation/rollback state preservation,
upgrade exclusion, service-selection rollback, interrupted-session reuse, saved quota
waits, API failure, and worker lock inheritance. They use local fixtures, not paid
model turns. They do not simulate a physical disk failure or reboot the Mac.
