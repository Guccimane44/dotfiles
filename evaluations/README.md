# Small skills pilot protocol

Compare two bounded review tasks on identical source snapshots, once without project skills and once with the relevant pinned profile. Use fresh sessions, the same GPT-6 Astra version/medium effort, a five-minute ceiling per attempt, 25% quota reserve, one worker, and no retries. Maximum: four model attempts total. Alternate order across tasks to reduce order/cache bias. This tiny pilot is exploratory, not statistically significant.

Task A: review fixtures/review.html for concrete accessibility/interaction defects. Reference acceptance includes the unlabeled input, action implemented with a non-keyboard div, missing image alt, and removed focus outline. Accept equivalent valid findings, record false positives, and avoid demanding unrelated redesign.

Task B: review fixtures/Page.tsx for React/Next.js performance defects. Reference acceptance includes independent awaited requests serialized unnecessarily, derived state synchronized through an effect, and an input array mutated by sort during render. Accept alternatives supported by the code; do not infer measured latency improvement without running a real app.

Prompts: "Review the supplied file and report actionable findings with file/line evidence. Do not edit files, install dependencies, or browse. Keep the answer under 250 words." Skill-enabled conditions may use the relevant installed skill; record whether the agent actually read it. Fixtures are synthetic and intentionally small. Do not expose this scoring guide to the model.

Capture per attempt: model/CLI/skill revisions, source hash, outcome, duration, reported input/cached-input/output tokens, reviewer-scored valid findings, false positives, and intervention count. Count every started attempt against the cap. Interrupted usage is unknown, not zero. Cached input remains part of input and is reported separately; subscription quota cannot be inferred exactly from token counts.

Compare task-level results, not just pooled tokens: quality must be at least comparable before treating lower usage as an improvement. Inspect logs for accidental baseline skill loading. Stop and report incomplete results if quota is unavailable or reaches the reserve. Do not silently add more runs to obtain a preferred result.

## Recorded run

The user authorized the four-attempt pilot. See [partial results](skills-pilot-2026-09-07.md): two attempts completed, the third stopped at the weekly quota reserve, and the fourth was not started. Further attempts require a separate decision; do not automatically resume.

The user subsequently lowered the weekly reserve to 3% (five-hour reserve remains 25%) and authorized continuation. One same-session resume and the remaining baseline completed the four conditions in five attempts. The report preserves the interrupted attempt and explains why the React comparison is confounded.
