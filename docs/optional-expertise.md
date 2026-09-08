# Optional external expertise

Ryan Lopopolo's [Harness Engineering](https://github.com/lopopolo/harness-engineering)
is pinned at `226c8d35fb6ea3ed55467753dba6dea2b5fd5778` under
`vendor/expertise/harness-engineering`. The adjacent lock records upstream provenance
and every file hash. Original files, attribution, COPYING.md, and licenses are retained
unchanged. This is an external reference snapshot, not installed skill instructions.

Consult it only when local evidence leaves a concrete harness decision unresolved,
or when the user requests its perspective. Do not read the corpus during ordinary
coding, documentation, or issue drafting. It is not injected into worker prompts or
installed in global/project skill directories. No network or model call is needed
for retrieval; text consumes context only when a supervising agent or worker reads it.

1. Read the target's instructions and evidence; name the unresolved decision.
2. Run `agent-work expertise index`, then `agent-work expertise read AGENTS.md`.
3. Select one route below. Read another only for a distinct unresolved concern.
4. Apply only relevant ideas under local authority. Record the source path/revision,
   decision, and actual verification in the existing issue/handoff; avoid duplicate reports.

| Decision | Starting reference |
| --- | --- |
| Context overhead and selective retrieval | docs/just-in-time-context/README.md |
| Cost and outcome measurement | docs/effectiveness/README.md |
| Evaluation design | evals/README.md |
| Recovery lessons and repeated failures | docs/feedback/README.md |
| Verification and release identity | docs/proof/README.md |
| Permissions and ownership | docs/authority/README.md |
| Model capability assumptions | docs/fixed-worker/README.md |
| Improve one observed job or review a repository | playbooks/README.md, then the selected playbook |

For playbooks, also read playbooks/AGENTS.md. Playbooks are editorial syntheses,
not proven procedures or performance guarantees. They do not authorize model trials,
new tools, subagents, product registration, or changes to quota/retry/publication policy.
Simple excerpts and summaries fit Luna; complex design and evaluation decisions use Astra.

Example: `agent-work expertise read docs/just-in-time-context/README.md --lines 80`.
The reader limits each response to 200 lines and 16,000 excerpt characters; use `--start`
for more only when needed. It verifies the full local snapshot before returning text.
For a worker, put the specific reference command and unresolved question in the task,
not the whole library. Updates require a deliberate reviewed pin/hash change and a new
runtime release; retrieval never follows upstream HEAD or executes upstream helpers.
