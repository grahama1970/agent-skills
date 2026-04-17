#!/usr/bin/env python3
"""
Skill integration wrappers for monitor-personas.

Provides clean Python interfaces to sibling skills:
- taxonomy: Extract Federated Taxonomy tags
- memory: Learn content with scope/tags
- doc2qra: QRA extraction via LLM
- extractor: Structure extraction (sections, tables, metadata)
- episodic-archiver: Archive sessions
- edge-verifier: Verify knowledge graph relationships
"""

import json
import subprocess
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


SKILL_DIR = Path(__file__).parent
PROJECT_ROOT = SKILL_DIR.parent.parent.parent


@dataclass
class TaxonomyResult:
    """Result from taxonomy extraction."""
    bridge_tags: List[str]
    collection_tags: Dict[str, List[str]]
    raw_output: str


@dataclass
class MemoryLearnResult:
    """Result from memory learning."""
    success: bool
    documents_ingested: int
    chunks_created: int
    message: str


class TaxonomyIntegration:
    """Wrapper for /taxonomy skill."""

    # Map persona categories to taxonomy collections
    CATEGORY_COLLECTION_MAP = {
        "fictitious": "operational",       # depends on persona's scope
        "horus_lore": "lore",
        "video_generation": "cinematography",
        "ml_training": "operational",
        "music_production": "lore",
        "security": "sparta",
        "filmmaking": "cinematography",
        "behavioral": "behavioral",
    }

    # Map persona scope prefixes to taxonomy collections
    SCOPE_COLLECTION_MAP = {
        "sparta": "sparta",
        "lore": "lore",
        "horus": "lore",
        "behavioral": "behavioral",
        "cinema": "cinematography",
        "film": "cinematography",
    }

    def __init__(self, project_root: Path = PROJECT_ROOT):
        self.taxonomy_dir = project_root / ".pi/skills/taxonomy"
        self.run_sh = self.taxonomy_dir / "run.sh"

    def is_available(self) -> bool:
        """Check if taxonomy skill is available."""
        return self.run_sh.exists()

    def collection_for_persona(self, category: str = "", scope: str = "") -> str:
        """Determine taxonomy collection from persona category or scope.

        Priority: scope prefix > category mapping > default 'operational'.
        """
        # Check scope first
        scope_lower = scope.lower()
        for prefix, collection in self.SCOPE_COLLECTION_MAP.items():
            if prefix in scope_lower:
                return collection

        # Then check category
        if category in self.CATEGORY_COLLECTION_MAP:
            return self.CATEGORY_COLLECTION_MAP[category]

        return "operational"

    def extract(
        self,
        text: str,
        collection: str = "operational",
        bridges_only: bool = True,
        fast: bool = True,
    ) -> TaxonomyResult:
        """
        Extract taxonomy tags from text.

        Args:
            text: Text to analyze (truncated to 3000 chars)
            collection: Collection type (lore|operational|sparta|behavioral)
            bridges_only: Only return bridge tags
            fast: Use keyword extraction only (no LLM)

        Returns:
            TaxonomyResult with extracted tags
        """
        if not self.is_available():
            return TaxonomyResult(bridge_tags=[], collection_tags={}, raw_output="Taxonomy not available")

        cmd = [str(self.run_sh), "extract", "--text", text[:3000]]

        if collection:
            cmd.extend(["--collection", collection])
        if bridges_only:
            cmd.append("--bridges-only")
        if fast:
            cmd.append("--fast")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=self.taxonomy_dir,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )

            if result.returncode != 0:
                return TaxonomyResult(
                    bridge_tags=[],
                    collection_tags={},
                    raw_output=f"Error: {result.stderr}",
                )

            # Parse output - taxonomy outputs one tag per line by default
            output = result.stdout.strip()
            tags = [t.strip() for t in output.split('\n') if t.strip()]

            return TaxonomyResult(
                bridge_tags=tags,
                collection_tags={},
                raw_output=output,
            )

        except subprocess.TimeoutExpired:
            return TaxonomyResult(bridge_tags=[], collection_tags={}, raw_output="Timeout")
        except Exception as e:
            return TaxonomyResult(bridge_tags=[], collection_tags={}, raw_output=str(e))


