## 6. Async & Concurrency (HIGH/MEDIUM)

### Rule: `async-structured`

Use `tokio::task::JoinSet` for structured concurrency — NOT unbounded `tokio::spawn`:

```rust
use tokio::task::JoinSet;

async fn process_batch(items: Vec<Item>) -> Result<Vec<Output>> {
    let mut set = JoinSet::new();

    for item in items {
        // Each task runs concurrently on the tokio thread pool
        set.spawn(async move { process_one(item).await });
    }

    let mut results = Vec::with_capacity(set.len());
    while let Some(res) = set.join_next().await {
        results.push(res??);  // First ? is JoinError, second is task error
    }
    Ok(results)
}
```

### Rule: `async-spawn-blocking`

Offload CPU-bound work to `tokio::task::spawn_blocking`. NEVER block the async reactor:

```rust
// BAD: blocks the tokio runtime thread — starves other tasks
let hash = expensive_hash(&data);

// GOOD: runs on dedicated blocking thread pool, won't starve async tasks
let hash = tokio::task::spawn_blocking(move || expensive_hash(&data)).await?;
```

### Rule: `async-cancellation`

Use `tokio::select!` with cancellation safety in mind. Prefer `tokio_util::sync::CancellationToken`
over manual `select!` for graceful shutdown:

```rust
use tokio_util::sync::CancellationToken;

async fn run_server(token: CancellationToken) {
    loop {
        tokio::select! {
            // CancellationToken is cancel-safe — no data loss on branch switch
            _ = token.cancelled() => {
                tracing::info!("shutting down gracefully");
                break;
            }
            conn = listener.accept() => {
                handle_connection(conn?).await;
            }
        }
    }
}
```

### Rule: `async-send-sync`

Understand `Send` and `Sync` for multi-threaded async runtimes:

```rust
// Send = safe to MOVE between threads (most types)
// Sync = safe to SHARE (&T) between threads
// !Send = pinned to one thread (Rc, raw pointers)

// tokio's multi-threaded runtime requires Send futures:
tokio::spawn(async move {
    // Everything captured must be Send
    // Use Arc<Mutex<T>> for shared mutable state, not Rc<RefCell<T>>
});

// Prefer:
// - Arc over Rc (thread-safe reference counting)
// - Mutex/RwLock from tokio::sync (async-aware) over std::sync (blocking)
// - Channels (mpsc) for message passing between tasks
```

### Rule: `async-rayon-cpu`

Use `rayon` for CPU-bound parallelism, `tokio` for IO-bound concurrency. Bridge with
`spawn_blocking`:

```rust
use rayon::prelude::*;

// CPU-bound parallel processing bridged into async context
let results = tokio::task::spawn_blocking(move || {
    items.par_iter()
        .map(|item| expensive_transform(item))
        .collect::<Vec<_>>()
}).await?;
```

### Rule: `async-channels`

Use channels for message passing between tasks. Prefer `tokio::sync::mpsc` for async,
`crossbeam::channel` for sync contexts. ALWAYS use bounded channels to prevent unbounded
memory growth:

```rust
let (tx, mut rx) = tokio::sync::mpsc::channel(32);  // bounded: backpressure at 32

tokio::spawn(async move {
    while let Some(msg) = rx.recv().await {
        process(msg).await;
    }
});
```

### Rule: `async-mutex-vs-rwlock`

Use `RwLock` when reads vastly outnumber writes. Use `Mutex` for simple exclusive access.
Consider lock-free alternatives (`dashmap`, atomics) for hot paths:

```rust
// Many readers, rare writes → RwLock
let config = Arc::new(tokio::sync::RwLock::new(Config::default()));
let val = config.read().await;  // multiple readers OK

// Simple exclusive access → Mutex
let counter = Arc::new(tokio::sync::Mutex::new(0u64));
*counter.lock().await += 1;
```

---

## 7. axum HTTP Server Patterns

### Rule: `conventions-axum`

