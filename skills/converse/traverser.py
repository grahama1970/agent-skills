"""Federated Taxonomy graph traverser — the standard OS operation.

Every component in the converse skill queries through this module.
Multihop graph traversal via ArangoDB, connected by Federated Taxonomy
bridge attributes (Precision, Resilience, Fragility, Corruption,
Loyalty, Stealth). Returns connected nodes across all scopes:
episodes, dreams, music, conversations, lessons, UI elements.
"""

from __future__ import annotations
import os

import asyncio
import json
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from loguru import logger as log

SKILLS_ROOT = Path(__file__).resolve().parent.parent
# Removed: memory accessed via httpx to Unix socket (see _memory_cmd)
sys.path.insert(0, str(SKILLS_ROOT / "common"))

# Bridge attributes — the universal edge type
BRIDGE_ATTRIBUTES = [
    "Precision", "Resilience", "Fragility",
    "Corruption", "Loyalty", "Stealth",
]

# Scopes that contain nodes Embry traverses
TRAVERSAL_SCOPES = [
    "persona",       # persona state, mood, emotional history
    "horus_lore",    # dreams, creative content, persona voice
    "operational",   # episodes, lessons, work context
    "tom",           # theory of mind — user observations
    "social_intel",  # conversation history, relationship data
]


class NodeType(str, Enum):
    """Types of nodes in the taxonomy graph."""
    UTTERANCE = "utterance"
    EPISODE = "episode"
    DREAM = "dream"
    MUSIC = "music"
    UI_ELEMENT = "ui_element"
    LESSON = "lesson"
    CONVERSATION = "conversation"
    PERSONA_STATE = "persona_state"


@dataclass
class TaxonomyNode:
    """A node returned from graph traversal."""
    node_type: str
    title: str
    content: str
    bridge_attributes: list[str]
    bridge_scores: dict[str, float] = field(default_factory=dict)
    scope: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    depth: int = 0  # hops from seed
    relevance: float = 0.0  # fused score


@dataclass
class TraversalResult:
    """Result of a multihop graph traversal."""
    seed_text: str
    seed_bridges: list[str]
    nodes: list[TaxonomyNode]
    depth: int
    scopes_searched: list[str]

    @property
    def found(self) -> bool:
        return len(self.nodes) > 0

    def by_type(self, node_type: str) -> list[TaxonomyNode]:
        return [n for n in self.nodes if n.node_type == node_type]

    def by_bridge(self, bridge: str) -> list[TaxonomyNode]:
        return [n for n in self.nodes if bridge in n.bridge_attributes]

    def top(self, k: int = 5) -> list[TaxonomyNode]:
        return sorted(self.nodes, key=lambda n: n.relevance, reverse=True)[:k]

    def to_context(self, max_items: int = 5) -> str:
        """Format as context string for LLM prompts."""
        items = self.top(max_items)
        if not items:
            return ""
        lines = [f"[Connected context via {', '.join(self.seed_bridges)}]"]
        for node in items:
            bridges = ', '.join(node.bridge_attributes) if node.bridge_attributes else 'none'
            lines.append(f"- [{node.node_type}] {node.title} (bridges: {bridges}, depth: {node.depth})")
            if node.content:
                lines.append(f"  {node.content[:150]}")
        return '\n'.join(lines)


