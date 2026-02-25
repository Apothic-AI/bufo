# bufo

`bufo` is a terminal-first, web-second orchestration framework for ACP-compatible AI agents.

It provides one Textual-based control plane for agent prompting, persistent shell execution, session resume, settings, and local metadata persistence.

## Current capabilities

- Agent store / launcher with built-in catalog descriptors and custom overrides.
- Mode-backed multi-session runtime with resumable metadata in SQLite.
- Conversation workspace that merges agent prompting, slash commands, and persistent shell commands.
- JSON-RPC transport + ACP bridge for process-based agents over stdio.
- ACP session-scoped compatibility for strict servers: negotiated `sessionId` is reused for prompt/mode/cancel calls.
- ACP prompt payload shaping with text/resource blocks plus legacy fallback behavior.
- Permission modal workflow, diff rendering helpers, command risk analysis.
- Project-scoped prompt/shell histories and XDG-based config/state/data layout.
- Project tree panel with scanner + watcher-driven refresh.

## CLI

```bash
# default run command
bufo

# launch directly into a catalog agent
bufo run --agent codex-cli

# open launcher/store explicitly
bufo run --store

# serve in browser via textual-serve
bufo serve --host 127.0.0.1 --port 8123

# run a custom ACP command
bufo acp "my-agent --acp" --name "My Agent" /path/to/project

# print settings location
bufo settings-path

# app metadata
bufo about

# replay JSONL events for ACP debugging
bufo replay ./events.jsonl --limit 100
```

## Example: yolo-v2 ACP

```bash
bufo acp \
  "uv run --directory /home/bitnom/Code/yolo-v2 yolo-acp --config /home/bitnom/Code/yolo-v2/yolo.config.toml --cwd /home/bitnom/Code/yolo-v2" \
  --name "Yolo v2 (config)" \
  /home/bitnom/Code/yolo-v2
```

## Testing

```bash
# full test suite (unit + integration + e2e)
uv run python -m unittest discover -s tests -v
```

The suite currently covers core persistence/protocol paths, ACP bridge compatibility, ACP update normalization, CLI integration, and end-to-end Textual app flows.

## Notes

- Browser serving is wired through `textual-serve` when available in the environment.
- Runtime requires Textual and ACP tooling installed in your local environment.
