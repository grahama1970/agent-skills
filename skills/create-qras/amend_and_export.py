#!/usr/bin/env python3
"""
Amend all QRAs with evidence case, normalize schema, export to HuggingFace.

Pipeline:
1. Fetch QRAs in batches from sparta_qra
2. For each QRA, call /create-evidence-case to get crosswalk chains (PARALLEL)
3. Normalize schema (qra_type, sparta_linked, source/target, evidence_case)
4. Update in ArangoDB
5. Export to JSONL
6. Push to HuggingFace with dataset card

Usage:
    # Stats only
    python amend_and_export.py stats

    # Dry run (no writes)
    python amend_and_export.py amend --dry-run --limit 100

    # Full pipeline (parallel enrichment, ~1 hour on i9)
    python amend_and_export.py amend --all --export --push-hf

    # Export existing (skip amendment)
    python amend_and_export.py export --push-hf
"""

import asyncio
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

import httpx
import typer
from loguru import logger

# Parallelization settings (tuned for i9 + 256GB RAM)
DEFAULT_CONCURRENCY = 32  # Concurrent evidence-case calls

app = typer.Typer()

MEMORY_SOCKET = "/run/user/1000/embry/memory.sock"
MEMORY_DIRECT_URL = "http://127.0.0.1:8601"  # Direct to memory service (bypass proxy)
COLLECTION = "sparta_qra"
EXPORT_DIR = Path("/mnt/storage12tb/datasets/sparta-qra")
HF_REPO = "grahamaco/sparta-qra-grounded"
DATASET_VERSION = "1.0.0"

# Framework version tracking
FRAMEWORK_VERSIONS = {
    "sparta": "3.1",
    "cwe": "4.14",
    "capec": "3.9",
    "attack": "15.1",
    "nist": "800-53r5",
}


def get_client() -> httpx.Client:
    transport = httpx.HTTPTransport(uds=MEMORY_SOCKET)
    return httpx.Client(transport=transport, base_url="http://localhost", timeout=120.0)


def get_async_client(use_direct: bool = False) -> httpx.AsyncClient:
    """Get async HTTP client.

    Args:
        use_direct: If True, connect directly to memory service on port 8601
                    (bypasses Unix socket proxy, faster for batch ops)
    """
    if use_direct:
        return httpx.AsyncClient(base_url=MEMORY_DIRECT_URL, timeout=120.0)
    transport = httpx.AsyncHTTPTransport(uds=MEMORY_SOCKET)
    return httpx.AsyncClient(transport=transport, base_url="http://localhost", timeout=120.0)


def compute_content_hash(question: str, reasoning: str, answer: str) -> str:
    """SHA256 hash of normalized Q+R+A for deduplication."""
    normalized = f"{question.strip().lower()}|{reasoning.strip().lower()}|{answer.strip().lower()}"
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def estimate_tokens(text: str) -> int:
    """Rough token count (words * 1.3)."""
    if not text:
        return 0
    return int(len(text.split()) * 1.3)


def determine_difficulty(chains: list, question: str) -> str:
    """Determine difficulty based on crosswalk chain complexity."""
    if not chains:
        return "unknown"

    # Count total hops across all chains
    total_hops = sum(len(c.get("hops", [])) for c in chains)
    frameworks = {c.get("from_framework") for c in chains} | {c.get("to_framework") for c in chains}
    frameworks.discard("")
    frameworks.discard(None)

    if total_hops <= 2 and len(frameworks) <= 2:
        return "single_hop"
    elif total_hops <= 5 or len(frameworks) <= 3:
        return "multi_hop"
    else:
        return "synthesis"


def determine_question_type(qra_type: str, question: str) -> str:
    """Classify question type for training."""
    q_lower = question.lower()

    if "how" in q_lower and ("mitigat" in q_lower or "protect" in q_lower or "defend" in q_lower):
        return "mitigation"
    elif "why" in q_lower or "relevant" in q_lower or "relate" in q_lower:
        return "relationship"
    elif "what" in q_lower and ("indicator" in q_lower or "sign" in q_lower or "detect" in q_lower):
        return "detection"
    elif "implement" in q_lower or "configure" in q_lower:
        return "implementation"
    elif qra_type == "relationship":
        return "relationship"
    elif qra_type == "independent":
        return "explanation"
    else:
        return "general"


def extract_security_domains(chains: list) -> list:
    """Extract security domain tags from crosswalk chains."""
    domains = set()

    domain_keywords = {
        "authentication": ["auth", "credential", "login", "password", "identity", "IA-"],
        "access_control": ["access", "privilege", "permission", "authorization", "AC-"],
        "injection": ["inject", "xss", "sql", "command", "CWE-79", "CWE-89"],
        "cryptography": ["crypto", "encrypt", "key", "cipher", "hash", "SC-"],
        "network": ["network", "protocol", "traffic", "firewall", "comm"],
        "supply_chain": ["supply", "vendor", "third-party", "SBOM"],
        "detection": ["detect", "monitor", "audit", "log", "alert"],
    }

    chain_text = json.dumps(chains).lower()
    for domain, keywords in domain_keywords.items():
        if any(kw.lower() in chain_text for kw in keywords):
            domains.add(domain)

    return sorted(domains) if domains else ["general"]


