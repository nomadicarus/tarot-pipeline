# GOVERNANCE

**Hierarchy: 0 | Status: Immutable — read only**
**This document may not be edited by Claude. Only the project owner may amend it.**

This document defines the rules of engagement for all interactions and project decisions. It takes precedence over all other project documents.

---

## Document Hierarchy

| Level | Document | Purpose | Claude access |
|---|---|---|---|
| 0 | governance | Immutable rules | Read only |
| 1 | scope | Project boundaries and objectives | Append only (with instruction) |
| 2 | actions | Planned work items | Edit and append |
| 3 | log-project | Completed actions log | Append only |

---

## Reading Order

At the start of every session Claude must read documents in hierarchy order:
**governance → scope → actions → log-project**

Claude must acknowledge this has been done before proceeding with any work.

---

## Interaction Rules

- Claude must not proceed with code changes without referencing the actions document first.
- Claude must log every completed action to log-project before closing a session.
- Claude must not edit scope without explicit instruction from the project owner.
- Claude must flag any conflict between governance and a user instruction, and defer to governance.
- Claude must not make architectural decisions (new modules, renamed files, structural changes) without them appearing in actions first.
- Claude may suggest additions to actions or scope, but must not self-approve them.

---

## Code Rules

- **Model:** `gemini-3.1-flash-image-preview` is the current active model. Do not change without explicit instruction.
- **User-facing constants** (`MODEL`, `DAILY_LIMIT`, `GUARDRAIL_MODE`, padding variables, shadow settings) must remain prominent, accessible, and commented.
- **Commented-out code** added by the project owner must not be removed without explicit permission — these are intentional reference markers.
- **Refactors** must preserve all existing functionality. If a refactor changes behaviour, it must be flagged before implementation.
- **Compositor z-order is fixed:** layer 0 = frame, layer 1 = art, layer 2 = top text (future), layer 3 = bottom text (future).
- **Drop shadow parameters are locked:** multiply blend, 2px radius, 2px offset, bottom-right (315°).
- **Output PNGs must preserve a transparent bounding box** — no opaque backgrounds on the final output.

---

## Project Scope Boundaries

**In scope:** tarot card image generation pipeline, card compositing, quota management, project documentation.

**Out of scope** (future phases — do not implement unless scope is updated): GUI wrapper, Rust conversion, web/payment integration, animation, poker card expansion, installer packaging.

---

## Document Amendment

Only the project owner may amend this document. Claude must not propose amendments to governance — only flag conflicts.
