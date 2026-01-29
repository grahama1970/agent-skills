"""
Paper Writer Skill - Citations
Citation verification and BibTeX generation.
"""
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

import typer


def verify_arxiv_id(arxiv_id: str) -> Dict[str, Any]:
    """Verify an arXiv paper ID exists via arXiv API.

    Args:
        arxiv_id: arXiv ID like "2501.15355" or "2310.09876v1"

    Returns:
        Dict with status (Supported, Unsupported), title, authors if found
    """
    # Clean ID (remove version suffix)
    clean_id = arxiv_id.split("v")[0] if "v" in arxiv_id else arxiv_id

    try:
        url = f"https://export.arxiv.org/api/query?id_list={clean_id}"
        req = urllib.request.Request(url, headers={"User-Agent": "paper-writer/1.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read().decode("utf-8")

        if "<entry>" in content and "<title>" in content:
            title_match = re.search(r"<title>([^<]+)</title>", content)
            title = title_match.group(1).strip() if title_match else "Unknown"

            author_matches = re.findall(r"<name>([^<]+)</name>", content)
            authors = author_matches[:3] if author_matches else ["Unknown"]

            return {
                "status": "Supported",
                "source": "arXiv",
                "arxiv_id": clean_id,
                "title": title,
                "authors": authors,
                "url": f"https://arxiv.org/abs/{clean_id}",
            }
        else:
            return {
                "status": "Unsupported",
                "source": "arXiv",
                "arxiv_id": clean_id,
                "error": "Paper not found in arXiv",
            }

    except urllib.error.HTTPError as e:
        return {
            "status": "Unsupported",
            "source": "arXiv",
            "arxiv_id": clean_id,
            "error": f"HTTP {e.code}",
        }
    except Exception as e:
        return {
            "status": "Uncertain",
            "source": "arXiv",
            "arxiv_id": clean_id,
            "error": str(e),
        }


def verify_doi(doi: str) -> Dict[str, Any]:
    """Verify a DOI exists via CrossRef API.

    Args:
        doi: DOI like "10.1145/1234567.1234568"

    Returns:
        Dict with status (Supported, Unsupported), title, authors if found
    """
    clean_doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
    clean_doi = clean_doi.replace("doi.org/", "")

    try:
        url = f"https://api.crossref.org/works/{urllib.parse.quote(clean_doi, safe='')}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "paper-writer/1.0 (mailto:contact@example.com)",
        })

        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read().decode("utf-8")
            data = json.loads(content)

        if data.get("status") == "ok" and "message" in data:
            msg = data["message"]
            title = msg.get("title", ["Unknown"])[0] if msg.get("title") else "Unknown"

            authors_raw = msg.get("author", [])
            authors = [
                f"{a.get('given', '')} {a.get('family', '')}".strip()
                for a in authors_raw[:3]
            ]

            return {
                "status": "Supported",
                "source": "CrossRef",
                "doi": clean_doi,
                "title": title,
                "authors": authors if authors else ["Unknown"],
                "url": f"https://doi.org/{clean_doi}",
            }
        else:
            return {
                "status": "Unsupported",
                "source": "CrossRef",
                "doi": clean_doi,
                "error": "DOI not found in CrossRef",
            }

    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {
                "status": "Unsupported",
                "source": "CrossRef",
                "doi": clean_doi,
                "error": "DOI not found",
            }
        return {
            "status": "Uncertain",
            "source": "CrossRef",
            "doi": clean_doi,
            "error": f"HTTP {e.code}",
        }
    except Exception as e:
        return {
            "status": "Uncertain",
            "source": "CrossRef",
            "doi": clean_doi,
            "error": str(e),
        }


def verify_semantic_scholar(title: str, authors: List[str] = None) -> Dict[str, Any]:
    """Verify a paper exists via Semantic Scholar API by title search.

    Args:
        title: Paper title to search
        authors: Optional author names for verification

    Returns:
        Dict with status (Supported, Partial, Unsupported), match details
    """
    try:
        encoded_title = urllib.parse.quote(title[:100])
        url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={encoded_title}&limit=3"
        req = urllib.request.Request(url, headers={"User-Agent": "paper-writer/1.0"})

        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read().decode("utf-8")
            data = json.loads(content)

        papers = data.get("data", [])
        if papers:
            paper = papers[0]
            found_title = paper.get("title", "")

            title_lower = title.lower().strip()
            found_lower = found_title.lower().strip()

            if title_lower == found_lower:
                return {
                    "status": "Supported",
                    "source": "Semantic Scholar",
                    "title": found_title,
                    "paper_id": paper.get("paperId"),
                    "url": f"https://www.semanticscholar.org/paper/{paper.get('paperId')}",
                }
            elif title_lower[:50] in found_lower or found_lower[:50] in title_lower:
                return {
                    "status": "Partial",
                    "source": "Semantic Scholar",
                    "title": found_title,
                    "searched_title": title,
                    "paper_id": paper.get("paperId"),
                    "note": "Title partially matches - verify manually",
                }
            else:
                return {
                    "status": "Unsupported",
                    "source": "Semantic Scholar",
                    "searched_title": title,
                    "error": "No matching paper found",
                }
        else:
            return {
                "status": "Unsupported",
                "source": "Semantic Scholar",
                "searched_title": title,
                "error": "No results found",
            }

    except urllib.error.HTTPError as e:
        if e.code == 429:
            return {
                "status": "Uncertain",
                "source": "Semantic Scholar",
                "searched_title": title,
                "error": "Rate limited - try again later",
            }
        return {
            "status": "Uncertain",
            "source": "Semantic Scholar",
            "searched_title": title,
            "error": f"HTTP {e.code}",
        }
    except Exception as e:
        return {
            "status": "Uncertain",
            "source": "Semantic Scholar",
            "searched_title": title,
            "error": str(e),
        }


