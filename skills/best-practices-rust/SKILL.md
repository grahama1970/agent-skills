---
name: best-practices-rust
description: >
  Repo-specific Rust best practices for agentic coding: thiserror + anyhow error handling,
  tokio async runtime, tracing for observability, clap for CLI, axum for HTTP, serde patterns,
  cargo workspace conventions, ownership and lifetimes, and idiomatic Rust 2024 edition patterns.
triggers:
  - best practices rust
  - rust conventions
  - rust code review
  - cargo workspace
  - thiserror anyhow
  - tokio async
  - rust error handling
  - axum server
  - clap cli
  - rust performance
  - rust ownership lifetimes
  - rust edition 2024
license: MIT
metadata:
  language: rust
  edition: "2024"
  rust_versions: ["1.85+"]
  defaults:
    error_handling:
      libraries: thiserror
      applications: anyhow
    async_runtime: tokio
    http_server: axum
    http_client: reqwest
    cli: clap (derive)
    serialization: serde + serde_json
    logging: tracing + tracing-subscriber
    tui: ratatui + crossterm
    data_processing: polars
    parallelism: rayon
    progress: indicatif
    packaging: cargo
    style:
      max_line_length: 100
      indentation: 4 spaces
      naming:
        functions: snake_case
        types: PascalCase
        constants: SCREAMING_SNAKE_CASE
    testing:
      framework: built-in (#[test])
      runner: cargo test

provides:
  - best-practices-rust
composes:
  - agentic-evals

taxonomy:
  - validation
  - precision
  - resilience
disciplines:
  - engineering-standards
  - developer-tooling
---

# Rust Best Practices (Project Skill)

This skill is a curated set of atomic rules for writing and refactoring Rust in *this* repo.
Assume the reader is a Python expert but a Rust novice. Include additional code comments
around Rust-specific nuances that a Python developer may not recognize.

## Advanced Patterns Reference

See **[references/advanced-patterns.md](references/advanced-patterns.md)** for deep-dive content:
sealed traits, extension traits, HRTBs, `'static` misconceptions, Pin/Unpin, smart pointer
decision tree, interior mutability, serde advanced patterns, tracing layers, CI pipeline tools,
property-based testing, snapshot testing, and Rust 2024 edition features.

## Project Defaults (apply unless explicitly overridden)

- **Error Handling:** `thiserror` for library crates, `anyhow` for application crates
- **Async Runtime:** `tokio` (multi-threaded by default)
- **HTTP Server:** `axum` with `tower` middleware
- **HTTP Client:** `reqwest`
- **CLI:** `clap` with derive macros
- **Serialization:** `serde` + `serde_json`
- **Logging:** `tracing` + `tracing-subscriber` (NEVER `println!` for diagnostics)
- **TUI:** `ratatui` + `crossterm`
- **Data Processing:** `polars` (NEVER other dataframe libraries)
- **CPU Parallelism:** `rayon`
- **Progress Bars:** `indicatif` with contextually sensitive messages
- **Packaging:** `cargo` for builds, deps, and workspace management

## When to Apply

Use this skill whenever you:
- create or refactor Rust crates, binaries, libraries, or workspaces
- add error handling, async code, or network calls
- change `Cargo.toml` dependencies or workspace structure
- add tests or fix bugs
- build WASM or PyO3/maturin bridges

## Categories (priority order)

1. Correctness & Ownership (CRITICAL/HIGH): `correctness-`
2. Security (CRITICAL/HIGH): `security-`
3. Error Handling (CRITICAL): `errors-`
4. Type System (HIGH): `types-`
5. Conventions (HIGH): `conventions-`
6. Async & Concurrency (HIGH/MEDIUM): `async-`
7. Testing (HIGH/MEDIUM): `testing-`
8. Performance & Memory (MEDIUM): `perf-`
9. Cargo & Workspaces (MEDIUM): `cargo-`
10. Documentation (MEDIUM): `docs-`
11. Style & Maintainability (MEDIUM/LOW): `style-`

## Quick Reference (house rules)

- `correctness-ownership` — understand move vs borrow; prefer borrowing
- `correctness-lifetimes` — let the compiler infer; annotate only when required
- `correctness-clone-explicit` — call `.clone()` explicitly on non-`Copy` types
- `correctness-let-else` — use `let-else` for early returns on pattern failure
- `errors-thiserror-libraries` — use `thiserror` in library crates
- `errors-anyhow-applications` — use `anyhow` in application/binary crates
- `errors-no-unwrap` — NEVER `.unwrap()` in production code
- `errors-context` — add `.context()` to every `?` at module boundaries
- `errors-boundary-pattern` — three zones: library/app/API boundary
- `conventions-tracing` — use `tracing` for all observability
- `conventions-clap-derive` — use `clap` derive macros for CLI
- `conventions-serde` — use `serde` for all serialization
- `conventions-reqwest` — use `reqwest` with shared client for HTTP
- `conventions-no-emoji` — NEVER use emoji or unicode emoji-like chars
- `conventions-cargo-deps-complete` — every `use` needs a `Cargo.toml` entry
- `conventions-function-design` — single responsibility, max 5 params
- `conventions-no-debug-output` — NEVER commit `println!`/`dbg!`
- `types-newtype` — use newtypes to distinguish semantically different values
- `types-typestate` — use the Type State Pattern for compile-time state machines
- `types-sealed-trait` — seal public traits in libraries to allow evolution
- `types-option-over-sentinel` — prefer `Option<T>` over sentinel values
- `async-structured` — use structured concurrency with `JoinSet`
- `async-spawn-blocking` — offload CPU-bound work to `spawn_blocking`
- `async-send-sync` — understand `Send`/`Sync` bounds for threaded runtimes
- `async-cancellation` — use `CancellationToken` for graceful shutdown
- `async-mutex-vs-rwlock` — `RwLock` for read-heavy, `Mutex` for simple exclusive
- `perf-borrow-first` — prefer `&T` over owned `T` in function params
- `perf-cow` — use `Cow<'_, str>` when ownership is conditionally needed
- `perf-vec-capacity` — use `Vec::with_capacity()` when size is known
- `perf-iterators` — prefer iterator combinators over manual loops
- `testing-arrange-act-assert` — follow AAA pattern in all tests
- `testing-proptest` — property-based tests for roundtrip/invariant checks
- `testing-doc-tests` — doc examples are compiled and run by `cargo test`
- `cargo-workspace` — share deps via `[workspace.dependencies]`
- `cargo-features` — additive feature flags, minimal defaults
- `cargo-ci-tools` — `cargo-deny`, `cargo-audit`, `cargo-machete` in CI
- `style-rustfmt` — all code formatted with `rustfmt`
- `style-clippy-clean` — zero clippy warnings (`-D warnings`)
- `docs-public-items` — doc comments on all public items

---

## 1. Correctness & Ownership (CRITICAL)

Rust's ownership system is the biggest difference from Python. In Python, everything is
reference-counted and garbage-collected. In Rust, each value has exactly one owner, and
the compiler enforces this at compile time — no GC overhead, no use-after-free.

### Rule: `correctness-ownership`

Understand the three modes of passing data:

```rust
// MOVE: caller gives up ownership (like Python's only mode, but enforced)
fn consume(data: String) { /* data is owned here, freed when function ends */ }

// BORROW: caller lends read-only access (like a const reference)
fn inspect(data: &str) { /* can read data, can't modify or store it */ }

// MUTABLE BORROW: caller lends exclusive write access
fn modify(data: &mut String) { /* can modify, but no other refs can exist */ }
```

**Default to borrowing.** Only take ownership when you need to store or move the value.
Think of `&T` as Python's normal function args, and owned `T` as "I'm taking this from you."

### Rule: `correctness-lifetimes`

Let the compiler infer lifetimes. Only annotate when the compiler asks:

```rust
// GOOD: compiler infers lifetimes automatically (elision rules)
fn first_word(s: &str) -> &str {
    s.split_whitespace().next().unwrap_or("")
}

// ONLY annotate when the compiler needs help (multiple references in, one out)
fn longest<'a>(x: &'a str, y: &'a str) -> &'a str {
    if x.len() > y.len() { x } else { y }
}
// 'a means: the returned reference lives as long as BOTH inputs.
// Python equivalent: this is like guaranteeing the return value won't
// outlive either of the inputs — the compiler checks this for you.
```

### Rule: `correctness-clone-explicit`

MUST call `.clone()` explicitly on non-`Copy` types. Never hide clones in closures:

```rust
// BAD: hidden clone inside closure — easy to miss the allocation
let names: Vec<String> = items.iter().map(|i| i.name).collect(); // won't compile

// GOOD: explicit clone makes the cost visible
let names: Vec<String> = items.iter().map(|i| i.name.clone()).collect();

// BETTER: borrow if you don't need ownership
let names: Vec<&str> = items.iter().map(|i| i.name.as_str()).collect();
```

### Rule: `correctness-let-else`

Use `let-else` for early returns on pattern match failure (Rust 1.65+):

```rust
// BAD: nested match
fn process(input: Option<&str>) -> Result<()> {
    match input {
        Some(val) => {
            // deeply nested logic...
        }
        None => return Err(anyhow!("missing input")),
    }
}

// GOOD: flat control flow with let-else
fn process(input: Option<&str>) -> Result<()> {
    let Some(val) = input else {
        return Err(anyhow!("missing input"));
    };
    // val is bound here, no nesting
    Ok(())
}
```

---

## 2. Security (CRITICAL)

### Rule: `security-no-secrets-in-code`

NEVER store secrets, API keys, or passwords in code. Use `.env` files:

```rust
use dotenvy::dotenv;

fn main() {
    dotenv().ok();
    let api_key = std::env::var("API_KEY")
        .expect("API_KEY must be set");
}
```

Ensure `.env` is in `.gitignore`.

### Rule: `security-no-log-secrets`

NEVER log sensitive information. Use the `secrecy` crate for sensitive data types:

```rust
use secrecy::{Secret, ExposeSecret};

struct Config {
    api_key: Secret<String>,  // Debug/Display print "[REDACTED]"
}

// Only expose when actually needed for the API call
fn make_request(config: &Config) {
    let key = config.api_key.expose_secret();
    // key is &str — use it, then it's dropped
}
```

### Rule: `security-no-unsafe`

NEVER use `unsafe` unless absolutely necessary. When required, document safety invariants
with a `// SAFETY:` comment explaining why the invariants hold:

```rust
// SAFETY: `ptr` is guaranteed non-null and properly aligned because
// it was obtained from `Box::into_raw` on the line above, and no
// other code has accessed or freed it since.
unsafe { *ptr = value; }
```

### Rule: `security-input-validation`

Validate all external input at system boundaries. Use newtypes with validation:

```rust
struct Port(u16);
impl Port {
    fn new(value: u16) -> Result<Self, anyhow::Error> {
        anyhow::ensure!(value > 0 && value < 65536, "invalid port: {value}");
        Ok(Self(value))
    }
}
```

---

## 3. Error Handling (CRITICAL)

### Rule: `errors-thiserror-libraries`

Library crates MUST define structured error types with `thiserror`:

```rust
use thiserror::Error;

#[derive(Debug, Error)]
pub enum ParseError {
    #[error("invalid header at byte {offset}: {reason}")]
    InvalidHeader { offset: usize, reason: String },

    #[error("unsupported version {0}")]
    UnsupportedVersion(u32),

    // #[from] auto-implements From<std::io::Error> for ParseError
    #[error(transparent)]
    Io(#[from] std::io::Error),
}
```

### Rule: `errors-anyhow-applications`

Application/binary crates use `anyhow` for ad-hoc error context:

```rust
use anyhow::{Context, Result};

fn load_config(path: &Path) -> Result<Config> {
    let contents = std::fs::read_to_string(path)
        .context("failed to read config file")?;  // Always add context
    let config: Config = toml::from_str(&contents)
        .with_context(|| format!("failed to parse {}", path.display()))?;
    Ok(config)
}
```

### Rule: `errors-no-unwrap`

- **NEVER** use `.unwrap()` in production code paths
- Use `.expect("invariant: reason")` ONLY for true invariant violations with a descriptive message
- In library code, NEVER use `.unwrap()` or `.expect()` — always return `Result`

### Rule: `errors-context`

Every `?` propagation at a module boundary MUST have `.context()` or `.with_context()`:

```rust
// BAD: raw ? loses context — error says "No such file" with no clue WHICH file
let data = std::fs::read(path)?;

// GOOD: context explains what we were trying to do
let data = std::fs::read(path)
    .with_context(|| format!("reading input file {}", path.display()))?;
```

### Rule: `errors-boundary-pattern`

Error handling has three zones:
1. **Library internals** — `thiserror` enums, no `anyhow`
2. **Application logic** — `anyhow::Result`, `.context()` everywhere
3. **API boundaries** (axum handlers, CLI) — convert to user-facing messages, log internal details

```rust
// axum handler: boundary between internal errors and HTTP responses
async fn get_item(Path(id): Path<u64>) -> Result<Json<Item>, AppError> {
    let item = db::find_item(id)
        .await
        .context("database lookup failed")?;  // anyhow context
    Ok(Json(item))
}

// AppError converts anyhow::Error to HTTP status + log
struct AppError(anyhow::Error);
impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        tracing::error!(error = %self.0, "request failed");
        (StatusCode::INTERNAL_SERVER_ERROR, "internal error").into_response()
    }
}
```

---


See [RULES_DETAILED.md](references/RULES_DETAILED.md) for detailed rules on type system, conventions, async/concurrency, axum, testing, performance, cargo workspaces, documentation, and style.
