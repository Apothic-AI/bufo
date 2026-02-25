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
- Hardened ACP session update mapping with typed/legacy event normalization, including tool lifecycle, mode, slash-command, and state events.
- Added test-ready app injection points (custom bridge factory, optional watcher disable, optional update-check disable) for deterministic runtime testing.
- Added extensive end-to-end and integration coverage:
  - 12 Textual app e2e tests (launcher, resume, settings/sessions modals, prompt/shell flows, permission flows, tool lifecycle rendering, session navigation).
  - 6 CLI e2e/integration tests.
  - 6 ACP session-update mapping tests.
  - Existing 4 core persistence/protocol tests retained.
- Full automated suite currently passing: 28 tests total.

## In Progress
- Runtime hardening and UX polish for richer tool/diff timelines and broader ACP ecosystem compatibility.

## Next
- Expand UI coverage tests (screen interaction, session navigation, permission/diff flows).
- Add richer ACP event mapping for additional provider-specific payload variants.
- Improve web-serve command compatibility handling across textual-serve versions.