def derive_curation_status(doc: dict) -> str:
    """Derive curation status from verdict and existing fields."""
    verdict = doc.get("verdict", "").upper()
    if verdict == "SATISFIED":
        return "verified"
    elif verdict == "NEEDS_REVIEW":
        return "needs_review"
    elif doc.get("human_reviewed"):
        return "approved"
    else:
        return "raw"


def derive_creation_method(doc: dict) -> str:
    """Derive creation method from document metadata."""
    source = str(doc.get("generation_source", "") or doc.get("qra_id", "") or "")
    if "manual" in source.lower():
        return "manual"
    elif "doc2qra" in source.lower() or "url_knowledge" in source.lower():
        return "extracted"
    else:
        return "synthetic"


def determine_expertise(question: str, reasoning: str, answer: str, chains: list) -> str:
    """Determine target audience expertise level.

    Matches existing SPARTA persona schema:
        layperson: No assumed technical knowledge, plain language
        pm: Project manager level, dependency/schedule focus
        compliance: Compliance officer, regulatory/audit focus
        expert: Deep cybersecurity/technical expertise required
    """
    text = f"{question} {reasoning} {answer}".lower()

    # Expert-level indicators (MITRE IDs, specific frameworks, jargon)
    expert_terms = [
        "cwe-", "capec-", "cve-", "t1", "sv-", "cm0", "ia-", "ac-",
        "mitre att&ck", "nist 800", "lateral movement", "privilege escalation",
        "threat actor", "ioc", "ttp", "kill chain", "red team", "blue team",
        "cryptographic", "cipher suite", "key exchange", "pki", "telemetry",
    ]

    # Compliance-level indicators
    compliance_terms = [
        "cmmc", "ato", "poam", "stig", "fedramp", "hipaa", "gdpr", "sox",
        "audit", "compliance", "requirement", "control", "regulation",
        "certification", "assessment", "accreditation", "authorization",
    ]

    # PM-level indicators (impact, schedule, dependency)
    pm_terms = [
        "impact", "dependency", "schedule", "milestone", "deliverable",
        "stakeholder", "budget", "resource", "timeline", "risk management",
        "project", "integration", "coordination",
    ]

    # Count matches
    expert_count = sum(1 for term in expert_terms if term in text)
    compliance_count = sum(1 for term in compliance_terms if term in text)
    pm_count = sum(1 for term in pm_terms if term in text)

    # Check for framework-specific references in chains
    frameworks_in_chains = {c.get("from_framework", "") for c in chains} | {c.get("to_framework", "") for c in chains}
    has_specific_frameworks = bool(frameworks_in_chains - {"", None})

    # Determine level (priority: expert > compliance > pm > layperson)
    if expert_count >= 3 or (expert_count >= 1 and has_specific_frameworks and len(chains) > 2):
        return "expert"
    elif compliance_count >= 2:
        return "compliance"
    elif pm_count >= 2:
        return "pm"
    elif expert_count >= 1 or compliance_count >= 1 or has_specific_frameworks:
        return "compliance"  # Default technical to compliance
    else:
        return "layperson"


def build_evidence_case(client: httpx.Client, question: str) -> tuple[dict, str]:
    """Call /create-evidence-case for deterministic entity + crosswalk resolution.

    Returns (evidence_dict, status) where status is 'ok' or 'failed'.
    """
    try:
        resp = client.post("/create-evidence-case", json={"question": question}, timeout=60.0)
        resp.raise_for_status()
        return resp.json(), "ok"
    except Exception as e:
        logger.warning(f"Evidence case failed: {e}")
        return {}, "failed"


async def build_evidence_case_async(
    client: httpx.AsyncClient,
    question: str,
    semaphore: asyncio.Semaphore,
    source_id: str | None = None,
) -> tuple[dict, str]:
    """Async version of build_evidence_case with semaphore for concurrency control."""
    async with semaphore:
        try:
            payload = {
                "question": question,
                "skip_qra_recall": True,  # Batch mode: flashtext + graph only, no hybrid search
            }
            # Pass source_id for fast path (skips entity extraction entirely)
            if source_id:
                payload["source_id"] = source_id
            resp = await client.post("/create-evidence-case", json=payload, timeout=60.0)
            resp.raise_for_status()
            return resp.json(), "ok"
        except Exception as e:
            logger.warning(f"Evidence case failed: {e}")
            return {}, "failed"


async def _empty_evidence() -> tuple[dict, str]:
    """Return empty evidence for docs without questions."""
    return {}, "skipped"


async def enrich_batch_parallel(
    docs: list,
    concurrency: int = DEFAULT_CONCURRENCY,
    use_direct: bool = True,
) -> list[tuple[dict, dict, str]]:
    """Enrich a batch of docs with evidence cases in parallel.

    Args:
        docs: List of QRA documents to enrich
        concurrency: Number of parallel evidence-case calls
        use_direct: If True, bypass Unix socket proxy and call port 8601 directly

    Returns list of (doc, evidence_case, status) tuples.
    """
    semaphore = asyncio.Semaphore(concurrency)

    async with get_async_client(use_direct=use_direct) as client:
        tasks = []
        for doc in docs:
            question = doc.get("question", "")
            # Use source_control_id as source_id for fast path (skips entity extraction)
            source_id = doc.get("source_control_id") or doc.get("control_id") or ""
            if question:
                tasks.append(build_evidence_case_async(client, question, semaphore, source_id=source_id))
            else:
                # Return empty evidence for docs without questions
                tasks.append(_empty_evidence())

        # Gather with return_exceptions to prevent one failure from killing all
        results = await asyncio.gather(*tasks, return_exceptions=True)

        enriched = []
        for doc, result in zip(docs, results):
            if isinstance(result, Exception):
                logger.warning(f"Exception for {doc.get('_key')}: {result}")
                enriched.append((doc, {}, "failed"))
            else:
                evidence, status = result
                enriched.append((doc, evidence, status))

        return enriched


