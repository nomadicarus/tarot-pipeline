# ACTIONS
**Hierarchy: 2 | Status: Active planning document**

Planned actions in priority order. Completed actions move to log-project.
---
## Immediate — Code
- [ ] a recent major refactor to modular code and new git branch has confused code. test code to ensure current continuity. example suggested code structure added in refactored_runner.py, refactored_compositor.py and refactored_generator.py

---
## Near-Term — Features
- [ ] Add `--model` CLI argument to allow model override at runtime.
- [ ] the cards.json and decks.json needs some more work, realistically this will entail refactoring builder.py and the whole prompt
- [ ] Token metadata logging: capture `prompt_token_count`, `candidates_token_count`, `total_token_count` from `response.usage_metadata` per API call. Append to `quota_state.json`.
- [ ] SQLite RPM throttle: log each call with timestamp, calculate rolling 60s window, sleep until bucket refills if at RPM limit.
- [ ] Prompt convergence: test and document prompt differences between gemini-2.5 and gemini-3.1 to align visual style.
---
