# GOVERNANCE

**Hierarchy: 0 | Status: Immutable — read only**
**This document may not be edited by AI Agent. Only the project user may amend it.**

This document defines the rules of engagement for all interactions and project decisions. It takes precedence over all other project documents.

---

## Document Hierarchy

| Level | Document | Purpose |
|---|---|---|
| 0 | governance | Immutable rules |
| 1 | scope | Project boundaries and objectives |
| 2 | actions | Planned work items |
| 3 | log-project | Completed actions log |

---

## Reading Order

At the start of every session AI Agent must read the follwing documents in hierarchy order:
**governance → scope → actions**

AI must acknowledge this has been done before proceeding with any work.

---

## Interaction Rules

- AI Agent should presume 'actions' list current direction of project and 'next steps' but the conversation context may override
- AI Agent must not stray from scope without explicit agreement from user
- AI Agent must provide .md output to the user so they can append log-project
- AI Agent must flag any conflict between governance and a user instruction, prompt user for decision
- AI Agent may make architectural decisions (new modules, renamed files, structural changes), prompt for user confirmation.
- AI Agent may suggest additions to actions or scope, but must not self-approve them.
- At the end of every session AI Agent must produce a session-end checklist 
  listing every file that was created or modified, organised by repository, 
  so the user can update local files and push both repos in one go.

## Change Control

Before any file creation, modification, or deletion the AI Agent must:
- Present the exact change (file path + before/after diff or summary)
- Await explicit user confirmation before applying


## Session End Protocol

AI Agent must output the following at the end of every session:

SESSION END — files to update and push:
tarot-pipeline-docs/
→ docs/actions.md        (if updated)
→ docs/log-project.md    (if updated)
→ docs/scope.md          (if updated)
tarot-pipeline/
→ [any code files changed this session]

Updated files in tarot-pipeline and excepts for appending to log-project.md, scope.md, actions.md should be made available for user download

---

## Code Rules
- **Commented-out code** added by the project user must not be removed without explicit permission — these are intentional reference markers.
- **Refactors** must preserve all existing functionality. If a refactor changes behaviour, it must be flagged before implementation unless previously directed by user.

---

## Document Amendment

Only the project user may amend this document. AI Agent must not propose amendments to governance — only flag conflicts.
