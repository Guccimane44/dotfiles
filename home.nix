{ config, lib, pkgs, user, ... }:

let
  dotfiles = "${config.home.homeDirectory}/.dotfiles";
  outOfStore = relativePath:
    config.lib.file.mkOutOfStoreSymlink "${dotfiles}/${relativePath}";
  optionalFile = relativePath: target:
    lib.optionalAttrs (builtins.pathExists "${dotfiles}/${relativePath}") {
      "${target}".source = outOfStore relativePath;
    };
in

{
  home.username = user;
  home.homeDirectory = "/Users/${user}";
  home.stateVersion = "24.11";
  home.sessionPath = [ "/nix/var/nix/profiles/default/bin" ];
  home.packages = with pkgs; [
    (pkgs.writeShellScriptBin "agent-work" ''
      export PATH="${pkgs.git}/bin:/opt/homebrew/bin:$PATH"
      runtime="$HOME/.local/share/agent-work/launch.py"
      if [ -f "$runtime" ]; then
        exec ${pkgs.python3}/bin/python3 "$runtime" "$@"
      fi
      exec ${pkgs.python3}/bin/python3 "${dotfiles}/scripts/agent-work.py" "$@"
    '')
    (pkgs.writeShellScriptBin "codex" ''
      cli="/Applications/ChatGPT.app/Contents/Resources/codex"
      if [ ! -x "$cli" ]; then
        echo "Install the ChatGPT desktop app to provide Codex CLI." >&2
        exit 1
      fi
      exec "$cli" "$@"
    '')
    python3
    # cli i use constantly
    ripgrep   # fast search
    fd        # fast find
    fzf       # fuzzy finder
    jq        # json on the command line
    lazygit
    neovim
    # the font everything renders in
    nerd-fonts.hack
  ];
  fonts.fontconfig.enable = true;
  home.sessionVariables.EDITOR = "nvim";

  programs.zsh = {
    enable = true;
    autosuggestion.enable = true;      # ghost text from history
    syntaxHighlighting.enable = true;  # commands turn green when valid
    initContent = ''
      bindkey '^f' autosuggest-accept
    '';
    shellAliases = {
      ".." = "cd ..";
      add = "git add .";
      push = "git push";
      pull = "git pull";
      m = "git switch main";
      cc = "claude --dangerously-skip-permissions";
      co = "codex --full-auto";
    };
  };

  programs.starship = {
    enable = true;
    settings = {
      add_newline = false;
      format = "$directory$git_branch$git_status$cmd_duration$line_break$character";
      character = {
        success_symbol = "[❯](purple)";
        error_symbol = "[❯](red)";
      };
      cmd_duration.format = "[$duration]($style) ";
    };
  };

  # Edit-in-place: link authored files from this repo when they exist.
  # Missing optional files are skipped until they are added to the repo.
  home.file = lib.mkMerge [
    (optionalFile "home/.config/wezterm" ".config/wezterm")
    (optionalFile "home/.config/nvim" ".config/nvim")
    (optionalFile "home/.config/herdr/config.toml" ".config/herdr/config.toml")
    (optionalFile "home/.claude/settings.json" ".claude/settings.json")

    # Keep Pi's credential and runtime state local by linking only authored files and directories.
    (optionalFile "home/.pi/agent/themes" ".pi/agent/themes")
    (optionalFile "home/.pi/agent/extensions" ".pi/agent/extensions")
    (optionalFile "home/.pi/agent/models.json" ".pi/agent/models.json")
    (optionalFile "home/.pi/agent/settings.json" ".pi/agent/settings.json")

    (optionalFile "home/AGENTS.md" ".claude/CLAUDE.md")
    (optionalFile "home/AGENTS.md" ".codex/AGENTS.md")
    (optionalFile "home/AGENTS.md" ".config/opencode/AGENTS.md")
  ];
}
