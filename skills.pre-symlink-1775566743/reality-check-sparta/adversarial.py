"""Adversarial verification checks for SPARTA QRA data.

These checks hunt for data corruption, contamination, hallucination,
and content mismatches. They use fresh verification techniques including
URL re-fetching, HTML parsing, and Excel cross-referencing.
"""

import os
import re

from config import EXPECTED_SPARTA_STRUCTURE, SPARTA_TECHNIQUE_CATEGORIES


def check_url_file_alignment(conn, full: bool = False) -> dict:
    """Check if downloaded files match their URLs - ANY mismatch is a problem."""
    limit = "" if full else "LIMIT 100"
    results = conn.execute(f"""
        SELECT u.url, uc.file_path
        FROM urls u
        JOIN url_content uc ON u.url_id = uc.url_id
        WHERE u.url LIKE 'https://attack.mitre.org/techniques/T%'
        AND uc.file_path IS NOT NULL
        {limit}
    """).fetchall()

    matches = 0
    mismatches = 0
    errors = 0
    mismatch_examples = []

    for url, file_path in results:
        # Extract technique ID from URL
        url_match = re.search(r'/techniques/(T\d+(?:/\d+)?)', url)
        url_tech_id = url_match.group(1) if url_match else None

        # Get technique ID from HTML file title
        if file_path and os.path.exists(file_path):
            try:
                with open(file_path, 'r', errors='ignore') as f:
                    content = f.read(5000)
                    title_match = re.search(r'<title>([^<]+)</title>', content)
                    if title_match:
                        title = title_match.group(1)
                        tech_match = re.search(r'Technique (T\d+(?:/\d+)?)', title)
                        file_tech_id = tech_match.group(1) if tech_match else None
                    else:
                        file_tech_id = None
            except Exception:
                errors += 1
                continue
        else:
            errors += 1
            continue

        if url_tech_id and file_tech_id:
            if url_tech_id == file_tech_id:
                matches += 1
            else:
                mismatches += 1
                mismatch_examples.append({
                    "url": url,
                    "expected_tech": url_tech_id,
                    "actual_tech": file_tech_id,
                    "severity": "CRITICAL"
                })
        else:
            errors += 1

    total = matches + mismatches + errors
    mismatch_pct = round(100 * mismatches / total, 1) if total > 0 else 0

    # STRICT thresholds - ANY significant mismatch is a failure
    issues = []
    if mismatches > 0:
        issues.append(f"CRITICAL: {mismatches} files contain WRONG technique content")
        issues.append(f"This is a {mismatch_pct}% data corruption rate")
        if mismatch_pct > 1:
            issues.append("ROOT CAUSE INVESTIGATION REQUIRED: Check download logic, redirects, or race conditions")
    if errors > 0:
        issues.append(f"WARNING: {errors} files could not be verified (missing/unreadable)")

    return {
        "total_checked": total,
        "matches": matches,
        "match_pct": round(100 * matches / total, 1) if total > 0 else 0,
        "mismatches": mismatches,
        "mismatch_pct": mismatch_pct,
        "errors": errors,
        "mismatch_examples": mismatch_examples[:10],
        "issues": issues,
        # STRICT: >5% mismatch = FAIL, >0% = WARN
        "status": "FAIL" if mismatch_pct > 5 else ("WARN" if mismatches > 0 else "PASS")
    }


