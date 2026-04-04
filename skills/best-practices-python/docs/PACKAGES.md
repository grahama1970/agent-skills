# Embry OS Python Package Reference

> Auto-generated from 1,414 pyproject.toml files across all projects and 220+ skills.
> Agents: consult this BEFORE choosing a package. Violations are caught by skills-ci.

## Mandatory Standards (NON-NEGOTIABLE)

| Need | Use | NEVER Use | Why |
|------|-----|-----------|-----|
| HTTP client | `httpx` | `requests`, `urllib3` | Async+sync, timeout control, httpx.Timeout |
| CLI framework | `typer` | `argparse`, `click`, `fire` | Typer wraps click with type hints |
| Logging | `loguru` | `import logging` | Structured, colored, zero-config |
| Terminal output | `rich` | `print()` for tables/panels | Tables, progress bars, panels, trees |

## Standard Toolkit (use these first)

### Core (used in 90%+ of skills)

| Package | Purpose | Usage |
|---------|---------|-------|
| `typer` | CLI framework | `app = typer.Typer()` with type-hinted args |
| `loguru` | Structured logging | `from loguru import logger` |
| `rich` | Terminal formatting | Tables, panels, progress bars, console markup |
| `httpx` | HTTP client (sync+async) | `httpx.post(url, timeout=httpx.Timeout(10.0, connect=2.0))` |
| `python-dotenv` | .env file loading | Used in services, `load_dotenv()` at entry |
| `pydantic` | Data validation | API models, typed configs, settings |

### API / Services

| Package | Purpose | When to use |
|---------|---------|-------------|
| `fastapi` | REST API framework | Any HTTP service endpoint |
| `uvicorn` | ASGI server | Always paired with FastAPI |
| `tenacity` | Retry with backoff | Flaky API calls, external services |
| `json-repair` | Fix malformed JSON | LLM output parsing (they often produce broken JSON) |

### Database

| Package | Purpose | When to use |
|---------|---------|-------------|
| `python-arango` | ArangoDB driver | Knowledge graph, memory store, SPARTA |
| `duckdb` | In-process analytics DB | Analytics queries, data audits, batch reporting |
| `redis` | Cache / message broker | scillm proxy cache, task queues |

### PDF / Document Processing

| Package | Purpose | When to use |
|---------|---------|-------------|
| `pymupdf` | PDF reader (fitz) | Primary extraction, page rendering |
| `pymupdf4llm` | PDF → markdown | LLM-ready document conversion |
| `reportlab` | PDF generation | Tables, figures, test fixtures |
| `camelot-py` | PDF table extraction | Lattice and stream table detection |
| `ebooklib` | EPUB read/write | Book ingestion and export |

### ML / AI

| Package | Purpose | When to use |
|---------|---------|-------------|
| `scillm` | Internal LLM gateway | All LLM calls (routes to DeepSeek/Claude/local) |
| `transformers` | HuggingFace models | Embeddings, classifiers, fine-tuning |
| `torch` | PyTorch | Foundation for all local ML |
| `accelerate` | Distributed training | Multi-GPU, mixed precision with HF |
| `datasets` | HF dataset loading | Training data pipelines |
| `unsloth` | Fast LoRA fine-tuning | create-gpt, assistant-lab |
| `sentence-transformers` | Embedding models | Semantic search in /memory |
| `scikit-learn` | Classical ML | Classification, regression, metrics |
| `faiss-cpu` | Vector similarity | Memory recall, embedding service |
| `optuna` | Hyperparameter tuning | regressor-lab, classifier-lab |
| `openai` | OpenAI API client | GPT-4 calls, Codex integration |
| `litellm` | Universal LLM proxy | Route to any provider with one API |

### Audio / Media

