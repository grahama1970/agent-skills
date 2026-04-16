# Perplexity API Reference

Fetched from https://docs.perplexity.ai on 2026-02-12.

Complete documentation index: https://docs.perplexity.ai/llms.txt

---

## Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [SDKs & Installation](#sdks--installation)
4. [API Endpoints](#api-endpoints)
   - [Search API](#search-api)
   - [Agent API (Responses)](#agent-api-responses)
   - [Sonar API (Chat Completions)](#sonar-api-chat-completions)
5. [Models](#models)
6. [Presets](#presets)
7. [Pro Search](#pro-search)
8. [Tools](#tools)
9. [Search Filters](#search-filters)
10. [OpenAI SDK Compatibility](#openai-sdk-compatibility)
11. [Model Fallback](#model-fallback)
12. [Streaming](#streaming)
13. [Pricing](#pricing)
14. [Rate Limits & Usage Tiers](#rate-limits--usage-tiers)
15. [Privacy & Security](#privacy--security)
16. [Best Practices](#best-practices)
17. [Error Handling](#error-handling)

---

## Overview

Perplexity's API platform enables developers to power products with real-time, web-wide research and Q&A capabilities. Three primary APIs are offered:

- **Search API**: Ranked web search results with advanced filtering and real-time data.
- **Agent API (Responses)**: Multi-provider access to OpenAI, Anthropic, Google, and xAI models with granular control, web search tools, and presets.
- **Sonar API (Chat Completions)**: Web-grounded AI responses -- send a message, get a researched answer.

API key portal: https://perplexity.ai/account/api

---

## Authentication

- **Method**: Bearer token via `Authorization` header
- **Header format**: `Authorization: Bearer $PERPLEXITY_API_KEY`
- **Environment variable**: `PERPLEXITY_API_KEY`

Set the environment variable:
```bash
# macOS/Linux
export PERPLEXITY_API_KEY="your_api_key_here"

# Windows
setx PERPLEXITY_API_KEY "your_api_key_here"
```

Additional endpoints exist for programmatic token management:
- **Generate Auth Token**: Create new authentication tokens for API access
- **Revoke Auth Token**: Invalidate existing authentication tokens

---

## SDKs & Installation

### Python
```bash
pip install perplexityai
```

### TypeScript/JavaScript
```bash
npm install @perplexity-ai/perplexity_ai
```

### OpenAI SDK (Compatible)
```bash
# Python
pip install openai

# TypeScript
npm install openai
```

### SDK Initialization

**Native Python SDK:**
```python
from perplexity import Perplexity
client = Perplexity()
```

**Native TypeScript SDK:**
```typescript
import { Perplexity } from '@perplexity-ai/perplexity_ai';
const client = new Perplexity();
```

**OpenAI Python SDK (compatible):**
```python
from openai import OpenAI
client = OpenAI(
    api_key="YOUR_PERPLEXITY_API_KEY",
    base_url="https://api.perplexity.ai"
)
```

**OpenAI TypeScript SDK (compatible):**
```typescript
import OpenAI from 'openai';
const client = new OpenAI({
    apiKey: "YOUR_PERPLEXITY_API_KEY",
    baseURL: "https://api.perplexity.ai"
});
```

---

## API Endpoints

### Search API

**Endpoint**: `POST https://api.perplexity.ai/search`

Provides ranked web search results with filtering capabilities. Supports real-time data retrieval. Charged at $5.00 per 1,000 requests with no token-based fees.

#### Request Parameters

| Parameter | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| `query` | string or array | required | 1-5 queries | Search term(s); supports multi-query as array |
| `max_results` | integer | 10 | 1-20 | Number of results returned |
| `max_tokens_per_page` | integer | 4096 | -- | Content extraction per webpage |
| `max_tokens` | integer | 10,000 | up to 1,000,000 | Total content budget across all results |
| `country` | string | -- | ISO 3166-1 alpha-2 | Geographic filtering (e.g., "US", "GB") |
| `search_domain_filter` | array | -- | max 20 domains | Allowlist (no prefix) or denylist (use "-" prefix) |
| `search_language_filter` | array | -- | max 10 codes | ISO 639-1 language codes (e.g., "en", "fr") |

#### Example Request (Python)
```python
from perplexity import Perplexity

client = Perplexity()
search = client.search.create(
    query=["What is Comet Browser?", "Perplexity AI"],
    max_results=10
)
for result in search.results:
    print(f"{result.title}: {result.url}")
```

#### Example Request (cURL)
```bash
curl --request POST \
  --url https://api.perplexity.ai/search \
  --header "Authorization: Bearer $PERPLEXITY_API_KEY" \
  --header "Content-Type: application/json" \
  --data '{
    "query": ["What is Comet Browser?", "Perplexity AI"],
    "max_results": 10
  }'
```

#### Response Structure
```json
{
  "results": [
    {
      "title": "string",
      "url": "string",
      "snippet": "string",
      "date": "YYYY-MM-DD",
      "last_updated": "YYYY-MM-DD"
    }
  ],
  "id": "UUID"
}
```

Notes:
- Single query returns flat result list; multi-query returns grouped results.
- Multi-query supports up to 5 queries per request.

---

### Agent API (Responses)

**Endpoint**: `POST https://api.perplexity.ai/v1/responses`

Unified interface for accessing models from multiple providers (OpenAI, Anthropic, Google, xAI) with integrated web search, tool configuration, reasoning control, and token budgeting.

#### Core Request Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `model` | string | Model identifier (e.g., "openai/gpt-5.2") |
| `models` | array | Fallback chain of up to 5 models (takes priority over `model`) |
| `preset` | string | Alternative to model selection (e.g., "pro-search", "fast-search", "deep-research", "advanced-deep-research") |
| `input` | string or array | Query text or message array with roles (system/user) |
| `instructions` | string | System guidance for tool usage and response style |
| `max_output_tokens` | integer | Response length limit |
| `stream` | boolean | Enable Server-Sent Events streaming |
| `reasoning.effort` | string | "low", "medium", or "high" (ignored by non-reasoning models) |

#### Tools Configuration

Two available tools:
1. **web_search**: Retrieves current information; supports optional location parameters (latitude, longitude, country, city, region)
2. **fetch_url**: Extracts content from specific URLs

#### Input Formats

**String format:**
```python
input="Query text"
```

**Message array format:**
```python
input=[
    {"type": "message", "role": "system", "content": "System instructions"},
    {"type": "message", "role": "user", "content": "User query"}
]
```

#### Example Request (Python)
```python
from perplexity import Perplexity

client = Perplexity()
response = client.responses.create(
    model="openai/gpt-5.2",
    input="What are the latest developments in quantum computing?",
    stream=False
)
print(response.output_text)
```

#### Example Request (cURL)
```bash
curl --request POST \
  --url https://api.perplexity.ai/v1/responses \
  --header "Authorization: Bearer $PERPLEXITY_API_KEY" \
  --header "Content-Type: application/json" \
  --data '{
    "model": "openai/gpt-5.2",
    "input": "What are the latest developments in quantum computing?"
  }'
```

#### Example with Preset
```python
response = client.responses.create(
    preset="pro-search",
    input="What are major AI developments today?"
)
print(response.output_text)
```

#### Response Structure
```json
{
  "id": "resp_<uuid>",
  "model": "<provider/model>",
  "status": "completed",
  "created_at": 1234567890,
  "output": [
    {
      "type": "message",
      "role": "assistant",
      "content": [...]
    }
  ],
  "usage": {
    "input_tokens": 150,
    "output_tokens": 300,
    "total_tokens": 450,
    "cost": {
      "currency": "USD",
      "input_cost": 0.00025,
      "output_cost": 0.004,
      "total_cost": 0.00425
    }
  }
}
```

#### Response Properties
- `response.output_text`: Convenience property aggregating all text content
- `response.status`: "completed" or "failed"
- `response.error.message`: Error details when status is "failed"

---

### Sonar API (Chat Completions)

**Endpoint**: `POST https://api.perplexity.ai/chat/completions`

Web-grounded responses using Perplexity's Sonar models. OpenAI-compatible format.

#### Request Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `model` | string | Model identifier (e.g., "sonar", "sonar-pro") |
| `messages` | array | Message objects with `role` and `content` fields |
| `stream` | boolean | Enable streaming responses |
| `max_tokens` | integer | Maximum response tokens |
| `temperature` | float | Sampling temperature |
| `top_p` | float | Nucleus sampling parameter |
| `response_format` | object | JSON schema for structured output |
| `web_search_options` | object | Search filtering options (see below) |

#### web_search_options Parameters
| Parameter | Type | Description |
|-----------|------|-------------|
| `search_domain_filter` | array | Restrict results to specific domains |
| `search_recency_filter` | string | "day", "week", "month", "year" |
| `search_type` | string | "fast" (default), "pro", or "auto" (Sonar Pro only) |

#### Perplexity-Specific Extra Parameters (via `extra_body` with OpenAI SDK)
| Parameter | Type | Description |
|-----------|------|-------------|
| `search_domain_filter` | array | Restrict results to specific websites |
| `search_recency_filter` | string | "day", "week", "month", "year" |
| `return_images` | boolean | Include image URLs in responses |
| `return_related_questions` | boolean | Generate follow-up questions |
| `search_mode` | string | "web" or "academic" |
| `disable_search` | boolean | Disable web search entirely |

#### Example Request (Python)
```python
from perplexity import Perplexity

client = Perplexity()
response = client.chat.completions.create(
    model="sonar-pro",
    messages=[
        {"role": "user", "content": "What is the capital of France?"}
    ]
)
print(response.choices[0].message.content)
```

#### Example Request (cURL)
```bash
curl --request POST \
  --url https://api.perplexity.ai/chat/completions \
  --header "Authorization: Bearer $PERPLEXITY_API_KEY" \
  --header "Content-Type: application/json" \
  --data '{
    "model": "sonar-pro",
    "messages": [
      {"role": "user", "content": "What is the capital of France?"}
    ]
  }'
```

#### Example with Filters
```python
completion = client.chat.completions.create(
    model="sonar",
    messages=[{"role": "user", "content": "Latest climate research"}],
    web_search_options={
        "search_domain_filter": ["nature.com"],
        "search_recency_filter": "month"
    }
)
```

#### Example with OpenAI SDK (extra_body)
```python
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_PERPLEXITY_API_KEY",
    base_url="https://api.perplexity.ai"
)

completion = client.chat.completions.create(
    model="sonar-pro",
    messages=[{"role": "user", "content": "Climate research"}],
    extra_body={
        "search_domain_filter": ["nature.com"],
        "search_recency_filter": "month"
    }
)
```

#### Response Structure
```json
{
  "id": "pplx-<identifier>",
  "model": "sonar-pro",
  "created": 1234567890,
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Response text here"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 50,
    "completion_tokens": 200,
    "total_tokens": 250
  }
}
```

#### Perplexity-Specific Response Fields
- `search_results`: Array containing source titles, URLs, and dates
- `citations`: List of referenced URLs

---

## Models

### Sonar Models (Perplexity native)

| Model | Input (per 1M tokens) | Output (per 1M tokens) | Notes |
|-------|----------------------|------------------------|-------|
| sonar | $1 | $1 | Standard web-grounded responses |
| sonar-pro | $3 | $15 | Advanced web-grounded responses |
| sonar-reasoning-pro | $2 | $8 | Reasoning-enabled |
| sonar-deep-research | $2 input, $2 citation, $3 reasoning | $8 output, $5 per 1K search queries | Deep research |

### Agent API Models (Third-Party, No Markup)

#### Perplexity
| Model | Input/1M | Output/1M | Cache Read/1M |
|-------|----------|-----------|---------------|
| perplexity/sonar | $0.25 | $2.50 | $0.0625 |

#### Anthropic
| Model | Input/1M | Output/1M | Cache Read/1M |
|-------|----------|-----------|---------------|
| claude-opus-4-6 | $5 | $25 | $0.50 |
| claude-opus-4-5 | $5 | $25 | $0.50 |
| claude-sonnet-4-5 | $3 | $15 | $0.30 |
| claude-haiku-4-5 | $1 | $5 | $0.10 |

#### OpenAI
| Model | Input/1M | Output/1M | Cache Read/1M |
|-------|----------|-----------|---------------|
| gpt-5.2 | $1.75 | $14 | $0.175 |
| gpt-5.1 | $1.25 | $10 | $0.125 |
| gpt-5-mini | $0.25 | $2 | $0.025 |

#### Google
| Model | Input/1M | Output/1M | Cache Discount |
|-------|----------|-----------|----------------|
| gemini-3-pro-preview | $2.00-$4.00 | $12.00-$18.00 | 90% |
| gemini-3-flash-preview | $0.50 | $3.00 | 90% |
| gemini-2.5-pro | $1.25-$2.50 | $10.00-$15.00 | 90% |
| gemini-2.5-flash | $0.30 | $2.50 | 90% |

#### xAI
| Model | Input/1M | Output/1M | Cache Read/1M |
|-------|----------|-----------|---------------|
| grok-4-1-fast-non-reasoning | $0.20 | $0.50 | $0.05 |

Agent API tool costs:
- Web search: $0.005 per invocation
- URL fetching: $0.0005 per invocation

---

## Presets

Four pre-configured agent setups for the Agent API (`/v1/responses`):

### fast-search
- **Model**: xai/grok-4-1-fast-non-reasoning
- **Max Tokens/Page**: 3K | **Total Max Tokens**: 3K | **Max Steps**: 1
- **Tools**: web_search
- **Prompt Tokens**: ~1,240
- **Best for**: Quick responses to simple questions requiring minimal latency

### pro-search
- **Model**: openai/gpt-5.1
- **Max Tokens/Page**: 3K | **Total Max Tokens**: 3K | **Max Steps**: 3
- **Tools**: web_search, fetch_url
- **Prompt Tokens**: ~1,502
- **Best for**: Standard queries needing research and tool integration

### deep-research
- **Model**: openai/gpt-5.2
- **Max Tokens/Page**: 4K | **Total Max Tokens**: 10K | **Max Steps**: 10
- **Tools**: web_search, fetch_url
- **Prompt Tokens**: ~3,267
- **Best for**: Comprehensive analysis with multi-step reasoning

### advanced-deep-research
- **Model**: anthropic/claude-opus-4-6
- **Max Tokens/Page**: 4K | **Total Max Tokens**: 10K | **Max Steps**: 10
- **Tools**: web_search, fetch_url
- **Prompt Tokens**: ~3,500
- **Best for**: Maximum-depth research with sophisticated source coverage

Presets allow parameter overrides. You can customize `model`, `max_steps`, `max_output_tokens`, and `tools` while retaining other defaults.

---

## Pro Search

Pro Search enhances Sonar Pro with automated tool usage, enabling multi-step reasoning through intelligent tool orchestration including web search and URL content fetching.

### Requirements
- `stream: true` (mandatory -- non-streaming requests default to standard Sonar Pro)
- `web_search_options.search_type: "pro"`

### Search Type Options

| Value | Description |
|-------|-------------|
| `"fast"` | Optimized for simple queries; default when omitted |
| `"pro"` | Forces Pro Search for complex queries requiring multi-step tool usage |
| `"auto"` | System-determined routing based on query complexity (recommended) |

### Auto Classification Triggers

**Routes to Pro Search:**
- Multi-step reasoning or analysis
- Comparative analysis across multiple sources
- Deep research workflows

**Routes to Fast Search:**
- Simple fact lookups
- Direct information retrieval
- Basic question answering

### Built-in Tools (auto-selected)
1. **web_search**: Conducts targeted searches with custom queries and filters
2. **fetch_url_content**: Retrieves and analyzes specific URL content beyond snippets

### Example (Python)
```python
from perplexity import Perplexity

client = Perplexity(api_key="YOUR_API_KEY")
response = client.chat.completions.create(
    model="sonar-pro",
    messages=[{"role": "user", "content": "Compare AI chip architectures in 2026"}],
    stream=True,
    web_search_options={"search_type": "pro"}
)

for chunk in response:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

### Example (cURL)
```bash
curl --request POST \
  --url https://api.perplexity.ai/chat/completions \
  --header "Authorization: Bearer $PERPLEXITY_API_KEY" \
  --header "Content-Type: application/json" \
  --data '{
    "model": "sonar-pro",
    "messages": [{"role": "user", "content": "Compare AI chip architectures in 2026"}],
    "stream": true,
    "web_search_options": {"search_type": "pro"}
  }' --no-buffer
```

### Pro Search Response Fields
- `id`: Unique request identifier
- `model`: "sonar-pro"
- `created`: Unix timestamp
- `usage`: Token counts and cost breakdown
- `search_results`: Web sources found
- `reasoning_steps`: Detailed thought process showing individual thoughts, tool type (web_search, fetch_url_content), actual search keywords used, retrieved content with dates and URLs
- `choices`: Streamed assistant content

---

## Tools

### Agent API Tools

#### web_search
Retrieves current information from the web. Supports optional location parameters:
- `latitude` (float)
- `longitude` (float)
- `country` (string)
- `city` (string)
- `region` (string)

Cost: $0.005 per invocation

#### fetch_url
Extracts content from specific URLs.

Cost: $0.0005 per invocation

### Sonar Pro Search Built-in Tools
- **web_search**: Conducts targeted searches with custom queries and filters
- **fetch_url_content**: Retrieves and analyzes specific URL content beyond snippets

These are auto-orchestrated by the model during Pro Search.

---

## Search Filters

### Domain Filtering
- `search_domain_filter`: Array of up to 20 domains
- Allowlist mode: `["arxiv.org", "nature.com"]`
- Denylist mode: `["-reddit.com", "-quora.com"]`

### Recency Filtering
- `search_recency_filter`: String value
- Options: `"day"`, `"week"`, `"month"`, `"year"`

### Language Filtering (Search API)
- `search_language_filter`: Array of up to 10 ISO 639-1 codes (e.g., `["en", "fr"]`)

### Country Filtering (Search API)
- `country`: ISO 3166-1 alpha-2 code (e.g., `"US"`, `"GB"`)

### Search Mode (Sonar API)
- `search_mode`: `"web"` or `"academic"`

---

## OpenAI SDK Compatibility

Both Sonar API and Agent API work with OpenAI client libraries. Configure two settings:

1. **Base URL**: `https://api.perplexity.ai`
2. **API Key**: Your Perplexity API key

### Python
```python
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_PERPLEXITY_API_KEY",
    base_url="https://api.perplexity.ai"
)

completion = client.chat.completions.create(
    model="sonar-pro",
    messages=[{"role": "user", "content": "Your question here"}]
)
print(completion.choices[0].message.content)
```

### TypeScript
```typescript
import OpenAI from 'openai';

const client = new OpenAI({
    apiKey: "YOUR_PERPLEXITY_API_KEY",
    baseURL: "https://api.perplexity.ai"
});

const completion = await client.chat.completions.create({
    model: "sonar-pro",
    messages: [{role: "user", content: "Your question here"}]
});
console.log(completion.choices[0].message.content);
```

### Perplexity-Specific Features via extra_body
```python
completion = client.chat.completions.create(
    model="sonar-pro",
    messages=[{"role": "user", "content": "Climate research"}],
    extra_body={
        "search_domain_filter": ["nature.com"],
        "search_recency_filter": "month",
        "return_images": True,
        "return_related_questions": True
    }
)
```

### Compatible OpenAI Parameters
- `model` (use Perplexity model names)
- `messages`
- `max_tokens`
- `temperature`
- `top_p`
- `response_format`
- `stream`

Note: Perplexity recommends using the native SDK for the best experience with full type safety, enhanced features, and preset support.

---

## Model Fallback

Specify up to 5 models in a `models` array for automatic failover. The API tries each model in order until one succeeds.

### Key Features
- Automatic sequential failover
- Cross-provider support (mix OpenAI, Anthropic, Google, xAI)
- `models` array takes priority over single `model` field
- Charges apply only to the model that processes the request

### Example
```python
response = client.responses.create(
    models=["openai/gpt-5.2", "openai/gpt-5.1", "openai/gpt-5-mini"],
    input="What are the latest developments in AI?"
)
# response.model shows which model actually served the request
```

### Best Practices
- Position preferred models first in the array
- Consider pricing variations when ordering fallback chains
- Leverage cross-provider combinations for maximum reliability

---

## Streaming

### Sonar API Streaming
```python
stream = client.chat.completions.create(
    model="sonar-pro",
    messages=[{"role": "user", "content": "Query"}],
    stream=True
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
```

### Agent API Streaming Events
- `response.output_text.delta`: Text chunk delivery
- `response.completed`: Final response with aggregated data

### Pro Search Streaming (Required)
Pro Search requires `stream=True` to function. Non-streaming requests default to standard Sonar Pro behavior.

---

## Pricing

### Search API
- $5.00 per 1,000 requests (no token-based fees)

### Sonar API Token Pricing (per 1M tokens)

| Model | Input | Output | Notes |
|-------|-------|--------|-------|
| Sonar | $1 | $1 | |
| Sonar Pro | $3 | $15 | |
| Sonar Reasoning Pro | $2 | $8 | |
| Sonar Deep Research | $2 | $8 | + $2 citation tokens, $3 reasoning tokens, $5 per 1K search queries |

### Sonar API Request Fees (per 1,000 requests by context size)

| Model | Low Context | Medium Context | High Context |
|-------|-------------|----------------|--------------|
| Sonar | $5 | -- | $12 |
| Sonar Pro | $6 | -- | $14 |
| Sonar Reasoning Pro | $6 | -- | $14 |

Total cost per query = token costs + request fee

### Pro Search Request Fees (per 1,000 requests, Sonar Pro only)

| Search Type | Low Context | Medium Context | High Context |
|-------------|-------------|----------------|--------------|
| Fast | $6 | $10 | $14 |
| Pro | $14 | $18 | $22 |
| Auto | Variable (Fast or Pro rates based on classification) | | |

### Agent API
- Transparent, token-based pricing at direct provider rates with no markup (see Models section for per-model pricing)
- Web search tool: $0.005 per invocation
- URL fetch tool: $0.0005 per invocation

---

## Rate Limits & Usage Tiers

Rate limits are tiered based on cumulative API spending ($0 to $5,000+). Specific RPM (requests per minute) and TPM (tokens per minute) values are documented in the administration section of the API portal.

Key tier thresholds:
- $0 (Free tier)
- $50+
- $250+
- $1,000+
- $5,000+

Rate limit management:
- Implement exponential backoff with jitter for rate limit errors
- Pattern: `2 ** attempt + random.uniform(0, 1)` for delays
- Maximum 3 retries recommended
- Catch `RateLimitError` exceptions

---

## Privacy & Security

### Zero Data Retention Policy
Perplexity operates under strict zero data retention for the Sonar API. No data sent via the Sonar API is retained, and no customer data is used to train models.

### Collected Operational Metrics (billing only)
- Token counts processed
- Model selection per request
- Timestamps and request duration
- API key identification for billing

Prompt and response content is NOT retained.

### Security Certifications
1. **SOC 2 Type II Report**: Audits covering security, availability, processing integrity, confidentiality, and privacy
2. **2025 HIPAA Gap Assessment**: Healthcare data protection compliance readiness
3. **CAIQlite**: Cloud security assessment

Trust Center: https://trust.perplexity.ai/

---

## Best Practices

### Query Optimization
- Use detailed, contextual queries rather than vague terms
- Example: Replace "AI medical" with "artificial intelligence medical diagnosis accuracy 2024"

### Multi-Query Research
- Break topics into related sub-queries using multi-query (up to 5 per request)
- Process concurrently with `asyncio.gather()` or `Promise.all()`

### Rate Limit Handling
```python
import time
import random

def search_with_retry(client, query, max_retries=3):
    for attempt in range(max_retries):
        try:
            return client.search.create(query=query, max_results=10)
        except RateLimitError:
            delay = 2 ** attempt + random.uniform(0, 1)
            time.sleep(delay)
    raise Exception("Max retries exceeded")
```

### Concurrent Processing
```python
from perplexity import AsyncPerplexity
import asyncio

async with AsyncPerplexity() as client:
    tasks = [
        client.search.create(query="query1", max_results=5),
        client.search.create(query="query2", max_results=5)
    ]
    results = await asyncio.gather(*tasks)
```

### Caching
Implement caching with configurable TTL (recommended 1800-3600 seconds) for frequently repeated queries.

### Performance
- Request only necessary results (lower `max_results` = faster response)
- Use `AsyncPerplexity()` client for concurrent request handling
- Control concurrency with `asyncio.Semaphore` (recommended 3-5 concurrent)
- Add delays between batches to respect API limits

---

## Error Handling

### Python
```python
try:
    response = client.responses.create(
        model="openai/gpt-5.2",
        input="Query"
    )
except APIError as e:
    print(f"Error: {e.message}, Status: {e.status_code}")
```

### TypeScript
```typescript
try {
    const response = await client.responses.create({
        model: "openai/gpt-5.2",
        input: "Query"
    });
} catch (e) {
    if (e instanceof Perplexity.APIError) {
        console.error(`Error: ${e.message}, Status: ${e.status}`);
    }
}
```

### Common Error Types
- `RateLimitError`: Retry with exponential backoff
- `APIStatusError`: Log and handle gracefully
- Generic exceptions: Capture and log unexpected errors

---

## Additional Resources

### Async API Endpoints
- **Create Async Chat Completion**: Submit async chat completion requests
- **Get Async Chat Completion**: Retrieve responses for async requests
- **List Async Chat Completions**: Access all async requests for a given user

### Integrations
- **LangChain**: Use Perplexity models and search tools in LangChain
- **MCP Server**: Connect AI assistants to Perplexity via Model Context Protocol

### Community
- Community Forum: https://community.perplexity.ai
- Research Blog: https://research.perplexity.ai/articles
- API Roadmap: https://docs.perplexity.ai/docs/getting-started/api-roadmap
- System Status: https://docs.perplexity.ai/docs/resources/system-status
