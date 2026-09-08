# Single-Mac scheduler

Scope: only `Guccimane44/dotfiles`, up to four workers, routed to GPT-5.6 Luna or GPT-6 Astra, medium reasoning, subscription login, 25% five-hour and 3% weekly quota reserves, 20-minute attempt deadline. No product repositories, automatic retries of started attempts, code publication, or merges. Polling uses GitHub and account APIs, not model turns.

## Installation and controls

The existing Nix-managed `agent-work` launcher supplies Python and Git. No additional packages or administrator activation are needed. The generated user LaunchAgent is derived from `scripts/agent-scheduler.py`; regenerate it after moving dotfiles. It runs during this user's login session, approximately once per minute while the Mac is awake.

```sh
agent-work scheduler install
agent-work scheduler enable
agent-work scheduler status
agent-work scheduler disable
```

Installation alone does not enable dispatch. Disabling removes the local permission flag; an active worker notices at its next control check. For an immediate service stop, first disable, then `launchctl bootout gui/$(id -u)/local.agent-work.scheduler`. Reinstall to load it again. Do not install a second copy or run on another computer. The source checkout must stay clean; task workspaces are isolated from it and start from the remote default branch.

## Give work and intervene

1. Create a bounded issue with acceptance criteria and verification instructions.
2. Add `agent:ready` when you want its first attempt to run. No task dispatches just because it is open.
3. Follow its **Agent workpad** comment. It records startup, periodic checkpoints, and the stopped state. GitHub write failure prevents startup. Failures during final publication remain queued locally and are retried without a model call.
4. Remove `agent:ready`, add `agent:paused`/`agent:blocked`, close the issue, or add/edit feedback to stop the active attempt. The controller checks about every 30 seconds; network calls can delay detection. Feedback acknowledgment means detected, not implemented. The next approved attempt receives the updated issue and comments.
5. Inspect saved work and the checkpoint before approving another attempt. Then run `agent-work scheduler approve ISSUE_NUMBER` and ensure `agent:ready` is present with blocking labels removed. This authorizes exactly one further attempt. Keeping or re-adding the label alone never retries a spent attempt. The supervising agent performs routine review and can approve this bounded retry without asking the user. Escalate only high-level architectural decisions; actual environment permission requirements still apply.
6. Review code and run appropriate verification on the exact commit before publishing a draft PR. Routine acceptance review belongs to the supervising agent. Publication and merge remain within the task’s authorization; this policy alone does not enable automatic publication or merging. A completed agent turn is not a passing test or accepted issue.

## Recovery and accounting

State lives at `~/.local/state/agent-work/scheduler/state.json`; task sessions, checkpoints, JSONL logs, and per-attempt history live under `~/.local/state/agent-work/Guccimane44/dotfiles/ISSUE_NUMBER`. Scheduler state is fixed to this root. Do not relocate manual workers to bypass the shared lock.

A dispatch reservation is persisted before preparation/launch. Restarted reservations become `needs-approval`, never a fresh automatic attempt. The worker inherits the execution lock, so a surviving child blocks another worker even if its parent dies. Launchd normally terminates remaining job processes when a job exits. Do not clear lock files to bypass a live worker; inspect processes first.

Retries reuse saved Codex session IDs and workspaces. A missing ID after a started attempt blocks approval. A missing session on Codex's side stops the attempted resume and needs investigation; there is no fallback to a new thread. A preparation failure may leave a branch/worktree before state was saved; inspect and reconcile it manually.

Before launch, missing quota data blocks work. Exhausted reported windows persist a next-check time after their reset (at least five minutes); unknown reset/account failures wait at least five minutes. No model polls for quota. Active workers are checked periodically; reaching the applicable reserve or losing control-plane access stops the attempt and requires approval to resume. This does not consume reset credits or enable API billing.

The controller writes a cooperative checkpoint request and allows five seconds before termination on a detected stop/deadline. It cannot guarantee the worker reads that request. A forced stop may leave partial edits or a partial checkpoint. The nominal 20-minute deadline can overshoot while bounded control-plane calls finish. It is not a hard token cap, and other sessions can consume shared quota between checks.

Each normally finalized attempt records elapsed time, outcome, HEAD, and reported usage. Interrupted usage is marked unknown instead of zero; an abrupt controller kill may also omit final accounting. Keep JSONL logs for investigation. Do not infer billing or token savings from incomplete records. The authorization policy, not token estimates, prevents repeated spending.

Service logs are local `scheduler/service.log` and `scheduler/service-error.log`. They can contain task output and rotate after controller invocations at 2 MiB, keeping two backups; task logs remain retained. No credentials/session IDs are posted by the controller, but checkpoint text is agent-authored and is published to the private task issue; keep secrets out of checkpoints.

## Verification

`python3 -m unittest discover -s tests -v` tests recovery, no automatic retry, missing session, failed publication/API reads, quota wait persistence, controls, and lock exclusion without model calls. A separate small live infrastructure issue verifies installation and GitHub updates. This is single-host infrastructure, not a Symphony-compatible distributed service.

The weekly reserve was lowered to 3% at the user’s request. The scheduler rechecks quota when its policy changes instead of retaining a wait computed under the former 25% weekly threshold. This does not approve retries of already-started work.

## Review ownership

`needs-review` and `needs-approval` are supervising-agent queues, not mandatory human gates. The user is consulted for high-level architectural choices. The controller itself does not launch a second reviewer automatically: a supervising agent must inspect the result and record evidence before accepting it or approving one further attempt. This preserves protection against blind retry loops.
