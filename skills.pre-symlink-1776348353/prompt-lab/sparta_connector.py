"""
SPARTA Data Connector for Prompt Lab.
Connects to SPARTA DuckDB to fetch control data and relationships for QRA testing.
"""
import sys
from pathlib import Path

try:
    import duckdb
    HAS_DUCKDB = True
except ImportError:
    HAS_DUCKDB = False
    duckdb = None  # type: ignore
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import json


def _log_warn(msg: str):
    """Log a warning to stderr with yellow color."""
    print(f"\033[33m[sparta_connector] {msg}\033[0m", file=sys.stderr)

@dataclass
class SpartaTestCase:
    """A test case extracted from SPARTA data."""
    id: str
    source_control: Dict[str, Any]
    target_control: Optional[Dict[str, Any]]
    knowledge_excerpts: List[str]
    context_keywords: List[str]
    relationship: Optional[Dict[str, Any]] = None


class SpartaConnector:
    def __init__(self, db_path: Path):
        if not HAS_DUCKDB:
            raise ImportError("duckdb required. Install with: pip install duckdb")
        self.db_path = db_path
        if not self.db_path.exists():
            raise FileNotFoundError(f"SPARTA DuckDB not found at {self.db_path}")

    def get_connection(self):
        return duckdb.connect(str(self.db_path), read_only=True)

    def fetch_test_cases(self, limit: int = 100, phase: int = 0) -> List[SpartaTestCase]:
        """
        Fetch test cases from SPARTA DB.
        
        Phases:
        0 - Relationship-based (Technique -> Control) - Primary QRA source
        1 - Control-based (Control + Knowledge) - Simple QRA source
        """
        conn = self.get_connection()
        cases = []

        try:
            if phase == 0:
                # Fetch relationships (KNN or Taxonomy)
                # We prioritize taxonomy if available, else KNN
                # For this implementation, we'll try to join with controls and knowledge
                
                # Check for relationships tables
                has_taxonomy = False
                has_knn = False
                try:
                    conn.execute("SELECT 1 FROM relationships_taxonomy LIMIT 1")
                    has_taxonomy = True
                except Exception as e:
                    _log_warn(f"relationships_taxonomy not available: {e}")

                if not has_taxonomy:
                    try:
                        conn.execute("SELECT 1 FROM relationships_knn LIMIT 1")
                        has_knn = True
                    except Exception as e:
                        _log_warn(f"relationships_knn not available: {e}")

                if has_taxonomy or has_knn:
                    table = "relationships_taxonomy" if has_taxonomy else "relationships_knn"
                    
                    query = f"""
                        SELECT 
                            r.source_id, r.target_id, 
                            c_source.name as source_name, c_source.description as source_desc, c_source.control_type as source_type,
                            c_target.name as target_name, c_target.description as target_desc, c_target.control_type as target_type
                        FROM {table} r
                        JOIN controls c_source ON r.source_id = c_source.control_id
                        JOIN controls c_target ON r.target_id = c_target.control_id
                        WHERE c_source.description IS NOT NULL AND c_target.description IS NOT NULL
                        LIMIT {limit}
                    """
                    
                    results = conn.execute(query).fetchall()
                    
                    for row in results:
                        source_id, target_id, s_name, s_desc, s_type, t_name, t_desc, t_type = row

                        # Fetch knowledge for source (technique)
                        knowledge = self._fetch_knowledge(conn, source_id)

                        # Context keywords - expanded for both entities
                        keywords = (
                            self._expand_context_keywords(source_id, s_name) +
                            self._expand_context_keywords(target_id, t_name)
                        )
                        # Dedupe while preserving order
                        seen = set()
                        keywords = [k for k in keywords if not (k in seen or seen.add(k))]

                        cases.append(SpartaTestCase(
                            id=f"rel_{source_id}_{target_id}",
                            source_control={
                                "control_id": source_id,
                                "name": s_name,
                                "description": s_desc,
                                "type": s_type
                            },
                            target_control={
                                "control_id": target_id,
                                "name": t_name,
                                "description": t_desc,
                                "type": t_type
                            },
                            knowledge_excerpts=knowledge,
                            context_keywords=keywords,
                            relationship={"source": table}
                        ))
                else:
                    # No relationships tables - fall back to phase 1 (control-based)
                    # This allows test-sparta to work on DBs without relationship extraction
                    return self.fetch_test_cases(limit=limit, phase=1)

            elif phase == 1:
                # Control-based (with knowledge)
                query = f"""
                    SELECT c.control_id, c.name, c.description, c.control_type
                    FROM controls c
                    JOIN control_urls cu ON c.control_id = cu.control_id
                    JOIN url_knowledge uk ON cu.url_id = uk.url_id
                    WHERE c.description IS NOT NULL
                    GROUP BY c.control_id, c.name, c.description, c.control_type
                    LIMIT {limit}
                """
                results = conn.execute(query).fetchall()
                
                for row in results:
                    cid, name, desc, ctype = row
                    knowledge = self._fetch_knowledge(conn, cid)

                    keywords = self._expand_context_keywords(cid, name)

                    cases.append(SpartaTestCase(
                        id=f"control_{cid}",
                        source_control={
                            "control_id": cid,
                            "name": name,
                            "description": desc,
                            "type": ctype
                        },
                        target_control=None,
                        knowledge_excerpts=knowledge,
                        context_keywords=keywords
                    ))

            elif phase == 2:
                # Description-only (Phase 2 extraction)
                # These don't require knowledge/urls
                query = f"""
                    SELECT c.control_id, c.name, c.description, c.control_type
                    FROM controls c
                    WHERE c.description IS NOT NULL
                    LIMIT {limit}
                """
                results = conn.execute(query).fetchall()

                for row in results:
                    cid, name, desc, ctype = row
                    keywords = self._expand_context_keywords(cid, name)

                    cases.append(SpartaTestCase(
                        id=f"desc_{cid}",
                        source_control={
                            "control_id": cid,
                            "name": name,
                            "description": desc,
                            "type": ctype
                        },
                        target_control=None,
                        knowledge_excerpts=[],  # No knowledge for phase 2
                        context_keywords=keywords
                    ))
                    
        finally:
            conn.close()
            
        return cases

    def _fetch_knowledge(self, conn, control_id: str, limit: int = 5) -> List[str]:
        query = """
            SELECT uk.text
            FROM control_urls cu
            JOIN url_knowledge uk ON cu.url_id = uk.url_id
            WHERE cu.control_id = ? AND uk.text IS NOT NULL
            LIMIT ?
        """
        return [row[0] for row in conn.execute(query, [control_id, limit]).fetchall()]

    def _expand_context_keywords(self, control_id: str, name: str) -> List[str]:
        """
        Expand context keywords to include variations that might appear in questions.

        Handles:
        - T1110.002 -> ["T1110.002", "T1110"] (base technique ID)
        - CP-2(7) -> ["CP-2(7)", "CP-2"] (without enhancement number)
        - d3f:OperatingSystemPackagingTool -> ["d3f:OperatingSystemPackagingTool", "OperatingSystemPackagingTool"]
        - AC-4(17) -> ["AC-4(17)", "AC-4"] (NIST control without enhancement)
        - Name variations for long names
        """
        import re
        keywords = []

        # Add full ID and name
        if control_id:
            keywords.append(control_id)
        if name:
            keywords.append(name)

        if control_id:
            # 1. Strip namespace prefix (d3f:Foo -> Foo)
            if ":" in control_id:
                stripped = control_id.split(":", 1)[1]
                if stripped and stripped not in keywords:
                    keywords.append(stripped)

            # 2. Base technique ID (T1110.002 -> T1110, T1558.003 -> T1558)
            match = re.match(r"^(T\d+)\.\d+$", control_id)
            if match:
                base_id = match.group(1)
                if base_id not in keywords:
                    keywords.append(base_id)

            # 3. NIST control without enhancement (AC-4(17) -> AC-4, CP-2(7) -> CP-2)
            match = re.match(r"^([A-Z]{2,3}-\d+)\(\d+\)$", control_id)
            if match:
                base_control = match.group(1)
                if base_control not in keywords:
                    keywords.append(base_control)

            # 4. D3FEND technique IDs (D3-HBPI, D3-NVA etc.)
            if control_id.startswith("D3-"):
                # Also match without dash: "D3HBPI" or just the suffix "HBPI"
                suffix = control_id[3:]  # "HBPI"
                if suffix and suffix not in keywords:
                    keywords.append(suffix)

            # 5. CWE patterns (CWE-74 -> also match "CWE 74" without dash)
            match = re.match(r"^CWE-(\d+)$", control_id)
            if match:
                cwe_num = match.group(1)
                cwe_space = f"CWE {cwe_num}"
                if cwe_space not in keywords:
                    keywords.append(cwe_space)

            # 6. ESA technique IDs (ESA-T2001.004 -> ESA-T2001)
            match = re.match(r"^(ESA-T\d+)\.\d+$", control_id)
            if match:
                base_id = match.group(1)
                if base_id not in keywords:
                    keywords.append(base_id)

        if name:
            # 7. Strip namespace prefix from names too
            if ":" in name:
                stripped = name.split(":", 1)[1]
                if stripped and stripped not in keywords:
                    keywords.append(stripped)

            # 8. Significant words from long names (for fuzzy matching)
            # "Credential Access Through Kerberoasting" -> "Kerberoasting"
            if len(name) >= 25:
                words = name.split()
                if len(words) >= 3:
                    # Last significant word (often the key technique name)
                    last_word = words[-1]
                    if len(last_word) > 5 and last_word not in keywords:
                        keywords.append(last_word)

        # Filter out empty strings and None
        return [k for k in keywords if k]

