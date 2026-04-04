# Advanced Rust Patterns Reference

Deep-dive patterns referenced from SKILL.md. For Python experts learning Rust.

## Trait Design Patterns

### Sealed Trait Pattern

Prevents downstream crates from implementing your trait, giving you freedom to add
methods without breaking changes. Essential for library authors.

```rust
// In your library crate
mod private {
    pub trait Sealed {}
}

pub trait MyApi: private::Sealed {
    fn required_method(&self) -> String;

    // You can add new methods with defaults later — no breaking change
    // because no external crate can implement this trait
    fn new_method(&self) -> u32 { 0 }
}

// Only types in THIS crate can implement MyApi
impl private::Sealed for MyStruct {}
impl MyApi for MyStruct {
    fn required_method(&self) -> String { "hello".into() }
}
```

**Python analogy:** Like making a class with `__init_subclass__` that raises if subclassed
outside the module — but enforced at compile time.

### Extension Trait Pattern

Add methods to foreign types without modifying them. Named `*Ext` by convention:

```rust
// Add convenience methods to any iterator of Results
pub trait ResultIterExt<T, E>: Iterator<Item = Result<T, E>> {
    fn collect_or_first_err(self) -> Result<Vec<T>, E>;
}

impl<I, T, E> ResultIterExt<T, E> for I
where
    I: Iterator<Item = Result<T, E>>,
{
    fn collect_or_first_err(self) -> Result<Vec<T>, E> {
        self.collect()
    }
}

// Usage: any_iterator.collect_or_first_err()
```

**Python analogy:** Like adding methods via a mixin class, but the "mixin" is auto-applied
to any type that meets the trait bounds.

### Object Safety & `dyn Trait`

A trait is object-safe (can be used as `&dyn Trait`) only if:
- No methods return `Self`
- No methods have generic type parameters
- No `Self: Sized` bound on methods

```rust
// Object-safe: can use as &dyn Storage
trait Storage: Send + Sync {
    fn get(&self, key: &str) -> Result<Vec<u8>>;
    fn put(&self, key: &str, data: &[u8]) -> Result<()>;
}

// NOT object-safe: returns Self
trait Clonable {
    fn clone_self(&self) -> Self;  // Can't call through &dyn — don't know the size
}

// Fix: add Sized bound to exclude from vtable
trait Clonable {
    fn clone_self(&self) -> Self where Self: Sized;  // Now object-safe
}
```

**When to use `dyn Trait`:**
- Heterogeneous collections (`Vec<Box<dyn Widget>>`)
- Runtime polymorphism where performance isn't critical
- Plugin/extension systems

**When to use generics (static dispatch):**
- Performance-sensitive code (no vtable indirection)
- When you know the concrete type at compile time

### Newtype Conversion Traits

Implement `From`, `AsRef`, `Deref` for ergonomic newtypes:

```rust
struct UserId(String);

impl From<String> for UserId {
    fn from(s: String) -> Self { Self(s) }
}

impl AsRef<str> for UserId {
    fn as_ref(&self) -> &str { &self.0 }
}

// Now works:
let id = UserId::from("user-42".to_string());
let id: UserId = "user-42".to_string().into();
println!("{}", id.as_ref());  // borrows cheaply
```

---

## Advanced Lifetime Patterns

### Higher-Rank Trait Bounds (HRTBs)

`for<'a>` means "for ANY lifetime". Used when a closure or function must work with
references of different lifetimes:

```rust
// This closure must handle references with any lifetime
fn apply_to_lines<F>(text: &str, f: F) -> Vec<String>
where
    F: for<'a> Fn(&'a str) -> &'a str,  // works for any lifetime
{
    text.lines().map(|line| f(line).to_string()).collect()
}
```

**Python analogy:** There's no equivalent. In Python, every reference is implicitly
the same — garbage collected. HRTBs let Rust express "this function is generic over
reference lifetimes" which is a compile-time-only concept.

### `'static` vs `T: 'static`

This is the #1 lifetime misconception:

```rust
// &'static str: A reference valid for the ENTIRE program (rare)
let s: &'static str = "hello";  // string literals are 'static

// T: 'static: A type that OWNS all its data (very common!)
// String, Vec<u8>, i32, HashMap<K,V> — ALL satisfy T: 'static
// Only fails for types containing non-static references like &'a str

fn spawn_thread<T: Send + 'static>(data: T) {
    // T: 'static means T owns everything — safe to send to a thread
    // that might outlive the caller
    std::thread::spawn(move || {
        // data is moved here, no dangling references possible
    });
}

// This works! String is 'static (it owns its data)
spawn_thread("hello".to_string());

// This FAILS: &str with a non-static lifetime
let local = String::from("hello");
let reference: &str = &local;
// spawn_thread(reference);  // ERROR: borrowed data can't outlive the function
```

