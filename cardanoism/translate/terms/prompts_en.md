# Prompt Profile Schema

## Overview

This document defines the canonical schema for `prompts.yaml`,
which describes **Prompt Profiles** used to control AI behavior
such as translation style, tone, constraints, and task intent.

Prompt Profiles are intentionally separated from:
- terminology rules (terms.yaml)
- translation logic
- AI model selection

This schema is designed to be:
- Human-reviewable on GitHub
- Stable across AI model updates
- Compatible with gpt-5.x Responses API
- Exposable via future APIs

---

## File Structure

```yaml
version: <integer>

profiles:
  <profile_id>:
    description: <string>
    system: <string>
    task: <string>
    rules:
      - <string>
    output:
      format: <plain_text | markdown | json>
      language: <string>
```

---

## Root Fields

### `version` (required)

```yaml
version: 1
```

- Schema version for `prompts.yaml`
- Must be incremented for backward-incompatible changes

---

### `profiles` (required)

```yaml
profiles:
  technical_translation:
    ...
```

- Map of prompt profiles
- Key (`profile_id`) must be unique
- Used directly by code and future APIs

---

## Profile Object

Each profile defines **one AI task configuration**.

---

### `description` (required)

```yaml
description: Literal and reproducible technical translation
```

- Human-readable explanation
- Used for documentation and UI display

---

### `system` (required)

```yaml
system: |
  You are a professional technical translator.
  This task is a transformation of user-provided text.
```

- Defines the AI role and context
- Must clearly indicate **transformation task**
- gpt-5.x stability depends heavily on this field

---

### `task` (required)

```yaml
task: |
  Translate the input text from English to Japanese.
```

- Explicit task definition
- Should be concise and imperative
- Avoid ambiguity or conversational tone

---

### `rules` (required)

```yaml
rules:
  - Do not summarize, omit, or add information.
  - Preserve placeholders exactly.
  - Output Japanese text only.
```

- Ordered list of strict constraints
- Interpreted as **hard requirements**
- Recommended length: 3–7 rules

---

### `output` (optional but recommended)

```yaml
output:
  format: plain_text
  language: ja
```

#### `output.format`

Allowed values:

- `plain_text` – default for translation
- `markdown` – summaries, explanations
- `json` – structured outputs (future use)

#### `output.language`

- Output language hint (e.g. `ja`, `en`)
- Informational but useful for validation

---

## Validation Rules

Implementations SHOULD enforce:

### Structural Rules

- `version` must exist
- `profiles` must be a mapping
- Each profile must define:
  - `description`
  - `system`
  - `task`
  - `rules`

### Semantic Rules

- `rules` must be a non-empty list
- `system` must describe a transformation task
- No profile may reference terminology rules directly

---

## Design Principles

- Prompt Profiles define **how** AI should behave
- Terminology dictionaries define **what** words mean
- AI models are interchangeable execution engines

> Terminology is policy.  
> Prompts are intent.

---

## Non-Goals

- This schema does not define AI models
- This schema does not include terminology rules
- This schema does not encode safety policy logic

---

## Change Policy

- Backward-incompatible changes:
  - Increment `version`
  - Document migration strategy
- Backward-compatible additions:
  - Allowed without version bump

---

End of schema.