def analyze_chains(chains: list) -> dict:
    """Extract framework relationships from crosswalk_chains.

    Case-normalized for framework matching (SPARTA, sparta -> SPARTA).
    """
    result = {
        "sparta_linked": False,
        "source_framework": None,
        "source_id": None,
        "target_framework": None,
        "target_id": None,
        "frameworks": set(),
    }

    for chain in chains:
        from_fw = (chain.get("from_framework") or "").upper()
        to_fw = (chain.get("to_framework") or "").upper()
        from_id = chain.get("from", "")

        if from_fw:
            result["frameworks"].add(from_fw)
        if to_fw:
            result["frameworks"].add(to_fw)

        # Case-insensitive SPARTA check
        if from_fw == "SPARTA" or to_fw == "SPARTA":
            result["sparta_linked"] = True

        # First non-SPARTA framework becomes source
        if not result["source_framework"] and from_fw and from_fw != "SPARTA":
            result["source_framework"] = from_fw
            result["source_id"] = from_id

        # SPARTA in target position
        if to_fw == "SPARTA" and not result["target_framework"]:
            result["target_framework"] = "SPARTA"
            hops = chain.get("hops", [])
            for hop in hops:
                hop_fw = (hop.get("framework") or "").upper()
                hop_id = hop.get("id", "")
                if hop_fw == "SPARTA" or str(hop_id).startswith("SV-"):
                    result["target_id"] = hop_id
                    break

    result["frameworks"] = sorted(result["frameworks"])  # Deterministic order
    return result


def determine_qra_type(doc: dict, chain_analysis: dict) -> str:
    """Determine QRA type from document and chain analysis."""
    if doc.get("source_framework") and doc.get("target_framework"):
        return "relationship"
    # Check both singular and plural field names
    if doc.get("crosswalk_chain") or doc.get("crosswalk_chains") or doc.get("bridge_evidence"):
        return "relationship"
    if len(chain_analysis.get("frameworks", [])) >= 2:
        return "relationship"
    if doc.get("source_doc") or doc.get("source_url"):
        return "standalone"
    if len(chain_analysis.get("frameworks", [])) == 1:
        return "independent"
    return "legacy"


def compute_relationship_id(source_id: str | None, target_id: str | None) -> str:
    """Generate relationship_id from source + target control IDs.

    This links persona variants together - all expertise variations
    of the same QRA share this relationship_id.

    CRITICAL: Requires BOTH IDs to avoid false grouping collisions.
    """
    # Require both IDs to prevent ""::SV-... collisions
    if not source_id or not target_id:
        return ""
    normalized = f"{source_id.upper()}::{target_id.upper()}"
    return hashlib.sha256(normalized.encode()).hexdigest()[:12]