| Package | Purpose | When to use |
|---------|---------|-------------|
| `librosa` | Audio analysis | Spectrograms, features, pitch detection |
| `soundfile` | Audio I/O | Read/write wav, flac (paired with librosa) |
| `faster-whisper` | Speech-to-text | Primary transcription engine (CTranslate2) |
| `yt-dlp` | Media downloader | YouTube, audio, video downloads |
| `sox` | Audio processing | Resample, normalize, trim (CLI wrapper) |
| `pyloudnorm` | LUFS normalization | Audio loudness standards |
| `fal-client` | Fal.ai API | FLUX image generation |

### NLP

| Package | Purpose | When to use |
|---------|---------|-------------|
| `spacy` | NLP pipeline | Entity extraction, dependency parsing |
| `nltk` | Classic NLP | Tokenization, corpus tools |
| `rapidfuzz` | Fuzzy matching | Deduplication, approximate string search |

### Data Processing / Visualization

| Package | Purpose | When to use |
|---------|---------|-------------|
| `numpy` | Numerical arrays | Foundation for ML, signal processing |
| `pandas` | DataFrames | Analytics, batch reporting, data wrangling |
| `scipy` | Scientific computing | Statistics, signal processing, optimization |
| `matplotlib` | Plotting | create-figure, analytics charts |
| `seaborn` | Statistical viz | Built on matplotlib, prettier defaults |
| `pillow` | Image processing | Screenshots, thumbnails, preprocessing |
| `opencv-python` | Computer vision | Frame extraction, image analysis |

### Web Scraping

| Package | Purpose | When to use |
|---------|---------|-------------|
| `beautifulsoup4` | HTML parsing | fetcher, extract-html |
| `lxml` | Fast XML/HTML parser | BeautifulSoup backend, XPath queries |
| `playwright` | Browser automation | surf skill, JS-rendered pages |

### Testing

| Package | Purpose | When to use |
|---------|---------|-------------|
| `pytest` | Test framework | All skill and project tests |
| `pytest-asyncio` | Async test support | FastAPI, async function testing |
| `pytest-cov` | Coverage reporting | CI/CD coverage gates |

### Config / Serialization

| Package | Purpose | When to use |
|---------|---------|-------------|
| `pyyaml` | YAML parser | SKILL.md frontmatter, config files |
| `jsonschema` | JSON Schema validation | Config validation, API contracts |
| `orjson` | Fast JSON | 3-10x faster than stdlib json |

### Infrastructure

| Package | Purpose | When to use |
|---------|---------|-------------|
| `runpod` | GPU cloud | ops-runpod, remote training |
| `paramiko` | SSH client | Remote access to RunPod instances |
| `apscheduler` | Job scheduling | /scheduler skill backend |
| `discord.py` | Discord integration | ops-discord notifications |
| `mcp` / `fastmcp` | MCP protocol | Building MCP tool servers |

### Utility

| Package | Purpose | When to use |
|---------|---------|-------------|
| `tqdm` | Progress bars | Batch processing, training loops |
| `joblib` | Parallel exec | ML pipelines, parallel data processing |
| `python-dateutil` | Date parsing | Flexible date/time string parsing |
| `feedparser` | RSS/Atom feeds | consume-feed, news ingestion |
| `youtube-transcript-api` | YT transcripts | ingest-youtube |
| `tree-sitter` | Code parsing | treesitter skill, code analysis |

### GUI

| Package | Purpose | When to use |
|---------|---------|-------------|
| `pyside6` | Qt6 bindings | QML desktop apps, StreamController |

## Anti-Patterns (skills-ci will flag these)

| Bad | Good | Rule |
|-----|------|------|
| `import requests` | `import httpx` | `python.banned_import` |
| `import logging` | `from loguru import logger` | `python.banned_import` |
| `import argparse` | `import typer` | `python.banned_import` |
| `import click` | `import typer` | `python.banned_import` |
| `import ast` for imports | Use `ast` module correctly | Import detection must use `ast`, not regex |
| Manual `json.loads` on LLM output | `json_repair.loads()` | LLMs produce malformed JSON frequently |

## Package Manager

- **Always use `uv`** with `pyproject.toml`
- Every `import` in source MUST have a matching dep in `pyproject.toml`
- Never use `pip install` directly in skills
