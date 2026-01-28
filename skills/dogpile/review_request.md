# Code Review Request: Dogpile Deep Search Aggregator

## Overview
Dogpile is a comprehensive deep search aggregator that orchestrates searches across multiple sources:
- Brave Search (Web)
- Perplexity (AI Research)
- GitHub (Repos, Issues, Code via /github-search skill)
- ArXiv (Academic Papers)
- YouTube (Videos with Transcripts)
- Wayback Machine (Historical Snapshots)
- Codex (High-Reasoning Synthesis)

## Files to Review
- `dogpile.py` - Main implementation (~1500 lines)
- `SKILL.md` - Documentation

## Research-Backed Improvement Areas

Based on self-research using dogpile, here are the key improvements needed:

### 1. Rate Limiting & Backoff (Critical)

**Current Issues:**
- Uses ThreadPoolExecutor with no rate limiting
- No handling of Retry-After headers
- No backoff on 429/503 errors
- Risk of API bans (GitHub explicitly warns about this)

**Research-Backed Solutions:**
- Implement tenacity with `wait_random_exponential(min=1, max=120)` and jitter
- Parse `Retry-After`, `x-ratelimit-remaining`, `x-ratelimit-reset` headers
- Prepare for IETF RateLimit-* headers (draft expires Mar 2026)
- Convert 429/503 into scheduling signals, not errors
- Cap retries explicitly (count and/or total time)

**Key Insight:** Tenacity + ThreadPoolExecutor are complementary:
- ThreadPoolExecutor: Handles parallelism (fan-out)
- Tenacity: Handles retries with backoff per request
- Semaphore: Limits concurrent requests per provider

### 2. Retry Storm Prevention

**Current Risk:**
- Independent retries across multiple sources can cause 243x amplification (AWS example: 5 layers x 3 retries)

**Solutions:**
- Centralize retry policy per provider
- Use jitter to prevent synchronized retry waves
- Treat non-retryable errors as terminal

### 3. Deadline-Aware Orchestration

**Current Issues:**
- No global deadline for the search operation
- No per-source timeouts
- No partial result streaming

**Solutions:**
- Implement global deadline with per-source timeouts
- Stream partial results when available
- Cancel downstream work when deadlines expire

### 4. Idempotency

**Current Issues:**
- Some operations may not be safely retryable

**Solutions:**
- Design all aggregator steps to be safely retryable
- Mark non-retryable operations explicitly

### 5. Code Quality Issues

**Specific Problems:**
- `search()` function is too long (~400 lines)
- Duplicate code across search functions
- Inconsistent error handling
- Missing type hints in some areas
- Long query tailoring prompt that could be schema-based

### 6. Architecture Improvements

**Current:**
- Monolithic search function
- Direct API calls mixed with skill orchestration

**Suggested:**
- Policy-driven source adapters (each provider gets dedicated wrapper)
- Central budget manager for quota enforcement
- Adaptive throttling loop based on error rates and latency

## Specific Review Questions

1. How should we implement tenacity with ThreadPoolExecutor? (They're complementary)
2. Should we use asyncio instead of ThreadPoolExecutor for better cancellation?
3. How to parse and respect Retry-After headers across different providers?
4. Best pattern for partial result streaming during aggregation?
5. How to structure the central budget manager for multi-source quotas?

## Implementation Priority

1. **P0 (Critical):** Add tenacity with exponential backoff + jitter
2. **P0 (Critical):** Parse and respect rate limit headers
3. **P1 (High):** Add semaphore for per-provider concurrency limits
4. **P1 (High):** Refactor search() into smaller functions
5. **P2 (Medium):** Add global deadline with cancellation
6. **P2 (Medium):** Implement partial result streaming

## Code Context

The skill is used by AI agents for deep research tasks. It needs to be:
- **Reliable:** Handle API failures gracefully, avoid bans
- **Fast:** Parallel execution with proper throttling
- **Comprehensive:** Multiple source types with deep extraction
- **Memory-efficient:** Stream results, don't load everything

## Target Improvements

After this review, the code should:
1. Never trigger rate limit bans
2. Gracefully degrade when sources fail
3. Be more maintainable with smaller functions
4. Have proper type hints throughout
5. Include retry policies per provider
