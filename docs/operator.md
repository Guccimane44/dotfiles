# Operator workspace and project skills

Open the dedicated, already-configured Herdr session:

```sh
agent-work console open
```

Use the mouse to switch between review, scheduler status, and worker output. Closing/detaching Herdr leaves the scheduler's policy unchanged. These panes display the controller and its logs; they are not interactive attachments to the headless Codex worker. Historical error-log lines are not proof of a current failure. No additional agents start when you open this workspace.

For a fresh session, run `agent-work console workspace` from its Herdr pane. The command requires `HERDR_ENV=1` and the named `dotfiles` session. Wide terminals get split panes; narrow terminals get tabs. It refuses duplicate/stale layouts instead of silently replacing user panes. If a previously created layout was deleted, inspect the session before deleting its local `~/.local/state/agent-work/herdr-layout-*.json` marker and rebuilding.

```sh
agent-work console status
agent-work console review 7
agent-work console pause 7       # add the issue pause label
agent-work console pause         # pause all dispatch
agent-work console resume 7      # explicitly authorize ONE further attempt
agent-work scheduler enable      # lift the global pause
```

Review saved work before resume. Resume preserves global pause and other blocking labels. The existing one-worker lock and quota checks remain authoritative. When Herdr is attached: Ctrl-B then Q detaches; the mouse supports navigation and resizing. Optional shortcuts: Ctrl-B then Alt-S opens status, Alt-P requests a global pause, and Alt-G opens Git review. Ordinary commands above are the fallback if your terminal intercepts a shortcut.

Herdr 0.8.2 remains Homebrew-managed by the Nix declarations. Only `config.toml` is linked into dotfiles; runtime logs and sessions stay local. Background update/manifest checks are disabled for deliberate package updates. Its complete native agent-control skill is not installed globally, because our scheduled workers must not launch their own helpers or control another session.

## Pinned skills

`skills-lock.json` records upstream revisions, file hashes, profiles, and the documented offline web-rule adjustment. `vendor/skills` holds reviewed source, outside agent discovery paths. React-specific skills are not installed globally or activated on Nix-only tasks.

```sh
agent-work skills verify
agent-work skills install --profile web-review --project /absolute/project
agent-work skills install --profile react --project /absolute/project
```

The web-review profile contains web-design-guidelines. The React profile also contains vercel-react-best-practices and vercel-composition-patterns. The installer copies into `.agents/skills` and records project provenance in `.agents/dotfiles-skills.json`. It refuses overwrites and rejects escaped destinations or changed vendor files. Review updates deliberately; do not simply update the lock to accept unknown changes. The project can commit its installed skills and provenance so future worktrees inherit the same files. No new skills CLI or Node runtime is required for installation.

Skills become available on the next Codex turn/session in the selected project. Codex App Server discovery was verified for all three enabled skills in an isolated infrastructure profile. Behavioral usefulness and worker invocation still require representative task evaluation. React/Next.js version-specific advice must match the project's actual dependencies; guidelines do not authorize extra dependencies or scope changes.

An isolated installed profile is at `~/.local/state/agent-work/skill-profiles/react`. It is a discovery fixture, not a registered product project. The scheduler allowlist remains dotfiles only.

## Evaluation and next project

See `templates/agent-project` for onboarding and `evaluations/README.md` for the bounded comparison. Benchmark runs require the operator's chosen quota budget. Preserve failed and interrupted attempts in the measurements and report missing usage as unknown. No percentage savings claim follows from a smoke test.
