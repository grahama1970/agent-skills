"""
Hybrid correlation logic for linking black-box and white-box findings.

Matches DAST evidence (Nuclei/Nmap) with SAST findings (Semgrep/Bandit)
to boost confidence and provide better remediation context.
"""
from __future__ import annotations
import json
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional

@dataclass
class CorrelatedFinding:
    id: str
    title: str
    severity: str
    confidence: str # Low, Medium, High, Verified
    description: str
    evidence_black: List[Dict[str, Any]] # Nuclei/Nmap hits
    evidence_white: List[Dict[str, Any]] # Semgrep/Bandit hits
    remediation: str

# Mapping Nuclei template tags/IDs to Semgrep rule categories
DAST_SAST_MAP = {
    "sql-injection": ["python.lang.security.audit.formatted-sql-query", "sql-injection"],
    "xss": ["python.lang.security.audit.xss", "cross-site-scripting"],
    "lfi": ["python.lang.security.audit.path-traversal", "path-traversal"],
    "rce": ["python.lang.security.audit.dangerous-subshell-use", "remote-code-execution"],
    "exposed-secret": ["hardcoded-secret", "generic-secret"],
    "weak-crypto": ["weak-crypto", "md5", "sha1"],
}

def correlate_findings(
    black_hits: List[Dict[str, Any]], 
    white_hits: List[Dict[str, Any]],
    target_map: Optional[Dict[str, str]] = None
) -> List[CorrelatedFinding]:
    """
    Correlate findings from black-box and white-box scans.
    
    Args:
        black_hits: Nuclei/Nmap findings
        white_hits: Semgrep/Bandit findings
        target_map: Optional mapping of external URLs to internal file paths
    """
    correlated = []
    
    # Track which hits have been correlated
    processed_white = set()
    processed_black = set()
    
    # 1. Attempt to match by type/ID
    for i, b_hit in enumerate(black_hits):
        b_type = b_hit.get("template_id", "").lower()
        b_tags = b_hit.get("info", {}).get("tags", [])
        
        for j, w_hit in enumerate(white_hits):
            if j in processed_white: continue
            
            w_id = w_hit.get("rule_id", "").lower()
            
            # Check for matches in our mapping
            match_found = False
            for key, patterns in DAST_SAST_MAP.items():
                # If both hits match a common category
                if (key in b_type or any(t in key for t in b_tags)) and \
                   (any(p in w_id for p in patterns) or key in w_id):
                    match_found = True
                    break
            
            if match_found:
                # Potential match found - create correlated finding
                processed_white.add(j)
                processed_black.add(i)
                
                correlated.append(CorrelatedFinding(
                    id=f"HYBRID-{len(correlated)+1:03d}",
                    title=f"Hybrid Verified: {key.upper()}",
                    severity=max_severity(b_hit.get("info", {}).get("severity", "medium"), 
                                        w_hit.get("severity", "medium")),
                    confidence="Verified" if match_found else "Medium",
                    description=f"Both Black-box (DAST) and White-box (SAST) detected {key}. "
                                f"DAST identified it at {b_hit.get('matched_at', 'unknown')}. "
                                f"SAST pinpointed it in {w_hit.get('file')}:{w_hit.get('line')}.",
                    evidence_black=[b_hit],
                    evidence_white=[w_hit],
                    remediation=w_hit.get("message", "Review the identified code and apply fixes.")
                ))
    
    # 2. Add remaining uncorrelated white-box findings
    for j, w_hit in enumerate(white_hits):
        if j not in processed_white:
            correlated.append(CorrelatedFinding(
                id=f"SAST-{len(correlated)+1:03d}",
                title=w_hit.get("rule_id", "Static Analysis Finding"),
                severity=w_hit.get("severity", "medium"),
                confidence="Medium",
                description=w_hit.get("message", ""),
                evidence_black=[],
                evidence_white=[w_hit],
                remediation="Apply suggested code fix."
            ))

    return correlated

def max_severity(sev1: str, sev2: str) -> str:
    """Return the higher of two severities."""
    order = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4, 
             "INFORMATION": 0, "WARNING": 2, "ERROR": 3}
    s1 = order.get(sev1.upper(), 0)
    s2 = order.get(sev2.upper(), 0)
    
    inverse = {v: k for k, v in order.items() if len(k) > 2} # Avoid abbreviations
    return inverse.get(max(s1, s2), "MEDIUM").upper()

__all__ = ["CorrelatedFinding", "correlate_findings"]
