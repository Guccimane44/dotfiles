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
