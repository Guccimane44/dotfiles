# Four-worker capacity

The user approved up to four simultaneous workers on this Mac. Manual task runs,
scheduled task runs and explicit verification share four local capacity slots.
A single issue or saved workspace still allows only one operation at a time.
Workers retain isolated worktrees; nothing permits concurrent edits to one checkout.

The controller admits batches of up to four eligible issues and records completed
results independently. It owns scheduler-state writes; each worker writes only its
own task records. Workpad payload files are scoped to their issue to avoid collisions.
Capacity contention starts no model turn and does not consume retry authorization.
New work still needs the ready label, available quota and any required current review.

Children inherit issue, workspace, capacity and runtime leases. If the parent dies,
a live child prevents duplicate issue work and retains its capacity slot. Restart
reconciles only reservations whose issue lease can actually be acquired. There are
no automatic retries of interrupted work. Preparation of worktrees is serialized
per source repository; runtime upgrades remain exclusive and refuse active workers.

The controller retains its single state-writer lock for a batch. Status reads and
GitHub feedback/pause controls work during the batch; review/approve/verification
commands requiring that lock may need to be repeated after the batch finishes.
A batch admits at most four tasks per polling invocation; it does not continuously
refill completed slots. This keeps the scheduling change small and state handling
predictable. Cross-machine coordination remains unsupported.

The 25% scheduler short-window reserve and 3% weekly reserve are unchanged. Each
worker checks quota independently. These are polling thresholds, not a hard combined
token budget; four active workers can consume quota between checks. Worker-internal
subagent spawning remains disabled, so it cannot bypass the shared capacity limit.
Historical benchmark protocols intentionally retain their original serial execution.

Validation uses temporary repositories, fake workers, and real local child processes:
four issues can overlap; a fifth is blocked; duplicate issues and aliased workspaces
are blocked; orphaned children retain leases; all concurrent scheduler outcomes survive.
No live model attempts are needed to verify these concurrency contracts.