def normalize_qra(doc: dict, evidence_case: dict, enrichment_status: str = "ok") -> dict:
    """Normalize QRA to standard schema with embedded evidence case.

    Args:
        doc: Original QRA document
        evidence_case: Result from /create-evidence-case
        enrichment_status: 'ok' or 'failed' - tracks evidence enrichment success
    """
    chains = evidence_case.get("crosswalk_chains", [])
    chain_analysis = analyze_chains(chains)
    qra_type = determine_qra_type(doc, chain_analysis)

    question = doc.get("question", "")
    reasoning = doc.get("reasoning", "")
    answer = doc.get("answer", "")

    # Get source/target IDs (from doc or chain analysis)
    source_id = doc.get("source_control_id") or doc.get("source_id") or chain_analysis["source_id"]
    target_id = doc.get("target_control_id") or doc.get("target_id") or chain_analysis["target_id"]
    source_framework = doc.get("source_framework") or chain_analysis["source_framework"]
    target_framework = doc.get("target_framework") or chain_analysis["target_framework"]

    # Build normalized document
    normalized = {
        "_key": doc["_key"],

        # Core QRA fields
        "question": question,
        "reasoning": reasoning,
        "answer": answer,

        # Type classification
        "qra_type": qra_type,
        "sparta_linked": chain_analysis["sparta_linked"],

        # Source/target (from doc or chain analysis)
        "source_framework": source_framework,
        "source_id": source_id,
        "target_framework": target_framework,
        "target_id": target_id,

        # Relationship linkage (groups expertise variations of same QRA)
        "relationship_id": compute_relationship_id(source_id, target_id),
        # parent_qra_id: set when generating expertise variations (links back to original)
        "parent_qra_id": doc.get("parent_qra_id"),

        # Evidence (original + case)
        "evidence_quotes": doc.get("evidence_quotes", []),
        "evidence_case": {
            "crosswalk_chains": chains,
            "glossary": evidence_case.get("glossary", []),
            "resolved_entities": [
                {"id": g.get("id"), "name": g.get("name"), "framework": g.get("framework")}
                for g in evidence_case.get("glossary", [])
            ],
        },

        # Training metadata
        "difficulty": determine_difficulty(chains, question),
        "expertise": determine_expertise(question, reasoning, answer, chains),
        "question_type": determine_question_type(qra_type, question),
        "token_counts": {
            "question": estimate_tokens(question),
            "reasoning": estimate_tokens(reasoning),
            "answer": estimate_tokens(answer),
            "total": estimate_tokens(question) + estimate_tokens(reasoning) + estimate_tokens(answer),
        },

        # Deduplication
        "content_hash": compute_content_hash(question, reasoning, answer),

        # Provenance
        "generation_source": doc.get("generation_source") or str(doc.get("qra_id", "")).split("_")[0] or "unknown",
        "generation_model": doc.get("generation_model") or "unknown",
        "creation_method": derive_creation_method(doc),
        "dataset_version": DATASET_VERSION,
        "framework_versions": FRAMEWORK_VERSIONS,

        # Quality
        "enrichment_status": enrichment_status,  # 'ok' or 'failed' - tracks evidence case success
        "curation_status": derive_curation_status(doc),
        "grounding_score": float(doc.get("grounding_score") or (1.0 if doc.get("verdict") == "SATISFIED" else 0.5)),

        # Domain-specific (cybersecurity)
        "security_domains": extract_security_domains(chains),

        # Original metadata preserved (normalized types for Arrow/HF)
        "pair_type": str(doc.get("pair_type") or ""),
        "confidence": str(doc.get("confidence") or ""),  # Normalize to string
        "verdict": str(doc.get("verdict") or ""),
        "generated_at": int(doc.get("generated_at") or doc.get("ts") or 0),  # Normalize to int
        "amended_at": int(datetime.now().timestamp()),

        # Preserve indexed fields (unique constraint on run_id, qra_id)
        "run_id": doc.get("run_id"),
        "qra_id": doc.get("qra_id"),
    }

    return normalized


def normalize_types_for_export(doc: dict) -> dict:
    """Ensure strict types for Arrow/HuggingFace compatibility.

    All fields must have consistent types across all documents.
    """
    # String fields (must not be None)
    string_fields = [
        "question", "reasoning", "answer", "qra_type", "source_framework",
        "source_id", "target_framework", "target_id", "relationship_id",
        "parent_qra_id", "expertise", "difficulty", "question_type",
        "content_hash", "generation_source", "generation_model", "creation_method",
        "dataset_version", "enrichment_status", "curation_status", "pair_type",
        "confidence", "verdict",
    ]
    for field in string_fields:
        if doc.get(field) is None:
            doc[field] = ""

    # Boolean fields
    if doc.get("sparta_linked") is None:
        doc["sparta_linked"] = False

    # Float fields
    if doc.get("grounding_score") is None:
        doc["grounding_score"] = 0.0
    else:
        doc["grounding_score"] = float(doc["grounding_score"])

    # Int fields
    for field in ["generated_at", "amended_at"]:
        if doc.get(field) is None:
            doc[field] = 0
        else:
            doc[field] = int(doc[field])

    # List fields
    for field in ["evidence_quotes", "security_domains"]:
        if doc.get(field) is None:
            doc[field] = []

    # Dict fields
    for field in ["token_counts", "framework_versions", "evidence_case"]:
        if doc.get(field) is None:
            doc[field] = {}

    return doc


def fetch_qras(client: httpx.Client, filters: dict | None, limit: int, offset: int = 0) -> tuple[list, int]:
    """Fetch QRAs from memory."""
    payload = {"collection": COLLECTION, "limit": limit, "offset": offset}
    if filters:
        payload["filters"] = filters
    resp = client.post("/list", json=payload)
    resp.raise_for_status()
    data = resp.json()
    return data.get("documents", []), data.get("total", 0)


def upsert_batch(client: httpx.Client, documents: list) -> dict:
    """Upsert batch of documents. Raises on any errors."""
    resp = client.post("/upsert", json={"collection": COLLECTION, "documents": documents})
    resp.raise_for_status()
    result = resp.json()

    # Check for document-level errors (can happen even with 200 status)
    if result.get("errors"):
        error_count = len(result["errors"])
        first_error = result["errors"][0].get("error", "unknown")
        raise RuntimeError(f"Upsert failed for {error_count} docs: {first_error}")

    return result


@app.command()
def stats():
    """Show current QRA schema field coverage."""
    client = get_client()
    docs, total = fetch_qras(client, None, 500)

    logger.info(f"Total QRAs: {total:,}")
    logger.info(f"Sample size: {len(docs)}")

    if not docs:
        logger.warning("No documents found in sample")
        return

    fields = ["qra_type", "sparta_linked", "source_framework", "target_framework", "evidence_case", "relationship_id", "expertise", "parent_qra_id", "enrichment_status"]
    for field in fields:
        count = sum(1 for d in docs if d.get(field) is not None)
        pct = count / len(docs) * 100
        logger.info(f"  {field}: {count} ({pct:.1f}%)")

    qra_types = {}
    for doc in docs:
        qt = doc.get("qra_type", "missing")
        qra_types[qt] = qra_types.get(qt, 0) + 1

    logger.info("QRA types:")
    for qt, count in sorted(qra_types.items(), key=lambda x: -x[1]):
        logger.info(f"  {qt}: {count} ({count/len(docs)*100:.1f}%)")