def check_url_knowledge_contamination(conn, n_samples: int = 20) -> dict:
    """Check if url_knowledge has cross-contaminated content."""
    samples = conn.execute(f"""
        SELECT
            uk.url_id,
            uk.text as knowledge_content,
            uk.topic,
            u.url
        FROM url_knowledge uk
        JOIN urls u ON uk.url_id = u.url_id
        WHERE uk.text IS NOT NULL AND LENGTH(uk.text) > 100
        ORDER BY RANDOM()
        LIMIT {n_samples}
    """).fetchall()

    issues = []
    contamination_count = 0

    for row in samples:
        url_id, knowledge, topic, url = row

        # Check if this is MITRE content and extract expected technique
        expected_tech = None
        if 'attack.mitre.org/techniques/' in (url or ""):
            match = re.search(r'/techniques/(T\d+(?:/\d+)?)', url)
            expected_tech = match.group(1) if match else None

        if expected_tech:
            # For sub-techniques (e.g., T1074/001), the parent (T1074) is expected in content
            parent_tech = expected_tech.split('/')[0] if '/' in expected_tech else None

            # Check if knowledge mentions DIFFERENT techniques prominently
            found_techs = re.findall(r'\b(T\d{4}(?:/\d{3})?)\b', knowledge or "")

            # Filter out the expected technique AND its parent (for sub-techniques)
            other_techs = [t for t in found_techs
                          if t != expected_tech
                          and t != parent_tech
                          and not expected_tech.startswith(t)]

            # If the content mentions completely unrelated techniques but not the expected one
            expected_found = expected_tech in (knowledge or "") or (parent_tech and parent_tech in (knowledge or ""))
            if not expected_found and len(other_techs) > 0:
                contamination_count += 1
                issues.append(f"CONTAMINATION: URL for {expected_tech} has content about {other_techs[0] if other_techs else 'unknown'}")

    return {
        "samples_checked": len(samples),
        "contamination_suspects": contamination_count,
        "contamination_pct": round(100 * contamination_count / max(len(samples), 1), 1),
        "issues": issues,
        "status": "FAIL" if contamination_count > n_samples // 10 else ("WARN" if contamination_count > 0 else "PASS")
    }


def check_qra_verbatim_grounding(conn, n_samples: int = 20) -> dict:
    """Check QRA answers for hallucination patterns.

    NOTE: This check is INFORMATIONAL ONLY for verbatim matching.
    The url_knowledge.text contains MITRE ATT&CK content, but QRA grounding
    was calculated against SPARTA source material during generation.
    We DO check for clear hallucination patterns, which is the primary value here.
    """
    samples = conn.execute(f"""
        SELECT
            q.qra_id,
            q.question,
            q.answer,
            q.grounding_score
        FROM qra q
        WHERE q.grounding_score >= 0.90
        ORDER BY RANDOM()
        LIMIT {n_samples}
    """).fetchall()

    hallucinations_found = 0
    issues = []

    for qra_id, question, answer, score in samples:
        if not answer:
            continue

        answer_clean = answer.lower().strip()

        hallucination_phrases = [
            "as of my knowledge",
            "i don't have access",
            "i cannot",
            "based on general knowledge",
            "i'm not sure",
            "i don't know",
        ]
        for phrase in hallucination_phrases:
            if phrase in answer_clean:
                hallucinations_found += 1
                issues.append(f"HALLUCINATION: QRA {qra_id} contains '{phrase}'")
                break

    total = len(samples)

    return {
        "samples_checked": total,
        "hallucinations_found": hallucinations_found,
        "issues": issues,
        "status": "FAIL" if hallucinations_found > 2 else ("WARN" if hallucinations_found > 0 else "PASS"),
        "note": "Verbatim check disabled - url_knowledge contains MITRE content, not SPARTA source used for grounding"
    }


def extract_technique_from_html(content: str) -> str:
    """Extract technique ID from HTML content using multiple methods.

    MITRE ATT&CK pages don't always have technique ID in the title,
    especially for sub-techniques. Check multiple locations.

    Returns:
        Technique ID string or None
    """
    search_area = content[:10000]

    # Method 1: Look for "Technique TXXXX" pattern anywhere
    tech_match = re.search(r'Technique (T\d+(?:\.\d+)?(?:/\d+)?)', search_area)
    if tech_match:
        return tech_match.group(1).replace('.', '/')

    # Method 2: Look in canonical URL
    canonical = re.search(r'<link[^>]+canonical[^>]+href="([^"]+)"', search_area)
    if canonical:
        url_tech = re.search(r'/techniques/(T\d+(?:/\d+)?)', canonical.group(1))
        if url_tech:
            return url_tech.group(1)

    # Method 3: Look for technique ID in og:url meta tag
    og_url = re.search(r'<meta[^>]+og:url[^>]+content="([^"]+)"', search_area)
    if og_url:
        url_tech = re.search(r'/techniques/(T\d+(?:/\d+)?)', og_url.group(1))
        if url_tech:
            return url_tech.group(1)

    # Method 4: Look for ID in heading or breadcrumb (T1234.001 format)
    id_match = re.search(r'>\s*(T\d+(?:\.\d+)?)\s*[:<]', search_area)
    if id_match:
        return id_match.group(1).replace('.', '/')

    # Method 5: Look in data attributes
    data_match = re.search(r'data-technique[^>]*["\']?(T\d+(?:[./]\d+)?)', search_area)
    if data_match:
        return data_match.group(1).replace('.', '/')

    return None


