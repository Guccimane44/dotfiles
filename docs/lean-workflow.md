# Lean worker workflow

Normal manual and scheduled runs now use the lean prompt. Manual runs can select
`--workflow standard` to retain the previous checkpoint guidance for comparisons.
Both modes use the same model, sandbox, quota, session, stop and review controls.
The mode is recorded in worker state. Historical pilot code explicitly selects standard.

Before launch, the controller records HEAD, branch, worktree status, a bounded checkpoint
excerpt and the previous attempt's handoff. These facts are supplied directly to the
worker. They reduce repeated discovery; they do not replace applicable project instructions
or inspection of changed code. Truncation is indicated for checkpoint/status excerpts.

Small tasks can implement and verify in one work phase without planning checkpoints or
a duplicate final checkpoint. Long tasks still write short decision/next-action checkpoints
at meaningful recovery boundaries. Stop requests retain their existing checkpoint behavior.
Relevant tests remain required; the optimization is not permission to reduce correctness.

The controller durably captures each progress/final agent message in a per-attempt handoff
file, marked unverified. It records the final attempt outcome separately from model claims.
On a crash, the last saved progress message may be partial; no message means no recovered
reasoning. Explicit milestone checkpoints and saved sessions remain necessary for long work.
Status, manual sync and scheduled workpads include the latest handoff. Handoffs never count
as verification or acceptance evidence. Publication follows the existing authorization.

No token-saving claim is established by local tests. Next evaluation should compare lean
and standard modes with identical required code/tests, record model response counts,
uncached/cached input and output separately, and then test interrupted multi-file work.
Runtime is not an optimization target. No extra model-run budget is implied by this file.
