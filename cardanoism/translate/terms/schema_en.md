# Translation Control Dictionary Schema

---

## Schema Definition (YAML)

```yaml
version: <string>

terms:
  - id: <string>
    source: <string>
    keep: <string>
    prefer:
      - <string>
    avoid:
      - <string>
    note: <string>
```

---

## English Specification

### Overview

This document defines the canonical schema for the  
**Translation Control Dictionary**, which controls AI word choice during translation.

Operationally, the dictionary is stored in two files: `keep_terms.yaml` and `guidance_terms.yaml`.

The goals of this schema are:

- Control translation behavior using English trigger terms
- Keep terminology consistent and stable
- Avoid unnatural or misleading Japanese wording
- Lock proper nouns so they are not translated

This schema is **not intended for validation or error detection**.  
Translation results are always finalized and stored.

---

### Root Fields

#### `version` (required)

- Schema version
- Must be incremented for breaking changes

---

#### `terms` (required)

- List of translation control entries
- **One entry represents one English trigger term or concept**

---

### Term Object

#### `id` (required)

- Unique identifier within the dictionary
- Used for DB, API, and logging

---

#### `keep` (optional)

```yaml
keep: ステーキング
```

- Replaces the English term with a placeholder before translation
- Restores it to the `keep` value after translation
- Prevents any interpretation by the AI

---

#### `prefer` (optional)

```yaml
prefer:
  - ガバナンス
```

- Preferred Japanese wording during translation
- No post-translation replacement or validation

---

#### `avoid` (optional)

```yaml
avoid:
  - 洞察
```

- Japanese terms to avoid during translation
- No post-translation replacement or validation

#### `source` (required)

- English trigger word or phrase

---

#### `note` (optional)

- Additional natural-language guidance for the AI
- Used for tone and wording hints
- Injected into the prompt as "Notes"

---

### Design Principles

- Humans control terminology
- AI chooses natural expressions based on context
- Translation always succeeds and is stored

> Control terms  
> Let expression follow context

---