class MemoryIntegration:
    """Wrapper for /memory skill (horus_lore_cli)."""

    def __init__(self, project_root: Path = PROJECT_ROOT):
        self.memory_dir = project_root / ".pi/skills/memory"
        self.run_sh = self.memory_dir / "run.sh"

    def is_available(self) -> bool:
        """Check if memory skill is available."""
        return self.run_sh.exists()

    def ingest_youtube_directory(
        self,
        input_dir: Path,
        scope: str = "",
        tags: Optional[List[str]] = None,
    ) -> MemoryLearnResult:
        """
        Ingest a directory of YouTube transcripts to memory.

        This is the batch ingestion approach - ingest all transcripts
        in a persona directory at once.

        Args:
            input_dir: Directory containing JSON transcript files
            scope: Memory scope for this persona (e.g., 'sparta', 'lore')
            tags: Bridge tags to apply (e.g., ['Precision', 'Resilience'])

        Returns:
            MemoryLearnResult with ingestion status
        """
        if not self.is_available():
            return MemoryLearnResult(
                success=False,
                documents_ingested=0,
                chunks_created=0,
                message="Memory skill not available",
            )

        if not input_dir.exists():
            return MemoryLearnResult(
                success=False,
                documents_ingested=0,
                chunks_created=0,
                message=f"Input directory not found: {input_dir}",
            )

        cmd = [str(self.run_sh), "youtube", "--input", str(input_dir)]
        if scope:
            cmd.extend(["--scope", scope])
        if tags:
            for tag in tags:
                cmd.extend(["--tag", tag])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 min timeout for batch ingestion
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )

            if result.returncode != 0:
                return MemoryLearnResult(
                    success=False,
                    documents_ingested=0,
                    chunks_created=0,
                    message=f"Error: {result.stderr}",
                )

            # Try to parse stats from output
            output = result.stdout
            docs = 0
            chunks = 0

            # Look for patterns like "Ingested X documents" or "Created Y chunks"
            for line in output.split('\n'):
                if 'document' in line.lower() and any(c.isdigit() for c in line):
                    # Extract first number
                    nums = [int(s) for s in line.split() if s.isdigit()]
                    if nums:
                        docs = nums[0]
                if 'chunk' in line.lower() and any(c.isdigit() for c in line):
                    nums = [int(s) for s in line.split() if s.isdigit()]
                    if nums:
                        chunks = nums[0]

            return MemoryLearnResult(
                success=True,
                documents_ingested=docs,
                chunks_created=chunks,
                message=output[:500] if output else "Ingestion completed",
            )

        except subprocess.TimeoutExpired:
            return MemoryLearnResult(
                success=False,
                documents_ingested=0,
                chunks_created=0,
                message="Timeout during ingestion",
            )
        except Exception as e:
            return MemoryLearnResult(
                success=False,
                documents_ingested=0,
                chunks_created=0,
                message=str(e),
            )

    def learn_lesson(
        self,
        problem: str,
        solution: str,
        scope: str = "",
        tags: Optional[List[str]] = None,
    ) -> bool:
        """
        Store a single problem/solution lesson to memory.

        Memory system auto-handles timestamps, decay, contradictions.

        Args:
            problem: Problem description
            solution: Solution description
            scope: Memory scope (persona-specific)
            tags: Bridge tags (e.g., ['Precision', 'session:xyz'])

        Returns:
            True if stored successfully
        """
        if not self.is_available():
            return False

        cmd = [
            str(self.run_sh), "learn",
            "--problem", problem[:1000],
            "--solution", solution[:2000],
        ]
        if scope:
            cmd.extend(["--scope", scope])
        if tags:
            for tag in tags:
                cmd.extend(["--tag", tag])

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            return result.returncode == 0
        except Exception:
            return False

    def query(self, query_text: str) -> str:
        """
        Query memory for relevant content.

        Args:
            query_text: Query string

        Returns:
            Retrieved content as string
        """
        if not self.is_available():
            return "Memory skill not available"

        cmd = [str(self.run_sh), "query", query_text]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            return result.stdout if result.returncode == 0 else result.stderr
        except Exception as e:
            return str(e)

    def ask_colleague(
        self,
        query: str,
        colleague_persona_id: str,
        colleague_scope: str = "",
        k: int = 5,
    ) -> Dict[str, Any]:
        """Cross-persona recall — query a colleague's memory scope.

        Enables personas to access each other's knowledge via scoped recall.

        Args:
            query: Question to ask
            colleague_persona_id: Persona ID of the colleague
            colleague_scope: Memory scope of the colleague (if not provided, uses persona_id)
            k: Number of results to return

        Returns:
            Dict with recall results tagged with source_persona
        """
        if not self.is_available():
            return {"error": "Memory skill not available", "items": []}

        scope = colleague_scope or colleague_persona_id

        cmd = [
            str(self.run_sh), "recall",
            "--q", query[:500],
            "--scope", scope,
            "-k", str(k),
        ]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            if result.returncode != 0:
                return {"error": result.stderr[:200], "items": []}

            data = json.loads(result.stdout)
            items = data.get("items", [])

            # Tag each result with source persona
            for item in items:
                item["source_persona"] = colleague_persona_id

            return {
                "source_persona": colleague_persona_id,
                "scope": scope,
                "query": query,
                "found": len(items) > 0,
                "items": items,
            }
        except json.JSONDecodeError:
            return {"error": "Failed to parse recall response", "items": []}
        except Exception as e:
            return {"error": str(e), "items": []}

    def get_status(self) -> Dict[str, Any]:
        """Get memory status."""
        if not self.is_available():
            return {"error": "Memory skill not available"}

        cmd = [str(self.run_sh), "status"]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            return {"output": result.stdout, "returncode": result.returncode}
        except Exception as e:
            return {"error": str(e)}