def fetch_qras_keyset(client: httpx.Client, filters: dict | None, limit: int, after_key: str = "") -> tuple[list, int, str]:
    """Fetch QRAs using keyset pagination (stable during mutation).

    Returns (docs, total, last_key) where last_key is the cursor for next batch.
    """
    payload = {
        "collection": COLLECTION,
        "limit": limit,
        "sort": "_key",  # Stable sort for keyset pagination
    }
    if filters:
        payload["filters"] = filters
    if after_key:
        payload["after_key"] = after_key

    resp = client.post("/list", json=payload)
    resp.raise_for_status()
    data = resp.json()
    docs = data.get("documents", [])
    last_key = docs[-1]["_key"] if docs else ""
    return docs, data.get("total", 0), last_key


def save_checkpoint(checkpoint_path: Path, last_key: str, total_processed: int, total_amended: int, total_skipped: int):
    """Save checkpoint for resumable processing."""
    checkpoint_path.write_text(json.dumps({
        "last_key": last_key,
        "total_processed": total_processed,
        "total_amended": total_amended,
        "total_skipped": total_skipped,
        "timestamp": datetime.now().isoformat(),
    }))


def load_checkpoint(checkpoint_path: Path) -> dict:
    """Load checkpoint if exists."""
    if checkpoint_path.exists():
        return json.loads(checkpoint_path.read_text())
    return {"last_key": "", "total_processed": 0, "total_amended": 0, "total_skipped": 0}


@app.command()
def amend(
    all_qras: bool = typer.Option(False, "--all", help="Process all QRAs"),
    framework: str = typer.Option("", help="Filter by source_framework"),
    batch_size: int = typer.Option(200, help="Batch size (larger = better parallelism)"),
    limit: int = typer.Option(0, help="Max QRAs (0=unlimited)"),
    dry_run: bool = typer.Option(False, help="Preview without writing"),
    export_after: bool = typer.Option(False, "--export", help="Export to JSONL after"),
    push_hf: bool = typer.Option(False, "--push-hf", help="Push to HuggingFace"),
    resume: bool = typer.Option(False, help="Resume from checkpoint"),
    skip_failed: bool = typer.Option(True, help="Skip QRAs with failed enrichment (don't write)"),
    concurrency: int = typer.Option(DEFAULT_CONCURRENCY, help="Parallel evidence-case calls"),
):
    """Amend QRAs with evidence case and normalized schema.

    Uses PARALLEL enrichment (default 32 concurrent calls).
    Uses keyset pagination for stability during mutation.
    Streams writes to JSONL per batch (no memory accumulation).
    Checkpoints progress for resumability.

    With i9 + 256GB RAM: ~1 hour for 225K QRAs (vs 12h sequential).
    """
    if not all_qras and not framework:
        logger.error("Specify --all or --framework")
        raise typer.Exit(1)

    # Run the async version
    asyncio.run(_amend_async(
        all_qras=all_qras,
        framework=framework,
        batch_size=batch_size,
        limit=limit,
        dry_run=dry_run,
        export_after=export_after,
        push_hf=push_hf,
        resume=resume,
        skip_failed=skip_failed,
        concurrency=concurrency,
    ))