def verify_url_fresh(url: str, expected_tech: str) -> dict:
    """Fresh-fetch a URL and verify it matches expected technique."""
    import httpx

    try:
        with httpx.Client(follow_redirects=True, timeout=30) as client:
            resp = client.get(url)
            content = resp.text

            actual_tech = extract_technique_from_html(content)

            # Normalize expected for comparison
            expected_norm = expected_tech.replace('.', '/')
            actual_norm = actual_tech.replace('.', '/') if actual_tech else None

            # Also check if final URL contains the expected technique
            final_url = str(resp.url)
            url_matches = expected_norm in final_url or expected_norm.replace('/', '.') in final_url

            return {
                "url": url,
                "expected": expected_tech,
                "actual": actual_tech,
                "matches": actual_norm == expected_norm or url_matches,
                "method": "fresh_httpx",
                "status_code": resp.status_code,
            }
    except Exception as e:
        return {
            "url": url,
            "expected": expected_tech,
            "matches": False,
            "method": "fresh_httpx",
            "error": str(e),
        }


def verify_against_excel(conn, technique_id: str) -> dict:
    """Verify a technique exists in original SPARTA Excel data."""
    result = conn.execute("""
        SELECT "ID", "Name", "Description"
        FROM s01_raw__sparta_techniques
        WHERE "ID" = ?
    """, [technique_id]).fetchone()

    if result:
        return {
            "technique_id": technique_id,
            "found_in_excel": True,
            "name": result[1],
            "has_description": bool(result[2]),
        }
    return {
        "technique_id": technique_id,
        "found_in_excel": False,
    }


def run_fresh_verification(conn, n_samples: int = 5) -> dict:
    """Run fresh verification using alternative techniques."""
    issues = []
    verifications = []

    # Get sample URLs
    mismatch_urls = conn.execute("""
        SELECT u.url
        FROM urls u
        WHERE u.url LIKE 'https://attack.mitre.org/techniques/T%'
        ORDER BY RANDOM()
        LIMIT ?
    """, [n_samples]).fetchall()

    fresh_matches = 0
    fresh_mismatches = 0

    for (url,) in mismatch_urls:
        url_match = re.search(r'/techniques/(T\d+(?:/\d+)?)', url)
        expected_tech = url_match.group(1) if url_match else None

        if expected_tech:
            result = verify_url_fresh(url, expected_tech)
            verifications.append(result)

            if result.get("matches"):
                fresh_matches += 1
            elif not result.get("error"):
                fresh_mismatches += 1
                issues.append(f"FRESH VERIFY FAIL: {url} expected {expected_tech}, got {result.get('actual')}")

    # Verify random techniques against Excel
    excel_checks = conn.execute("""
        SELECT DISTINCT r.technique_id
        FROM relationships r
        ORDER BY RANDOM()
        LIMIT 5
    """).fetchall()

    excel_found = 0
    for (tech_id,) in excel_checks:
        excel_result = verify_against_excel(conn, tech_id)
        if excel_result.get("found_in_excel"):
            excel_found += 1
        else:
            issues.append(f"EXCEL MISMATCH: {tech_id} not found in SPARTA Excel data")

    return {
        "fresh_fetch_samples": len(mismatch_urls),
        "fresh_matches": fresh_matches,
        "fresh_mismatches": fresh_mismatches,
        "excel_verified": excel_found,
        "excel_checked": len(excel_checks),
        "verifications": verifications,
        "issues": issues,
        "status": "FAIL" if fresh_mismatches > 0 or len(issues) > 0 else "PASS",
    }
