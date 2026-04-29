# Agent Skills

This directory is the runtime source of truth for agent instructions.

`agents.utils.load_prompt()` looks here first and falls back to `prompts/` for compatibility.

Layout:

- `skills/manager.txt`
- `skills/manager_decision.txt`
- `skills/reviewer.txt`
- `skills/heads/*.txt`
- `skills/specialists/*.txt`
- `skills/specialists/sentiment.txt`