async def _amend_async(
    all_qras: bool,
    framework: str,
    batch_size: int,
    limit: int,
    dry_run: bool,
    export_after: bool,
    push_hf: bool,
    resume: bool,
    skip_failed: bool,
    concurrency: int,
):
    """Async implementation of amend command with parallel enrichment."""
    client = get_client()  # Sync client for fetch/upsert (fast operations)
    filters = {"source_framework": framework} if framework else None

    # Checkpoint setup
    checkpoint_path = EXPORT_DIR / "amend_checkpoint.json"
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    if resume:
        checkpoint = load_checkpoint(checkpoint_path)
        after_key = checkpoint["last_key"]
        total_processed = checkpoint["total_processed"]
        total_amended = checkpoint["total_amended"]
        total_skipped = checkpoint.get("total_skipped", 0)
        logger.info(f"Resuming from checkpoint: {total_processed:,} processed, after_key={after_key[:12]}...")
    else:
        after_key = ""
        total_processed = 0
        total_amended = 0
        total_skipped = 0

    # Streaming JSONL output
    jsonl_path = EXPORT_DIR / "train.jsonl"
    jsonl_mode = "a" if resume else "w"
    jsonl_file = open(jsonl_path, jsonl_mode) if export_after and not dry_run else None

    batch_num = total_processed // batch_size
    start_time = datetime.now()

    try:
        while True:
            fetch_limit = min(batch_size, limit - total_processed) if limit else batch_size
            if fetch_limit <= 0:
                break

            docs, total, last_key = fetch_qras_keyset(client, filters, fetch_limit, after_key)
            if not docs:
                break

            batch_num += 1
            if total_processed == 0 or (resume and batch_num == 1):
                logger.info(f"Total QRAs to process: {total:,}")
                logger.info(f"Concurrency: {concurrency} parallel evidence-case calls")

            batch_start = datetime.now()
            logger.info(f"Batch {batch_num}: enriching {len(docs)} QRAs in parallel...")

            # PARALLEL enrichment (the key optimization)
            enriched = await enrich_batch_parallel(docs, concurrency=concurrency)

            normalized_batch = []
            skipped_batch = 0

            for doc, evidence, status in enriched:
                if not doc.get("question"):
                    skipped_batch += 1
                    continue

                # Skip failed enrichments if configured (prevents silent corruption)
                if status == "failed" and skip_failed:
                    skipped_batch += 1
                    total_skipped += 1
                    continue

                if status == "skipped":
                    skipped_batch += 1
                    continue

                # Normalize with enrichment status
                normalized = normalize_qra(doc, evidence, enrichment_status=status)
                normalized_batch.append(normalized)

                # Stream to JSONL (no memory accumulation)
                if jsonl_file:
                    export_doc = {k: v for k, v in normalized.items() if not k.startswith("_") or k == "_key"}
                    export_doc = normalize_types_for_export(export_doc)
                    jsonl_file.write(json.dumps(export_doc, ensure_ascii=False) + "\n")

            batch_elapsed = (datetime.now() - batch_start).total_seconds()

            if normalized_batch:
                if dry_run:
                    logger.info(f"  Would amend {len(normalized_batch)} QRAs (skipped {skipped_batch}) [{batch_elapsed:.1f}s]")
                    for n in normalized_batch[:2]:
                        logger.info(f"    {n['_key']}: type={n['qra_type']}, sparta={n['sparta_linked']}")
                else:
                    upsert_batch(client, normalized_batch)
                    qps = len(normalized_batch) / batch_elapsed if batch_elapsed > 0 else 0
                    logger.info(f"  Amended {len(normalized_batch)} QRAs (skipped {skipped_batch}) [{batch_elapsed:.1f}s, {qps:.0f} QRA/s]")

                total_amended += len(normalized_batch)

            total_processed += len(docs)
            after_key = last_key

            # Progress estimate
            if total > 0:
                pct = total_processed / total * 100
                elapsed = (datetime.now() - start_time).total_seconds()
                rate = total_processed / elapsed if elapsed > 0 else 0
                remaining = (total - total_processed) / rate if rate > 0 else 0
                logger.info(f"  Progress: {total_processed:,}/{total:,} ({pct:.1f}%) - ETA: {remaining/60:.0f}m")

            # Save checkpoint every batch
            if not dry_run:
                save_checkpoint(checkpoint_path, after_key, total_processed, total_amended, total_skipped)

            if len(docs) < batch_size:
                break

    finally:
        if jsonl_file:
            jsonl_file.close()

    total_elapsed = (datetime.now() - start_time).total_seconds()
    logger.info(f"Total processed: {total_processed:,}")
    logger.info(f"Total amended: {total_amended:,}")
    logger.info(f"Total skipped: {total_skipped:,}")
    logger.info(f"Total time: {total_elapsed/60:.1f} minutes ({total_processed/total_elapsed:.0f} QRA/s)")

    if export_after and not dry_run:
        logger.info(f"Exported to {jsonl_path}")
        _write_dataset_card(total_amended)
        if push_hf:
            _push_to_hf()


@app.command()
def export(
    push_hf: bool = typer.Option(False, "--push-hf", help="Push to HuggingFace"),
    limit: int = typer.Option(0, help="Limit export (0=all)"),
):
    """Export QRAs to JSONL and optionally push to HuggingFace."""
    client = get_client()

    logger.info("Exporting QRAs to JSONL...")
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    all_docs = []
    offset = 0
    batch_size = 500

    while True:
        if limit and len(all_docs) >= limit:
            break

        docs, total = fetch_qras(client, None, batch_size, offset)
        if not docs:
            break

        if offset == 0:
            logger.info(f"Total QRAs: {total:,}")

        all_docs.extend(docs)
        offset += len(docs)
        logger.info(f"  Fetched {len(all_docs):,} / {total:,}")

        if len(docs) < batch_size:
            break

    if limit:
        all_docs = all_docs[:limit]

    _export_jsonl(all_docs)

    if push_hf:
        _push_to_hf()


def _export_jsonl(docs: list):
    """Write documents to JSONL file."""
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    jsonl_path = EXPORT_DIR / "train.jsonl"

    # Fields to exclude: embeddings (large), ArangoDB internals
    EXCLUDE_FIELDS = {"embedding", "_id", "_rev"}

    with open(jsonl_path, "w") as f:
        for doc in docs:
            # Remove embeddings and ArangoDB internal fields for smaller export
            export_doc = {
                k: v for k, v in doc.items()
                if k not in EXCLUDE_FIELDS and (not k.startswith("_") or k == "_key")
            }
            f.write(json.dumps(export_doc, ensure_ascii=False) + "\n")

    logger.info(f"Exported {len(docs):,} QRAs to {jsonl_path}")

    # Write dataset card
    _write_dataset_card(len(docs))