### Lifetime Elision Rules

The compiler infers lifetimes automatically in most cases. Only annotate when the
compiler asks:

1. Each reference parameter gets its own lifetime
2. If exactly one input lifetime, output gets that lifetime
3. If `&self` or `&mut self`, output gets the `self` lifetime

```rust
// All three are equivalent — the compiler infers the lifetimes:
fn first(s: &str) -> &str { ... }
fn first<'a>(s: &'a str) -> &'a str { ... }

// Must annotate: two input lifetimes, compiler can't guess which output uses
fn longest<'a>(x: &'a str, y: &'a str) -> &'a str { ... }
```

---

## Smart Pointer Guide

| Pointer | Use when | Thread-safe? | Python equivalent |
|---------|----------|-------------|-------------------|
| `Box<T>` | Heap allocation, trait objects, recursive types | Yes (if T: Send) | Just a Python object (everything is heap) |
| `Rc<T>` | Shared ownership, single thread | No | Python's reference counting |
| `Arc<T>` | Shared ownership, multi-thread | Yes | Python's `multiprocessing.Value` |
| `Cow<'a, T>` | Clone-on-write, conditional ownership | Depends on T | No equivalent |
| `Pin<Box<T>>` | Self-referential types, async futures | Depends on T | No equivalent |

### Interior Mutability

Rust normally forbids mutation through shared references (`&T`). Interior mutability
opts out of this rule, deferring the borrow check to runtime:

```rust
use std::cell::{Cell, RefCell};
use std::sync::{Mutex, RwLock};

// Cell<T>: for Copy types only, single-thread. Zero overhead.
let counter = Cell::new(0u32);
counter.set(counter.get() + 1);  // mutate through shared reference

// RefCell<T>: for any type, single-thread. Panics on double-borrow.
let data = RefCell::new(vec![1, 2, 3]);
data.borrow_mut().push(4);  // runtime borrow check

// Mutex<T>: for any type, multi-thread. Blocks on contention.
let shared = Arc::new(Mutex::new(HashMap::new()));
shared.lock().unwrap().insert("key", "value");

// RwLock<T>: many readers OR one writer, multi-thread.
let config = Arc::new(RwLock::new(Config::default()));
let val = config.read().unwrap();  // multiple readers OK
```

**Decision tree:**
- Single thread, Copy type → `Cell<T>`
- Single thread, any type → `RefCell<T>`
- Multi-thread, simple exclusive → `Mutex<T>` (use `tokio::sync::Mutex` in async)
- Multi-thread, read-heavy → `RwLock<T>` (use `tokio::sync::RwLock` in async)
- Multi-thread, concurrent map → `dashmap::DashMap`

---

## Pin and Unpin

`Pin` guarantees a value won't be moved in memory. This is essential for async/await
because futures may contain self-referential pointers.

```rust
use std::pin::Pin;
use std::future::Future;

// Most types are Unpin — Pin has no effect on them
// Pin only matters for !Unpin types (async futures, self-referential structs)

// When you see Pin in APIs, it's usually:
fn poll(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Output>;

// Creating pinned futures:
let future = Box::pin(async { 42 });  // Pin<Box<dyn Future<Output = i32>>>

// tokio::pin! macro for stack-pinning:
let future = async { heavy_computation().await };
tokio::pin!(future);  // now `future` is Pin<&mut impl Future>
```

**Rule of thumb:** You rarely need to think about Pin directly. Use `async/await`,
`Box::pin()`, and `tokio::pin!()` — they handle pinning for you. Only worry about
Pin when implementing `Future` manually or working with self-referential structs.

---

## Error Handling Ecosystem Comparison

| Crate | Use for | Features | Overhead |
|-------|---------|----------|----------|
| `thiserror` | Library error types | Derive macro, `#[from]`, `#[error]` format | Zero runtime (proc macro) |
| `anyhow` | Application errors | Context, downcasting, backtraces | Small (Box<dyn Error>) |
| `eyre` | Like anyhow + custom reports | `color-eyre` for pretty panics | Small |
| `miette` | User-facing diagnostics | Source spans, labels, codes, help text | Medium (diagnostic metadata) |

