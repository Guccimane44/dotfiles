# Dotfiles and issue-based development

Personal Apple Silicon macOS configuration plus a bounded GitHub/Codex workflow. Workers use GPT-6 Astra through the existing ChatGPT login. The opt-in scheduler runs on this Mac only. There is no paid API fallback, automatic code publication, merge, or deployment.

## Machine setup

`flake.nix` and `flake.lock` select Nix inputs. `configuration.nix` declares macOS and Homebrew settings; `home.nix` declares shell tools and launchers.

**Homebrew cleanup is intentionally `zap`.** Applying this configuration removes Homebrew packages/casks not declared in it. Review the lists before activation. Nix input locking does not pin Homebrew application versions.

The `codex` launcher uses the CLI bundled at `/Applications/ChatGPT.app/Contents/Resources/codex`; install/update the desktop app separately. Its version follows the app, not the Nix lockfile. The launcher fails clearly if the app is missing. `agent-work` uses Nix's Python; GitHub CLI is declared under Homebrew. Optional editor and agent configuration paths are skipped until their source files exist. Existing user Codex configuration and credentials are not overwritten.

Apply deliberate configuration changes with the existing nix-darwin installation:

```sh
sudo darwin-rebuild switch --flake ~/.dotfiles#mac
```

## Start here

```sh
agent-work quota
agent-work prepare OWNER/REPO 123 --checkout /absolute/path/to/clean/repo
agent-work run OWNER/REPO 123
agent-work status OWNER/REPO 123
agent-work sync OWNER/REPO 123              # preview the exact outgoing workpad
agent-work sync OWNER/REPO 123 --publish    # update one issue comment
```

Before Nix activation, `~/.dotfiles/scripts/agent-work` also works with Python 3, GitHub CLI, and the desktop app present.

1. Create one bounded GitHub issue using the template. Specify observable acceptance criteria and verification.
2. Prepare it from a clean committed checkout with an origin matching the requested GitHub repository. This fetches the remote default branch and creates `agent/issue-N` in an isolated worktree.
3. Run it explicitly. The launcher checks issue state and quota, then starts or resumes the saved Codex session. Workers must update `.agent-work/checkpoint.md` after milestones.
4. Review local results and tests. Preview the workpad before publishing it; do not include secrets or unrelated private information.
5. Commit selected files, push the branch, and create a draft PR linked with `Closes #N` when authorized. Neither the launcher nor its worker publishes code automatically. Check for new issue feedback before publishing.
6. Review/merge explicitly. Keep the workspace until accepted; there is no automatic cleanup of partial work.

You can ask your supervising agent to perform these steps; you do not have to remember the commands. It must obtain authorization for external publication if the current task does not already provide it.

## Single-Mac scheduler (Phase 2)

See [scheduler operations](docs/scheduler.md) for activation, issue controls, explicit retry approval, and limits. The following manual-run controls still apply to foreground runs.

## Pause and recovery

- Press Ctrl-C in the running launcher to stop. Partial edits, checkpoints, logs, and the saved session ID remain.
- `agent:paused`, `agent:blocked`, and `agent:waiting-quota` labels prevent the next dispatch. Labels and comments are read **before each run**, not continuously. A label change does not stop an already running worker.
- To intervene, stop the foreground run first, edit the issue/comment, remove the blocking label when ready, then run again. The same session receives a fresh issue snapshot and human comments.
- `agent-work run` reuses the saved session ID. It never silently creates a fresh session after an unsuccessful attempt without an ID. Missing sessions/workspaces need deliberate investigation.
- State defaults to `~/.local/state/agent-work/OWNER/REPO/N`; set `AGENT_WORK_STATE` to relocate it **before preparing tasks**. Switching state roots creates independent lock domains; use one root on this machine.
- A global process lock allows one operation/worker at a time. Process exit releases it. It does not coordinate other computers, external Codex sessions, or other tools.
- Checkpoints are locally durable and synchronized to GitHub only by explicit `sync --publish`. Checkpoint quality relies on the worker following the prompt. A hard kill can interrupt its latest write. Inspect the checkpoint plus Git state before trusting a recovery.
- A stale `running` status after a hard process kill is historical state, not proof a worker remains alive. Check processes before restarting; do not run duplicate workers manually.

## Cost controls and limits

Default: GPT-6 Astra, medium reasoning, one worker, 20-minute run ceiling, and at least 15% remaining in each reported quota window at launch. Override with `--minutes 5 --reserve 25` when needed. The quota check uses Codex App Server account reads and does not start an LLM turn. Missing quota data blocks launch. No quota-reset credits are consumed.

The launcher removes an inherited `OPENAI_API_KEY`, requires ChatGPT authentication, and ignores the user's base config for worker invocation so model/effort are explicit. It uses workspace-write sandboxing and refuses requests needing approval in the noninteractive worker. It does not bypass the sandbox, install tools, or change host configuration for workers. Missing tools/permissions should be reported for the supervisor to resolve.

**The reserve is a preflight check, not a hard per-run spending cap.** Other sessions share account limits. A running worker can exhaust quota; it stops and preserves state rather than retrying repeatedly. There is no hard token-budget enforcement. The optional scheduler adds persisted quota waiting and periodic monitoring. Logs include token usage for completed turns; interrupted-turn accounting may be incomplete. Logs and sessions stay local and may contain sensitive task data.

## Validate infrastructure

```sh
python3 -m unittest discover -s tests -v
python3 -m py_compile scripts/agent-work.py
```

The tests use fake agents and temporary Git repositories, with no model calls. They cover session reuse after failure, work preservation, concurrency exclusion, issue pause state, quota reserve, path validation, and private atomic state writes.

See [the staged rollout](docs/rollout.md). Vocabularium is not registered or modified by this setup.