class ExtractorIntegration:
    """Wrapper for /extractor skill (document structure extraction).

    Extracts document metadata (sections, tables, figures). For QRA generation,
    use Doc2QRAIntegration instead.
    """

    def __init__(self, project_root: Path = PROJECT_ROOT):
        self.extractor_dir = project_root / ".pi/skills/extractor"
        self.run_sh = self.extractor_dir / "run.sh"

    def is_available(self) -> bool:
        """Check if extractor skill is available."""
        return self.run_sh.exists()

    def extract_qra(
        self,
        file_path: Path,
        preset: str = "auto",
        fast: bool = True,
    ) -> Dict[str, Any]:
        """
        Extract content from a document.

        Args:
            file_path: Path to document (PDF, MD, HTML, etc.)
            preset: Extraction preset
            fast: Use fast extraction mode

        Returns:
            Dict with extracted content and metadata
        """
        if not self.is_available():
            return {"error": "Extractor skill not available"}

        cmd = [str(self.run_sh), str(file_path)]

        if fast:
            cmd.append("--fast")
        if preset != "auto":
            cmd.extend(["--preset", preset])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )

            if result.returncode != 0:
                return {"error": result.stderr}

            return {"output": result.stdout, "success": True}

        except Exception as e:
            return {"error": str(e)}

    def convert(
        self,
        file_path: Path,
        scope: str = "research",
        context: str = "",
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Extract and learn a text/markdown file to memory.

        Drop-in replacement for Doc2QRAIntegration.convert().

        Args:
            file_path: Path to text file (MD, TXT, etc.)
            scope: Memory scope for this persona
            context: Domain focus (unused by extractor, kept for API compat)
            dry_run: Preview without storing to memory

        Returns:
            Dict with section count, success status, and summary
        """
        if not self.is_available():
            return {"error": "Extractor skill not available", "qra_count": 0}

        cmd = [str(self.run_sh), str(file_path), "--fast"]
        if not dry_run:
            cmd.extend(["--learn", "--scope", scope])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=180,
                cwd=self.extractor_dir,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )

            if result.returncode != 0:
                return {"error": result.stderr, "qra_count": 0}

            output = result.stdout.strip()
            try:
                data = json.loads(output)
                # Map extractor sections to QRA count for backward compat
                sections = data.get("document", {}).get("sections", [])
                section_count = len(sections) if isinstance(sections, list) else 0
                return {
                    "success": True,
                    "qra_count": section_count,
                    "qras": sections,
                    "summary": data.get("document", {}).get("metadata", {}).get("title", ""),
                    "memory_learned": data.get("memory_learned", False),
                    "raw": output,
                }
            except json.JSONDecodeError:
                # Non-JSON output — count section-like patterns
                lines = output.split("\n")
                section_count = sum(1 for l in lines if l.strip().startswith("#"))
                return {
                    "success": True,
                    "qra_count": max(section_count, 1) if output else 0,
                    "raw": output,
                }

        except subprocess.TimeoutExpired:
            return {"error": "Timeout during extraction", "qra_count": 0}
        except Exception as e:
            return {"error": str(e), "qra_count": 0}


class Doc2QRAIntegration:
    """Wrapper for /doc2qra skill — QRA extraction via LLM.

    Complements ExtractorIntegration (structure extraction).
    doc2qra produces true QRA triplets; extractor produces document metadata.
    """

    def __init__(self, project_root: Path = PROJECT_ROOT):
        self.doc2qra_dir = project_root / ".pi/skills/doc2qra"
        self.run_sh = self.doc2qra_dir / "run.sh"

    def is_available(self) -> bool:
        """Check if doc2qra skill is available."""
        return self.run_sh.exists()

    def convert(
        self,
        file_path: Path,
        scope: str = "research",
        context: str = "",
        persona: str = "",
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Extract QRA pairs from a document via doc2qra.

        Args:
            file_path: Path to text file (MD, TXT, PDF, etc.)
            scope: Memory scope for this persona
            context: Domain focus for extraction
            persona: Persona name for quality gating
            dry_run: Preview without storing to memory

        Returns:
            Dict with qra_count, qras, summary, persona_verdict, success
        """
        if not self.is_available():
            return {"error": "doc2qra skill not available", "qra_count": 0}

        cmd = [
            "bash", str(self.run_sh), "distill",
            "--file", str(file_path),
            "--scope", scope,
            "--json",
        ]
        if persona:
            cmd.extend(["--persona", persona])
        if context:
            cmd.extend(["--context", context])
        if dry_run:
            cmd.append("--dry-run")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                cwd=self.doc2qra_dir,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )

            if result.returncode != 0:
                return {"error": result.stderr, "qra_count": 0}

            output = result.stdout.strip()
            try:
                data = json.loads(output)
                return {
                    "success": True,
                    "qra_count": data.get("extracted", 0),
                    "qras": data.get("qra_pairs", []),
                    "summary": data.get("summary", ""),
                    "persona_verdict": data.get("persona_verdict"),
                }
            except json.JSONDecodeError:
                return {
                    "success": True,
                    "qra_count": 0,
                    "raw": output,
                }

        except subprocess.TimeoutExpired:
            return {"error": "Timeout during QRA extraction", "qra_count": 0}
        except Exception as e:
            return {"error": str(e), "qra_count": 0}