**House rule:** Use `thiserror` for libraries, `anyhow` for applications. Consider
`miette` for CLI tools where user-facing error messages with source context matter.

```rust
// miette example: rich diagnostic errors for CLI tools
use miette::{Diagnostic, SourceSpan};
use thiserror::Error;

#[derive(Debug, Error, Diagnostic)]
#[error("invalid configuration")]
#[diagnostic(code(config::invalid), help("check your config.toml syntax"))]
struct ConfigError {
    #[source_code]
    src: String,
    #[label("this value is invalid")]
    span: SourceSpan,
}
```

---

## Serde Advanced Patterns

### Adjacently Tagged Enums

For clean JSON representation of enum variants:

```rust
#[derive(Serialize, Deserialize)]
#[serde(tag = "type", content = "data")]  // adjacently tagged
enum Message {
    Text { body: String },
    Image { url: String, width: u32 },
    Delete { id: u64 },
}

// Serializes to: {"type": "Text", "data": {"body": "hello"}}
// vs internally tagged: {"type": "Text", "body": "hello"}
// vs externally tagged (default): {"Text": {"body": "hello"}}
```

### Custom Deserializer (String or Struct)

Accept both `"value"` and `{"key": "value"}` in JSON:

```rust
use serde::de::{self, Deserializer, Visitor};

#[derive(Debug, Deserialize)]
struct Config {
    #[serde(deserialize_with = "string_or_struct")]
    database: DatabaseConfig,
}

fn string_or_struct<'de, D>(deserializer: D) -> Result<DatabaseConfig, D::Error>
where
    D: Deserializer<'de>,
{
    struct StringOrStruct;

    impl<'de> Visitor<'de> for StringOrStruct {
        type Value = DatabaseConfig;

        fn expecting(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
            f.write_str("string or map")
        }

        fn visit_str<E: de::Error>(self, v: &str) -> Result<DatabaseConfig, E> {
            Ok(DatabaseConfig { url: v.to_string(), ..Default::default() })
        }

        fn visit_map<M: de::MapAccess<'de>>(self, map: M) -> Result<DatabaseConfig, M::Error> {
            Deserialize::deserialize(de::value::MapAccessDeserializer::new(map))
        }
    }

    deserializer.deserialize_any(StringOrStruct)
}
```

### Flatten and Deny Unknown Fields

```rust
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]  // reject typos in config files
struct Config {
    name: String,
    #[serde(flatten)]  // inline nested struct fields
    database: DatabaseConfig,
}
```

---

## Tracing: Spans, Layers, and Subscribers

### Structured Spans

