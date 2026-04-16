---
title: Every ArangoDB Call Needs Filesystem Fallback
impact: HIGH
impactDescription: ArangoDB may be down — all page/button operations must work offline via config/page_templates/
tags: arango, resilience, fallback, offline
---

## Every ArangoDB Call Needs Filesystem Fallback

ArangoDB is optional infrastructure. Every operation that reads pages, buttons, or templates must fall back to the filesystem when ArangoDB is unavailable.

**Incorrect:**
```python
from streamdeck.services.page_store import get_page

def load_my_page(key):
    page = get_page(key)  # Returns None if ArangoDB is down
    buttons = [ButtonDef.from_dict(b) for b in page["buttons"]]  # ← crashes
    return buttons
```

**Correct:**
```python
from streamdeck.services.page_recall import get_buttons_as_defs

def load_my_page(key):
    # page_recall tries ArangoDB first, falls back to filesystem
    return get_buttons_as_defs(key)
```

**Or manually:**
```python
from streamdeck.services.page_store import get_page
from streamdeck.utils.page_memory import load_template

def load_my_page(key):
    # Try ArangoDB first
    page = get_page(key)
    if page and page.get("buttons"):
        return [ButtonDef.from_dict(b) for b in page["buttons"]]

    # Fallback to filesystem
    return load_template(key)  # raises FileNotFoundError if truly missing
```

### Fallback Table

| Component | Online (ArangoDB up) | Offline |
|-----------|---------------------|---------|
| Page recall | Hybrid tag + vector search | Filesystem template search |
| Intent classification | page_recall classify_intent | topic_page regex matching |
| Context matching | Anticipation scoring engine | Static context_rules.yaml |
| Button discovery | Graph traversal + tag search | Template-embedded buttons |
| Usage tracking | ArangoDB usage_stats update | Silently skipped |
| Icon generation | Pillow renderer (always local) | Same |

### Notes
- `page_store.is_available()` checks ArangoDB reachability
- `page_recall` module handles all fallback logic — prefer using it over direct page_store calls
- `page_memory.load_template()` already tries ArangoDB first with filesystem fallback
- Widget renderers are always local (Pillow) — they never depend on ArangoDB
