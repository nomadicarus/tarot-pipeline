# LOG-PROJECT

**Hierarchy: 3 | Status: Append only — newest entries first**

---

## 2026-04-30

**Migrated project documents from .docx to Markdown.** Docs now live in `docs/` within the project folder and are included in the project zip. Format: governance.md, scope.md, actions.md, log-project.md.

---

## 2026-04-29

**Initialised four project governance documents** (governance, scope, actions, log-project).

**Reviewed owner-refactored code from `tarot-claude.7z` upload.** Key changes identified:
- `compositor.py`: z-order corrected (frame behind, art on top). `PAD_ART_W`/`PAD_ART_H` padding variables added. Transparent bounding box preserved on output. Commented-out code retained as owner reference markers.
- `settings.py`: model set to `gemini-3.1-flash-image-preview`. Rate table added (RPD/RPM per model). `DAILY_LIMIT` set to 100 for testing.
- `quota.py` / `runner.py`: owner version uses previous quota API — reconciliation flagged in actions.
- `web2api/` notes added with prompt tips, RPM throttle concept, response metadata approach.

---

## Earlier Sessions (summary)

**Built full pipeline:** `cards.json` (78 cards, full Thoth symbolism), `decks.json` (3 decks), prompt builder, Gemini API generator, Pillow compositor, quota tracker, runner with tqdm progress.

**Implemented three-mode guardrail system** (`preflight` / `realtime` / `off`) with CLI override `--guardrail`.

**Implemented PT-timezone daily quota tracking** with server sync attempt and transparent fallback to local count. Differentiates successful vs failed requests.

**Drop shadow locked in:** multiply blend, 2px radius, 2px offset, bottom-right (315°).

**Card frame analysed:** 734×1024px SVG with embedded PNG, subtle diagonal shading gradient confirmed present.
