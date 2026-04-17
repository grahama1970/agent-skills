# Brave Search API - Complete Documentation Reference

> Fetched from https://api-dashboard.search.brave.com/documentation on 2026-02-12

---

## Table of Contents

1. [Quickstart](#quickstart)
2. [Authentication](#authentication)
3. [Versioning](#versioning)
4. [Rate Limiting](#rate-limiting)
5. [Pricing](#pricing)
6. [Web Search API](#web-search-api)
7. [News Search API](#news-search-api)
8. [Video Search API](#video-search-api)
9. [Image Search API](#image-search-api)
10. [Summarizer API](#summarizer-api)
11. [LLM Context API](#llm-context-api)
12. [Answers API](#answers-api)
13. [Autosuggest API](#autosuggest-api)
14. [Spellcheck API](#spellcheck-api)
15. [Search Operators](#search-operators)
16. [Goggles (Custom Re-Ranking)](#goggles-custom-re-ranking)
17. [Skills (Agent Integration)](#skills-agent-integration)
18. [Web Search API Reference (Full Schema)](#web-search-api-reference-full-schema)

---

## Quickstart

### Prerequisites
- Valid email address for registration
- Credit card for plan subscription
- Basic HTTP request familiarity

### Step 1: Create Your Account
Visit the Brave Search API Dashboard registration page:
1. Enter email and create a secure password
2. Verify email via confirmation link
3. Log in to proceed

### Step 2: Subscribe to a Plan
After account creation, access the Available Plans section in your dashboard, review options, and enter credit card information.

### Step 3: Create an API Key
1. Go to the API Keys section
2. Click "Add API Key"
3. Give your key a descriptive name
4. Copy and securely store it

**Security note:** Your API key is confidential. Never share it publicly, commit it to version control, or expose it in client-side code.

### Step 4: Make Your First Search Request

**cURL:**
```bash
curl "https://api.search.brave.com/res/v1/web/search?q=artificial+intelligence" \
  -H "X-Subscription-Token: YOUR_API_KEY"
```

**Python:**
```python
import requests

url = "https://api.search.brave.com/res/v1/web/search"
headers = {
    "Accept": "application/json",
    "Accept-Encoding": "gzip",
    "X-Subscription-Token": "YOUR_API_KEY"
}
params = {
    "q": "artificial intelligence"
}
response = requests.get(url, headers=headers, params=params)
results = response.json()

if results.get("web", {}).get("results"):
    first_result = results["web"]["results"][0]
    print(f"Title: {first_result['title']}")
    print(f"URL: {first_result['url']}")
    print(f"Description: {first_result['description']}")
```

**Node.js:**
```javascript
const url = new URL("https://api.search.brave.com/res/v1/web/search");
url.searchParams.append("q", "artificial intelligence");

const response = await fetch(url, {
  headers: {
    Accept: "application/json",
    "Accept-Encoding": "gzip",
    "X-Subscription-Token": "YOUR_API_KEY",
  },
});
const results = await response.json();

if (results.web?.results?.length > 0) {
  const firstResult = results.web.results[0];
  console.log(`Title: ${firstResult.title}`);
  console.log(`URL: ${firstResult.url}`);
  console.log(`Description: ${firstResult.description}`);
}
```

### Understanding the Response
```json
{
  "type": "search",
  "query": {
    "original": "artificial intelligence"
  },
  "web": {
    "results": [
      {
        "title": "Artificial Intelligence - Overview",
        "url": "https://example.com/ai",
        "description": "Learn about artificial intelligence...",
        "age": "2024-10-08T10:30:00.000Z"
      }
    ]
  }
}
```

---

## Authentication

Every API request must include your subscription token in the request header to authenticate and authorize access.

### Obtaining API Keys
1. Subscribe to a plan via the Brave Search API subscription page
2. Navigate to the API Keys section in your dashboard to create a new key
3. Copy your subscription token for use in requests

### Authentication Header
All requests require the subscription token as an HTTP header:

```
X-Subscription-Token: YOUR_API_KEY
```

### Security Best Practices
- Never hardcode API keys in source code
- Use environment variables instead
- Implement regular key rotation through the dashboard
- Immediately revoke compromised keys and generate replacements
- Reference OWASP Secrets Management guidelines for additional guidance

---

## Versioning

Brave Search employs two distinct versioning mechanisms.

### 1. Major Version in URL Path
The API includes a major version number (`v1`) in the request URL:
```
/v1/web/search
```
This version is rarely changed and occurs only during significant API redesigns.

### 2. Version Header for Backwards-Incompatible Changes
A dated header format (`YYYY-MM-DD`) named `Api-Version` controls specific versions:
```
-H "Api-Version: 2023-01-01"
```
The system defaults to the latest version when no header is provided.

### Compatible Changes (no user action required)
- Adding optional request parameters or headers
- Adding new response properties
- Adding new API resources
- Reordering response properties
- Modifying string value length and format

### Incompatible Changes (require developer updates)
- Removing existing request parameters or headers
- Removing response properties
- Renaming response properties
- Altering property value types

---

## Rate Limiting

The Brave Search API enforces rate limiting using a **1-second sliding window** to count requests per subscription. When exceeded, the system returns a **429** status code and fails the request.

### Rate Limit Response Headers

| Header | Description | Example |
|--------|-------------|---------|
| `X-RateLimit-Limit` | Maximum requests allowed per time window | `1, 15000` (1/sec and 15,000/month) |
| `X-RateLimit-Policy` | Complete policy specifications with window sizes in seconds | `1;w=1, 15000;w=2592000` |
| `X-RateLimit-Remaining` | Available requests within each time window | `1, 1000` |
| `X-RateLimit-Reset` | Seconds until quota windows reset | `1, 1419704` |

### Best Practices
- Implement retry logic with exponential backoff when receiving 429 responses
- Monitor remaining quota before subsequent requests
- Distribute requests evenly throughout time windows
- Track multiple limit windows simultaneously

### Notes
- The request count is increased when the request is received
- Only successful requests count against quotas
- Plans typically include both burst (per-second) and quota (per-month) limits

---

## Pricing

### Search Plan
- **Price:** $5.00 per 1,000 requests
- **Rate limit:** 50 requests per second, unlimited requests overall
- **Features:** Web search (human-readable URLs & text snippets), LLM context (results optimized for models & agents), news, videos, images
- **Free trial:** $5 monthly credits

### Answers Plan
- **Price:** $4.00 per 1,000 queries + $5.00 per 1,000,000 input tokens + $5.00 per 1,000,000 output tokens
- **Rate limit:** 2 requests per second, unlimited requests overall
- **Features:** LLM-generated answers grounded on single or multiple searches
- **Free trial:** $5 monthly credits

### Spellcheck Plan
- **Price:** $5.00 per 10,000 requests
- **Rate limit:** 100 requests per second, unlimited requests
- **Features:** Spellcheck, autosuggest, enriched autosuggest
- **Free trial:** $5 monthly credits

### Autosuggest Plan
- **Price:** $5.00 per 10,000 requests
- **Rate limit:** 100 requests per second, unlimited requests
- **Features:** Spellcheck, autosuggest, enriched autosuggest
- **Free trial:** $5 monthly credits

### Custom Plans
Contact: searchapi-support@brave.com

---

## Web Search API

**Endpoint:** `GET https://api.search.brave.com/res/v1/web/search`

Provides access to a comprehensive index of web pages, enabling retrieval of relevant results from across the internet.

### Key Features
- Search across billions of indexed web pages
- Regularly updated index for current information
- Local business data enrichments (Search plan required)
- Third-party data integrations for real-time results

### Freshness Filtering
Date-based filtering options:
- `pd` - Last 24 hours
- `pw` - Last 7 days
- `pm` - Last 31 days
- `py` - Last year
- Custom date ranges: `YYYY-MM-DDtoYYYY-MM-DD`

### Geographic & Language Targeting
- Country-specific results using 2-character codes
- Search language filtering
- UI language preferences

### Extra Snippets
Up to 5 additional excerpts per result via `extra_snippets=true` parameter.

### Pagination
- `count`: max 20 (default 20)
- `offset`: 0-based (max 9)
- `more_results_available` field for determining additional pages

### Safe Search
Control via `safesearch` parameter: `off`, `moderate`, `strict`

---

## News Search API

**Endpoint:** `GET https://api.search.brave.com/res/v1/news/search`

Send queries and receive relevant news from a specialized index of articles sourced from trusted outlets worldwide.

### Parameters

| Parameter | Description | Values |
|-----------|-------------|--------|
| `q` | Search query | string (required) |
| `freshness` | Date filter | `pd`, `pw`, `pm`, `py`, or `YYYY-MM-DDtoYYYY-MM-DD` |
| `country` | Country code | 2-character code |
| `search_lang` | Content language | language code |
| `extra_snippets` | Additional excerpts | `true`/`false` (AI and Data plans) |
| `count` | Results per page | max 50, default 20 |
| `offset` | Page number | 0-based, max 9 |
| `safesearch` | Content filtering | `off`/`moderate`/`strict` (default: strict) |

### Changelog
- 2025-01-15: Added Goggles support for custom re-ranking

---

## Video Search API

**Endpoint:** `GET https://api.search.brave.com/res/v1/videos/search`

Send queries and receive relevant video results from a dedicated index spanning various platforms and sources across the web.

### Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `q` | Search query | required |
| `country` | 2-character country code | - |
| `search_lang` | Content language filter | - |
| `count` | Results per page | max 50, default 20 |
| `offset` | Page number (0-based) | max 9 |
| `freshness` | Date-based filtering | `pd`/`pw`/`pm`/`py`/custom range |
| `safesearch` | Content filtering level | `off`/`moderate` (default)/`strict` |
| `spellcheck` | Enable/disable | default enabled |

### Search Operators Supported
- Exact phrases: `"python programming"`
- Exclusions: `cooking -vegan`
- Site-specific: `site:youtube.com fitness workout`

### Changelog
- 2023-06-20: Initial API resource release
- 2024-02-15: Added freshness filtering with custom date ranges
- 2024-11-05: Enhanced search operators support

---

## Image Search API

**Endpoint:** `GET https://api.search.brave.com/res/v1/images/search`

Access a vast index of images from across the internet with continuous crawling and indexing capabilities.

### Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `q` | Search query | required |
| `country` | Target specific countries or `ALL` for worldwide | - |
| `search_lang` | Preferred content language | - |
| `count` | Number of results | default 50, max 200 |
| `safesearch` | Content filtering | `strict` (default) or `off` |
| `spellcheck` | Automatic correction | boolean |

### Example Request
```bash
curl "https://api.search.brave.com/res/v1/images/search?q=modern+architecture&country=US&search_lang=en&count=150&safesearch=strict" \
  -H "X-Subscription-Token: <YOUR_API_KEY>"
```

### Response Elements
Results include image URLs, thumbnails, source page URLs, dimensions, titles, descriptions, and publisher information. Thumbnails are resized to have a width of 500 pixels while maintaining the original aspect ratio.

### Best Practices
- Use descriptive, specific query terms
- Maintain strict safe search for public applications
- Implement caching to minimize API calls
- Be aware of copyright and licensing when using discovered images

---

## Summarizer API

The Summarizer Search API leverages advanced AI to provide intelligent summaries and answers based on real-time web search results. Requires a Search plan subscription.

### Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /res/v1/web/search` | Initial web search (with `summary=1`) |
| `GET /res/v1/summarizer/search` | Fetch summary by key |
| `GET /res/v1/summarizer/summary` | Direct summary |
| `GET /res/v1/summarizer/summary_streaming` | Streaming summary |
| `GET /res/v1/summarizer/title` | Summary title |
| `GET /res/v1/summarizer/enrichments` | Summary enrichments |
| `GET /res/v1/summarizer/followups` | Follow-up queries |
| `GET /res/v1/summarizer/entity_info` | Entity information |

### Workflow: Traditional Flow (Web Search + Summarizer)

**Step 1:** Make web search request with `summary=1` parameter:
```bash
curl "https://api.search.brave.com/res/v1/web/search?q=what+is+the+second+highest+mountain&summary=1" \
  -H "X-Subscription-Token: <YOUR_API_KEY>"
```

**Step 2:** Extract `summarizer.key` from the response.

**Step 3:** Fetch summary using the key:
```bash
curl "https://api.search.brave.com/res/v1/summarizer/search?key=<URL_ENCODED_KEY>&entity_info=1" \
  -H "X-Subscription-Token: <YOUR_API_KEY>"
```

### Important Notes
- Summarizer requests are **not billed** -- only the initial web search request counts toward your plan limits.
- Only web search requests count toward rate limits. Summarizer endpoint calls are free.

### Advanced Features

**Inline References:** Include `inline_references=true` to add reference markers throughout the summary text.

**Entity Information:** Add `entity_info=1` to retrieve descriptions, images, and metadata about key entities.

### Response Structure
- `status`: `complete` or `failed`
- `title`: Summary title
- `summary`: Main content with text and entities
- `enrichments`: Raw text, images, Q&A pairs, entity details, source references
- `followups`: Suggested follow-up queries
- `entities_info`: Detailed entity information (when requested)

### Caching
Summary results are cached for a limited time. After cache expiration, restart the flow with a new web search.

### Changelog
- 2025-06-13: Added inline references via query parameter
- 2024-04-23: Launched "AI Answers" resource replacing previous API
- 2023-08-25: Initial API release (now deprecated)

---

## LLM Context API

Provides pre-extracted, relevance-scored web content optimized for grounding LLM responses in real-time search results. Delivers actual page content rather than just links and snippets.

### Endpoints
```
GET  https://api.search.brave.com/res/v1/llm/context
POST https://api.search.brave.com/res/v1/llm/context
```

### Query Parameters

| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `q` | string | required | 1-400 chars, max 50 words |
| `country` | string | `us` | 2-char code |
| `search_lang` | string | `en` | 2+ char code |
| `count` | int | 20 | 1-50 |

### Context Size Parameters

| Parameter | Default | Range |
|-----------|---------|-------|
| `maximum_number_of_urls` | 20 | 1-50 |
| `maximum_number_of_tokens` | 8192 | 1024-32768 |
| `maximum_number_of_snippets` | 50 | 1-100 |
| `maximum_number_of_tokens_per_url` | 4096 | 512-8192 |
| `maximum_number_of_snippets_per_url` | 50 | 1-100 |

### Filtering Parameters

| Parameter | Values |
|-----------|--------|
| `context_threshold_mode` | `strict`, `balanced`, `lenient`, `disabled` |
| `enable_local` | `true`, `false`, `null` (auto-detect) |
| `goggles` | URL or inline definition |

### Response Structure
```json
{
  "grounding": {
    "generic": [
      {
        "url": "string",
        "title": "string",
        "snippets": ["string"]
      }
    ],
    "poi": {},
    "map": []
  },
  "sources": {
    "url": {
      "title": "string",
      "hostname": "string",
      "age": ["array"] or null
    }
  }
}
```

### Use Cases
AI agents, RAG pipelines, chatbots, question answering, fact-checking, and content research.

---

## Answers API

Provides AI-generated answers backed by verifiable sources from the web. Powers Brave's "Ask Brave" feature and achieves state-of-the-art (SOTA) performance on the SimpleQA benchmark.

### Endpoint
```
POST https://api.search.brave.com/res/v1/chat/completions
```

### Authentication
API key passed as `x-subscription-token` header or via OpenAI SDK configuration.

### Request Parameters

**Basic:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `messages` | array | Array of message objects with `role` and `content` |
| `model` | string | Must be `"brave"` |
| `stream` | boolean | Enable streaming responses |

**Advanced (via `extra_body`):**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `country` | `"us"` | Target country for results |
| `language` | `"en"` | Response language |
| `enable_entities` | false | Include entity data (requires streaming) |
| `enable_citations` | false | Include inline citations (requires streaming) |
| `enable_research` | false | Enable multi-search mode (requires streaming) |

### Response Format
Responses contain special message tags:
- `<citation>`: JSON with URL, snippet, start/end indices
- `<enum_item>`: Entity data with UUID and metadata
- `<usage>`: Cost and token metrics

### Pricing
```
Cost = (searches x $4/1000) + (input_tokens x $5/1000000) + (output_tokens x $5/1000000)
```

### Rate Limits
2 requests per second (default)

### Performance Characteristics
- **Single Search (default):** ~4.5 seconds average
- **Multiple Searches (research mode):** Can extend to minutes; p99 queries analyzed 1000 pages over ~300 seconds

---

## Autosuggest API

Offers intelligent query autocompletion and search suggestions as users type.

### Endpoint
```
GET https://api.search.brave.com/res/v1/suggest/search
```

### Parameters

| Parameter | Description |
|-----------|-------------|
| `q` | Query string |
| `country` | Country code (e.g., `US`) |
| `count` | Number of suggestions (e.g., `5`) |
| `rich` | Boolean for enhanced metadata |

### Basic Response Example
```json
{
  "type": "suggest",
  "query": {"original": "hello"},
  "results": [
    {"query": "hello world"},
    {"query": "hello kitty"},
    {"query": "hello neighbor"},
    {"query": "hello fresh"},
    {"query": "hello sunshine"}
  ]
}
```

### Rich Suggestions Response Example
With `rich=true`:
```json
{
  "results": [
    {
      "query": "albert einstein",
      "is_entity": true,
      "title": "Albert Einstein",
      "description": "Theoretical physicist who developed the theory of relativity",
      "img": "https://example.com/einstein.jpg"
    }
  ]
}
```

### Best Practices
- Implement 150-300ms debouncing to reduce API calls
- Cache repeated queries client-side
- Respect subscription plan limitations

---

## Spellcheck API

Provides advanced spell checking capabilities for search queries by detecting errors and suggesting corrections.

### Endpoint
```
GET https://api.search.brave.com/res/v1/spellcheck/search
```

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `q` | Yes | Search query to check |
| `country` | Yes | Country code (e.g., `"US"`) |

### Example Request
```bash
curl "https://api.search.brave.com/res/v1/spellcheck/search?q=helo&country=US" \
  -H "X-Subscription-Token: <YOUR_API_KEY>"
```

### Response Schema
```json
{
  "type": "spellcheck",
  "query": {
    "original": "[original_query]"
  },
  "results": [
    {
      "query": "[corrected_query]"
    }
  ]
}
```

### Response Behaviors
- **Spelling error detected:** Returns corrected suggestion in results array
- **No errors found:** Returns empty results array
- **Multi-word queries:** Handles multiple corrections per request

### Best Practices
- Debounce requests (200-300ms delay recommended)
- Cache frequently checked queries
- Process spellcheck asynchronously
- Display suggestions non-intrusively
- Preserve user intent by allowing original searches

---

## Search Operators

Search operators are special commands that can be added to search queries to filter and refine results.

### File Extension and Type

| Operator | Purpose | Example |
|----------|---------|---------|
| `ext:` | Returns pages with specific file extension | `Honda GX120 owners manual ext:pdf` |
| `filetype:` | Returns pages created in specified file type | `evaluation of age cognitive changes filetype:pdf` |

### Content Location

| Operator | Purpose | Example |
|----------|---------|---------|
| `intitle:` | Returns pages with term in title | `seo conference intitle:2023` |
| `inbody:` | Returns pages with term in body | `nvidia 1080 ti inbody:"founders edition"` |
| `inpage:` | Returns pages with term in title or body | `oscars 2024 inpage:"best costume design"` |

### Language and Location

| Operator | Purpose | Example |
|----------|---------|---------|
| `lang:` / `language:` | Filter by language (ISO 639-1) | `visas lang:es` |
| `loc:` / `location:` | Filter by country (ISO 3166-1 alpha-2) | `niagara falls loc:ca` |

Common language codes: en, es, fr, de, ja, zh
Common location codes: us, gb, ca, au, de, fr

### Domain Filtering

| Operator | Purpose | Example |
|----------|---------|---------|
| `site:` | Limit to specific website/domain | `goggles site:brave.com` |

Supports subdomains and partial domains.

### Inclusion and Exclusion

| Operator | Purpose | Example |
|----------|---------|---------|
| `+` | Force inclusion of a term | `gpu +freesync` |
| `-` | Exclude pages containing term | `office -microsoft` |

### Exact Matching

| Operator | Purpose | Example |
|----------|---------|---------|
| `""` | Exact match | `harry potter "order of the phoenix"` |

### Logical Operators

| Operator | Purpose | Example |
|----------|---------|---------|
| `AND` | All conditions must match | `visa loc:gb AND lang:en` |
| `OR` | Any condition can match | `travel requirements inpage:australia OR inpage:"new zealand"` |
| `NOT` | Exclude condition | `brave search NOT site:brave.com` |

**Note:** Logical operators must be written in uppercase (`AND`, `OR`, `NOT`).

### Using with the API
```bash
curl "https://api.search.brave.com/res/v1/web/search?q=machine+learning+filetype:pdf+lang:en" \
  -H "X-Subscription-Token: YOUR_API_KEY"
```

### Limitations
Search operators are experimental and in the early stages of development. Behavior and availability may change. Not all queries may return results with very restrictive operator combinations.

---

## Goggles (Custom Re-Ranking)

Goggles enable customization of search result rankings through a domain-specific language. They work with Web Search and News Search APIs, allowing users to boost, downrank, or completely filter results based on URL patterns, domains, and other criteria.

### Basic Actions

| Action | Purpose | Example |
|--------|---------|---------|
| `$boost` | Increase ranking | `$boost,site=example.com` |
| `$boost=N` | Boost with strength 1-10 | `$boost=5,site=example.com` |
| `$downrank` | Decrease ranking | `$downrank,site=example.com` |
| `$downrank=N` | Downrank with strength 1-10 | `$downrank=3,site=example.com` |
| `$discard` | Remove completely | `$discard,site=spam.com` |

### URL Targeting
- `site=` -- Match specific domains
- Path patterns -- Target URL paths
- Wildcards (`*`) -- Match any characters (max 2 per instruction)
- Carets (`^`) -- Additional matching (max 2 per instruction)

### Required Metadata
Every Goggles file must include:
```
! name: [Title]
! description: [Brief explanation]
! public: [true/false]
! author: [Name]
```

### Optional Metadata
- `homepage` -- Project website
- `issues` -- Issue tracking URL
- `avatar` -- Color code
- `license` -- License type

### Limitations
- Maximum file size: 2MB
- Maximum 100,000 instructions per file
- Maximum 500 characters per instruction
- Maximum 2 wildcards per instruction
- Maximum 2 carets per instruction

### Conflict Resolution Priority
1. `$discard` (highest priority)
2. `$boost` over `$downrank`
3. Higher strength values over lower ones

### Submission Methods
1. **Hosted URL** -- Link to GitHub, GitLab, or Gist files
2. **Inline Specification** -- Rules directly in request (limited by URL length)
3. **Mixed** -- Combine multiple hosted URLs with inline rules

Files must be submitted to Brave Search at `search.brave.com/goggles/create` before API use.

### Code Examples

**cURL with Hosted Goggles:**
```bash
curl "https://api.search.brave.com/res/v1/web/search?q=programming+tutorials&goggles=[URL]" \
  -H "X-Subscription-Token: YOUR_API_KEY"
```

**Inline Rules:**
```
goggles=$boost=3,site=dev.to
```

**Multiple Goggles:** Pass multiple `goggles` parameters in the same request.

---

## Skills (Agent Integration)

Brave Search API offers Skills -- modular, reusable workflows extending AI capabilities. These follow an open-sourced standard and work with Claude Code, Cursor, GitHub Copilot, and other agents supporting the Agent Skills standard.

### Setup by Agent

**Claude Code:** Add API key to `~/.claude/settings.json` under an `env` object, or use `.claude/settings.local.json` for project-specific configuration.

**Cursor:** Use direnv (directory-scoped) or shell profile exports. Restart Cursor after configuration. Skills can also be added via Settings > Rules > Add Rule > Remote Rule using GitHub URLs.

**Codex:** Configure via `~/.codex/config.toml` or shell environment variables.

**OpenClaw:** Set key in `~/.openclaw/.env` or within `openclaw.json` under skill configuration.

### Available Skills
1. **llm-context** -- Pre-extracted web content for LLM grounding
2. **answers** -- AI-grounded answers with OpenAI SDK compatibility
3. **web-search** -- Ranked results with snippets
4. **images-search** -- Image search supporting 200+ results
5. **news-search** -- News articles with freshness filtering
6. **videos-search** -- Video content with metadata
7. **suggest** -- Query autocomplete
8. **spellcheck** -- Query correction

---

## Web Search API Reference (Full Schema)

### Base URL
```
GET https://api.search.brave.com/res/v1/web/search
```

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `q` | string | Yes | N/A | User's search query. Max 400 characters and 50 words. Cannot be empty. |
| `country` | SearchCountry | No | `US` | Two-character country code for search results origin |
| `search_lang` | Language-Input | No | `en` | Language code (2+ characters) for result language |
| `ui_lang` | MarketCodes | No | `en-US` | User interface language, format: `<language_code>-<country_code>` |
| `count` | integer | No | `20` | Results per page (1-20); applies only to web results |
| `offset` | integer | No | `0` | Zero-based page offset (0-9) for pagination |
| `safesearch` | SafeSearch | No | `moderate` | Values: `off`, `moderate`, `strict` |
| `spellcheck` | boolean | No | `true` | Enable spell checking on query |
| `freshness` | string | No | `""` | Filter by recency: `pd`, `pw`, `pm`, `py`, or `YYYY-MM-DDtoYYYY-MM-DD` |
| `text_decorations` | boolean | No | `true` | Include highlighting markers in display strings |
| `result_filter` | array/string | No | `null` | Comma-delimited result types: `discussions`, `faq`, `infobox`, `news`, `query`, `summarizer`, `videos`, `web`, `locations` |
| `units` | MeasurementUnit | No | `null` | Values: `metric`, `imperial` |
| `goggles_id` | string | No | `null` | Custom re-ranking ID (deprecated; use `goggles`) |
| `goggles` | string/array | No | `null` | Goggles act as a custom re-ranking on top of Brave's search index |
| `extra_snippets` | boolean | No | `null` | Get up to 5 additional, alternative excerpts |
| `summary` | boolean | No | `null` | Enable summary key generation for web results |
| `enable_rich_callback` | boolean | No | `false` | Enable real-time rich results via callback URL. Requires Pro subscription |
| `include_fetch_metadata` | boolean | No | `false` | Include fetch metadata |
| `operators` | boolean | No | `true` | Apply search operators |

### Header Parameters

| Header | Type | Required | Description |
|--------|------|----------|-------------|
| `x-subscription-token` | string | Yes | API key for authentication |
| `x-loc-lat` | number | No | Latitude (-90 to +90) for local results |
| `x-loc-long` | number | No | Longitude (-180 to +180) for local results |
| `x-loc-timezone` | string | No | IANA timezone identifier |
| `x-loc-city` | string | No | Client city name |
| `x-loc-state` | string | No | State/region code (ISO 3166-2) |
| `x-loc-state-name` | string | No | State/region name |
| `x-loc-country` | Country | No | Two-letter country code |
| `x-loc-postal-code` | string | No | Client postal code |
| `api-version` | string | No | API version (YYYY-MM-DD format); defaults to latest |
| `accept` | Accept | No | Media type: `application/json` or `*/*` |
| `cache-control` | CacheControl | No | Set to `no-cache` to prevent caching |
| `user-agent` | string | No | Browser user agent string |

### HTTP Response Codes

| Code | Condition |
|------|-----------|
| 200 | Successful response with search results |
| 404 | Subscription not found (`SUBSCRIPTION_NOT_FOUND`) |
| 422 | Invalid subscription token (`SUBSCRIPTION_TOKEN_INVALID`) |
| 429 | Rate or quota limit exceeded (`RATE_LIMITED` or `QUOTA_LIMITED`) |

### Response Type: `WebSearchApiResponse`

#### Top-Level Fields

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `type` | string | No | Response type identifier |
| `query` | Query | No | Processed query information |
| `mixed` | MixedResponse | Yes | Result ranking order |
| `web` | WebResults | Yes | Web search results |
| `news` | News | Yes | News results |
| `videos` | Videos | Yes | Video results |
| `infobox` | GraphInfobox | Yes | Knowledge graph infoboxes |
| `faq` | FAQ | Yes | Frequently asked questions |
| `discussions` | Discussions | Yes | Forum/discussion posts |
| `summarizer` | Summarizer | Yes | AI summary data |
| `locations` | Locations | Yes | Location-based results |
| `response_callback` | ResponseCallback | Yes | Rich callback info |

#### Query Object

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `original` | string | No | Original user query |
| `altered` | string | Yes | Modified query after spell-check |
| `spellcheck_off` | boolean | No | Spell-check disabled flag |

#### WebResults Object

| Field | Type | Description |
|-------|------|-------------|
| `type` | `"search"` (const) | Always `"search"` |
| `results` | Result[] | Web search results array |
| `mutated_by_goggles` | boolean | Modified by Goggles flag |

#### Result Object

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `title` | string | No | Web page title |
| `url` | string | No | Page URL |
| `is_source_local` | boolean | No | Local source flag |
| `is_source_both` | boolean | No | Both local/global flag |
| `description` | string | No | Page description |
| `page_age` | string | Yes | Page age date |
| `page_fetched` | string | Yes | Last fetch date |
| `fetched_content_timestamp` | integer | Yes | Fetch timestamp |
| `profile` | Profile | Yes | Associated profile |
| `language` | string | No | Page language |
| `family_friendly` | boolean | No | Family-safe flag |
| `meta_url` | object | Yes | Aggregated URL info |
| `thumbnail` | Thumbnail | Yes | Page thumbnail |
| `age` | string | Yes | Result age string |
| `deep_results` | DeepResult | Yes | Nested results |
| `schemas` | array | Yes | Schema.org structures |
| `location` | LocationResult | Yes | Restaurant/business data |
| `restaurant` | LocationResult | Yes | Deprecated: use `location` |
| `video` | VideoData | Yes | Associated video |
| `movie` | MovieData | Yes | Movie information |
| `faq` | FAQ | Yes | Page FAQs |
| `qa` | QAPage | Yes | Q&A information |
| `book` | Book | Yes | Book details |
| `rating` | Rating | Yes | Page ratings |
| `article` | Article | Yes | Article metadata |
| `product` | Product or Review | Yes | Product data |
| `product_cluster` | array | Yes | Multiple products |
| `cluster_type` | string | Yes | Cluster identifier |
| `cluster` | Result[] | Yes | Clustered results |
| `creative_work` | CreativeWork | Yes | Creative work data |
| `music_recording` | MusicRecording | Yes | Music data |
| `review` | Review | Yes | Review information |
| `recipe` | Recipe | Yes | Recipe details |
| `software` | Software | Yes | Software product data |
| `organization` | Organization | Yes | Org information |
| `content_type` | string | Yes | Page content type |
| `extra_snippets` | string[] | Yes | Alternative excerpts |
| `icons` | PostprocessedIcon[] | Yes | Associated icons |

#### LocationResult Object

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `title` | string | No | Location name |
| `url` | string | No | Location URL |
| `is_source_local` | boolean | No | Local source flag |
| `is_source_both` | boolean | No | Both flag |
| `description` | string | No | Description |
| `page_age` | string | Yes | Page age |
| `page_fetched` | string | Yes | Last fetch date |
| `fetched_content_timestamp` | integer | Yes | Fetch timestamp |
| `profile` | Profile | Yes | Profile |
| `language` | string | Yes | Language |
| `family_friendly` | boolean | No | Family-safe flag |
| `type` | `"location_result"` | No | Const type |
| `provider_url` | string | No | Complete provider URL |
| `coordinates` | [number, number] | Yes | Lat/long pair |
| `zoom_level` | integer | No | Map zoom level (default: 7) |
| `thumbnail` | Thumbnail | Yes | Thumbnail |
| `postal_address` | PostalAddress | Yes | Address |
| `opening_hours` | OpeningHours | Yes | Business hours |
| `contact` | Contact | Yes | Contact info |
| `price_range` | string | Yes | Price classification |
| `rating` | Rating | Yes | Rating |
| `distance` | Unit | Yes | Distance |
| `profiles` | DataProvider[] | Yes | Profiles |
| `reviews` | Reviews | Yes | Reviews |
| `pictures` | PictureResults | Yes | Pictures |
| `action` | Action | Yes | Action |
| `serves_cuisine` | string[] | Yes | Cuisine types |
| `categories` | string[] | No | Location categories |
| `icon_category` | string | Yes | Icon category |
| `timezone` | string | Yes | IANA timezone |
| `timezone_offset` | integer | Yes | UTC offset |
| `id` | string | Yes | Temporary id valid for 8 hours |
| `results` | LocationWebResult[] | Yes | Related web results |

#### PostalAddress Object

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `type` | `"PostalAddress"` | No | Const type |
| `country` | string | Yes | Country |
| `postalCode` | string | Yes | Postal code |
| `streetAddress` | string | Yes | Street address |
| `addressRegion` | string | Yes | Region |
| `addressLocality` | string | Yes | Locality |
| `displayAddress` | string | No | Formatted address |

#### OpeningHours Object

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `current_day` | DayOpeningHours[] | Yes | Today's hours |
| `days` | DayOpeningHours[][] | Yes | Weekly schedule |

#### DayOpeningHours Object

| Field | Type | Description |
|-------|------|-------------|
| `abbr_name` | string | Day abbreviation |
| `full_name` | string | Full day name |
| `opens` | string | 24-hour opening time |
| `closes` | string | 24-hour closing time |

#### Contact Object

| Field | Type | Optional |
|-------|------|----------|
| `email` | string | Yes |
| `telephone` | string | Yes |

#### MovieData Object

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Movie name |
| `description` | string | Yes | Plot summary |
| `url` | string | Yes | URL |
| `thumbnail` | Thumbnail | Yes | Thumbnail |
| `release` | string | Yes | Release date |
| `directors` | Person[] | Yes | Directors |
| `actors` | Person[] | Yes | Actors |
| `rating` | Rating | Yes | Rating |
| `duration` | string | Yes | Format: HH:MM:SS |
| `genre` | string[] | Yes | Genres |
| `query` | string | Yes | Query |

#### Book Object

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `title` | string | No | Book title |
| `author` | Person[] | No | Authors |
| `date` | string | Yes | Publishing date |
| `price` | Price | Yes | Price |
| `pages` | integer | Yes | Page count |
| `publisher` | Person | Yes | Publisher |
| `rating` | Rating | Yes | Rating |

#### Recipe Object

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `title` | string | No | Recipe title |
| `description` | string | No | Description |
| `thumbnail` | Thumbnail | No | Thumbnail |
| `url` | string | No | URL |
| `domain` | string | No | Domain |
| `favicon` | string | No | Favicon |
| `time` | string | Yes | Total cooking time |
| `prep_time` | string | Yes | Preparation time |
| `cook_time` | string | Yes | Cooking time |
| `ingredients` | string | Yes | Ingredients |
| `instructions` | HowTo[] | Yes | Steps |
| `servings` | integer | Yes | Servings |
| `calories` | integer | Yes | Calories |
| `publisher` | string | Yes | Publisher |
| `rating` | Rating | Yes | Rating |
| `recipeCategory` | string | Yes | Category |
| `recipeCuisine` | string | Yes | Cuisine |
| `video` | VideoData | Yes | Video |

#### Article Object

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `author` | Person[] | Yes | Author(s) |
| `date` | string | Yes | Publication date |
| `publisher` | Organization | Yes | Publisher |
| `thumbnail` | Thumbnail | Yes | Thumbnail |
| `isAccessibleForFree` | boolean | Yes | Free access flag |

#### Product Object

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `type` | `"Product"` | No | Const type |
| `name` | string | No | Product name |
| `url` | string | Yes | URL |
| `category` | string | Yes | Category |
| `price` | string | No | Price value |
| `thumbnail` | Thumbnail | No | Thumbnail |
| `description` | string | Yes | Description |
| `offers` | Offer[] | No | Available offers |
| `rating` | Rating | Yes | Rating |
| `gtin` | string | Yes | GTIN |
| `gtin8` | string | Yes | GTIN-8 |
| `gtin12` | string | Yes | GTIN-12 |
| `gtin13` | string | Yes | GTIN-13 |
| `gtin14` | string | Yes | GTIN-14 |

#### Review Object

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `type` | `"Review"` | No | Const type |
| `name` | string | No | Review title |
| `thumbnail` | Thumbnail | No | Thumbnail |
| `description` | string | No | Description |

#### Rating Object

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `rating` | number | No | Rating value |
| `ratingCount` | integer | Yes | Number of ratings |
| `reviewCount` | integer | Yes | Number of reviews |
| `confidence` | number | Yes | Confidence score |
| `sources` | DataProvider[] | Yes | Rating sources |

#### Thumbnail Object

| Field | Type | Description |
|-------|------|-------------|
| `src` | string | Image URL |

#### Profile Object

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `name` | string | No | Profile name |
| `url` | string | No | Profile URL |
| `long_name` | string | Yes | Long name |
| `img` | string | Yes | Image URL |

#### DeepResult Object

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `news` | NewsResult[] | Yes | News results |
| `buttons` | ButtonResult[] | Yes | Button results |
| `videos` | VideoResult[] | Yes | Video results |
| `images` | Image[] | Yes | Image results |

#### NewsResult Object

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `title` | string | No | Title |
| `url` | string | No | URL |
| `is_source_local` | boolean | No | Local flag |
| `is_source_both` | boolean | No | Both flag |
| `description` | string | No | Description |
| `page_age` | string | Yes | Page age |
| `page_fetched` | string | Yes | Fetch date |
| `fetched_content_timestamp` | integer | Yes | Fetch timestamp |
| `profile` | Profile | Yes | Profile |
| `language` | string | Yes | Language |
| `family_friendly` | boolean | No | Family-safe flag |
| `meta_url` | object | Yes | Meta URL |
| `source` | string | Yes | Source |
| `breaking` | boolean | No | Breaking news flag |
| `is_live` | boolean | No | Live flag |
| `thumbnail` | Thumbnail | Yes | Thumbnail |
| `age` | string | Yes | Age string |
| `extra_snippets` | string[] | Yes | Extra snippets |
| `icons` | PostprocessedIcon[] | Yes | Icons |

#### DiscussionResult Object

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `title` | string | No | Title |
| `url` | string | No | URL |
| `is_source_local` | boolean | No | Local flag |
| `is_source_both` | boolean | No | Both flag |
| `description` | string | No | Description |
| `page_age` | string | Yes | Page age |
| `page_fetched` | string | Yes | Fetch date |
| `fetched_content_timestamp` | integer | Yes | Fetch timestamp |
| `profile` | Profile | Yes | Profile |
| `language` | string | No | Language |
| `family_friendly` | boolean | No | Family-safe flag |
| `type` | `"discussion"` | No | Const type |
| `subtype` | string | No | Subtype |
| `is_live` | boolean | No | Live flag |
| `data` | ForumData | Yes | Forum data |

#### ForumData Object

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `forum_name` | string | No | Forum name |
| `num_answers` | integer | Yes | Number of answers |
| `score` | string | Yes | Score |
| `title` | string | Yes | Title |
| `question` | string | Yes | Question |
| `top_comment` | string | Yes | Top comment |

#### GraphInfobox Object

| Field | Type | Description |
|-------|------|-------------|
| `type` | `"graph"` (const) | Always `"graph"` |
| `results` | (GenericInfobox or QAInfobox or InfoboxPlace or InfoboxWithLocation or EntityInfobox)[] | Infobox results |

#### EntityInfobox Object

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `title` | string | No | Title |
| `url` | string | No | URL |
| `is_source_local` | boolean | No | Local flag |
| `is_source_both` | boolean | No | Both flag |
| `description` | string | No | Description |
| `page_age` | string | Yes | Page age |
| `page_fetched` | string | Yes | Fetch date |
| `fetched_content_timestamp` | integer | Yes | Fetch timestamp |
| `profile` | Profile | Yes | Profile |
| `language` | string | Yes | Language |
| `family_friendly` | boolean | No | Family-safe flag |
| `type` | `"infobox"` | No | Const type |
| `position` | integer | No | Position |
| `label` | string | Yes | Label |
| `category` | string | Yes | Category |
| `long_desc` | string | Yes | Long description |
| `thumbnail` | Thumbnail | Yes | Thumbnail |
| `attributes` | [string, string][] | No | Key-value pairs |
| `profiles` | Profile[] or DataProvider[] | Yes | Profiles |
| `website_url` | string | Yes | Website URL |
| `ratings` | Rating[] | Yes | Ratings |
| `providers` | DataProvider[] | Yes | Providers |
| `distance` | Unit | Yes | Distance |
| `images` | Thumbnail[] | Yes | Images |
| `movie` | MovieData | Yes | Movie data |
| `subtype` | `"entity"` | No | Const subtype |

#### GenericInfobox Object
All EntityInfobox fields plus:
- `subtype`: `"generic"` (const)
- `found_in_urls`: string[] (optional)

#### QAInfobox Object
Base infobox fields plus:
- `subtype`: `"code"` (const)
- `data`: QAPage
- `meta_url`: MetaUrl (optional)

#### InfoboxPlace Object
Base infobox fields plus:
- `subtype`: `"place"` (const)
- `found_in_urls`: string[] (optional)
- `is_location`: boolean
- `coordinates`: [number, number] (optional)
- `zoom_level`: integer (optional)
- `location`: LocationResult

#### InfoboxWithLocation Object
Base infobox fields plus:
- `subtype`: `"location"` (const)
- `found_in_urls`: string[] (optional)
- `is_location`: boolean
- `coordinates`: [number, number] (optional)
- `zoom_level`: integer (optional)
- `location`: LocationResult (optional)

#### QAPage Object

| Field | Type | Description |
|-------|------|-------------|
| `question` | string | The question |
| `answer` | Answer | The answer |

#### Answer Object

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `text` | string | No | Answer text |
| `author` | string | Yes | Author |
| `upvoteCount` | integer | Yes | Upvotes |
| `downvoteCount` | integer | Yes | Downvotes |

#### FAQ Object

| Field | Type | Description |
|-------|------|-------------|
| `type` | `"faq"` (const) | Always `"faq"` |
| `results` | QA[] | FAQ entries |

#### QA Object

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `question` | string | No | Question |
| `answer` | string | No | Answer |
| `title` | string | No | Title |
| `url` | string | No | URL |
| `meta_url` | MetaUrl | Yes | Meta URL |

#### Discussions Object

| Field | Type | Description |
|-------|------|-------------|
| `type` | `"search"` (const) | Always `"search"` |
| `results` | DiscussionResult[] | Discussion results |
| `mutated_by_goggles` | boolean | Goggles flag |

#### Locations Object

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `type` | `"locations"` (const) | No | Always `"locations"` |
| `results` | LocationResult[] | No | Location results |
| `provider` | object | Yes | Provider info |

#### MixedResponse Object

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `type` | `"mixed"` (const) | No | Always `"mixed"` |
| `main` | ResultReference[] | Yes | Main ranking |
| `top` | ResultReference[] | Yes | Top section |
| `side` | ResultReference[] | Yes | Side section |

#### ResultReference Object

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `type` | string | No | Result type |
| `index` | integer | Yes | Display position |
| `all` | boolean | No | Include all results of type |

#### Person Object

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `type` | `"person"` (const) | No | Always `"person"` |
| `name` | string | No | Name |
| `url` | string | Yes | URL |
| `thumbnail` | Thumbnail | Yes | Thumbnail |
| `email` | string | Yes | Email |

#### Organization Object

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `type` | `"organization"` (const) | No | Always `"organization"` |
| `name` | string | No | Name |
| `url` | string | Yes | URL |
| `thumbnail` | Thumbnail | Yes | Thumbnail |
| `contact_points` | ContactPoint[] | Yes | Contact points |

#### ContactPoint Object

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `type` | `"contact_point"` (const) | No | Always `"contact_point"` |
| `name` | string | No | Name |
| `url` | string | Yes | URL |
| `thumbnail` | Thumbnail | Yes | Thumbnail |
| `telephone` | string | Yes | Phone |
| `email` | string | Yes | Email |

#### CreativeWork Object

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `name` | string | No | Work name |
| `rating` | Rating | Yes | Rating |
| `thumbnail` | Thumbnail | No | Thumbnail |

#### MusicRecording Object

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `name` | string | No | Song/album name |
| `rating` | Rating | Yes | Rating |
| `thumbnail` | Thumbnail | Yes | Thumbnail |

#### Action Object

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Action type |
| `url` | string | Action URL |

#### ButtonResult Object

| Field | Type | Description |
|-------|------|-------------|
| `type` | `"button_result"` (const) | Always `"button_result"` |
| `title` | string | Title |
| `url` | string | URL |

#### Image Object

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `thumbnail` | Thumbnail | No | Thumbnail |
| `url` | string | Yes | URL |
| `properties` | ImageProperties | Yes | Properties |

#### ImageProperties Object

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `url` | string | No | Original image URL |
| `resized` | string | No | Quality resized URL |
| `placeholder` | string | No | Placeholder URL |
| `height` | integer | Yes | Height |
| `width` | integer | Yes | Width |
| `format` | string | Yes | Format |
| `content_size` | string | Yes | Content size |

#### PostprocessedIcon Object

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `href` | string | No | Icon URL |
| `sizes` | string | Yes | Sizes |
| `rel` | string | Yes | Rel |
| `type` | string | Yes | Type |
| `ext` | string | Yes | Extension |

#### Unit Object

| Field | Type | Description |
|-------|------|-------------|
| `value` | number | Value |
| `unit` | string | Unit |

#### HowTo Object

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `text` | string | No | Instruction text |
| `name` | string | Yes | Step name |
| `url` | string | Yes | URL |
| `image` | string[] | Yes | Images |

#### Reviews Object

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `viewMoreUrl` | string | Yes | View more URL |
| `results` | array | No | Review/rating objects |

#### PictureResults Object

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `viewMoreUrl` | string | Yes | View more URL |
| `results` | Thumbnail[] | No | Thumbnails |

#### ResponseCallback Object

| Field | Type | Description |
|-------|------|-------------|
| `vertical` | SearchAPIVertical | Vertical type |
| `callback_key` | string | Unique callback identifier |

### Enum Values

#### Language-Input
`ar`, `eu`, `bn`, `bg`, `ca`, `zh-hans`, `zh-hant`, `hr`, `cs`, `da`, `nl`, `en`, `en-gb`, `et`, `fi`, `fr`, `gl`, `de`, `el`, `gu`, `he`, `hi`, `hu`, `is`, `it`, `jp`, `kn`, `ko`, `lv`, `lt`, `ms`, `ml`, `mr`, `nb`, `pl`, `pt-br`, `pt-pt`, `pa`, `ro`, `ru`, `sr`, `sk`, `sl`, `es`, `sv`, `ta`, `te`, `th`, `tr`, `uk`, `vi`

#### MarketCodes (ui_lang)
`es-AR`, `en-AU`, `de-AT`, `nl-BE`, `fr-BE`, `pt-BR`, `en-CA`, `fr-CA`, `es-CL`, `da-DK`, `fi-FI`, `fr-FR`, `de-DE`, `el-GR`, `zh-HK`, `en-IN`, `en-ID`, `it-IT`, `ja-JP`, `ko-KR`, `en-MY`, `es-MX`, `nl-NL`, `en-NZ`, `no-NO`, `zh-CN`, `pl-PL`, `en-PH`, `ru-RU`, `en-ZA`, `es-ES`, `sv-SE`, `fr-CH`, `de-CH`, `zh-TW`, `tr-TR`, `en-GB`, `en-US`, `es-US`

#### SafeSearch
`off`, `moderate`, `strict`

#### MeasurementUnit
`imperial`, `metric`

#### Accept
`application/json`, `*/*`

#### CacheControl
`no-cache`
