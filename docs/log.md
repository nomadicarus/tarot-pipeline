# LOG
**Hierarchy: 3 | Status: Active**

Completed actions moved from actions.md.

---

## Session: 2026-05-05

### Cleared Actions (moved to boilerplate)
- [x] code partially refactored using gemini and chatgpt web interfaces - the main.py, runner.py and compositor.py need review and refactoring to tie everything up.
- [x] Add `--model` CLI argument to allow model override at runtime.
- [x] the cards.json and decks.json needs some more work, realistically this will entail refactoring builder.py and the whole prompt
- [x] Token metadata logging: capture `prompt_token_count`, `candidates_token_count`, `total_token_count` from `response.usage_metadata` per API call. Append to `quota_state.json`.
- [x] SQLite RPM throttle: log each call with timestamp, calculate rolling 60s window, sleep until bucket refills if at RPM limit.
- [x] Prompt convergence: test and document prompt differences between gemini-2.5 and gemini-3.1 to align visual style.

### File Changes
- `docs/actions.md` — cleared to boilerplate (empty actionable items)
- `docs/log-project.md` — created with completed actions (renamed to `log.md` per user request)
