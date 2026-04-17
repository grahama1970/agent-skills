"""
Horus Preset Storage - ArangoDB Collection Management
Implements queryable semantic contracts for filmmaking (lighting, camera, lens, etc.)
"""
import os
import sys
from typing import Any, Dict, List, Optional
from datetime import datetime
from pathlib import Path

# Add skill dir to path for imports
SKILL_DIR = Path(__file__).parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

# Ensure common.taxonomy is reachable
COMMON_SKILLS_DIR = SKILL_DIR.parent
if str(COMMON_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_SKILLS_DIR))

from common.taxonomy import extract_taxonomy_features, ContentType

try:
    from db import get_db
except ImportError:
    # Fallback/stub for isolated testing if needed, though we usually run in-engine
    def get_db():
        raise ImportError("ArangoDB connection not configured. Set ARANGO_URL, etc.")

def ensure_preset_collections(db: Any):
    """
    Ensure all collections for the Preset Methodology exist with proper indexes.
    """
    # 1. Documents: presets
    if not db.has_collection("presets"):
        db.create_collection("presets")
        print("Created collection: presets")
    presets = db.collection("presets")
    
    # Indexes for presets
    presets_indexes = {idx["name"] for idx in presets.indexes()}
    if "idx_type" not in presets_indexes:
        presets.add_index(fields=["type"], type="persistent", name="idx_type")
    if "idx_tags" not in presets_indexes:
        presets.add_index(fields=["tags[*]"], type="persistent", name="idx_tags")

    # 2. Documents: preset_sets
    if not db.has_collection("preset_sets"):
        db.create_collection("preset_sets")
        print("Created collection: preset_sets")
    preset_sets = db.collection("preset_sets")
    
    # Indexes for preset_sets
    sets_indexes = {idx["name"] for idx in preset_sets.indexes()}
    if "idx_tags" not in sets_indexes:
        preset_sets.add_index(fields=["tags[*]"], type="persistent", name="idx_tags")

    # 3. Documents: media_assets (if not already managed elsewhere)
    if not db.has_collection("media_assets"):
        db.create_collection("media_assets")
        print("Created collection: media_assets")
    
    # 4. Edges: preset_refs (preset -> media_asset)
    if not db.has_collection("preset_refs"):
        db.create_collection("preset_refs", edge=True)
        print("Created collection: preset_refs (edge)")
    
    # 6. Vertices: media_assets (for Evidence Layer)
    if not db.has_collection("media_assets"):
        db.create_collection("media_assets")
        print("Created collection: media_assets")

def get_preset_evidence(db: Any, preset_id: str) -> Dict[str, List[Dict]]:
    """
    Retrieve positive and negative evidence (media references) for a preset.
    Returns: {"positive": [...], "negative": [...]}
    """
    # AQL to fetch linked media assets
    # Positive refs
    pos_cursor = db.aql.execute("""
        FOR doc, edge IN OUTBOUND @preset_id preset_refs
        RETURN {
            "asset": doc,
            "why": edge.why,
            "confidence": edge.confidence,
            "tc_in_s": edge.tc_in_s,
            "tc_out_s": edge.tc_out_s
        }
    """, bind_vars={"preset_id": preset_id})
    
    # Negative refs
    neg_cursor = db.aql.execute("""
        FOR doc, edge IN OUTBOUND @preset_id preset_ref_negatives
        RETURN {
            "asset": doc,
            "why": edge.why,
            "confidence": edge.confidence,
            "tc_in_s": edge.tc_in_s,
            "tc_out_s": edge.tc_out_s
        }
    """, bind_vars={"preset_id": preset_id})
    
    return {
        "positive": list(pos_cursor),
        "negative": list(neg_cursor)
    }

    # 6. Search View (Recommended for Memory Skill)
    existing_views = [v["name"] for v in db.views()]
    if "memory_view_preset" not in existing_views:
        db.create_arangosearch_view(
            name="memory_view_preset",
            properties={
                "links": {
                    "presets": {
                        "analyzers": ["text_en", "identity"],
                        "fields": {
                            "title": {"analyzers": ["text_en"]},
                            "description": {"analyzers": ["text_en"]},
                            "tags": {"analyzers": ["identity"]}
                        }
                    },
                    "preset_sets": {
                        "analyzers": ["text_en", "identity"],
                        "fields": {
                            "title": {"analyzers": ["text_en"]},
                            "description": {"analyzers": ["text_en"]},
                            "tags": {"analyzers": ["identity"]}
                        }
                    }
                }
            }
        )
        print("Created ArangoSearch view: memory_view_preset")