class TaxonomyTraverser:
    """Federated Taxonomy multihop graph traverser.

    The standard operation for Embry OS. Every component queries through
    this: thinker for response context, idler for music selection,
    emotion for history-informed transitions, listener for grounding
    transcriptions in work context.

    Traversal path:
    1. Extract bridge attributes from input text
    2. Seed the graph with matching nodes
    3. Traverse outward via bridge attribute edges
    4. Fuse BM25 + graph connectivity + taxonomy overlap
    5. Return connected nodes across all scopes
    """

    def __init__(self):
        self._taxonomy_extractor = None

    @staticmethod
    def _memory_cmd(self, args: list, timeout: int = 60) -> dict:
        """Call embry-memory daemon via Unix socket HTTP API."""
        str_args = [str(a) for a in args]
        subcmd = str_args[0] if str_args else ""
        rest = str_args[1:]
    
        # Parse CLI-style flags into a dict
        params: dict = {}
        list_keys: dict[str, list] = {}
        i = 0
        while i < len(rest):
            if rest[i].startswith("--"):
                key = rest[i][2:].replace("-", "_")
                if i + 1 < len(rest) and not rest[i + 1].startswith("--"):
                    val = rest[i + 1]
                    if key in ("tag", "tags", "collections"):
                        list_keys.setdefault(key, []).append(val)
                    else:
                        params[key] = val
                    i += 2
                else:
                    params[key] = True
                    i += 1
            else:
                i += 1
        for k, v in list_keys.items():
            params[k] = v
    
        transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
        with httpx.Client(transport=transport, base_url="http://localhost", timeout=float(timeout)) as client:
            if subcmd == "recall":
                body = {"q": params.get("q", params.get("query", "")), "k": int(params.get("k", params.get("limit", 5)))}
                for opt in ("scope", "threshold"):
                    if opt in params:
                        body[opt] = float(params[opt]) if opt == "threshold" else params[opt]
                if "collections" in params:
                    c = params["collections"]
                    body["collections"] = c if isinstance(c, list) else [c]
                if "tags" in params:
                    t = params["tags"]
                    body["tags"] = t if isinstance(t, list) else [t]
                resp = client.post("/recall", json=body)
            elif subcmd == "learn":
                body = {"problem": params.get("problem", ""), "solution": params.get("solution", "")}
                if "scope" in params:
                    body["scope"] = params["scope"]
                if "collection" in params:
                    body["scope"] = params["collection"]
                if "tag" in params:
                    body["tags"] = params["tag"] if isinstance(params["tag"], list) else [params["tag"]]
                if "tags" in params:
                    body["tags"] = params["tags"] if isinstance(params["tags"], list) else [params["tags"]]
                if "json" in params:
                    body.update(json.loads(params["json"]))
                resp = client.post("/learn", json=body)
            elif subcmd == "count":
                coll = params.get("collection", params.get("scope", "lessons"))
                resp = client.post("/query", json={"aql": f"RETURN LENGTH({coll})", "bind_vars": {}})
            elif subcmd == "sample":
                body = {"collection": params.get("collection", "lessons"), "limit": int(params.get("limit", 10))}
                if "fields" in params:
                    body["return_fields"] = [f.strip() for f in str(params["fields"]).split(",")]
                resp = client.post("/list", json=body)
            elif subcmd == "tag":
                if "doc" in params:
                    doc = json.loads(params["doc"]) if isinstance(params["doc"], str) else params["doc"]
                    resp = client.post("/upsert", json={"collection": params.get("collection", "lessons"), "documents": [doc]})
                elif "key" in params:
                    tags_val = params.get("tags", "[]")
                    tags_list = json.loads(tags_val) if isinstance(tags_val, str) else tags_val
                    field = params.get("field", "tags")
                    resp = client.post("/upsert", json={"collection": params.get("collection", "lessons"), "documents": [{"_key": params["key"], field: tags_list}]})
                else:
                    raise RuntimeError(f"Unsupported tag args: {rest}")
            elif subcmd == "search":
                body = {"q": params.get("q", params.get("query", "")), "k": int(params.get("limit", 10))}
                if "collection" in params:
                    body["collections"] = [params["collection"]]
                if "scope" in params:
                    body["scope"] = params["scope"]
                resp = client.post("/recall", json=body)
            else:
                raise RuntimeError(f"Unsupported memory subcommand via httpx: {subcmd}")
            resp.raise_for_status()
            return resp.json()

    def extract_bridges(self, text: str) -> list[str]:
        """Extract Federated Taxonomy bridge attributes from text.

        Uses the taxonomy skill's extraction, falling back to keyword matching.
        """
        try:
            from taxonomy import extract_taxonomy_features, ContentType
            result = extract_taxonomy_features(
                content_type=ContentType.OPERATIONAL,
                title=text[:200],
                description=text,
                tags=[],
            )
            bridges = result.get("bridge_attributes", [])
            if bridges:
                return bridges
        except Exception as e:
            logger.debug("result extraction failed: {}", e)

        # Keyword fallback
        text_lower = text.lower()
        bridges = []
        keyword_map = {
            "Precision": ["exact", "specific", "technical", "precise", "correct", "accurate", "detail", "focus", "spacing", "alignment"],
            "Resilience": ["strong", "endure", "persist", "keep going", "manage", "overcome", "steady", "push through"],
            "Fragility": ["careful", "gentle", "delicate", "vulnerable", "soft", "fragile", "sensitive", "miss", "lost", "afraid", "worried", "hurt"],
            "Loyalty": ["trust", "promise", "always", "together", "committed", "dedicated", "reliable", "count on"],
            "Stealth": ["quiet", "subtle", "hidden", "indirect", "between the lines", "implicit", "unnoticed"],
            "Corruption": ["broken", "twisted", "wrong", "corrupt", "dark", "decay", "damage", "rotten", "failing"],
        }
        for attr, keywords in keyword_map.items():
            if any(kw in text_lower for kw in keywords):
                bridges.append(attr)
        return bridges or ["Resilience"]  # default bridge if nothing detected

    async def traverse(
        self,
        text: str,
        bridges: Optional[list[str]] = None,
        depth: int = 2,
        limit: int = 10,
        scopes: Optional[list[str]] = None,
        node_types: Optional[list[str]] = None,
    ) -> TraversalResult:
        """Multihop graph traversal from text, connected by Federated Taxonomy.

        Args:
            text: Seed text (utterance, query, observation)
            bridges: Override bridge attributes (auto-extracted if None)
            depth: Max hops from seed
            limit: Max nodes returned
            scopes: Scopes to search (default: all)
            node_types: Filter by node type (default: all)
        """
        if bridges is None:
            bridges = self.extract_bridges(text)
        target_scopes = scopes or TRAVERSAL_SCOPES

        log.debug(f"Traversing: bridges={bridges}, depth={depth}, scopes={target_scopes}")

        # Use /memory subprocess for recall across scopes
        return await self._traverse_via_memory_cmd(text, bridges, depth, limit, target_scopes, node_types)

    async def _traverse_via_memory_cmd(
        self,
        text: str,
        bridges: list[str],
        depth: int,
        limit: int,
        scopes: list[str],
        node_types: Optional[list[str]],
    ) -> TraversalResult:
        """Traverse using /memory subprocess recall across scopes."""
        nodes = []
        loop = asyncio.get_event_loop()

        # Query each scope with bridge-augmented query via /memory recall
        bridge_query = f"{text} {' '.join(bridges)}"
        for scope_name in scopes:
            try:
                result = await loop.run_in_executor(
                    None, self._memory_cmd,
                    ["recall", "--q", bridge_query, "--scope", scope_name, "--k", str(limit)],
                )
                for item in result.get("items", result.get("results", [])):
                    node = TaxonomyNode(
                        node_type=self._infer_node_type(item, scope_name),
                        title=item.get("title", item.get("problem", ""))[:200],
                        content=item.get("solution", item.get("problem", ""))[:300],
                        bridge_attributes=item.get("bridge_attributes", item.get("tags", [])),
                        scope=scope_name,
                        depth=0,
                        relevance=item.get("_score", item.get("score", 0.5)),
                    )
                    # Score by bridge overlap
                    overlap = len(set(node.bridge_attributes) & set(bridges))
                    node.relevance = (node.relevance * 0.6) + (overlap * 0.2 / max(1, len(bridges)))
                    nodes.append(node)
            except Exception as e:
                log.debug(f"Memory recall scope {scope_name} failed: {e}")

        if node_types:
            nodes = [n for n in nodes if n.node_type in node_types]

        nodes.sort(key=lambda n: n.relevance, reverse=True)
        return TraversalResult(text, bridges, nodes[:limit], depth, scopes)

    def _item_to_node(self, item: dict, scope: str, depth: int) -> Optional[TaxonomyNode]:
        """Convert a search result item to a TaxonomyNode."""
        title = item.get("title", item.get("problem", ""))
        if not title:
            return None
        return TaxonomyNode(
            node_type=self._infer_node_type(item, scope),
            title=title[:200],
            content=item.get("solution", item.get("details", ""))[:300],
            bridge_attributes=item.get("bridge_attributes", item.get("tags", [])),
            scope=scope,
            metadata={k: v for k, v in item.items() if k in ("_key", "cluster_id", "updated_at")},
            depth=depth,
            relevance=item.get("_score", item.get("score", 0.5)),
        )

    def _infer_node_type(self, item: dict, scope: str) -> str:
        """Infer node type from item and scope."""
        source = item.get("_source", "")
        if source == "episodes" or "episode" in str(item.get("_key", "")):
            return NodeType.EPISODE
        if scope == "horus_lore":
            title = item.get("title", "").lower()
            if "dream" in title:
                return NodeType.DREAM
            if "music" in title or "song" in title:
                return NodeType.MUSIC
            return NodeType.LESSON
        if scope == "tom":
            return NodeType.PERSONA_STATE
        if scope == "social_intel":
            return NodeType.CONVERSATION
        return NodeType.LESSON

    # -- Convenience methods for specific traversal patterns --

    async def find_music(self, bridges: list[str], mood: str, limit: int = 10) -> TraversalResult:
        """Find music connected to given bridges and mood."""
        query = f"music {mood} {' '.join(bridges)}"
        return await self.traverse(
            query, bridges=bridges, depth=2, limit=limit,
            scopes=["horus_lore", "persona"],
            node_types=[NodeType.MUSIC, NodeType.DREAM],
        )

    async def find_episodes(self, text: str, limit: int = 5) -> TraversalResult:
        """Find episodic memories connected to text."""
        return await self.traverse(
            text, depth=2, limit=limit,
            scopes=["operational", "social_intel"],
            node_types=[NodeType.EPISODE, NodeType.CONVERSATION],
        )

    async def find_dreams(self, bridges: list[str], limit: int = 3) -> TraversalResult:
        """Find dream motifs connected to bridges."""
        query = f"dream motifs {' '.join(bridges)}"
        return await self.traverse(
            query, bridges=bridges, depth=2, limit=limit,
            scopes=["horus_lore"],
            node_types=[NodeType.DREAM],
        )

    async def find_work_context(self, text: str, limit: int = 5) -> TraversalResult:
        """Find work context (lessons, episodes) for grounding conversation in current task."""
        return await self.traverse(
            text, depth=2, limit=limit,
            scopes=["operational", "persona"],
            node_types=[NodeType.LESSON, NodeType.EPISODE],
        )

    async def log_utterance(self, text: str, role: str, bridges: list[str],
                            emotion: str = "", session_id: str = ""):
        """Log a conversation utterance as a node in the graph."""
        try:
            loop = asyncio.get_event_loop()
            tags_str = ",".join(bridges) if bridges else ""
            await loop.run_in_executor(
                None, self._memory_cmd,
                [
                    "learn",
                    "--problem", f"[{role}] {text[:100]}",
                    "--solution", text,
                    "--scope", "social_intel",
                    "--tag", tags_str,
                ],
            )
        except Exception as e:
            log.debug(f"Failed to log utterance: {e}")