Keep request handlers async, returning `Result<Response, AppError>` to centralize error handling.
Use layered extractors and shared state structs instead of global mutable data:

```rust
use axum::{extract::State, routing::get, Router, Json};
use std::sync::Arc;

struct AppState {
    db: DatabasePool,
    config: Config,
}

async fn list_items(
    State(state): State<Arc<AppState>>,
    Query(params): Query<ListParams>,
) -> Result<Json<Vec<Item>>, AppError> {
    let items = state.db.query_items(&params).await
        .context("listing items")?;
    Ok(Json(items))
}

fn app(state: Arc<AppState>) -> Router {
    Router::new()
        .route("/items", get(list_items))
        .with_state(state)
        .layer(tower_http::trace::TraceLayer::new_for_http())
        .layer(tower_http::timeout::TimeoutLayer::new(Duration::from_secs(30)))
        .layer(tower_http::compression::CompressionLayer::new())
}
```

Add `tower` middleware (timeouts, tracing, compression) for observability and resilience.
Offload CPU-bound work to `tokio::task::spawn_blocking` to avoid blocking the reactor.

---

## 8. Testing (HIGH/MEDIUM)

### Rule: `testing-arrange-act-assert`

Follow the Arrange-Act-Assert pattern. Use `#[cfg(test)]` modules:

```rust

## 9. Performance & Memory (MEDIUM)

### Rule: `perf-borrow-first`

Prefer borrowing (`&T`, `&mut T`) over ownership. Only take ownership when you need to
store or move the value:

```rust
// BAD: takes ownership unnecessarily — caller loses their String
fn process(data: String) -> usize { data.len() }

// GOOD: borrows — caller keeps ownership, no allocation
fn process(data: &str) -> usize { data.len() }
```

### Rule: `perf-cow`

Use `Cow<'_, str>` when ownership is conditionally needed:

```rust
use std::borrow::Cow;

fn normalize(input: &str) -> Cow<'_, str> {
    if input.contains('\t') {
        // Only allocate when transformation is needed
        Cow::Owned(input.replace('\t', "    "))
    } else {
        // Zero-cost borrow when input is already valid
        Cow::Borrowed(input)
    }
}
```

### Rule: `perf-vec-capacity`

Use `Vec::with_capacity()` when the final size is known or estimable:

```rust
// BAD: reallocates as it grows (amortized, but wasteful when size is known)
let mut results = Vec::new();

// GOOD: single allocation up front
let mut results = Vec::with_capacity(items.len());
```

### Rule: `perf-iterators`

Use iterators and combinators over explicit loops where they improve clarity:

```rust
// Prefer this — declarative, no mutable state
let sum: u64 = items.iter()
    .filter(|i| i.is_active())
    .map(|i| i.value)
    .sum();

// Over this — imperative, mutable accumulator
let mut sum = 0u64;
for item in &items {
    if item.is_active() {
        sum += item.value;
    }
}
```

Use `enumerate()` instead of manual counter variables.

### Rule: `perf-no-unnecessary-alloc`

Prefer `&str` over `String`, `&[T]` over `Vec<T>` in function parameters.
Prefer stack allocation over heap when appropriate.
Use `Arc` and `Rc` judiciously — prefer borrowing.

---

## 10. Cargo & Workspaces (MEDIUM)

### Rule: `cargo-workspace`

Multi-crate projects MUST use cargo workspaces. Share dependency versions via
`[workspace.dependencies]` to avoid version drift:

```toml

## 11. Documentation (MEDIUM)

### Rule: `docs-public-items`

MUST include doc comments for all public functions, structs, enums, and methods.
Document parameters, return values, errors, and include examples for complex functions:

```rust
/// Calculate the total cost of items including tax.
///
/// # Arguments
///
/// * `items` - Slice of item structs with price fields
/// * `tax_rate` - Tax rate as decimal (e.g., 0.08 for 8%)
///
/// # Returns
///
/// Total cost including tax
///
/// # Errors
///
/// Returns `CalculationError::EmptyItems` if items is empty
/// Returns `CalculationError::InvalidTaxRate` if tax_rate is negative
///
/// # Examples
///
/// ```
/// let items = vec![Item { price: 10.0 }, Item { price: 20.0 }];
/// let total = calculate_total(&items, 0.08)?;
/// assert_eq!(total, 32.40);
/// ```
pub fn calculate_total(items: &[Item], tax_rate: f64) -> Result<f64, CalculationError> {
    // ...
}
```

---

## 12. Style & Maintainability (MEDIUM/LOW)

### Rule: `style-rustfmt`

ALL code MUST be formatted with `rustfmt`. Run `cargo fmt --check` before committing.

### Rule: `style-clippy-clean`

Zero clippy warnings. Run `cargo clippy -- -D warnings` before committing.
Use `-D warnings` in CI, NOT `#![deny(warnings)]` in source (the latter breaks on new Rust versions).

### Rule: `style-line-length`

Limit line length to 100 characters (rustfmt default).

### Rule: `style-builder-pattern`

Use the builder pattern for complex struct construction:

```rust
let config = ConfigBuilder::new()
    .with_timeout(Duration::from_secs(30))
    .with_retries(3)
    .with_base_url("https://api.example.com")
    .build()?;
```

### Rule: `style-if-let`

Prefer `if let` and `while let` for single-pattern matching:

```rust
// GOOD: concise
if let Some(value) = optional {
    process(value);
}

// BAD: verbose (unless you need the else branch)
match optional {
    Some(value) => process(value),
    None => {},
}
```

### Rule: `style-struct-privacy`

Make struct fields private by default. Provide accessor methods when external access is needed:

```rust
pub struct Config {
    timeout: Duration,  // private — enforce invariants via constructor
    retries: u32,
}

impl Config {
    pub fn new(timeout: Duration, retries: u32) -> Result<Self> {
        anyhow::ensure!(retries <= 10, "retries must be <= 10");
        Ok(Self { timeout, retries })
    }

    pub fn timeout(&self) -> Duration { self.timeout }
    pub fn retries(&self) -> u32 { self.retries }
}
```

---

## Cargo.toml Dependency Completeness (NON-NEGOTIABLE)

### Rule: `conventions-cargo-deps-complete`

**Every `use` in a crate's `.rs` files MUST have a corresponding entry in `Cargo.toml` `[dependencies]`.**

This is a hard gate. Missing dependencies cause compile errors in clean builds.
Use version constraints (`thiserror = "2"` or `tokio = { version = "1", features = ["full"] }`).

### Verification pattern

```bash

## PyO3/Maturin Bridge (when applicable)

When using Python to call Rust code via PyO3/`maturin`:

- NEVER build with `cargo build --features python` — this will always fail. Use `maturin` instead.
- ALWAYS use `uv` for Python package management and create a `.venv` if not present.
- Ensure `.venv` is in `.gitignore`.
- Rebuild after Rust changes: `source .venv/bin/activate && maturin develop --release --features python`
- Install `ipykernel` and `ipywidgets` in `.venv` for Jupyter compatibility (not in package deps).

## WASM (when applicable)

When compiling to WASM:
- All deep computation MUST occur within the WASM binary. NEVER use JavaScript for computation.
- Front-end MUST use Pico CSS and vanilla JavaScript. NEVER jQuery or component frameworks (React, etc.).
- Adaptive light/dark themes by default with a toggle.
- Modern typography — add appropriate fonts from Google Fonts. NEVER use Pico CSS defaults as-is.
- A separate CSS/SCSS file is encouraged. The design MUST logically complement the application use case.
- ALWAYS rebuild the WASM binary if any underlying Rust code is touched:
  `wasm-pack build --target web --out-dir web/pkg`

## Data Processing with Polars (when applicable)

- ALWAYS use `polars` instead of other dataframe libraries for tabular data.
- If printing a dataframe, NEVER simultaneously print the entry count or schema (redundant).
- NEVER ingest more than 10 rows at a time for analysis. Only analyze subsets to avoid memory overload.

---

## Before Committing Checklist

1. All tests pass: `cargo test`
2. No compiler warnings: `cargo build`
3. Clippy clean: `cargo clippy -- -D warnings`
4. Formatted: `cargo fmt --check`
5. If workspace: `cargo build --workspace && cargo test --workspace`
6. If CI available: `cargo deny check && cargo audit`
7. If PyO3 project + Rust touched: `source .venv/bin/activate && maturin develop --release --features python`
8. If WASM project + Rust touched: `wasm-pack build --target web --out-dir web/pkg`
9. All public items have doc comments
10. No commented-out code or debug statements (`println!`, `dbg!`)
11. No hardcoded credentials
12. Every `use` has a matching `Cargo.toml` dependency
13. Feature flags tested: `--all-features` and `--no-default-features`

## 4. Type System (HIGH)

### Rule: `types-newtype`

Use newtypes to distinguish semantically different values of the same underlying type:

```rust
// BAD: both are just u64 — easy to swap arguments
fn transfer(from: u64, to: u64, amount: u64) { }