def upsert_preset(db: Any, preset_id: str, data: Dict):
    """Upsert a preset into the database."""
    presets = db.collection("presets")
    # Auto-taxonomy extraction (Federated Taxonomy)
    taxonomy_meta = {}
    try:
        tax_res = extract_taxonomy_features(
            content_type=ContentType.MOVIE, # Presets are for filmmaking
            title=data.get("title", preset_id),
            description=data.get("description", ""),
            tags=data.get("tags", [])
        )
        taxonomy_meta = {
            "bridge_tags": tax_res.get("bridge_attributes", []),
            "collection_tags": tax_res.get("collection_tags", {})
        }
    except Exception as e:
        print(f"Warning: taxonomy extraction failed for preset {preset_id}: {e}", file=sys.stderr)

    doc = {
        "_key": preset_id,
        "updated_at": datetime.now().isoformat(),
        "taxonomy": taxonomy_meta,
        **data
    }
    if "created_at" not in data:
        doc["created_at"] = doc["updated_at"]
    
    # Merge bridge tags into main tags for searchability if desired
    if taxonomy_meta.get("bridge_tags"):
        existing_tags = data.get("tags", [])
        all_tags = list(set(existing_tags + taxonomy_meta["bridge_tags"]))
        doc["tags"] = all_tags

    presets.insert(doc, overwrite=True)
    return preset_id

MAX_PRESET_DEPTH = 5

# Override Allowlist (Safe Params)
VALID_PARAMS = frozenset({
    # Camera
    "camera_stabilization", "camera_movement", "camera_movement_intensity", "camera_movement_speed", "shot_size",
    # Lens
    "lens_focal_length", "lens_aperture", "lens_compression", "lens_intent",
    # Lighting
    "lighting_key_type", "lighting_key_angle", "lighting_contrast", "lighting_fill", "lighting_temperature",
    # Styles
    "composition_style", "visual_precision", "color_palette", "motion_style",
    # Narrative/Mood
    "emotion", "mood", "pacing"
})

def expand_preset_ids(db: Any, current_ids: Dict[str, str], depth: int = 0, visited: Optional[set] = None) -> Dict[str, str]:
    """
    Recursively expand 'set' IDs into a flat dictionary of category->preset_id.
    Enforces depth limits and cycle detection.
    """
    if visited is None:
        visited = set()
        
    if depth >= MAX_PRESET_DEPTH:
        print(f"Warning: Max preset depth ({MAX_PRESET_DEPTH}) reached. Stop expansion at {current_ids}.")
        return current_ids

    # If no set to expand, we're done
    if "set" not in current_ids:
        return current_ids

    set_id = current_ids.pop("set")
    
    # Cycle detection
    if set_id in visited:
        raise ValueError(f"Cycle detected in preset sets: {set_id} has already been visited/expanded.")
    
    visited.add(set_id)
    
    try:
        set_doc = db.collection("preset_sets").get(set_id)
        if not set_doc:
            msg = f"Warning: Preset set '{set_id}' not found."
            print(msg)
            # In strict mode (future), this duplicates behaviors, but here we just return unexpanded
            return current_ids
            
        # 1. Get defaults from the set (Legacy v1.0)
        defaults = set_doc.get("defaults", {}).copy()
        
        # 2. V1.1: Resolve 'preset_ids' list (The new standard)
        # We need to map these IDs to their types (camera, lens, etc.)
        if "preset_ids" in set_doc and isinstance(set_doc["preset_ids"], list):
            # Fetch all referenced components
            component_ids = set_doc["preset_ids"]
            if component_ids:
                cursor = db.aql.execute("""
                    FOR p IN presets
                    FILTER p._key IN @ids
                    RETURN {type: p.type, key: p._key}
                """, bind_vars={"ids": component_ids})
                
                for item in cursor:
                    defaults[item["type"]] = item["key"]

        # 3. If the set itself inherits from another set (Legacy recursion)
        if "set" in defaults:
            defaults = expand_preset_ids(db, defaults, depth + 1, visited.copy())
            
        # 4. Merge: Current explicit IDs override defaults
        merged = defaults
        merged.update(current_ids)
        
        return merged
        
    except Exception as e:
        print(f"Error expanding set {set_id}: {e}")
        return current_ids

