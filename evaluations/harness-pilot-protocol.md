# Six-attempt harness pilot (2026-09-08)

Authorized maximum: six attempts, five minutes each, one worker, GPT-6 Astra with
medium reasoning, 25% short-window and 3% weekly reserves. No replacement runs.
Compare three paired Python infrastructure fixes: duration parsing, job deduplication,
and capped retry delay. Specifications and initial source are identical within pairs.
Order: raw/harness, harness/raw, raw/harness. Graders run after the model finishes.

Raw uses the same subscription CLI, model, sandbox and configuration isolation, with
a direct task prompt. Harness uses the actual agent-work run function with an explicit
local-fixture tracker adapter, its normal checkpoint instructions, saved session and
attempt records. Both share quota and single-worker protections for this pilot.
No GitHub issue is fabricated or dispatched; the adapter replaces tracker reads only.
No project skills are added to either condition. Shared built-in/global discovery may
still exist; this is a controlled CLI baseline, not a measurement of every raw UI setup.

Record every started attempt, reported input/cached-input/output tokens, wall time,
completion, checkpoint update and external test results. Unknown usage is not zero.
Do not convert subscription tokens into dollars or exact quota percentage. Correctness
must be comparable before describing token reductions as efficiency improvements.

This tiny, synthetic, fresh-session pilot measures routine task overhead. It does not
measure interruption recovery, large-project quality, GitHub latency, multi-agent work,
Vercel skill value, or Vocabularium delivery speed. Do not extrapolate a general uplift.
Public noninteractive CLI reference: https://learn.chatgpt.com/docs/non-interactive-mode
