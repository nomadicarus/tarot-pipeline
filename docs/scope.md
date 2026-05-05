# SCOPE

**Hierarchy: 1 | Status: Active**

---

## Project

Automated card deck image generation pipeline using AI Image Generation via API, producing decks composited onto a custom card frame.
Initial build will be tarot card decks

---

## Decks

1. **Thoth Tarot** — Lady Frieda Harris projective geometry style with Aleister Crowley symbolism.
2. **Claymation Thoth** — Thoth symbolism rendered in Aardman-style clay stop-motion aesthetic.

---

## Pipeline Components

- Current AI Image generation via Gemini API (current model: `gemini-3.1-flash-image-preview`) >> inital app build, more models currently out of scope.
- Image metadata (deck name, card name, number, suit) written to PNG EXIF/iTXt as well as a json listing generation data.
- Card compositing: generated art placed inside card frame with configurable padding buffer and centring.
- Resumable runs: skips already-generated cards; raw art preserved separately from final composites.

---

## Output

- Tarot deck: final PNG cards (78 per deck) <we are currently in testing phase, no full deck runs will be made>
- Raw art preserved in `output/{deck}/raw/` for re-compositing without API calls.

---

## Near-Term Additions (once pipeline passes user approval)
- Template card for composition manipulated as required from SVG template (Drop shadow, Colors etc)
- Quota management: daily limit tracking (PT timezone), three guardrail modes (`preflight` / `realtime` / `off`).
- Expanded card composition. Metadata / referenced JSON provides image(s), raw image location, fields for text overlay, colors etc
- Model selection via CLI argument (`--model`).
- Token metadata logging per API response.
- Prompt convergence work between gemini-2.5 and gemini-3.1 styles.
- SQLite-based RPM throttle (token bucket self-throttle).

---

## Out of Scope, future direction

GUI, GUI Card Composition +SVG, Rust conversion, web/payment integration, animation, Additional deck / card types, installer.
