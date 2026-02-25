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
- Fixed ACP session-scoped RPC compatibility for agents that require `sessionId` on prompt/mode/cancel calls (validated against `yolo-acp` in `../yolo-v2`).
- Added test-ready app injection points (custom bridge factory, optional watcher disable, optional update-check disable) for deterministic runtime testing.
- Added extensive end-to-end and integration coverage:
  - 22 Textual app e2e tests (launcher, resume, settings/sessions modals, prompt/shell flows, permission flows, tool lifecycle rendering, protocol-gating, session navigation, copy/selection, watcher refresh).
  - 6 CLI e2e/integration tests.
  - 8 ACP session-update mapping tests.
  - 7 ACP bridge tests (session payloads + strict-session regression + fail-fast process-exit behavior).
  - Existing 4 core persistence/protocol tests retained.
- Added strict-session regression test to ensure `session/new` followed by prompt always sends `sessionId` (covers the real `yolo-acp` failure mode: `Missing or invalid sessionId`).
- Updated `README.md` to reflect current CLI surface, ACP session-scoped compatibility behavior, and canonical test command.
- Implemented UI/runtime fixes requested in current review:
  - Selection auto-copy on mouse selection with in-app "copied" notification.
  - Slash command popup suggestions with keyboard cycling and apply behavior.
  - Session strip with per-session tab buttons and explicit "New Session" action.
  - Watcher-driven file tree auto-refresh hardening (directory events + multi-callback manager).
  - Removed manual tree refresh button; file tree now relies on automatic watcher refresh.
  - Structured JSONL runtime logging (`--log-level`, `--log-file`, `BUFO_LOG_LEVEL`, `BUFO_LOG_FILE`).
- Added/expanded tests for those behaviors:
  - New e2e coverage for slash popup, session tabs/new-session flow, selection copy helper, and watcher-triggered tree refresh.
  - New runtime logging tests for JSONL output + env/flag configuration.
- Fixed drag-selection in conversation/terminal logs by introducing a selectable RichLog wrapper that emits selection offsets and supports selected-text extraction/highlighting.
- Added regression coverage ensuring timeline logs expose mouse selection offsets (guards clipboard auto-copy behavior).
- Fixed runtime logging sink behavior so `--log-file` is created deterministically at startup (even at default warning level) and emits a `logging.configured` JSONL event.
- Switched clipboard copy path to system clipboard via `pyperclip` with explicit fallback notification when a host clipboard backend is unavailable.
- Added tests for log file creation at default level and clipboard success/fallback behavior.
- Fixed ACP UI compatibility issues seen with strict/nested ACP servers:
  - Parsed nested `sessionUpdate` payloads (`agent_message_chunk`, `current_mode_update`, `available_commands_update`) into human-readable timeline output.
  - Registered slash-command suggestions from `availableCommands` updates (with `/` prefix normalization).
  - Displayed agent `name` in the conversation header instead of internal `identity` (`__custom__` no longer shown as label).
  - Routed agent stderr to structured logs only (no stderr spam in the chat timeline).
- Added regression tests covering nested ACP update parsing, custom agent name rendering, stderr timeline suppression, and yolo-style command/mode updates.
- Fixed launch freeze conditions for misconfigured/unsupported agent commands:
  - ACP bridge now monitors subprocess exit and cancels pending RPC waits immediately.
  - Startup/control RPCs use bounded timeouts and raise explicit errors when a process exits or fails to respond.
  - Added stderr-tail context to bridge exit errors for faster diagnosis.
- Added regression tests for early process-exit fail-fast behavior and cancelled-RPC exit handling.
- Corrected catalog/protocol behavior for Codex CLI:
  - Updated built-in descriptor to reflect MCP server mode (`protocol = "mcp"`, `codex mcp-server`).
  - Enforced ACP-only launches in app runtime; non-ACP entries are rejected with a clear user-facing error.
- Removed duplicate runtime logger initialization from CLI entrypoints (prevents duplicate `logging.configured` lines at startup).
- Added e2e coverage for unsupported-protocol launch rejection.
- Fixed project file-browser rendering/refresh regressions:
  - Replaced flat root rendering with true hierarchical tree rendering.
  - Directory nodes are now expandable/collapsible as expected.
  - Stabilized refresh ordering to avoid visual path shuffling/flicker on auto-refresh.
  - Scoped tree worker-group IDs per widget instance to avoid cross-session refresh worker collisions.
- Added e2e regression test for expandable directory nodes and nested child placement.
- Increased default ACP startup/control RPC timeout from 10s to 30s for slower agents.
- Improved conversation rendering quality for provider session updates:
  - Added normalized parsing for `sessionUpdate=plan`, `tool_call`, and `tool_call_update`.
  - Added markdown rendering support for message/detail blocks (including fenced code).
  - Added collapsed-by-default tool detail handling with slash-command expansion/collapse controls.
- Added regression tests for plan/tool-call normalization and collapsed/expandable tool details in the UI.
- Full automated suite currently passing: 54 tests total.

## In Progress
- Runtime hardening and UX polish for richer tool/diff timelines and broader ACP ecosystem compatibility.

## Next
- Expand UI coverage tests (screen interaction, session navigation, permission/diff flows).
- Add richer ACP event mapping for additional provider-specific payload variants beyond current nested `sessionUpdate` coverage.
- Improve web-serve command compatibility handling across textual-serve versions.