def compile_spec(db: Any, preset_ids: Dict[str, str], overrides: Optional[Dict] = None, strict: bool = False) -> Dict:
    """
    Compile a deterministic specification from a set of preset IDs.
    
    Args:
        strict: If True, raises ValueError on missing IDs or invalid overrides.
    
    Precedence (Low to High):
    1. Preset Set Defaults (recursive)
    2. Preset Set Params (the persona itself)
    3. Component Presets (Camera, Lens, etc.)
    4. Overrides (Filtered by VALID_PARAMS)
    """
    overrides = overrides or {}
    compiled = {
        "spec_version": "1.1",
        "params": {},
        "tags": set(),
        "resolved_ids": {},
        "constraints_applied": [],
        "warnings": {
            "illegal_overrides": [],
            "missing_ids": [],
            "logic_errors": []
        },
        "taxonomy": {
            "bridge_tags": set(),
            "collection_tags": {}
        }
    }
    
    # Filter Overrides (Allowlist Enforcement)
    safe_overrides = {}
    for k, v in overrides.items():
        if k in VALID_PARAMS:
            safe_overrides[k] = v
        else:
            msg = f"Dropped illegal override: {k}"
            compiled["warnings"]["illegal_overrides"].append(k)
            if strict:
                raise ValueError(f"Strict Mode: {msg}")
    
    # 1. Recursive Expansion
    try:
        flat_ids = expand_preset_ids(db, preset_ids.copy())
    except ValueError as e:
        compiled["constraints_applied"].append(f"Error: {e}")
        return compiled

    # 2. Fetch all documents (Sets and Presets)
    # We need to fetch the Sets involved (for their direct params/tags) AND the component Presets
    # Since expand_preset_ids returns a flat list of component IDs, we might have lost the Set IDs.
    # To properly merge Set params (Layer 2), we should ideally keep track of them.
    # For simplicity in this implementation, we will assume 'flat_ids' contains the component presets.
    # IF the original request had a "set", we should fetch that one Set to apply its params.
    # NOTE: Deeply nested set params are complex to merge. We'll stick to the TOP LEVEL set if provided.
    
    root_set_id = preset_ids.get("set")
    docs_to_fetch = list(flat_ids.values())
    if root_set_id:
        docs_to_fetch.append(root_set_id)
        
    if not docs_to_fetch:
         compiled["params"].update(overrides)
         return compiled

    # Deduplicate and Fetch
    docs_to_fetch = list(set(docs_to_fetch))
    cursor = db.aql.execute("""
        FOR doc IN FLATTEN([
            (FOR p IN presets FILTER p._key IN @ids RETURN p),
            (FOR s IN preset_sets FILTER s._key IN @ids RETURN s)
        ])
        RETURN doc
    """, bind_vars={"ids": docs_to_fetch})
    
    doc_map = {d["_key"]: d for d in cursor}
    
    # Helper for merging logic
    def merge_doc(d: Dict):
        # Params
        if "params" in d:
            compiled["params"].update(d["params"])
        # Tags
        if "tags" in d:
            for t in d["tags"]:
                compiled["tags"].add(t)
        # Taxonomy
        if "taxonomy" in d:
            tax = d["taxonomy"]
            if "bridge_tags" in tax:
                for bt in tax["bridge_tags"]:
                    compiled["taxonomy"]["bridge_tags"].add(bt)
            if "collection_tags" in tax:
                compiled["taxonomy"]["collection_tags"].update(tax["collection_tags"])

    # LAYER 1.5: Persona/Set Direct Params (Root Set)
    # These are params explicitly defined in the root preset_set document
    if root_set_id and root_set_id in doc_map:
        merge_doc(doc_map[root_set_id])
        compiled["resolved_ids"]["set"] = root_set_id
        # Propagate set_type for orchestrator enforcement
        compiled["set_type"] = doc_map[root_set_id].get("set_type", "complete")
    
    # LAYER 2: Component Presets (Category Order)
    # "Camera" component overrides "Persona" generic camera params
    category_order = ["persona", "intent", "camera", "lens", "lighting", "audio", "grade"]
    for cat in category_order:
        pid = flat_ids.get(cat)
        if not pid:
            continue
            
        if pid not in doc_map:
            compiled["warnings"]["missing_ids"].append(pid)
            if strict:
                raise ValueError(f"Strict Mode: Missing component ID '{pid}'")
            continue
            
        compiled["resolved_ids"][cat] = pid
        merge_doc(doc_map[pid])

    # LAYER 3: Overrides (Highest Precedence)
    compiled["params"].update(safe_overrides)
    
    # Formatting outputs
    compiled["tags"] = sorted(list(compiled["tags"]))
    compiled["taxonomy"]["bridge_tags"] = sorted(list(compiled["taxonomy"]["bridge_tags"]))
    
    return compiled

if __name__ == "__main__":
    # Smoke test: ensure collections
    try:
        db = get_db()
        ensure_preset_collections(db)
        print("✓ Preset collections verified.")
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)
