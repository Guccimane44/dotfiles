# Matched lean versus standard pilot — 2026-09-08

Lean reduced worker input-plus-output tokens by **27.2%** while preserving the required deliverables in this pilot. Uncached input fell **9.3%**, cached input **28.9%**, and output **40.2%**. These are token measurements, not an exact subscription-cost reduction.

All six authorized attempts completed. Each condition received the same source, specification, supplied tests and required verification commands. No replacement attempts were run.

| Metric | Standard | Lean | Lean change |
|---|---:|---:|---:|
| Correct fixtures | 3 | 3 | +0.0% |
| Model responses | 15 | 11 | -26.7% |
| Input tokens | 250,431 | 182,622 | -27.1% |
| Cached input (subset of input) | 227,328 | 161,664 | -28.9% |
| Uncached input | 23,103 | 20,958 | -9.3% |
| Output tokens | 3,218 | 1,923 | -40.2% |
| Input + output | 253,649 | 184,545 | -27.2% |
| Model checkpoint-write actions | 6 | 0 | -100.0% |

| Fixture | Mode | Responses | Uncached input | Cached input | Output | Correct |
|---|---|---:|---:|---:|---:|---|
| duration | lean | 4 | 5,524 | 60,544 | 628 | Pass |
| duration | standard | 5 | 5,728 | 77,184 | 1,029 | Pass |
| dedupe | standard | 5 | 10,858 | 72,320 | 901 | Pass |
| dedupe | lean | 3 | 9,812 | 40,192 | 613 | Pass |
| retry | lean | 4 | 5,622 | 60,928 | 682 | Pass |
| retry | standard | 5 | 6,517 | 77,824 | 1,288 | Pass |

## Verdict

Keep lean as the default for bounded issue tasks. It reduced all three token categories in this sample, not just repeated cached context. Each pair passed the same provided tests; only task.py changed, and the tests remained unchanged. The six model-authored checkpoint-write actions in standard disappeared in lean, while controller-captured handoffs were present in all six runs. Model responses fell from 15 to 11. This supports the intended mechanism: less administration performed by the model.

The reduction is not entirely attributable to checkpoint writing: prompt differences, batching, inference variability and cache reuse also contribute. All runs still performed instruction-file discovery; that remains a possible future optimization, provided instruction precedence is preserved.

Do not promise 27% project-wide cost savings. This measures worker usage only; supervisor investigation/reporting cost is excluded. It also does not prove equal recovery quality during long interruptions. The next useful experiment would target that recovery tradeoff on a representative multi-file task, with a separate model-run allowance.

## Method and limits

GPT-6 Astra, medium reasoning, Codex CLI 0.153.4; worker code at the recorded continuation revision. Fresh sessions, one worker, five-minute ceilings, 25% short-window and 3% weekly reserves. The original quota block launched zero attempts; this continuation used the six authorized attempts. Pair order: lean/standard, standard/lean, lean/standard.

Required checks were inspected in the execution logs. The reference grader reran outside the model turn. Supplied test files were unchanged and changed files were inspected. No interruptions, retries, product registration or model/skill migrations were introduced. Both workflows used the current controller; standard retained the former checkpoint prompt.

Token categories are not interchangeable prices. Cached input is already included in input. No inference of exact subscription charges or quota percentage is supported. Execution time is not an optimization target for this report. Model-response counts come from distinct token-usage events, with sums checked against turn totals.

Three small tasks, one observation per condition: descriptive evidence, not a statistically reliable project-wide forecast. Cached-input differences can reflect warm-cache/order effects. Identical public tests constrain deliverables but do not establish broad correctness. Long-task interruption recovery is unmeasured. Do not compare these matched runs directly to the earlier raw pilot as if prompts and required artifacts were unchanged.

See [protocol](lean-pilot-protocol.md) and [sanitized measurements](lean-pilot-2026-09-08.json). Session identifiers remain local.
