# Project onboarding checklist

This template does not register a repository or enable dispatch.

- Record repository owner/name, default branch, stack versions, and project scope.
- Define one reproducible setup command plus existing build, typecheck, test, and UI verification commands. Mark unavailable checks explicitly.
- Choose a skill profile only when the stack/task warrants it; install and commit the chosen files and provenance.
- Keep project instructions short and specific. Put product decisions in durable project documentation; reference them from issues.
- Create an initial bounded issue with outcome, in-scope files, exclusions, acceptance checks, and human decisions needed.
- Validate manual dispatch and same-session recovery in a disposable task before requesting scheduler allowlist changes.
- Set concurrency, quota reserve, attempt deadline, retry authority, and publication policy explicitly.
- Validate the exact proposed commit before publishing a PR; preserve human merge authority.

Vocabularium is intentionally not registered by this infrastructure template.

Fill in `project.json` and run `agent-work project validate /absolute/path/project.json`.
The supplied template is intentionally incomplete. Passing validates structure only;
you must still execute the declared setup/checks and demonstrate recovery. Keep dispatch
disabled during onboarding. See the dotfiles `docs/reviews.md` for review evidence format.
