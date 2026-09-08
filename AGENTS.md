# Project notes for agents

Deliberate decisions in this repo - do NOT silently revert them:

- `homebrew.onActivation.cleanup = "zap"` in `configuration.nix` is intentional. It forces the good habit of declaring every Homebrew package in the Nix config instead of installing things ad-hoc, which keeps the machine reproducible. Do not soften it to `uninstall` or `none`. Users are warned about its effect in README.md; this note is for anyone tempted to change the setting itself.
- Never commit `.no-mistakes/` validation evidence to this public repo. `.no-mistakes/` is gitignored; if a validation pipeline stages evidence into a branch, drop it before merging.

## Infrastructure workflow

Use GitHub issues for substantive infrastructure tasks and link PRs to their issue.
Read README.md for manual dispatch and recovery. Keep runtime logs, session IDs,
and credentials outside Git. Test changes with `python3 -m unittest discover -s tests -v`.
Routine implementation choices, verification, acceptance reviews, and bounded retry
approvals belong to the supervising agent. Do not ask the user to review routine
work. Ask the user for high-level architectural choices that materially change
system boundaries, technology/platform choices, data ownership, or long-term
trade-offs. Record review evidence before acceptance or another attempt. Preserve
quota, sandbox, repository-scope, and retry protections; an execution permission
that the environment actually requires must still be surfaced. Do not register
product repositories as part of dotfiles infrastructure work.

## Worker model routing

Use Luna for simple issue drafts, documentation, and bounded mechanical work; use
Astra for complex implementation, debugging, architecture, and analytical documents.
Set the issue's Work class or model label before dispatch; see docs/model-routing.md.
Do not spend a separate model turn classifying a task or silently retry on Astra.

## Optional expertise

For an unresolved harness-design decision, consult docs/optional-expertise.md;
retrieve one relevant pinned reference only when local evidence is insufficient.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
