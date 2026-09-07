# Vercel skills pilot: partial results

Date: 2026-09-07. **Verdict: keep skills selective; this pilot does not demonstrate a general quality or quota-efficiency gain.**

All three pinned skills passed the supplied Skill Creator validator with temporary PyYAML 6.0.2. The dependency was installed outside global Python and is not a scheduler runtime dependency.

## What ran

The approved cap was four fresh GPT-6 Astra/medium attempts: two identical task pairs, with and without project skills. Two attempts completed. The third was stopped when the shared weekly quota reached the 25% reserve; the fourth never started. There were no controller retries, paid API fallback, or reset-credit consumption.

Each attempt used an isolated Codex home with the existing subscription login, a fresh workspace, the same CLI/settings, a five-minute deadline, and read-only sandboxing. Both web runs received the same prompt and source bytes. The scoring rubric was not placed in the workspaces. The web pair ran baseline first; the planned React pair reversed that order but did not complete. Account-level caching and other sessions' quota use were not controlled.

## Completed web-review pair

| Measure | No project skill | Pinned web-review skill |
|---|---:|---:|
| Predefined defects found | 4/4 | 4/4 |
| Additional valid findings | 1 | 1 |
| Observed false positives | 0 | 0 |
| Duration | 28.07 s | 28.95 s |
| Reported input tokens | 46,503 | 49,738 |
| Cached input (included above) | 39,424 | 43,264 |
| Uncached input (difference) | 7,079 | 6,474 |
| Output tokens | 500 | 561 |
| Human interventions | 0 | 0 |

Both found the missing input label, inaccessible clickable div, missing image alternative text, and suppressed focus indicators. Both also found the undefined action handlers. Scoring was a manual, unblinded source review; it was not an independent production-quality evaluation.

The skill run read both its entry point and pinned guideline file. The baseline's recorded commands did not read a skill. Both preserved all workspace files. The skill run used **7.0% more total input** and **12.2% more output**, while uncached input was **8.5% lower**. Runtime was 0.88 seconds longer. These are observations from one pair, not estimates of expected project performance. Different cache reuse prevents treating the uncached-input reduction as proven skill savings. Token counts do not map directly to subscription quota or financial cost.

## Interrupted React condition

The third attempt read the React skill and the relevant parallel-fetching, derived-state, and immutable-sort references. The quota guard stopped it after 31.27 seconds; it produced no final answer. No quality score is assigned. The React baseline was not started.

The native session log retained a partial cumulative snapshot: 51,215 input tokens, including 44,928 cached, and 269 output tokens. It may omit usage still in flight when the process was stopped. The complete interrupted-attempt total remains unknown; this is not counted as a zero-cost attempt.

## Decision

Keep the profiles pinned and opt-in for relevant projects. They provide inspectable engineering conventions, and actual skill reading was verified, but this sample showed no extra defects found on the completed task. Do not expand global instructions or add workers on the assumption that skills save quota.

Herdr's usability, checkpoint recovery, and the scheduler's effect on full-project delivery were not compared here. This experiment measures only the marginal effect of the selected skills on small static reviews. It cannot establish how much Kun's complete methodology improves GPT-6 development.

A complete React comparison and broader task sample would need a separate quota decision after sufficient quota is available. The controller will not resume this pilot automatically. Preserve these incomplete results rather than replacing them with a cleaner-looking rerun.

Machine-readable metrics and source hashes: `skills-pilot-2026-09-07.json`. Raw transcripts, prompts, isolated workspaces, and the executed helper remain local under `~/.local/state/agent-work/evaluations/skills-pilot-2026-09-07/`; credential references and session identifiers are not included in the published summary.
