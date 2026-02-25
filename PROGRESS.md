# Bufo Build Progress

## Constraints
- Cleanroom implementation only. No code copied from sibling repositories.

## Completed
- Parsed `README.md` and `../BUFO_PROJECT_SPEC.md` into implementation requirements.
- Established cleanroom constraint in project plan.
- Built a full cleanroom `src/bufo` package with:
  - CLI command surface (`run`, `serve`, `acp`, `settings-path`, `about`, `replay`).
  - Textual app shell, store screen, mode-backed main sessions, settings/sessions modals.
  - Conversation orchestrator with slash commands, prompt resource expansion, shell routing.
  - JSON-RPC transport layer and ACP stdio bridge scaffold.
  - Persistent shell subsystem (PTY-backed), command risk analyzer, permission modal flow.
  - Agent registry schema + built-in provider catalog (15 descriptors), custom override loading.
  - SQLite session metadata store and project-scoped JSONL histories.
  - Filesystem scanner, ignore filter, shared watcher manager, project tree panel.
  - Diff rendering helper, telemetry + notifications + version check utilities.
- Added core cleanroom tests for settings/session store/prompt resources/JSON-RPC.
- Updated packaging metadata (`pyproject.toml`) and `README.md`.

## In Progress
- Runtime hardening and UX polish for deeper ACP interoperability and richer tool/diff timelines.

## Next
- Expand UI coverage tests (screen interaction, session navigation, permission/diff flows).
- Add richer ACP event mapping (tool lifecycle states, plan blocks, mode updates).
- Improve web-serve command compatibility handling across textual-serve versions.