Spans create a tree of execution context (like Python's `logging` with `extra` fields):

```rust
use tracing::{info, info_span, Instrument};

async fn handle_request(req_id: u64) {
    let span = info_span!("handle_request", req_id);

    async {
        info!("starting");  // automatically includes req_id in context
        let result = process().instrument(info_span!("process")).await;
        info!(result = ?result, "completed");
    }
    .instrument(span)
    .await;
}
```

### Layer Composition

Stack multiple output layers (console + file + OpenTelemetry):

```rust
use tracing_subscriber::{fmt, prelude::*, EnvFilter, Registry};

fn init_tracing() {
    let fmt_layer = fmt::layer()
        .with_target(false)
        .with_thread_names(true);

    let filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new("info"));

    // Optional: JSON output for production
    let json_layer = fmt::layer().json();

    Registry::default()
        .with(filter)
        .with(fmt_layer)
        // .with(json_layer)  // enable for structured logging
        .init();
}
```

---

## CI Pipeline Tools

### Dependency Auditing

```toml
# .cargo/config.toml or CI step
[alias]
ci = "clippy --workspace -- -D warnings && cargo test --workspace && cargo fmt -- --check"
```

| Tool | Purpose | Command |
|------|---------|---------|
| `cargo-deny` | License + advisory + duplicate checks | `cargo deny check` |
| `cargo-audit` | Security vulnerability scan (RustSec DB) | `cargo audit` |
| `cargo-machete` | Find unused dependencies | `cargo machete` |
| `cargo-udeps` | Find unused dependencies (nightly) | `cargo +nightly udeps` |
| `cargo-semver-checks` | Detect accidental breaking changes | `cargo semver-checks` |

### Recommended CI Pipeline

```yaml
# GitHub Actions snippet
steps:
  - run: cargo fmt -- --check
  - run: cargo clippy --workspace -- -D warnings
  - run: cargo test --workspace
  - run: cargo deny check
  - run: cargo audit
  - run: cargo machete
  - run: cargo doc --no-deps  # verify docs compile
```

---

## Testing Patterns

### Property-Based Testing with `proptest`

Generate random inputs to find edge cases the developer wouldn't think of:

```rust
use proptest::prelude::*;

proptest! {
    #[test]
    fn parse_roundtrip(s in "[a-zA-Z0-9]{1,100}") {
        let parsed = parse(&s).unwrap();
        let rendered = render(&parsed);
        prop_assert_eq!(s, rendered);
    }

    #[test]
    fn add_is_commutative(a in 0u64..1000, b in 0u64..1000) {
        prop_assert_eq!(add(a, b), add(b, a));
    }
}
```

### Benchmarking with `criterion`

```rust
use criterion::{black_box, criterion_group, criterion_main, Criterion};

fn bench_parse(c: &mut Criterion) {
    let input = include_str!("../fixtures/large.json");
    c.bench_function("parse_json", |b| {
        b.iter(|| parse(black_box(input)))
    });
}

criterion_group!(benches, bench_parse);
criterion_main!(benches);
```

### Snapshot Testing with `insta`

```rust
use insta::assert_snapshot;

#[test]
fn test_error_display() {
    let err = ParseError::InvalidHeader { offset: 42, reason: "bad magic".into() };
    assert_snapshot!(format!("{err}"));
    // First run creates snapshots/__FILE__-test_error_display.snap
    // Subsequent runs compare against it
    // Review changes: cargo insta review
}
```

---

## Conditional Compilation & Feature Flags

```rust
// Platform-specific code
#[cfg(target_os = "linux")]
fn get_memory() -> u64 { /* linux-specific */ }

#[cfg(target_os = "macos")]
fn get_memory() -> u64 { /* macos-specific */ }

// Feature-gated code
#[cfg(feature = "python")]
mod python_bindings {
    use pyo3::prelude::*;
    // ...
}

// Conditional dependencies in Cargo.toml
// [dependencies]
// pyo3 = { version = "0.22", optional = true }
//
// [features]
// python = ["pyo3"]
```

### Feature Flag Best Practices

1. **Additive only** — features should only ADD functionality, never remove it
2. **No default features** for optional heavy deps (e.g., `python`, `wasm`)
3. **Test all feature combinations in CI**: `cargo test --all-features && cargo test --no-default-features`
4. **Document features** in both `Cargo.toml` and README

---

## Rust 2024 Edition Key Features

### `async fn` in Traits (No More Proc Macro)

```rust
// Before 2024: required #[async_trait] proc macro
#[async_trait::async_trait]
trait OldWay {
    async fn fetch(&self) -> Result<Vec<u8>>;
}

// 2024 Edition: native async fn in traits
trait NewWay {
    async fn fetch(&self) -> Result<Vec<u8>>;
    // Note: this returns impl Future, which is NOT object-safe by default
    // For dyn dispatch, you still need #[async_trait] or manual boxing
}
```

### Return Position `impl Trait` in Traits (RPITIT)

```rust
trait Collection {
    fn items(&self) -> impl Iterator<Item = &str>;
    // Callers see: returns "some iterator" — concrete type hidden
}

struct MyCollection { data: Vec<String> }
impl Collection for MyCollection {
    fn items(&self) -> impl Iterator<Item = &str> {
        self.data.iter().map(|s| s.as_str())
    }
}
```

### Lifetime Capture Rules

Edition 2024 changes how `impl Trait` captures lifetimes. Use `+ use<'a>` for explicit:

```rust
// Edition 2024: explicit lifetime capture
fn filter_active<'a>(items: &'a [Item]) -> impl Iterator<Item = &'a Item> + use<'a> {
    items.iter().filter(|i| i.is_active())
}
```

### `unsafe_op_in_unsafe_fn`

In 2024, the body of `unsafe fn` is no longer implicitly unsafe. You must explicitly
wrap unsafe operations:

```rust
// 2024 Edition: must mark unsafe ops explicitly even inside unsafe fn
unsafe fn old_way(ptr: *const u8) -> u8 {
    unsafe { *ptr }  // explicit unsafe block required now
}
```
