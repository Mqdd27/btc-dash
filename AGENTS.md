# AGENTS.md

## Persistent memory

This project uses an Obsidian vault as persistent long-term memory across sessions. Plain Markdown files only — no Obsidian plugins, no MCP, no extra database or service.

- Memory root: `/Users/macbook/Library/Mobile Documents/com~apple~CloudDocs/Obsidian Vault/AI Mem`
- Project memory for btc-dash: `/Users/macbook/Library/Mobile Documents/com~apple~CloudDocs/Obsidian Vault/AI Mem/Projects/btc-dash.md`

Rules:
- Before working on anything related to previous implementation, architecture, bugs, deployment, configuration, decisions, or past work, read the project memory file first.
- Don't load the whole vault if it isn't needed — only read what's relevant.
- Source code and the actual server/deployment state are always the source of truth. If memory disagrees with them, trust the actual state and correct the memory.
- After finishing a task or making a change, revise the memory file.
- Never blindly append. Update the existing `Current State` section to reflect the latest condition instead of stacking new entries on top of stale ones.
- Move old state into `History` only if it's still useful to know later.
- Avoid duplicate facts across sections.
- Never store secrets (passwords, API keys, tokens, cookies, private keys, credentials) in memory.
