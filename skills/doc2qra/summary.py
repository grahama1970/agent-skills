"""Summary generation for doc2qra skill.

Provides LLM-based document summarization with heuristic fallback
when no LLM provider is available.
"""

from __future__ import annotations

from .utils import log


# =============================================================================
# Prompts
# =============================================================================

SUMMARY_SYSTEM_PROMPT = """You are a document summarization assistant. Create a clear, comprehensive summary.

CRITICAL RULES:
- Write 2-3 paragraphs (150-300 words total)
- First paragraph: Document overview and main topic
- Second paragraph: Key findings, methods, or main points
- Third paragraph (optional): Conclusions or implications
- Use clear, professional language
- Do NOT include references to "this document" or "this paper" - be direct
- Extract the most important information that someone would want to know
"""

SUMMARY_PROMPT = """Summarize this document in 2-3 paragraphs:

{text}

Summary:"""


# =============================================================================
# LLM Summary
# =============================================================================


async def generate_summary_async(
    content: str,
    context: str = None,
    timeout: int = 60,
) -> str:
    """Generate a 2-3 paragraph summary of the document using LLM.

    Args:
        content: Full document content (will be truncated if too long)
        context: Optional domain context for focused summarization
        timeout: Request timeout in seconds

    Returns:
        Summary string (2-3 paragraphs)
    """
    from .config import get_llm_provider_chain

    providers = get_llm_provider_chain()
    if not providers:
        log("No LLM providers configured, using heuristic summary", style="yellow")
        return heuristic_summary(content)

    try:
        from scillm import acompletion
    except ImportError:
        log("scillm not available, using heuristic summary", style="yellow")
        return heuristic_summary(content)

    system_prompt = SUMMARY_SYSTEM_PROMPT
    if context:
        system_prompt = f"You are a {context}.\n\n{system_prompt}"

    max_chars = 12000
    truncated_content = content[:max_chars]
    if len(content) > max_chars:
        truncated_content += "\n\n[Content truncated...]"

    user_prompt = SUMMARY_PROMPT.format(text=truncated_content)

    for provider in providers:
        provider_name = provider.get("name", provider["model"][:20])
        try:
            resp = await acompletion(
                model=provider["model"],
                api_base=provider["api_base"],
                api_key=provider["api_key"],
                custom_llm_provider="openai_like",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=500,
                temperature=0.3,
                timeout=timeout,
            )
            summary = resp.choices[0].message.content
            return (summary or "").strip()
        except Exception as e:
            error_str = str(e)
            is_429 = "429" in error_str or "rate" in error_str.lower()
            if is_429:
                log(f"Summary [{provider_name}] rate-limited, trying next provider", style="yellow")
                continue
            log(f"Summary [{provider_name}] failed: {e}", style="red")
            continue

    log("All providers failed for summary, using heuristic", style="red")
    return heuristic_summary(content)


def generate_summary(content: str, context: str = None, timeout: int = 60) -> str:
    """Synchronous wrapper for summary generation.

    Args:
        content: Full document content
        context: Optional domain context
        timeout: Request timeout

    Returns:
        Summary string (2-3 paragraphs)
    """
    import asyncio
    try:
        return asyncio.run(generate_summary_async(content, context, timeout))
    except Exception as e:
        log(f"Summary generation error: {e}", style="red")
        return heuristic_summary(content)


# =============================================================================
# Heuristic Fallback
# =============================================================================


def heuristic_summary(content: str, max_length: int = 500) -> str:
    """Generate a simple heuristic summary when LLM is unavailable.

    Extracts the first few sentences as a basic summary.

    Args:
        content: Document content
        max_length: Maximum summary length

    Returns:
        Basic summary string
    """
    from .text_handler import split_sentences

    sentences = split_sentences(content)
    if not sentences:
        return "No content available for summary."

    summary_parts = []
    current_length = 0

    for sent in sentences[:10]:  # Check first 10 sentences
        sent = sent.strip()
        if not sent:
            continue
        if current_length + len(sent) > max_length:
            break
        summary_parts.append(sent)
        current_length += len(sent) + 1  # +1 for space

    if not summary_parts:
        return sentences[0][:max_length] if sentences else "No content available."

    return " ".join(summary_parts)


# Backwards-compatible alias
_heuristic_summary = heuristic_summary
