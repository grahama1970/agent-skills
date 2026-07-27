#!/usr/bin/env python3
"""Result synthesis and report generation for Dogpile.

Generates markdown reports from aggregated search results.
"""
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add parent directory to path for package imports when running as script
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR.parent))

# Import smaller formatters
from dogpile.formatters import (
    format_wayback_section,
    format_codex_section,
    format_perplexity_section,
    format_readarr_section,
)


def _error_text(result: Any) -> Optional[str]:
    """Return a readable error if a provider result is degraded."""
    if isinstance(result, dict) and result.get("error"):
        hint = result.get("hint")
        return f"{result['error']} -> {hint}" if hint else str(result["error"])
    if isinstance(result, dict) and result.get("skipped"):
        hint = result.get("hint")
        return f"Skipped: {result['skipped']} -> {hint}" if hint else f"Skipped: {result['skipped']}"
    if isinstance(result, str) and result.startswith("Error:"):
        return result.removeprefix("Error:").strip()
    return None


def _safe_section(name: str, formatter, *args, **kwargs) -> List[str]:
    """Format one report section without letting it hide other successes."""
    try:
        return formatter(*args, **kwargs)
    except Exception as e:
        return [
            f"## {name}",
            f"> Error: report formatting failed for this section: {e}",
            "",
        ]


