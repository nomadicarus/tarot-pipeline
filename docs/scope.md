# SCOPE

**Hierarchy: 1 | Status: Active**

---

## Project

Automated tarot deck image generation pipeline using the Gemini image generation API, producing three stylistically distinct 78-card decks composited onto a custom card frame.

---

## Decks

1. **Lego Explosive Media** — LEGO minifigure characters in a satirical anti-war graphic novel style.
2. **Thoth Tarot** — Lady Frieda Harris projective geometry style with Aleister Crowley symbolism.
3. **Claymation Thoth** — Thoth symbolism rendered in Aardman-style clay stop-motion aesthetic.

---

## Pipeline Components

- Image generation via Gemini API (current model: `gemini-3.1-flash-image-preview`).
- Card compositing: generated art placed inside card frame with configurable padding buffer and centring.
- Drop shadow: multiply blend, 2px radius, 2px offset, bottom-right.
- Quota management: daily limit tracking (PT timezone), three guardrail modes (`preflight` / `realtime` / `off`).
- Resumable runs: skips already-generated cards; raw art preserved separately from final composites.

---

## Output

- 234 final PNG cards (78 per deck) with transparent bounding box.
- Raw art preserved in `output/{deck}/raw/` for re-compositing without API calls.

---

## Near-Term Additions (approved for actions)

- Card text overlay: card number (roman numerals, top) and card name (bottom), toggleable.
- Model selection via CLI argument (`--model`).
- Token metadata logging per API response.
- Prompt convergence work between gemini-2.5 and gemini-3.1 styles.
- SQLite-based RPM throttle (token bucket self-throttle).
- Image metadata (deck name, card name, number, suit) written to PNG EXIF/iTXt.

---

## Out of Scope

GUI, Rust conversion, web/payment integration, animation, poker card expansion, installer. See governance.
