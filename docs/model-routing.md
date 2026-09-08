# Worker model routing

Both manual and scheduled workers use the same deterministic selector. No model
call is spent classifying work. Luna means `gpt-5.6-luna`; Astra means `gpt-6-astra`.
Both retain medium reasoning, four shared slots, and existing quota/retry controls.

Choose **Work class** in the issue form: Simple documentation, Simple issue writing,
or Simple bounded work selects Luna; Complex work selects Astra. The supervising
agent makes this selection while defining the task. Analytical documents, design
choices, security work, and difficult debugging belong to Complex work even when
the deliverable is prose. Unclassified new tasks default to Astra.

For existing issues, use one label: `agent:model:luna` or `agent:model:astra`.
Labels override the form. Two model labels block dispatch. A malformed/duplicate
Work class field also blocks dispatch unless explicitly overridden by a model label.
Manual runs accept `--model luna` or `--model astra`, overriding issue routing.
Otherwise, an unclassified resumed task retains its last recorded model; legacy
sessions without model records use Astra. Explicit reclassification can change
the next approved attempt's model while retaining the saved session and workspace.
Model changes do not authorize retries. Scheduled issue edits stop active work under
the existing feedback rules. No automatic fallback or escalation to Astra occurs.

Each reserved attempt records its selected model and selection reason alongside
usage, including launch failures. Workpads show the last attempt's selected model;
older records are marked unrecorded. Model availability errors require investigation,
not a paid fallback. Selection is a request to Codex, not independent proof of server
execution. Routing tests use fake workers; no live Luna quality/cost claim is made.

Workers draft issue text locally; existing external-publication restrictions still
apply. A supervisor publishes an authorized draft. The form change appears on GitHub
once merged into the default branch; model labels work with the deployed runtime now.