def format_degraded_sources_section(
    stage1_results: Optional[Dict[str, Any]] = None,
    stage2_results: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Summarize failed/degraded providers while preserving successful sections."""
    lines: List[str] = []
    failures: List[tuple[str, str]] = []

    for stage, results in [("stage1", stage1_results or {}), ("stage2", stage2_results or {})]:
        if not isinstance(results, dict):
            continue
        for provider, result in results.items():
            err = _error_text(result)
            if err:
                failures.append((f"{stage}:{provider}", err))

    if failures:
        lines.append("## Degraded Sources")
        lines.append("Dogpile returned all successful source results. These sources failed or degraded:")
        for provider, err in failures:
            lines.append(f"- **{provider}**: {err}")
        lines.append("")
    return lines


def format_github_section(
    github_res: Dict[str, Any],
    github_details: List[Dict],
    github_deep: Dict,
    target_repo: Optional[str],
    deep_code_res: List,
    code_explanation: Optional[str] = None,
) -> List[str]:
    """Format GitHub search results."""
    lines = ["## GitHub"]

    if not isinstance(github_res, dict):
        lines.append(f"> Error: unexpected result type {type(github_res).__name__}")
    elif "skipped" in github_res:
        lines.append(f"> Skipped: {github_res['skipped']}")
    elif "error" in github_res:
        lines.append(f"> Error: {github_res['error']}")
    else:
        lines.append("### Repositories")
        repos = github_res.get("repos", [])

        if not repos:
            lines.append("No repositories found.")
        elif isinstance(repos, list):
            for repo in repos:
                desc = repo.get("description", "No description") or "No description"
                star = f"* {repo.get('stargazersCount', 0)}"
                is_target = repo.get("fullName") == target_repo
                prefix = "**TARGET**" if is_target else "-"
                lines.append(f"{prefix} **[{repo.get('fullName')}]({repo.get('html_url')})** ({star})")
                lines.append(f"  {desc}")

        # Stage 2: README Deep Dive for evaluated repos
        if github_details:
            lines.append("\n### Repository Deep Dive (README Analysis)")
            for detail in github_details:
                repo_name = detail.get("fullName", "Unknown")
                meta = detail.get("metadata", {})
                is_target = repo_name == target_repo
                target_marker = " **SELECTED**" if is_target else ""

                lines.append(f"\n#### [{repo_name}]({meta.get('url', '#')}){target_marker}")

                topics = meta.get("repositoryTopics") or []
                topic_names = [t.get("name", "") for t in topics if isinstance(t, dict)] if isinstance(topics, list) else []
                lang_info = meta.get("primaryLanguage")
                lang = lang_info.get("name", "Unknown") if isinstance(lang_info, dict) else (lang_info or "Unknown")
                stars = meta.get("stargazerCount", 0)
                updated = meta.get("updatedAt", "Unknown")[:10] if meta.get("updatedAt") else "Unknown"

                lines.append(f"**Language:** {lang} | **Stars:** {stars} | **Updated:** {updated}")
                if topic_names:
                    lines.append(f"**Topics:** {', '.join(topic_names)}")

                readme = detail.get("readme", "")
                if readme:
                    readme_excerpt = readme[:500] + "..." if len(readme) > 500 else readme
                    lines.append(f"\n**README excerpt:**\n```\n{readme_excerpt}\n```")

                langs = detail.get("languages", {})
                if langs:
                    total = sum(langs.values())
                    top_langs = sorted(langs.items(), key=lambda x: x[1], reverse=True)[:5]
                    lang_pcts = [f"{l[0]}: {l[1]*100/total:.1f}%" for l in top_langs]
                    lines.append(f"**Languages:** {', '.join(lang_pcts)}")

        # Stage 3: Multi-Strategy Deep Code Search Results
        if github_deep and target_repo:
            lang = github_deep.get("language", "Unknown")
            lines.append(f"\n### Multi-Strategy Deep Search in {target_repo}")
            lines.append(f"**Primary Language:** {lang}")

            file_tree = github_deep.get("file_tree", [])
            if file_tree:
                lines.append("\n**Project Structure:**")
                lines.append("```")
                for f in file_tree[:15]:
                    lines.append(f"|-- {f}")
                if len(file_tree) > 15:
                    lines.append(f"|-- ... ({len(file_tree) - 15} more)")
                lines.append("```")

            symbol_matches = github_deep.get("symbol_matches", [])
            if symbol_matches:
                lines.append("\n#### Symbol Definitions Found")
                lines.append("*Using `symbol:` qualifier for tree-sitter parsed definitions*")
                for item in symbol_matches:
                    path = item.get("path", "unknown")
                    url = item.get("url", "#")
                    symbol = item.get("symbol", "")
                    lines.append(f"- [`{symbol}`]({url}) in `{path}`")
                    text_matches = item.get("textMatches", [])
                    for tm in text_matches[:1]:
                        fragment = tm.get("fragment", "")[:200]
                        if fragment:
                            lines.append(f"  ```\n  {fragment}\n  ```")

            code_matches = github_deep.get("code_matches", [])
            if code_matches:
                lines.append("\n#### Text Matches")
                for item in code_matches:
                    path = item.get("path", "unknown")
                    url = item.get("url", "#")
                    lines.append(f"- [`{path}`]({url})")
                    text_matches = item.get("textMatches", [])
                    for tm in text_matches[:2]:
                        fragment = tm.get("fragment", "")[:150]
                        if fragment:
                            lines.append(f"  > `{fragment}...`")

            path_matches = github_deep.get("path_matches", [])
            if path_matches:
                lines.append("\n#### Path-Filtered Matches")
                lines.append("*Searched in: src/, lib/, core/, pkg/*")
                for item in path_matches:
                    path = item.get("path", "unknown")
                    url = item.get("url", "#")
                    searched_path = item.get("searched_path", "")
                    lines.append(f"- [`{path}`]({url}) (via `{searched_path}`)")

            file_contents = github_deep.get("file_contents", [])
            if file_contents:
                lines.append("\n#### Full File Content (Key Files)")
                for fc in file_contents:
                    path = fc.get("path", "unknown")
                    content = fc.get("content", "")
                    size = fc.get("size", 0)
                    truncated = fc.get("truncated", False)
                    lines.append(f"\n**`{path}`** ({size} bytes{' - truncated' if truncated else ''})")
                    preview = content[:1500] + "\n..." if len(content) > 1500 else content
                    lines.append(f"```\n{preview}\n```")

            if code_explanation:
                lines.append("\n#### Code Explanation")
                lines.append(code_explanation)

            total = len(symbol_matches) + len(code_matches) + len(path_matches)
            if total == 0:
                lines.append("\nNo specific code matches found.")
            else:
                lines.append(f"\n**Summary:** {len(symbol_matches)} definitions, {len(code_matches)} text matches, {len(path_matches)} path matches")

        elif deep_code_res:
            lines.append(f"\n### Code Matches in {target_repo}")
            for item in deep_code_res:
                lines.append(f"- [`{item.get('path')}`]({item.get('url')})")

        lines.append("\n### Issues/Discussions")
        issues = github_res.get("issues", [])
        if not issues:
            lines.append("No issues found.")
        elif isinstance(issues, list):
            for issue in issues:
                repo_name = issue.get("repository", {}).get("nameWithOwner", "unknown")
                lines.append(f"- **{repo_name}**: [{issue.get('title')}]({issue.get('html_url')}) ({issue.get('state')})")

    lines.append("")
    return lines


def format_brave_section(brave_res: Dict[str, Any], brave_deep: List[Dict]) -> List[str]:
    """Format Brave search results."""
    lines = ["## Web Results (Brave)"]

    if not isinstance(brave_res, dict):
        lines.append(f"> Error: unexpected result type {type(brave_res).__name__}")
    elif "skipped" in brave_res:
        lines.append(f"> Skipped: {brave_res['skipped']}")
    elif "error" in brave_res:
        lines.append(f"> Error: {brave_res['error']}")
    else:
        web_results = brave_res.get("web", {}).get("results", []) or brave_res.get("results", [])
        for item in web_results[:5]:
            lines.append(f"- **[{item.get('title', 'No Title')}]({item.get('url', '#')})**")
            lines.append(f"  {item.get('description', '')}")

        if brave_deep:
            lines.append("\n### Deep Extracted Content (Stage 2)")
            for deep in brave_deep:
                if deep.get("extracted"):
                    lines.append(f"**Source:** [{deep.get('title', 'Unknown')}]({deep.get('url')})")
                    content = deep.get("content", "")
                    if len(content) > 3000:
                        content = content[:3000] + "\n\n[... truncated for brevity ...]"
                    lines.append(f"```\n{content}\n```")
                    lines.append("")
                elif deep.get("error"):
                    lines.append(f"> Extraction failed for {deep.get('url')}: {deep.get('error')}")

    lines.append("")
    return lines


def format_brave_questions_section(brave_questions_res: Dict[str, Any]) -> List[str]:
    """Format concurrent Brave question results replacing Perplexity."""
    lines = ["## Concurrent Brave Questions"]

    if not isinstance(brave_questions_res, dict):
        lines.append(f"> Error: unexpected result type {type(brave_questions_res).__name__}")
        lines.append("")
        return lines

    if brave_questions_res.get("error"):
        lines.append(f"> Error: {brave_questions_res['error']}")
        lines.append("")
        return lines

    if brave_questions_res.get("replacement_for"):
        lines.append(f"_Replacement for: {brave_questions_res['replacement_for']}_")

    question_runs = brave_questions_res.get("results", [])
    if not question_runs:
        lines.append("No concurrent Brave question results found.")
        lines.append("")
        return lines

    for run in question_runs:
        query = run.get("query", "Unknown query")
        result = run.get("result", {})
        lines.append(f"### {query}")
        if isinstance(result, dict) and result.get("error"):
            lines.append(f"> Error: {result['error']}")
            continue
        web_results = result.get("web", {}).get("results", []) or result.get("results", [])
        for item in web_results[:3]:
            lines.append(f"- **[{item.get('title', 'No Title')}]({item.get('url', '#')})**")
            if item.get("description"):
                lines.append(f"  {item.get('description')}")
        lines.append("")

    return lines


def format_arxiv_section(
    arxiv_res: Dict[str, Any],
    arxiv_details: List[Dict],
    arxiv_deep: List[Dict]
) -> List[str]:
    """Format ArXiv search results."""
    lines = ["## Academic Papers (ArXiv)"]

    if isinstance(arxiv_res, dict) and ("error" in arxiv_res or "skipped" in arxiv_res):
        label = "Error" if "error" in arxiv_res else "Skipped"
        lines.append(f"> {label}: {arxiv_res.get('error') or arxiv_res.get('skipped')}")
        lines.append("")
        return lines

    if arxiv_details:
        lines.append("### Deep Dive: Paper Details")
        for paper in arxiv_details:
            lines.append(f"#### [{paper.get('title')}]({paper.get('abs_url')})")
            lines.append(f"**Authors:** {', '.join(paper.get('authors', []))}")
            abstract = paper.get("abstract", "")
            if len(abstract) > 500:
                abstract = abstract[:500] + "..."
            lines.append(f"**Summary:** {abstract}")
            lines.append("")

        if arxiv_deep:
            lines.append("### Full Paper Extraction (Stage 3)")
            for deep in arxiv_deep:
                if deep.get("extracted"):
                    lines.append(f"**Paper ID:** `{deep.get('paper_id')}`")
                    full_text = deep.get("full_text", "")
                    if len(full_text) > 2000:
                        full_text = full_text[:2000] + "\n\n[... truncated for brevity ...]"
                    lines.append(f"```\n{full_text}\n```")
                    lines.append("")
                elif deep.get("error"):
                    lines.append(f"> Extraction failed for {deep.get('paper_id')}: {deep.get('error')}")
            lines.append("")

        lines.append("### Other Relevant Papers")

    if isinstance(arxiv_res, dict) and "items" in arxiv_res:
        for p in arxiv_res["items"][len(arxiv_details):len(arxiv_details)+5]:
            lines.append(f"- **[{p.get('title')}]({p.get('abs_url')})** ({p.get('published')})")
    elif isinstance(arxiv_res, str):
        lines.append(arxiv_res)

    lines.append("")
    return lines


def format_youtube_section(youtube_res: List[Dict], youtube_transcripts: List[Dict]) -> List[str]:
    """Format YouTube search results."""
    lines = ["## Videos (YouTube)"]

    if isinstance(youtube_res, dict) and ("error" in youtube_res or "skipped" in youtube_res):
        label = "Error" if "error" in youtube_res else "Skipped"
        lines.append(f"> {label}: {youtube_res.get('error') or youtube_res.get('skipped')}")
        lines.append("")
        return lines

    if not isinstance(youtube_res, list):
        lines.append(f"> Error: unexpected result type {type(youtube_res).__name__}")
        lines.append("")
        return lines

    if youtube_transcripts:
        lines.append("### Video Insights (Transcripts)")
        for trans in youtube_transcripts:
            lines.append(f"#### [{trans.get('title')}]({trans.get('url')})")
            text = trans.get("full_text", "")
            if len(text) > 800:
                text = text[:800] + "..."
            lines.append(f"> {text}")
            lines.append("")
        lines.append("### More Videos")

    if not youtube_res:
        lines.append("No videos found or error.")
    else:
        for video in youtube_res[len(youtube_transcripts):len(youtube_transcripts)+5]:
            if "Error" in video.get("title", ""):
                lines.append(f"> {video['title']}")
            else:
                lines.append(f"- **[{video['title']}]({video['url']})**")
                if video.get("description"):
                    lines.append(f"  _{video.get('description')}_")

    lines.append("")
    return lines


def generate_report(
    query: str,
    wayback_res: Dict[str, Any],
    codex_src_res: str | Dict[str, Any],
    perp_res: Dict[str, Any],
    readarr_res: List[Dict],
    github_res: Dict[str, Any],
    github_details: List[Dict],
    github_deep: Dict,
    target_repo: Optional[str],
    deep_code_res: List,
    brave_res: Dict[str, Any],
    brave_questions_res: Dict[str, Any],
    brave_deep: List[Dict],
    arxiv_res: Dict[str, Any],
    arxiv_details: List[Dict],
    arxiv_deep: List[Dict],
    youtube_res: List[Dict],
    youtube_transcripts: List[Dict],
    synthesis: Optional[str] = None,
    code_explanation: Optional[str] = None,
    stage1_results: Optional[Dict[str, Any]] = None,
    stage2_results: Optional[Dict[str, Any]] = None,
) -> str:
    """Generate full markdown report from all search results."""
    md_lines = [f"# Dogpile Report: {query}", ""]

    md_lines.extend(format_degraded_sources_section(stage1_results, stage2_results))
    md_lines.extend(_safe_section("Wayback", format_wayback_section, wayback_res))
    md_lines.extend(_safe_section("Codex Technical Overview", format_codex_section, codex_src_res))
    md_lines.extend(_safe_section("AI Research (Perplexity)", format_perplexity_section, perp_res))
    md_lines.extend(_safe_section("Books & Usenet (Readarr)", format_readarr_section, readarr_res))
    md_lines.extend(_safe_section(
        "GitHub",
        format_github_section,
        github_res, github_details, github_deep, target_repo, deep_code_res,
        code_explanation=code_explanation,
    ))
    md_lines.extend(_safe_section("Web Results (Brave)", format_brave_section, brave_res, brave_deep))
    md_lines.extend(_safe_section("Concurrent Brave Questions", format_brave_questions_section, brave_questions_res))
    md_lines.extend(_safe_section("Academic Papers (ArXiv)", format_arxiv_section, arxiv_res, arxiv_details, arxiv_deep))
    md_lines.extend(_safe_section("Videos (YouTube)", format_youtube_section, youtube_res, youtube_transcripts))

    if synthesis and not synthesis.startswith("Error:"):
        md_lines.append("## Evidence Synthesis")
        md_lines.append(synthesis)
        md_lines.append("")

    return "\n".join(md_lines)