def _write_dataset_card(count: int):
    """Generate HuggingFace dataset card."""
    card = f"""---
license: cc-by-nc-4.0
task_categories:
  - question-answering
  - text-generation
  - text2text-generation
language:
  - en
tags:
  - cybersecurity
  - compliance
  - space-systems
  - SPARTA
  - CWE
  - CAPEC
  - ATT&CK
  - NIST
  - grounded-qa
  - chain-of-thought
  - reasoning
  - instruction-tuning
size_categories:
  - 100K<n<1M
pretty_name: SPARTA QRA Grounded Dataset
dataset_info:
  features:
    - name: question
      dtype: string
    - name: reasoning
      dtype: string
    - name: answer
      dtype: string
    - name: qra_type
      dtype: string
    - name: sparta_linked
      dtype: bool
    - name: source_framework
      dtype: string
    - name: source_id
      dtype: string
    - name: target_framework
      dtype: string
    - name: target_id
      dtype: string
    - name: relationship_id
      dtype: string
    - name: expertise
      dtype: string
    - name: difficulty
      dtype: string
    - name: content_hash
      dtype: string
    - name: enrichment_status
      dtype: string
  splits:
    - name: train
      num_examples: {count}
configs:
  - config_name: default
    data_files:
      - split: train
        path: train.jsonl
---

# SPARTA QRA Grounded Dataset

A large-scale Question-Reasoning-Answer dataset for cybersecurity compliance, featuring **{count:,}** QRA pairs grounded in MITRE frameworks with deterministic evidence chains.

## Dataset Description

### Summary

This dataset contains grounded Q&A pairs for cybersecurity compliance training, with a focus on:
- **Space systems security** (SPARTA framework)
- **Cross-framework mappings** (CWE → CAPEC → ATT&CK → SPARTA)
- **Chain-of-thought reasoning** with evidence citations

### Intended Use

- **Fine-tuning LLMs** for compliance-aware Q&A
- **Instruction tuning** with reasoning traces
- **RAG evaluation** with grounded evidence
- **Cybersecurity training** with authoritative sources

### Languages

English only.

## Dataset Structure

### Data Fields

| Field | Type | Description |
|-------|------|-------------|
| `question` | string | The compliance/security question |
| `reasoning` | string | Step-by-step chain-of-thought reasoning |
| `answer` | string | Grounded answer with evidence support |
| `qra_type` | string | `relationship`, `independent`, `standalone`, or `legacy` |
| `sparta_linked` | bool | True if linked to SPARTA space security framework |
| `source_framework` | string | Source framework (CWE, CAPEC, ATT&CK, NIST) |
| `source_id` | string | Source control ID (e.g., CWE-79) |
| `target_framework` | string | Target framework (usually SPARTA) |
| `target_id` | string | Target control ID (e.g., SV-AC-2) |
| `relationship_id` | string | Hash linking persona variations of same QRA |
| `expertise` | string | Target audience: `layperson`, `pm`, `compliance`, `expert` |
| `difficulty` | string | Reasoning complexity: `single_hop`, `multi_hop`, `synthesis` |
| `content_hash` | string | Deduplication hash (Q+R+A) |
| `evidence_case` | object | Embedded crosswalk chains and resolved entities |
| `evidence_quotes` | list | Direct quotes from source documents |
| `enrichment_status` | string | `ok` or `failed` (evidence extraction status) |
| `token_counts` | object | Token estimates for Q, R, A, and total |
| `security_domains` | list | Domain tags (authentication, access_control, etc.) |

### Evidence Case Structure

Each QRA includes deterministic evidence from `/create-evidence-case`:

```json
{{
  "crosswalk_chains": [
    {{
      "from": "CWE-79",
      "from_framework": "CWE",
      "to_framework": "SPARTA",
      "hops": [
        {{"id": "CAPEC-86", "framework": "CAPEC"}},
        {{"id": "T1059", "framework": "ATT&CK"}},
        {{"id": "SV-AC-2", "framework": "SPARTA"}}
      ]
    }}
  ],
  "resolved_entities": [
    {{"id": "CWE-79", "name": "Cross-site Scripting", "framework": "CWE"}}
  ]
}}
```

### QRA Types

| Type | Description | Approximate % |
|------|-------------|---------------|
| `relationship` | Cross-framework mapping (CWE→SPARTA) | ~60% |
| `independent` | Single-framework control Q&A | ~25% |
| `standalone` | Document-based extraction | ~10% |
| `legacy` | Pre-schema QRAs | ~5% |

### Expertise Levels

| Level | Description |
|-------|-------------|
| `layperson` | No assumed technical knowledge, plain language |
| `pm` | Project manager level, dependency/schedule focus |
| `compliance` | Compliance officer, regulatory/audit focus |
| `expert` | Deep cybersecurity/technical expertise required |

## Usage

```python
from datasets import load_dataset

# Load dataset (requires authentication for private repo)
ds = load_dataset("grahamaco/sparta-qra-grounded", token="your_hf_token")

# Filter for SPARTA-linked expert-level QRAs
expert_sparta = ds["train"].filter(
    lambda x: x["sparta_linked"] and x["expertise"] == "expert"
)

# Access evidence chains
for row in expert_sparta:
    print(f"Q: {{row['question']}}")
    print(f"A: {{row['answer']}}")
    for chain in row["evidence_case"]["crosswalk_chains"]:
        hops = " → ".join([h["id"] for h in chain.get("hops", [])])
        print(f"  Evidence: {{chain['from']}} → {{hops}}")
```

### Training Format

Convert to instruction-tuning format:

```python
def to_instruction(row):
    return {{
        "instruction": row["question"],
        "input": "",
        "output": f"Reasoning: {{row['reasoning']}}\\n\\nAnswer: {{row['answer']}}"
    }}

train_data = [to_instruction(r) for r in ds["train"]]
```

## Source Frameworks

| Framework | Description | Version |
|-----------|-------------|---------|
| **SPARTA** | Space Attack Research & Tactic Analysis (NASA/MITRE) | 3.1 |
| **CWE** | Common Weakness Enumeration | 4.14 |
| **CAPEC** | Common Attack Pattern Enumeration and Classification | 3.9 |
| **ATT&CK** | MITRE ATT&CK Enterprise | 15.1 |
| **NIST** | NIST 800-53 Controls | r5 |

## Dataset Creation

### Curation Rationale

This dataset addresses the lack of grounded Q&A data for cybersecurity compliance training. Unlike generic Q&A datasets, each answer is:
1. **Grounded** in authoritative MITRE/NIST frameworks
2. **Traceable** via deterministic crosswalk chains
3. **Verifiable** through embedded evidence quotes

### Source Data

- SPARTA v3.1 techniques and countermeasures
- CWE weakness descriptions and mitigations
- CAPEC attack pattern descriptions
- ATT&CK technique descriptions
- NIST 800-53 control descriptions
- URL knowledge extractions from authoritative sources

### Annotations

QRAs are generated via LLM with deterministic grounding:
1. **Entity extraction** via flashtext (no LLM)
2. **Crosswalk resolution** via ArangoDB graph traversal
3. **QRA generation** via LLM with grounding constraints
4. **Quality gates** verify evidence presence and grounding

### Personal and Sensitive Information

This dataset contains no personal or sensitive information. All content is derived from publicly available security frameworks.

## Considerations

### Social Impact

This dataset enables training of cybersecurity-aware LLMs that can:
- Provide grounded compliance guidance
- Trace answers to authoritative sources
- Support audit and assessment workflows

### Limitations

- **English only**: All content is in English
- **Domain specific**: Focused on cybersecurity/compliance
- **Framework versions**: Tied to specific framework versions (may need updates)
- **Synthetic reasoning**: Reasoning traces are LLM-generated (not human-written)

### Recommendations

- Use with RAG systems for production deployments
- Verify critical compliance answers against authoritative sources
- Update periodically as framework versions change

## License

CC-BY-NC-4.0 (non-commercial use)

## Citation

```bibtex
@dataset{{sparta_qra_grounded_2026,
  title={{SPARTA QRA Grounded Dataset}},
  author={{Graham Neubig}},
  year={{2026}},
  publisher={{Hugging Face}},
  url={{https://huggingface.co/datasets/grahamaco/sparta-qra-grounded}},
  note={{Private dataset for cybersecurity compliance Q&A}}
}}
```

## Dataset Card Contact

For questions or issues, contact via HuggingFace or the dataset repository.
"""
    card_path = EXPORT_DIR / "README.md"
    card_path.write_text(card)
    logger.info(f"Wrote dataset card to {card_path}")


