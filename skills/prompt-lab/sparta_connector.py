"""
SPARTA Data Connector for Prompt Lab.
Connects to SPARTA DuckDB to fetch control data and relationships for QRA testing.
"""
import duckdb
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import json

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
                
                # Check for relationships_taxonomy table
                has_taxonomy = False
                try:
                    conn.execute("SELECT 1 FROM relationships_taxonomy LIMIT 1")
                    has_taxonomy = True
                except:
                    pass

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
                    
                    # Context keywords
                    keywords = [k for k in [s_name, t_name, source_id, target_id] if k]
                    
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

            elif phase == 1:
                # Control-based
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
                    
                    keywords = [k for k in [name, cid] if k]
                    
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

