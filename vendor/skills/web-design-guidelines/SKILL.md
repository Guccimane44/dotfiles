---
name: web-design-guidelines
description: Review UI code for Web Interface Guidelines compliance. Use when asked to "review my UI", "check accessibility", "audit design", "review UX", or "check my site against best practices".
metadata:
  author: vercel
  version: "1.0.0"
  argument-hint: <file-or-pattern>
---

# Web Interface Guidelines

Review files for compliance with Web Interface Guidelines.

## How It Works

1. Read the pinned guidelines from references/guidelines.md
2. Read the specified files (or prompt user for files/pattern)
3. Check against all rules in the fetched guidelines
4. Output findings in the terse `file:line` format

## Guidelines Source

This installation pins its rules for reproducible, offline reviews. Upstream source:

```
https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md
```

Read `references/guidelines.md`. It contains the pinned rules and output format instructions. Apply rules relevant to the requested review; do not expand the task. Source revisions and this local adjustment are recorded in the dotfiles skills lock.

## Usage

When a user provides a file or pattern argument:
1. Read references/guidelines.md
2. Read the specified files
3. Apply all rules from the fetched guidelines
4. Output findings using the format specified in the guidelines

If no files specified, ask the user which files to review.