def _push_to_hf():
    """Push dataset to HuggingFace Hub as a private dataset."""
    from dotenv import load_dotenv
    load_dotenv()

    token = os.environ.get("HF_TOKEN", "")
    if not token:
        logger.error("HF_TOKEN not set in .env — cannot push")
        return

    try:
        from datasets import load_dataset, DatasetDict
        from huggingface_hub import HfApi, create_repo

        api = HfApi(token=token)

        # Ensure repo exists and is private
        logger.info(f"Creating/verifying private repo {HF_REPO}...")
        try:
            create_repo(
                repo_id=HF_REPO,
                token=token,
                repo_type="dataset",
                private=True,
                exist_ok=True,
            )
        except Exception as e:
            logger.warning(f"Repo creation note: {e}")

        logger.info(f"Loading dataset from {EXPORT_DIR}...")
        ds = load_dataset("json", data_files=str(EXPORT_DIR / "train.jsonl"))

        # Wrap in DatasetDict for proper split handling
        if not isinstance(ds, DatasetDict):
            ds = DatasetDict({"train": ds["train"]})

        logger.info(f"Pushing {len(ds['train']):,} examples to {HF_REPO}...")
        ds.push_to_hub(
            HF_REPO,
            token=token,
            private=True,
            commit_message=f"Update dataset: {len(ds['train']):,} QRAs with evidence case enrichment",
        )

        # Upload the README (dataset card)
        logger.info("Uploading dataset card...")
        api.upload_file(
            path_or_fileobj=str(EXPORT_DIR / "README.md"),
            path_in_repo="README.md",
            repo_id=HF_REPO,
            repo_type="dataset",
            commit_message="Update dataset card with schema and usage documentation",
        )

        logger.info(f"Successfully pushed to https://huggingface.co/datasets/{HF_REPO}")

    except Exception as e:
        logger.error(f"HF push failed: {e}")
        raise


if __name__ == "__main__":
    app()