// GOOD: compiler catches argument swaps at call site
struct AccountId(u64);
struct Amount(u64);
fn transfer(from: AccountId, to: AccountId, amount: Amount) { }
```

### Rule: `types-typestate`

Use the Type State Pattern to encode state machines in the type system. Invalid states
become unrepresentable at compile time (zero runtime cost):

```rust
// Each state is a zero-sized type — no memory overhead
struct Draft;
struct Published;
struct Archived;

// The state is a generic parameter — you can't call publish() on an Archived post
struct Post<State> {
    title: String,
    body: String,
    _state: std::marker::PhantomData<State>,  // zero-sized, exists only for the type checker
}

impl Post<Draft> {
    fn publish(self) -> Post<Published> {
        // `self` is consumed (moved) — the Draft post no longer exists
        Post { title: self.title, body: self.body, _state: std::marker::PhantomData }
    }
}

impl Post<Published> {
    fn archive(self) -> Post<Archived> {
        Post { title: self.title, body: self.body, _state: std::marker::PhantomData }
    }
}
// Post<Archived> has no transition methods — it's a terminal state.
// Trying to call .publish() on Post<Archived> is a COMPILE ERROR, not a runtime bug.
```

### Rule: `types-exhaustive-match`

MUST use pattern matching exhaustively. Avoid catch-all `_` patterns when possible
so the compiler catches new variants:

```rust
// BAD: silent bug when a new variant is added later
match status {
    Status::Active => handle_active(),
    _ => handle_other(),  // new Status::Suspended silently falls through
}

// GOOD: compiler error forces you to handle new variants
match status {
    Status::Active => handle_active(),
    Status::Inactive => handle_inactive(),
    Status::Pending => handle_pending(),
}
```

### Rule: `types-derive-common`

MUST derive common traits on all public types:

```rust
#[derive(Debug, Clone, PartialEq)]           // minimum for most types
#[derive(Debug, Clone, PartialEq, Default)]   // when a sensible default exists
#[derive(Debug, Clone, PartialEq, Eq, Hash)]  // when used as HashMap keys
```

### Rule: `types-option-over-sentinel`

Prefer `Option<T>` over sentinel values. Rust has no null — `Option` makes absence explicit:

```rust
// BAD: Python-style sentinel
fn find_index(items: &[Item], target: &str) -> i64 {
    // returns -1 if not found — caller might forget to check
}

// GOOD: Option makes the "might not exist" case explicit
fn find_index(items: &[Item], target: &str) -> Option<usize> {
    items.iter().position(|i| i.name == target)
}
```

### Rule: `types-sealed-trait`

For library crates, seal public traits to prevent downstream implementations.
This lets you add methods to the trait later without breaking changes:

```rust
mod private { pub trait Sealed {} }