def verify_citation_from_bib(bib_entry: str) -> Dict[str, Any]:
    """Extract identifiers from a BibTeX entry and verify existence.

    Checks in order: arXiv ID, DOI, then falls back to Semantic Scholar title search.

    Args:
        bib_entry: Raw BibTeX entry string

    Returns:
        Verification result dict
    """
    # Extract arXiv ID
    arxiv_match = re.search(r"arXiv[:\s]+(\d{4}\.\d{4,5}(?:v\d+)?)", bib_entry, re.IGNORECASE)
    if arxiv_match:
        return verify_arxiv_id(arxiv_match.group(1))

    # Extract DOI
    doi_match = re.search(r"doi\s*=\s*[{\"]?([^},\"]+)", bib_entry, re.IGNORECASE)
    if doi_match:
        return verify_doi(doi_match.group(1))

    # Extract URL with doi.org
    url_match = re.search(r"https?://doi\.org/(10\.[^}\s]+)", bib_entry)
    if url_match:
        return verify_doi(url_match.group(1))

    # Fall back to title search via Semantic Scholar
    title_match = re.search(r"title\s*=\s*[\"{](.+?)[\"}]", bib_entry, re.IGNORECASE | re.DOTALL)
    if title_match:
        title = title_match.group(1).replace("{", "").replace("}", "").replace("\n", " ")
        return verify_semantic_scholar(title.strip())

    return {
        "status": "Uncertain",
        "source": "None",
        "error": "No identifiable information in BibTeX entry",
    }


def check_citations(paper_dir: Path) -> Dict[str, Any]:
    """Check that all citations in tex files have matching BibTeX entries.

    Args:
        paper_dir: Path to paper directory with sections/ and references.bib

    Returns:
        Report with missing, unused, and valid citations
    """
    report = {
        "valid": [],
        "missing": [],
        "unused": [],
        "errors": [],
    }

    sections_dir = paper_dir / "sections"
    tex_files = list(sections_dir.glob("*.tex")) if sections_dir.exists() else []
    main_tex = paper_dir / "draft.tex"
    if main_tex.exists():
        tex_files.append(main_tex)

    if not tex_files:
        report["errors"].append("No .tex files found")
        return report

    cited = set()
    cite_pattern = re.compile(r'\\cite[tp]?\{([^}]+)\}')

    for tex_file in tex_files:
        try:
            content = tex_file.read_text()
            matches = cite_pattern.findall(content)
            for match in matches:
                for ref in match.split(","):
                    cited.add(ref.strip())
        except Exception as e:
            report["errors"].append(f"Error reading {tex_file.name}: {e}")

    bib_file = paper_dir / "references.bib"
    bib_entries = set()

    if bib_file.exists():
        try:
            bib_content = bib_file.read_text()
            entry_pattern = re.compile(r'@\w+\{([^,]+),')
            bib_entries = set(entry_pattern.findall(bib_content))
        except Exception as e:
            report["errors"].append(f"Error reading references.bib: {e}")
    else:
        report["errors"].append("references.bib not found")

    report["valid"] = list(cited & bib_entries)
    report["missing"] = list(cited - bib_entries)
    report["unused"] = list(bib_entries - cited)

    return report


def generate_bibtex_entry(paper_info: Dict[str, Any], cite_key: str = None) -> str:
    """Generate a BibTeX entry from paper information.

    Args:
        paper_info: Paper information dict
        cite_key: Optional citation key (auto-generated if not provided)

    Returns:
        BibTeX entry string
    """
    # Generate cite key if not provided
    if not cite_key:
        authors = paper_info.get("authors", ["unknown"])
        year = paper_info.get("year", paper_info.get("published", "")[:4])
        first_author = authors[0].split()[-1].lower() if authors else "unknown"
        title_word = paper_info.get("title", "paper").split()[0].lower()
        cite_key = f"{first_author}{year}{title_word}"

    # Clean cite key
    cite_key = re.sub(r'[^a-zA-Z0-9]', '', cite_key)

    title = paper_info.get("title", "Unknown Title")
    authors = paper_info.get("authors", ["Unknown"])
    year = paper_info.get("year", paper_info.get("published", "")[:4] or "2024")
    arxiv_id = paper_info.get("arxiv_id", paper_info.get("id", ""))
    doi = paper_info.get("doi", "")

    # Format authors
    author_str = " and ".join(authors)

    entry = f"""@article{{{cite_key},
    title = {{{title}}},
    author = {{{author_str}}},
    year = {{{year}}},"""

    if arxiv_id:
        entry += f"""
    eprint = {{{arxiv_id}}},
    archiveprefix = {{arXiv}},"""

    if doi:
        entry += f"""
    doi = {{{doi}}},"""

    entry += """
}"""

    return entry
