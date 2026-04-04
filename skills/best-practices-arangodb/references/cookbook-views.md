# Cookbook: ArangoSearch View Creation

Every searchable collection needs an ArangoSearch view. Views are created in `setup_schema.py`.

## Standard View Pattern (text_en + identity)

```python
from graph_memory.arango_client import get_db
db = get_db()

# Check if view already exists
existing_views = [v.get("name") for v in db.views()]

if "my_collection_search" not in existing_views and db.has_collection("my_collection"):
    db.create_arangosearch_view(
        "my_collection_search",
        properties={
            "links": {
                "my_collection": {
                    "includeAllFields": False,        # NEVER True — index only what you search
                    "analyzers": ["text_en"],          # default analyzer for unspecified fields
                    "fields": {
                        # Full-text searchable fields → text_en (stemming + stop words)
                        "title": {"analyzers": ["text_en"]},
                        "description": {"analyzers": ["text_en"]},
                        "content": {"analyzers": ["text_en"]},
                        # Fields that need BOTH stemmed and exact search
                        "name": {"analyzers": ["text_en", "identity"]},
                        # Exact match only fields → identity (no stemming)
                        "control_id": {"analyzers": ["identity"]},
                        "scope": {"analyzers": ["identity"]},
                        "category": {"analyzers": ["identity"]},
                    },
                }
            }
        },
    )
```

## Analyzer Selection Guide

| Analyzer | Use When | Example Fields |
|----------|----------|----------------|
| `text_en` | Full-text search with English stemming/stop words | `description`, `content`, `answer`, `question` |
| `identity` | Exact string matching (IDs, categories, enum-like values) | `control_id`, `scope`, `framework`, `status` |
| Both `["text_en", "identity"]` | Need both fuzzy AND exact search on same field | `name` (search "tamper protect" OR exact "Tamper Protection") |

## Common Mistakes

```python
# BAD — includeAllFields indexes everything (wastes memory, slow indexing)
"includeAllFields": True

# BAD — using text_en on control IDs (stems "SV-AC-2" incorrectly)
"control_id": {"analyzers": ["text_en"]}

# BAD — missing identity on scope (can't do exact scope filter)
"scope": {"analyzers": ["text_en"]}

# BAD — forgetting to check if view already exists (errors on restart)
db.create_arangosearch_view("my_view", ...)  # crashes if already exists
```

## Updating an Existing View (add fields)

```python
if "my_collection_search" in existing_views:
    db.update_arangosearch_view(
        "my_collection_search",
        properties={
            "links": {
                "my_collection": {
                    "includeAllFields": False,
                    "analyzers": ["text_en"],
                    "fields": {
                        # All existing fields PLUS new ones
                        "title": {"analyzers": ["text_en"]},
                        "new_field": {"analyzers": ["text_en"]},  # added
                    },
                }
            }
        },
    )
```

**WARNING**: `update_arangosearch_view` REPLACES the entire view definition. You must include ALL fields, not just the new one.