class EpisodicArchiverIntegration:
    """Wrapper for /episodic-archiver skill."""

    def __init__(self, project_root: Path = PROJECT_ROOT):
        self.archiver_dir = project_root / ".pi/skills/episodic-archiver"
        self.run_sh = self.archiver_dir / "run.sh"

    def is_available(self) -> bool:
        """Check if episodic-archiver skill is available."""
        return self.run_sh.exists()

    def archive_session(
        self,
        session_id: str,
        content: str,
        metadata: Dict[str, Any],
    ) -> bool:
        """
        Archive a session to episodic memory.

        Args:
            session_id: Unique session identifier
            content: Session content/transcript
            metadata: Session metadata (persona, scope, etc.)

        Returns:
            True if archived successfully
        """
        if not self.is_available():
            return False

        raise NotImplementedError("archive_session not yet implemented — episodic-archiver CLI not defined")

    def list_unresolved(self) -> List[Dict[str, Any]]:
        """List unresolved sessions that need reflection."""
        if not self.is_available():
            return []

        raise NotImplementedError("list_unresolved not yet implemented")


class EdgeVerifierIntegration:
    """Wrapper for /edge-verifier skill."""

    def __init__(self, project_root: Path = PROJECT_ROOT):
        self.verifier_dir = project_root / ".pi/skills/edge-verifier"
        self.run_sh = self.verifier_dir / "run.sh"

    def is_available(self) -> bool:
        """Check if edge-verifier skill is available."""
        return self.run_sh.exists()

    def verify_edges(
        self,
        source_text: str,
        collection: str = "operational",
    ) -> Dict[str, Any]:
        """
        Verify relationships between source text and existing knowledge.

        Args:
            source_text: New content to verify against existing knowledge
            collection: Knowledge graph collection to check

        Returns:
            Dict with verification results (verifies/contradicts/related)
        """
        if not self.is_available():
            return {"error": "Edge verifier not available"}

        raise NotImplementedError("verify_edges not yet implemented — edge-verifier CLI not defined")


# Convenience functions
def get_taxonomy() -> TaxonomyIntegration:
    return TaxonomyIntegration()


def get_memory() -> MemoryIntegration:
    return MemoryIntegration()


def get_extractor() -> ExtractorIntegration:
    return ExtractorIntegration()


def get_doc2qra() -> Doc2QRAIntegration:
    return Doc2QRAIntegration()


def get_episodic_archiver() -> EpisodicArchiverIntegration:
    return EpisodicArchiverIntegration()


def get_edge_verifier() -> EdgeVerifierIntegration:
    return EdgeVerifierIntegration()