pub trait MyApi: private::Sealed {
    fn method(&self) -> String;
    // Can safely add new methods with defaults later — no external implementors
}

// Only types in THIS crate can implement MyApi
impl private::Sealed for MyStruct {}
impl MyApi for MyStruct { fn method(&self) -> String { "ok".into() } }
```

See [references/advanced-patterns.md](references/advanced-patterns.md) for extension traits,
object safety, and newtype conversion patterns.

---

## 5. Conventions (HIGH)

### Rule: `conventions-tracing`

Use `tracing` for ALL observability. NEVER use `println!` or `eprintln!` for diagnostics:

```rust
use tracing::{info, warn, error, debug, instrument};

#[instrument(skip(db))]  // auto-logs function entry/exit with args (skip large types)
async fn process_item(id: u64, db: &Database) -> Result<()> {
    info!(id, "processing item");       // structured key-value logging
    // ...
    if retries > 3 {
        warn!(id, retries, "excessive retries");
    }
    Ok(())
}
```

Initialize subscriber in `main()`:

```rust
tracing_subscriber::fmt()
    .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
    .init();
// Control verbosity at runtime: RUST_LOG=debug cargo run
```

### Rule: `conventions-clap-derive`

Use `clap` with derive macros for CLI. Keep handlers thin — business logic in separate functions:

```rust
use clap::Parser;

#[derive(Parser)]
#[command(name = "mytool", about = "Does useful things")]
struct Cli {
    /// Input file path
    #[arg(short, long)]
    input: PathBuf,

    /// Enable verbose output
    #[arg(short, long, default_value_t = false)]
    verbose: bool,

    #[command(subcommand)]
    command: Commands,
}

#[derive(clap::Subcommand)]
enum Commands {
    /// Process a file
    Process {
        /// Output format
        #[arg(long, default_value = "json")]
        format: String,
    },
}

fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();
    // Thin: parse args, init tracing, call business logic, exit
    match cli.command {
        Commands::Process { format } => process::run(&cli.input, &format)?,
    }
    Ok(())
}
```

### Rule: `conventions-serde`

Use `serde` for all serialization. Prefer `#[serde(rename_all = "camelCase")]` for JSON APIs
and `#[serde(rename_all = "snake_case")]` for config files:

```rust
#[derive(Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ApiResponse {
    item_count: u32,
    #[serde(skip_serializing_if = "Option::is_none")]
    next_cursor: Option<String>,
    #[serde(default)]  // deserializes to Vec::new() if missing
    tags: Vec<String>,
}
```

### Rule: `conventions-reqwest`

Use `reqwest` for HTTP client calls. Create a shared client (connection pooling):

```rust
use reqwest::Client;

// Create ONCE and reuse — the client pools connections internally
let client = Client::builder()
    .timeout(Duration::from_secs(30))
    .user_agent("my-tool/1.0")
    .build()?;

// JSON request with typed response
let response: ApiResponse = client
    .get("https://api.example.com/items")
    .bearer_auth(&token)
    .send()
    .await?
    .error_for_status()?  // converts 4xx/5xx to Err
    .json()
    .await?;
```

### Rule: `conventions-function-design`

- MUST keep functions focused on a single responsibility
- Limit function parameters to 5 or fewer; use a config struct for more
- Return early to reduce nesting
- Use iterators and combinators over explicit loops where clearer

```rust
// BAD: too many params — easy to swap booleans
fn send(host: &str, port: u16, data: &[u8], compress: bool, encrypt: bool, retry: bool) { }

// GOOD: config struct with builder or Default
#[derive(Debug, Default)]
struct SendOptions {
    compress: bool,
    encrypt: bool,
    retry: bool,
}
fn send(host: &str, port: u16, data: &[u8], opts: &SendOptions) { }
```

### Rule: `conventions-no-emoji`

NEVER use emoji or unicode that emulates emoji (e.g., checkmarks, crosses) in code output.
The only exception is when writing tests that specifically test multibyte character handling.

