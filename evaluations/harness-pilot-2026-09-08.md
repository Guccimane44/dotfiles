# Harness pilot results — 2026-09-08

All six authorized attempts completed. Both conditions passed all three external fixture graders. On these small, uninterrupted tasks, the harness increased reported input-plus-output tokens by **50.0%** and elapsed time by **88.4%**.

| Task | Condition | Correct | Input | Cached input¹ | Output | Seconds |
|---|---|---:|---:|---:|---:|---:|
| duration | raw | Pass | 63,879 | 55,552 | 683 | 31.5 |
| duration | harness | Pass | 83,810 | 73,216 | 1,450 | 58.2 |
| dedupe | harness | Pass | 99,862 | 89,728 | 1,235 | 53.1 |
| dedupe | raw | Pass | 63,870 | 55,680 | 637 | 31.4 |
| retry | raw | Pass | 63,995 | 55,424 | 769 | 35.1 |
| retry | harness | Pass | 102,485 | 95,360 | 1,834 | 73.3 |

¹ Cached input is a subset of input; it is not added again. Reported reasoning-output fields are retained in the JSON and are not added to output totals.

| Total | Raw | Harness | Change |
|---|---:|---:|---:|
| Input tokens | 191,744 | 286,157 | +49.2% |
| Cached input tokens | 166,656 | 258,304 | +55.0% |
| Uncached input tokens | 25,088 | 27,853 | +11.0% |
| Output tokens | 2,089 | 4,519 | +116.3% |
| Input + output | 193,833 | 290,676 | +50.0% |
| Elapsed seconds | 97.975 | 184.565 | +88.4% |

## Interpretation

This pilot does not support adopting the full workflow to save tokens on tiny standalone fixes. Use direct, bounded work for those. The harness produced durable checkpoints in all three runs and adds review/recovery controls, which remain useful for longer issue-driven work; this experiment did not quantify their benefit.

Uncached input rose only 11.0%, illustrating why total token growth is not a subscription-cost estimate. No dollar or exact quota savings can be inferred. Model: gpt-6-astra; CLI: codex-cli 0.153.4. Six fresh sessions, medium reasoning, alternating pair order, five-minute ceiling, one worker and unchanged 25% short-window / 3% weekly reserves. No retries or extra model attempts.

The harness condition used the actual agent-work worker with a local fixture tracker adapter, not the full GitHub scheduler. The raw condition shared its model, sandbox, configuration isolation and budget monitoring. No project skills were installed. Built-in/global discovery was not isolated into a new account. Inputs were identical within pairs; code review found task-scoped changes. The harness retry fixture also added a reusable four-test test_task.py; the other five workspaces had no nonignored extra files. This additional verification artifact contributes to the work/time difference and may have maintenance value beyond the grader score. External graders were added after the turns.

Limitations: three synthetic tasks, one observation per condition, no randomization beyond alternating order, cache/order effects, no interruption or multi-agent experiment, and no Vocabularium workload. Correctness here means passing the specified graders plus scoped code inspection, not universal correctness. Do not extrapolate project-level improvement percentages.

Next evidence needed: a separately budgeted interruption/recovery comparison on representative multi-file tasks before making any project-wide efficiency claim. See [protocol](harness-pilot-protocol.md) and [machine-readable results](harness-pilot-2026-09-08.json).
