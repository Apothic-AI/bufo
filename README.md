# bufo

`bufo` is a cleanroom terminal-first orchestration framework for ACP-compatible coding agents.

It provides one Textual-based control plane for agent prompting, persistent shell execution, session resume, settings, and local metadata persistence.

## Current capabilities

- Agent store / launcher with built-in catalog descriptors and custom overrides.
- Mode-backed multi-session runtime with resumable metadata in SQLite.
- Conversation workspace that merges agent prompting, slash commands, and persistent shell commands.
- JSON-RPC transport + ACP bridge for process-based agents over stdio.
- Permission modal workflow, diff rendering helpers, command risk analysis.
- Project-scoped prompt/shell histories and XDG-based config/state/data layout.
- Project tree panel with scanner + watcher-driven refresh.

## CLI

```bash
# default run command
bufo

# launch directly into an agent
bufo run --agent codex-cli

# open launcher/store explicitly
bufo run --store

# run a custom ACP command
bufo acp "my-agent --acp" --name "My Agent"

# print settings location
bufo settings-path
```

## Notes

- Browser serving is wired through `textual-serve` when available in the environment.
- Runtime currently requires Textual and ACP tooling installed in your local environment.