### Rule: `conventions-imports`

Organize imports in this order, separated by blank lines:
1. Standard library (`std::`)
2. External crates
3. Local modules (`crate::`, `super::`)

NEVER use wildcard imports (`use module::*`) except for preludes and `use super::*` in test modules.
Use `rustfmt` to automate import formatting.

### Rule: `conventions-naming`

- `snake_case` for functions, variables, modules
- `PascalCase` for types, traits, enum variants
- `SCREAMING_SNAKE_CASE` for constants and statics
- Use `format!` macro for string formatting (NEVER manual concatenation)

### Rule: `conventions-no-debug-output`

NEVER commit `println!`, `eprintln!`, or `dbg!` statements. Use `tracing` macros instead.
`dbg!` is for interactive debugging only — it writes to stderr with file:line and is never appropriate in committed code.

---

See [RULES_DETAILED.md](RULES_DETAILED.md) for detailed rules on async/concurrency, axum patterns, testing, performance, cargo workspaces, documentation, and style.

---

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_valid_header() {
        // Arrange
        let input = b"MAGIC\x01\x00";

        // Act
        let header = Header::parse(input).unwrap();  // .unwrap() OK in tests

        // Assert
        assert_eq!(header.version, 1);
    }

    #[tokio::test]  // requires tokio with "macros" feature
    async fn fetch_returns_data() {
        // Arrange
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .respond_with(ResponseTemplate::new(200))
            .mount(&server).await;

        // Act
        let result = fetch_data(&server.uri()).await;

        // Assert
        assert!(result.is_ok());
    }
}
```

### Rule: `testing-mock-boundaries`

Mock external dependencies (APIs, databases, file systems). Use trait objects or generics
for dependency injection:

```rust
// Define a trait for the dependency (like Python's ABC/Protocol)
#[cfg_attr(test, mockall::automock)]  // auto-generate MockStorage in tests
#[async_trait::async_trait]
trait Storage: Send + Sync {
    async fn get(&self, key: &str) -> Result<Vec<u8>>;
    async fn put(&self, key: &str, data: &[u8]) -> Result<()>;
}

// Production implementation
struct S3Storage { client: aws_sdk_s3::Client }

#[async_trait::async_trait]
impl Storage for S3Storage {
    async fn get(&self, key: &str) -> Result<Vec<u8>> { /* real S3 call */ }
    async fn put(&self, key: &str, data: &[u8]) -> Result<()> { /* real S3 call */ }
}

// In tests, use MockStorage (from mockall) or a manual HashMap-backed impl
```

### Rule: `testing-no-dead-code`

NEVER commit commented-out tests, `#[ignore]` without a reason, or debug `println!`/`dbg!` macros.

### Rule: `testing-doc-tests`

