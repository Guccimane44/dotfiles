# Matched standard versus lean pilot

User authorized six fresh GPT-6 Astra/medium attempts, at most five minutes each,
with one worker and existing 25% short-window / 3% weekly reserves. No retries.
An atomic local reservation prevents replay of the allowance.

Three existing Python fixtures: duration parsing, typed job deduplication, capped
retry delay. Both conditions receive identical source, specification and supplied
unittest file. Both must run the same tests and diff check, change only task.py,
and leave supplied tests unchanged. Recovery files are allowed in both conditions.
Order: lean/standard, standard/lean, lean/standard. Both use the same current worker;
only the workflow selection differs. No model/skill/environment migration is included.
Grading reruns the reference checks externally and checks unchanged tests/extra files.

Primary outcomes: correctness and tokens split into uncached input, cached input,
and output. Also inspect model-response counts and whether required checks actually
ran. Runtime is recorded for provenance, not an optimization target. No direct
subscription charge or quota-consumption inference from token totals.

This is a single observation per condition per tiny task. It tests whether reducing
administrative steps helps with matched deliverables. It does not establish broad
project savings or recovery performance. Cache effects and stochastic behavior remain.

## Initial quota block

On 2026-09-08 at approximately 02:27 Berlin time, preflight reported 88% five-hour
usage (12% remaining), below the required 25% reserve. No model attempt started.
The reported reset was 06:19 Berlin time. The user explicitly chose to keep the
reserve and leave the pilot ready for later. No automatic wakeup was scheduled.

After quota becomes eligible, explicitly run:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 evaluations/run-lean-pilot.py --continue-unstarted
```

The fixed local ledger retains the original six-attempt allowance. Continuation
skips completed conditions and rejects any started/interrupted attempt needing review.
A separate process lock prevents concurrent controllers. It still checks the original
25% short-window and 3% weekly reserves before and during every model attempt.

## Completed comparison

After the user reported refreshed quota and authorized continuation, all six conditions
completed without retries. See [results](lean-pilot-2026-09-08.md) and
[sanitized measurements](lean-pilot-2026-09-08.json). All six passed the matched checks;
lean reduced worker tokens in each category. This allowance is now fully consumed.
