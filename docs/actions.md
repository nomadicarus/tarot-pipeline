# ACTIONS

**Hierarchy: 2 | Status: Active planning document**

Planned actions in priority order. Completed actions move to log-project.

---

## Immediate — Code

- [ ] Refactor `compositor.py`: clean up commented-out code, preserve all functional changes from owner refactor, ensure `PAD_ART_W` / `PAD_ART_H` variables are accessible and documented.
- [ ] Merge owner's `settings.py` model comments and rate table into canonical `settings.py`.
- [ ] Reconcile `quota.py` / `runner.py`: owner's uploaded version uses older `check_and_gate(interactive=)` API — align with latest three-mode guardrail system.
- [ ] Add `--model` CLI argument to allow model override at runtime.

---

## Near-Term — Features

- [ ] Card text overlay: layer 2 (top — roman numeral card number) and layer 3 (bottom — card name). Font, style, colour configurable. Toggle flags in `settings.py` and CLI.
- [ ] Token metadata logging: capture `prompt_token_count`, `candidates_token_count`, `total_token_count` from `response.usage_metadata` per API call. Append to `quota_state.json`.
- [ ] SQLite RPM throttle: log each call with timestamp, calculate rolling 60s window, sleep until bucket refills if at RPM limit.
- [ ] Prompt convergence: test and document prompt differences between gemini-2.5 and gemini-3.1 to align visual style.
- [ ] Add image metadata (deck name, card name, number, suit) to output PNG EXIF/iTXt for later processing.

---

## Near-Term — Project

- [ ] Expand `web2api/` notes into a structured prompt refinement document.

---

## Future — Deferred

- [ ] Expand pipeline to support additional deck formats (poker cards etc).
- [ ] GUI wrapper.
- [ ] Rust conversion / packaging.
- [ ] Website, distribution, payment integration.
