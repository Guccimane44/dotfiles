# Feedback, review and project readiness

A changed issue title, body or comment stops a running attempt at its next control
check. The existing GitHub workpad explicitly acknowledges that detection and lists
observed comment IDs. This means received and stopped for review, not implemented.
Only workpads authored by the authenticated operator are excluded from new feedback.
If GitHub publication fails, the saved update remains queued for a later control tick.

## Review a stopped task

```sh
agent-work console review ISSUE
agent-work scheduler inspect ISSUE
```

Inspect code changes, including staged and untracked files, and run the relevant
checks. The inspection supplies a `revision` hash covering HEAD, branch, index,
nonignored file contents/modes, attempt number, and issue feedback. Save the evidence
outside the task worktree, for example in its local state folder:

```json
{
  "revision": "HASH_FROM_INSPECTION",
  "summary": "What was reviewed, the conclusion, and the next action",
  "checks": [
    {"name": "Actual command or manual check", "result": "passed", "evidence": "Actual result and relevant observations"}
  ]
}
```

Record checks honestly. The harness validates the evidence structure and revision;
it does not independently establish that an asserted check was executed or correct.
Do not include credentials or sensitive output. A result is `passed`, `failed`, or
`skipped`; acceptance requires all listed checks to pass. A retry review may explain
failed or skipped checks and the bounded next action.

```sh
agent-work console accept ISSUE --evidence /absolute/path/review.json
agent-work console resume ISSUE --evidence /absolute/path/review.json
```

Acceptance records the exact reviewed state locally and queues a brief GitHub update;
it does not commit, publish code, merge or deploy. The accepted revision is historical:
subsequent edits are not covered by that acceptance. Resume authorizes only one attempt.
Missing/stale evidence blocks approval, and dispatch rechecks it after quota waits.
Existing accepted records from before this feature are retained as historical records.
Their earlier acceptance is not retroactively promoted to this stronger review contract.

Ignored files (including `.agent-work` runtime files) are outside the revision hash;
check inputs must not depend on unreviewed ignored content. Submodule/special-file
workspaces require a separate review policy. Checks should use the project's pinned
environment and existing verification commands. This is not a remote merge gate or
an attestation against a malicious local user.

## Prepare a future project

Copy the files under `templates/agent-project` deliberately into a candidate project,
fill in `project.json`, and validate its structure:

```sh
agent-work project validate /absolute/path/project.json
```

The intentionally incomplete template fails until repository, branch, scope, stack,
setup arguments and verification commands are supplied. Validation never executes
commands, installs tools, registers repositories or enables dispatch. Initial policy
is one worker, 20 minutes, 25% short-window reserve, 3% weekly reserve, supervising-agent
retry review and no automatic publication. Demonstrate setup, checks and saved-session
recovery in a disposable task before proposing an allowlist change. Product repositories,
including Vocabularium, remain excluded from the current scheduler.

## Run automated verification before acceptance

The supervisor reviews the contract's commands, then explicitly runs:

```sh
agent-work verify ISSUE --contract /absolute/path/project.json --seconds 300
```

This executes the declared check argument lists in the saved task workspace. It does
not run setup, install dependencies, start a model, publish results or enable dispatch.
These are local commands with the operator's permissions, not a new security sandbox;
only use commands already authorized for the task. The default total limit is five
minutes (maximum ten). A failed check stops the sequence. Each output is capped at
1 MiB; timeout/output overflow fails the check and kills its process group.

Results, exit codes, command arguments, durations and hashed logs are retained privately
under the task's `verifications/ID/` directory. The report is saved before execution
and after every check. An interruption cannot leave a passing report. Checks that change
nonignored code or run against changed issue feedback fail revision validation.

Add the returned `verification` ID to the review evidence JSON alongside `revision`,
`summary` and manual `checks`. Acceptance now requires a matching successful automated
report and unchanged output logs; a retry review may still document failed verification.
The supervisor remains responsible for checking that the chosen tests establish the
issue's acceptance criteria. Passing a weak test suite is not proof of correctness.
This requirement applies to new acceptance decisions, not historical accepted jobs.
