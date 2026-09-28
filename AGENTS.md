# Repository Guidelines

## Project Structure & Module Organization

This repository distributes Claude Code plugins. The root `.claude-plugin/marketplace.json` lists the published plugins. Each `plugins/<plugin-name>/` directory contains its own `.claude-plugin/plugin.json`; hook plugins keep shell code in `hooks/` alongside `hooks.json`, while command plugins keep instructions in `skills/<skill-name>/SKILL.md`. Some plugins also have `scripts/`; `java-formatter` includes Java source and `eclipse-formatter.xml`. There is no shared application source tree, asset directory, or test suite.

## Build, Test, and Development Commands

There is no repository-wide build command. Use `claude --plugin-dir ./plugins/java-formatter` to load one plugin locally, or add another `--plugin-dir` flag to test interactions. Run `find plugins -name '*.sh' -exec bash -n {} +` to check shell syntax. Run `jq empty .claude-plugin/marketplace.json plugins/*/.claude-plugin/plugin.json plugins/*/hooks/hooks.json` to validate plugin and hook JSON. The Java formatter requires `jbang`; its Java version is pinned in `.tool-versions`.

## Coding Style & Naming Conventions

Use lowercase, hyphenated plugin directories (for example, `block-git-push`), matching the name in each `plugin.json` and the marketplace entry. Keep skill files named `SKILL.md` and hook scripts descriptive, such as `hooks/block-git-push.sh`. Follow the existing four-space indentation in JSON and shell blocks. Quote shell variables and preserve the existing Bash conventions in each script. For Java formatter changes, use the checked-in Eclipse formatter settings rather than introducing another style.

## Testing Guidelines

No test framework or coverage threshold is configured. For hook changes, run the syntax and JSON checks above, then load the plugin with `claude --plugin-dir` and exercise both an expected match and a non-match using representative hook input. Check the resulting JSON and exit status. For skill changes, invoke the skill locally and verify its instructions produce the intended behavior.

## Commit & Pull Request Guidelines

Recent commits use short Korean subject lines that name the affected plugin and the change; there is no enforced Conventional Commits prefix. Follow that pattern, for example, `block-git-push 훅 오탐지 수정`. In pull requests, describe the affected plugin, behavior change, local checks, and any required tools or environment variables. Link a related issue when one exists; include sample hook input and output for behavior changes.
