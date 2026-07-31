"""Role-scoped /memory HTTP hooks for the universal Battle lineage engine.

All graph traversal belongs to the Memory daemon. Battle sends only the supported
HTTP contracts:

* POST /recall {q, k, scope, collections, tags}
* POST /store {document, collection}
* POST /upsert {collection, documents}

This module contains no AQL, no direct ArangoDB client, no ``MemoryClient`` import,
and no inline vector arrays. ArangoDB receives pointer/text metadata; the Memory
project remains responsible for Qdrant synchronization and multihop traversal.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence
from urllib.parse import urlparse

import httpx

from .adaptive_lineage_engine import (
    AdaptiveLineageContractError,
    GenerationRequest,
    RecallResult,
    candidate_id,
    canonical_sha256,
    json_safe,
)

MEMORY_COLLECTION = "battle_lineage_graph"
MEMORY_NODE_SCHEMA = "battle.lineage_memory_node.v2"
MEMORY_RECALL_SCHEMA = "battle.lineage_memory_recall.v2"
MEMORY_WRITEBACK_SCHEMA = "battle.lineage_survivor_writeback.v2"
CANONICAL_ROLES = (
    "arena-creator",
    "red",
    "blue",
    "judge",
    "researcher",
)


def _safe_key_fragment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.:-]+", "-", value).strip("-")
    if not cleaned:
        raise ValueError("memory key component normalized to empty")
    return cleaned


def _document_id(document: Mapping[str, Any]) -> str | None:
    for key in ("_key", "node_id", "memory_id", "id"):
        value = document.get(key)
        if value not in (None, ""):
            return str(value).split("/", 1)[-1]
    return None


def _edge_targets(document: Mapping[str, Any]) -> list[str]:
    targets: list[str] = []
    for edge in document.get("graph_edges_raw") or []:
        if not isinstance(edge, Mapping):
            continue
        target = edge.get("target_memory_id") or edge.get("target_id")
        if target not in (None, ""):
            targets.append(str(target).split("/", 1)[-1])
    return targets


def _edge(edge_type: str, target_id: str) -> dict[str, str]:
    return {"edge_type": edge_type, "target_id": target_id}


def _score_map(item: Mapping[str, Any]) -> dict[str, float]:
    raw = item.get("scores") or {}
    if not isinstance(raw, Mapping):
        raw = {}
    return {
        name: float(raw.get(name) or 0.0)
        for name in ("bm25", "graph", "dense", "freshness")
    }


def _deterministic_key(
    kind: str,
    *,
    request: GenerationRequest,
    identity: str,
) -> str:
    material = {
        "schema": MEMORY_NODE_SCHEMA,
        "kind": kind,
        "battle_id": request.battle_id,
        "lineage_id": request.lineage_id,
        "role": request.role,
        "generation": request.generation,
        "identity": identity,
    }
    digest = canonical_sha256(material)[:24]
    return ":".join(
        (
            "battle-lineage",
            _safe_key_fragment(request.battle_id),
            _safe_key_fragment(request.lineage_id),
            _safe_key_fragment(request.role),
            f"g{request.generation:04d}",
            _safe_key_fragment(kind),
            digest,
        )
    )


@dataclass(frozen=True)
class RoleMemoryScope:
    """Tags and scope sent to /memory for one isolated role lineage."""

    battle_id: str
    lineage_id: str
    role: str

    @property
    def private_scope(self) -> str:
        return f"battle:{self.battle_id}:role:{self.role}"

    @property
    def public_scope(self) -> str:
        return f"battle:{self.battle_id}:public"

    @property
    def recall_scope(self) -> str:
        return f"battle:{self.battle_id}:role:{self.role}+public"

    @property
    def base_tags(self) -> tuple[str, ...]:
        return (
            "battle",
            f"battle:{self.battle_id}",
            f"lineage:{self.lineage_id}",
        )

    @property
    def recall_tags(self) -> tuple[str, ...]:
        # ``access`` is duplicated with scope intentionally: the daemon receives
        # both role-scoped signals, and callers can audit either one in receipts.
        return (*self.base_tags, f"access:{self.role}")

    def survivor_tags(self) -> list[str]:
        # Public-visible is provenance/spectator metadata. The document remains in
        # the role-private scope and carries only this role's access tag, so it is
        # not opponent-readable through lineage recall.
        return [
            *self.base_tags,
            f"role:{self.role}",
            f"access:{self.role}",
            "visibility:public",
            "kind:survivor",
        ]

    def bad_material_tags(self) -> list[str]:
        return [
            *self.base_tags,
            f"role:{self.role}",
            f"access:{self.role}",
            "visibility:role-only",
            "kind:bad-genetic-material",
        ]

    def allows(self, document: Mapping[str, Any]) -> bool:
        tags = {str(tag) for tag in document.get("tags") or []}
        scope = str(document.get("scope") or document.get("scope_id") or "")
        required = set(self.recall_tags)
        if not required.issubset(tags):
            return False
        if scope == self.public_scope:
            return True
        return scope == self.private_scope and f"role:{self.role}" in tags

    def as_dict(self) -> dict[str, Any]:
        return {
            "battle_id": self.battle_id,
            "lineage_id": self.lineage_id,
            "role": self.role,
            "private_scope": self.private_scope,
            "public_scope": self.public_scope,
            "recall_scope": self.recall_scope,
            "recall_tags": list(self.recall_tags),
        }


class HttpPostClient(Protocol):
    def post(
        self,
        url: str,
        *,
        json: Mapping[str, Any],
        headers: Mapping[str, str],
        timeout: httpx.Timeout,
    ) -> httpx.Response: ...


class MemoryBackend:
    """Real /memory daemon backend with an injectable HTTP client."""

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:8601",
        collection: str = MEMORY_COLLECTION,
        connect_timeout_s: float = 5.0,
        read_timeout_s: float = 30.0,
        write_timeout_s: float = 30.0,
        pool_timeout_s: float = 5.0,
        client: HttpPostClient | None = None,
        caller_skill: str = "battle",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.collection = collection
        self.timeout = httpx.Timeout(
            connect=connect_timeout_s,
            read=read_timeout_s,
            write=write_timeout_s,
            pool=pool_timeout_s,
        )
        self.client = client
        self.caller_skill = caller_skill

    def _post(self, path: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        headers = {
            "Content-Type": "application/json",
            "X-Caller-Skill": self.caller_skill,
        }
        if self.client is not None:
            response = self.client.post(
                f"{self.base_url}{path}",
                json=json_safe(payload),
                headers=headers,
                timeout=self.timeout,
            )
        else:
            with httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout,
                headers=headers,
            ) as client:
                response = client.post(path, json=json_safe(payload))
        response.raise_for_status()
        parsed = response.json()
        if not isinstance(parsed, Mapping):
            raise AdaptiveLineageContractError(
                f"Memory {path} returned non-object JSON"
            )
        return parsed

    def _scope(self, request: GenerationRequest) -> RoleMemoryScope:
        role = str(request.subgraph_scope.get("role") or request.role)
        if role != request.role:
            raise AdaptiveLineageContractError(
                "subgraph_scope cannot change the generation role"
            )
        return RoleMemoryScope(
            battle_id=request.battle_id,
            lineage_id=request.lineage_id,
            role=role,
        )

    def recall(self, *, request: GenerationRequest) -> RecallResult:
        scope = self._scope(request)
        query = str(
            request.context.get("recall_query")
            or (
                f"inherit adaptive lineage knowledge for {request.role} "
                f"generation {request.generation} in {request.battle_id}"
            )
        )
        payload = {
            "q": query,
            "k": request.recall_k,
            "scope": scope.recall_scope,
            "collections": [self.collection],
            "tags": list(scope.recall_tags),
        }
        response = self._post("/recall", payload)
        raw_items = response.get("items") or []
        if not isinstance(raw_items, Sequence) or isinstance(
            raw_items, (str, bytes)
        ):
            raise AdaptiveLineageContractError(
                "Memory /recall response field 'items' must be a list"
            )

        items: list[dict[str, Any]] = []
        scores: list[dict[str, float]] = []
        dropped_forbidden: list[str] = []
        for raw in raw_items:
            if not isinstance(raw, Mapping):
                raise AdaptiveLineageContractError(
                    "Memory /recall items must be JSON objects"
                )
            item = dict(raw)
            if not scope.allows(item):
                identifier = _document_id(item) or "<unidentified>"
                dropped_forbidden.append(identifier)
                continue
            item_scores = _score_map(item)
            item["scores"] = item_scores
            items.append(item)
            scores.append(item_scores)

        confidence = float(response.get("confidence") or 0.0)
        should_scan = bool(response.get("should_scan", not items))
        receipt = {
            "schema": MEMORY_RECALL_SCHEMA,
            "status": "PASS",
            "battle_id": request.battle_id,
            "lineage_id": request.lineage_id,
            "run_id": request.run_id,
            "role": request.role,
            "daemon_url": self.base_url,
            "daemon_multihop": True,
            "request": payload,
            "scope": scope.as_dict(),
            "item_count": len(items),
            "confidence": confidence,
            "should_scan": should_scan,
            "score_fields": ["bm25", "graph", "dense", "freshness"],
            "dropped_forbidden_item_count": len(dropped_forbidden),
            "dropped_forbidden_item_ids": dropped_forbidden,
            "isolation_policy": "drop_forbidden_daemon_hits_before_context",
        }
        return RecallResult(
            documents=tuple(items),
            confidence=confidence,
            should_scan=should_scan,
            item_scores=tuple(scores),
            receipt=receipt,
        )

    def store_document(
        self,
        *,
        collection: str,
        document: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        response = self._post(
            "/store",
            {"document": json_safe(document), "collection": collection},
        )
        self._require_write_ack("/store", response)
        return response

    def upsert_documents(
        self,
        *,
        collection: str,
        documents: Sequence[Mapping[str, Any]],
    ) -> Mapping[str, Any]:
        response = self._post(
            "/upsert",
            {
                "collection": collection,
                "documents": [json_safe(document) for document in documents],
            },
        )
        self._require_write_ack("/upsert", response)
        return response

    @staticmethod
    def _require_write_ack(path: str, response: Mapping[str, Any]) -> None:
        if _write_ack_applied_count(response) >= 1 and not _write_ack_has_error(
            response
        ):
            return
        raise AdaptiveLineageContractError(
            f"Memory {path} did not acknowledge success: {json_safe(response)}"
        )

    def write_survivor(
        self,
        *,
        request: GenerationRequest,
        recall: RecallResult,
        survivor: Mapping[str, Any],
        oracle_evidence: Mapping[str, Any],
        bad_genetic_material: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        scope = self._scope(request)
        selected_id = candidate_id(survivor)
        survivor_key = _deterministic_key(
            "survivor", request=request, identity=selected_id
        )
        bad_key = _deterministic_key(
            "bad-material",
            request=request,
            identity=canonical_sha256(bad_genetic_material),
        )

        parent_ids = [
            identifier
            for item in recall.documents
            if (identifier := _document_id(item)) is not None
            and str(item.get("node_kind") or "")
            in {"arena", "judge_verdict", "lineage_root", "survivor"}
        ]
        parent_ids = sorted(set(parent_ids))[-8:]
        survivor_document = {
            "_key": survivor_key,
            "schema": MEMORY_NODE_SCHEMA,
            "collection": self.collection,
            "battle_id": request.battle_id,
            "lineage_id": request.lineage_id,
            "run_id": request.run_id,
            "generation": request.generation,
            "role": request.role,
            "owner_role": request.role,
            "scope": scope.private_scope,
            "node_kind": "survivor",
            "candidate_id": selected_id,
            "text": (
                f"{request.role} lineage survivor {selected_id} selected at "
                f"generation {request.generation} for {request.battle_id}."
            ),
            "retrieval_text": json.dumps(
                {
                    "survivor": json_safe(survivor),
                    "oracle_evidence": json_safe(oracle_evidence),
                },
                sort_keys=True,
            ),
            "survivor": json_safe(survivor),
            "oracle_evidence": json_safe(oracle_evidence),
            "tags": scope.survivor_tags(),
            "graph_edges_raw": [
                _edge("inherits_from", parent_id) for parent_id in parent_ids
            ],
            "qdrant": {
                "sync": "memory-daemon-owned",
                "vector_inline": False,
            },
        }
        bad_document = {
            "_key": bad_key,
            "schema": MEMORY_NODE_SCHEMA,
            "collection": self.collection,
            "battle_id": request.battle_id,
            "lineage_id": request.lineage_id,
            "run_id": request.run_id,
            "generation": request.generation,
            "role": request.role,
            "owner_role": request.role,
            "scope": scope.private_scope,
            "node_kind": "bad_genetic_material",
            "text": (
                f"{bad_genetic_material.get('bad_count', 0)} of "
                f"{bad_genetic_material.get('population_size', 0)} specimens were "
                f"bad genetic material in generation {request.generation}."
            ),
            "bad_genetic_material": json_safe(bad_genetic_material),
            "tags": scope.bad_material_tags(),
            "graph_edges_raw": [_edge("rejected_alongside", survivor_key)],
            "qdrant": {
                "sync": "memory-daemon-owned",
                "vector_inline": False,
            },
        }

        survivor_ack = self.store_document(
            collection=self.collection,
            document=survivor_document,
        )
        bad_ack = self.store_document(
            collection=self.collection,
            document=bad_document,
        )
        return {
            "schema": MEMORY_WRITEBACK_SCHEMA,
            "status": "PASS",
            "collection": self.collection,
            "survivor_key": survivor_key,
            "bad_genetic_material_key": bad_key,
            "survivor_tags": survivor_document["tags"],
            "bad_genetic_material_tags": bad_document["tags"],
            "scope": scope.as_dict(),
            "survivor_store_ack": json_safe(survivor_ack),
            "bad_material_store_ack": json_safe(bad_ack),
            "deterministic_keys": True,
            "daemon_owned_multihop": True,
        }


class FakeMemoryHttpClient:
    """Offline fake of /recall, /store, and /upsert.

    The fake applies the same caller-visible contract as the daemon: collection and
    tag filtering, role+public scope isolation, then graph expansion only inside the
    permitted projection. It returns ``items`` with the four documented score fields.
    """

    def __init__(
        self,
        documents: Sequence[Mapping[str, Any]] = (),
        *,
        default_collection: str = MEMORY_COLLECTION,
    ) -> None:
        self.default_collection = default_collection
        self.documents: dict[str, dict[str, dict[str, Any]]] = {}
        self.calls: list[dict[str, Any]] = []
        self.seed(documents, collection=default_collection)

    def seed(
        self,
        documents: Sequence[Mapping[str, Any]],
        *,
        collection: str | None = None,
    ) -> None:
        target_collection = collection or self.default_collection
        target = self.documents.setdefault(target_collection, {})
        for raw in documents:
            document = dict(raw)
            key = _document_id(document)
            if key is None:
                raise ValueError("fake memory seed document requires deterministic _key")
            document.setdefault("collection", target_collection)
            target[key] = document

    def post(
        self,
        url: str,
        *,
        json: Mapping[str, Any],
        headers: Mapping[str, str],
        timeout: httpx.Timeout,
    ) -> httpx.Response:
        path = urlparse(url).path
        payload = dict(json)
        self.calls.append(
            {
                "path": path,
                "json": json_safe(payload),
                "headers": dict(headers),
                "timeout": {
                    "connect": timeout.connect,
                    "read": timeout.read,
                    "write": timeout.write,
                    "pool": timeout.pool,
                },
            }
        )
        request = httpx.Request("POST", url)
        try:
            if path == "/store":
                body = self._store(payload)
            elif path == "/upsert":
                body = self._upsert(payload)
            elif path == "/recall":
                body = self._recall(payload)
            else:
                return httpx.Response(
                    404,
                    request=request,
                    json={"ok": False, "error": f"unsupported path {path}"},
                )
        except (KeyError, TypeError, ValueError) as exc:
            return httpx.Response(
                400,
                request=request,
                json={"ok": False, "error": str(exc)},
            )
        return httpx.Response(200, request=request, json=body)

    def _store(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        collection = str(payload["collection"])
        document = payload["document"]
        if not isinstance(document, Mapping):
            raise TypeError("/store document must be an object")
        self.seed([document], collection=collection)
        return {
            "ok": True,
            "collection": collection,
            "_key": _document_id(document),
            "upserted": True,
        }

    def _upsert(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        collection = str(payload["collection"])
        documents = payload["documents"]
        if not isinstance(documents, Sequence) or isinstance(
            documents, (str, bytes)
        ):
            raise TypeError("/upsert documents must be a list")
        mapped = [item for item in documents if isinstance(item, Mapping)]
        if len(mapped) != len(documents):
            raise TypeError("/upsert documents must contain only objects")
        self.seed(mapped, collection=collection)
        return {"ok": True, "collection": collection, "upserted": len(mapped)}

    def _recall(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        expected = {"q", "k", "scope", "collections", "tags"}
        if set(payload) != expected:
            raise ValueError(
                f"/recall payload keys must be exactly {sorted(expected)}, "
                f"got {sorted(payload)}"
            )
        k = int(payload["k"])
        if k < 1:
            raise ValueError("/recall k must be positive")
        collections = payload["collections"]
        tags = payload["tags"]
        if not isinstance(collections, Sequence) or isinstance(
            collections, (str, bytes)
        ):
            raise TypeError("/recall collections must be a list")
        if not isinstance(tags, Sequence) or isinstance(tags, (str, bytes)):
            raise TypeError("/recall tags must be a list")

        battle_id, role = self._parse_scope(str(payload["scope"]))
        private_scope = f"battle:{battle_id}:role:{role}"
        public_scope = f"battle:{battle_id}:public"
        required_tags = {str(tag) for tag in tags}

        eligible: dict[str, dict[str, Any]] = {}
        for collection in (str(item) for item in collections):
            for key, document in self.documents.get(collection, {}).items():
                scope = str(document.get("scope") or document.get("scope_id") or "")
                document_tags = {str(tag) for tag in document.get("tags") or []}
                if scope not in {private_scope, public_scope}:
                    continue
                if not required_tags.issubset(document_tags):
                    continue
                if scope == private_scope and f"role:{role}" not in document_tags:
                    continue
                eligible[key] = dict(document)

        seeds = sorted(
            key
            for key, document in eligible.items()
            if document.get("retrieval_seed") is True
            or str(document.get("node_kind") or "")
            in {"arena", "judge_verdict", "lineage_root", "shared_public"}
        )
        if not seeds:
            seeds = sorted(eligible)

        adjacency: dict[str, set[str]] = {key: set() for key in eligible}
        for source_key, document in eligible.items():
            for target_key in _edge_targets(document):
                if target_key not in eligible:
                    continue
                adjacency[source_key].add(target_key)
                adjacency[target_key].add(source_key)

        hops: dict[str, int] = {}
        frontier = list(seeds)
        hop = 0
        while frontier:
            next_frontier: list[str] = []
            for key in sorted(frontier):
                if key in hops:
                    continue
                hops[key] = hop
                for neighbor in sorted(adjacency.get(key, ())):
                    if neighbor not in hops and neighbor not in next_frontier:
                        next_frontier.append(neighbor)
            frontier = next_frontier
            hop += 1

        # Disconnected but directly filter-matching docs remain valid retrieval hits.
        for key in sorted(eligible):
            hops.setdefault(key, 0)

        ordered = sorted(hops, key=lambda key: (hops[key], key))[:k]
        items: list[dict[str, Any]] = []
        for key in ordered:
            item = dict(eligible[key])
            item_hop = hops[key]
            item["scores"] = {
                "bm25": 1.0 if item_hop == 0 else 0.0,
                "graph": 0.0 if item_hop == 0 else 1.0 / item_hop,
                "dense": 0.75 if item_hop == 0 else 0.25,
                "freshness": 1.0,
            }
            items.append(item)
        return {
            "items": items,
            "confidence": 1.0 if items else 0.0,
            "should_scan": not bool(items),
        }

    @staticmethod
    def _parse_scope(scope: str) -> tuple[str, str]:
        marker = ":role:"
        suffix = "+public"
        if marker not in scope or not scope.endswith(suffix):
            raise ValueError(
                "fake /recall scope must be battle:<id>:role:<role>+public"
            )
        prefix, role_plus = scope.rsplit(marker, 1)
        if not prefix.startswith("battle:"):
            raise ValueError("fake /recall scope must start with battle:")
        battle_id = prefix[len("battle:") :]
        role = role_plus[: -len(suffix)]
        if not battle_id or not role:
            raise ValueError("fake /recall scope lacks battle or role")
        return battle_id, role


def public_document_tags(
    *,
    battle_id: str,
    lineage_id: str,
    roles: Sequence[str] = CANONICAL_ROLES,
) -> list[str]:
    """Tags for a shared public node visible to explicitly listed roles."""

    return [
        "battle",
        f"battle:{battle_id}",
        f"lineage:{lineage_id}",
        *(f"access:{role}" for role in roles),
        "visibility:public",
    ]


_WRITE_COUNT_FIELDS = (
    "upserted",
    "inserted",
    "updated",
    "modified",
    "created",
    "stored",
    "written",
    "write_count",
    "documents_written",
    "affected",
    "count",
)


def _write_ack_has_error(value: Any) -> bool:
    if isinstance(value, Mapping):
        ok = value.get("ok")
        if ok is False:
            return True
        status = str(value.get("status") or "").upper()
        if status in {"FAIL", "FAILED", "ERROR", "ERR", "REJECTED"}:
            return True
        if value.get("error") not in (None, "", False):
            return True
        errors = value.get("errors")
        if isinstance(errors, Sequence) and not isinstance(errors, (str, bytes)):
            if errors:
                return True
        elif errors not in (None, "", False):
            return True
        return any(_write_ack_has_error(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_write_ack_has_error(item) for item in value)
    return False


def _write_ack_applied_count(response: Mapping[str, Any]) -> int:
    total = 0
    for field in _WRITE_COUNT_FIELDS:
        raw = response.get(field)
        if isinstance(raw, bool):
            total += int(raw)
        elif isinstance(raw, int):
            total += max(raw, 0)
        elif isinstance(raw, float):
            total += max(int(raw), 0)
    for field in ("_key", "key", "id", "_id"):
        if response.get(field) not in (None, ""):
            total += 1
            break
    for field in ("result", "results", "documents", "items"):
        raw = response.get(field)
        if isinstance(raw, Mapping):
            if not _write_ack_has_error(raw):
                total += max(_write_ack_applied_count(raw), 1)
        elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
            for item in raw:
                if isinstance(item, Mapping) and not _write_ack_has_error(item):
                    total += max(_write_ack_applied_count(item), 1)
    return total