Doc examples (`/// ````) are compiled and run by `cargo test`. Use them for public API
usage examples — they serve as both documentation and tests:

```rust
/// Parse a CSV row into fields.
///
/// ```
/// let fields = parse_row("a,b,c");
/// assert_eq!(fields, vec!["a", "b", "c"]);
/// ```
pub fn parse_row(line: &str) -> Vec<&str> { /* ... */ }
```

### Rule: `testing-proptest`

Use property-based testing (`proptest`) for roundtrip invariants and edge case discovery:

```rust
use proptest::prelude::*;

proptest! {
    #[test]
    fn parse_roundtrip(s in "[a-zA-Z0-9]{1,100}") {
        let parsed = parse(&s).unwrap();
        let rendered = render(&parsed);
        prop_assert_eq!(s, rendered);
    }
}
```

See [references/advanced-patterns.md](references/advanced-patterns.md) for `criterion` benchmarks
and `insta` snapshot testing patterns.

---

# Root Cargo.toml
[workspace]
members = ["crates/*"]
resolver = "2"

[workspace.dependencies]
tokio = { version = "1", features = ["full"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
anyhow = "1"
thiserror = "2"
tracing = "0.1"

# Crate Cargo.toml — inherit version from workspace
[dependencies]
tokio = { workspace = true }
serde = { workspace = true }
```

### Rule: `cargo-features`

Use feature flags for optional functionality. Keep the default feature set minimal:

```toml
[features]
default = []
python = ["pyo3"]  # PyO3 bridge, only built via maturin
full = ["python", "cli"]
```

### Rule: `cargo-edition`

Use Rust edition 2024 for new projects. Key 2024 features to leverage:

- **`async fn` in traits** — no more `#[async_trait]` proc macro for many cases
- **RPITIT (return position `impl Trait` in traits)** — cleaner trait APIs
- **`let chains` in `if let`** — combine multiple conditions
- **Lifetime capture rules** — `impl Trait + use<'a>` for explicit captures

```rust
// Edition 2024: async fn directly in traits (no proc macro needed)
trait DataSource {
    async fn fetch(&self, key: &str) -> Result<Vec<u8>>;
}

// Edition 2024: RPITIT — return impl Iterator from trait methods
trait Collection {
    fn items(&self) -> impl Iterator<Item = &str>;
}
```

See [references/advanced-patterns.md](references/advanced-patterns.md) for `unsafe_op_in_unsafe_fn`,
lifetime capture rules, and full edition migration guide.

### Rule: `cargo-ci-tools`

Use these tools in CI pipelines for comprehensive quality gates:

| Tool | Purpose | Command |
|------|---------|---------|
| `cargo-deny` | License, advisory, duplicate dep checks | `cargo deny check` |
| `cargo-audit` | Security vulnerability scan (RustSec DB) | `cargo audit` |
| `cargo-machete` | Find unused dependencies | `cargo machete` |

```bash
# Recommended CI pipeline order:
cargo fmt -- --check
cargo clippy --workspace -- -D warnings
cargo test --workspace
cargo deny check        # licenses + advisories
cargo audit             # security vulnerabilities
cargo machete           # unused deps
cargo doc --no-deps     # verify docs compile
```

Feature flag testing: always test both `--all-features` and `--no-default-features`.

---

# After any Cargo.toml change:
cargo build && cargo test
# In a workspace:
cargo build --workspace && cargo test --workspace
```

### Common dependencies reference

| Crate | Use case | Typical features |
|-------|----------|-----------------|
| `tokio` | Async runtime | `["full"]` or `["rt-multi-thread", "macros"]` |
| `serde` | Serialization | `["derive"]` |
| `serde_json` | JSON | — |
| `thiserror` | Library errors | — |
| `anyhow` | Application errors | — |
| `clap` | CLI parsing | `["derive"]` |
| `tracing` | Structured logging | — |
| `tracing-subscriber` | Log output | `["env-filter"]` |
| `axum` | HTTP server | — |
| `tower-http` | HTTP middleware | `["trace", "timeout", "compression-gzip"]` |
| `reqwest` | HTTP client | `["json"]` |
| `rayon` | CPU parallelism | — |
| `indicatif` | Progress bars | — |
| `polars` | DataFrames | `["lazy"]` |
| `ratatui` | TUI | — |
| `crossterm` | Terminal control | — |
| `dotenvy` | .env loading | — |
| `secrecy` | Secret types | — |
| `tokio-util` | Cancellation, codecs | `["full"]` |
| `dashmap` | Concurrent HashMap | — |
| `proptest` | Property-based testing | — (dev-dependency) |
| `criterion` | Benchmarking | — (dev-dependency) |
| `insta` | Snapshot testing | — (dev-dependency) |
| `mockall` | Test mocking | — (dev-dependency) |
| `wiremock` | HTTP mock server | — (dev-dependency) |
| `cargo-deny` | License/advisory checks | — (CI tool) |
| `cargo-audit` | Security vulnerability scan | — (CI tool) |
| `cargo-machete` | Unused dep detection | — (CI tool) |

---
