# Task List: Rust Polars Data Integrity Layer for /extract-tables

**Created**: 2026-03-06
**Goal**: Add Polars-based data integrity validation to the extract-tables Rust module, enabling schema-enforced table construction and validation at the Rust boundary — foundation for a pure-Rust extraction pipeline suitable for 1000+ page documents.

## Context

The `/extract-tables` skill currently uses Python Polars only for serialization (`write_csv`, `write_json`). Data flows through unvalidated `list[list[str]]` grids and `Cell` dataclasses with no schema enforcement, bbox validation, or rectangular grid guarantees. By adding `pyo3-polars` to the Rust module, we can:
1. Validate table grids at the Rust/Python boundary (schema + rectangular enforcement)
2. Build DataFrames in Rust, eliminating Python object overhead for large documents
3. Compute integrity metrics (null ratios, bbox validity) as Polars expressions
4. Lay the foundation for moving the full lattice parser to Rust

## Capability Overlap

- No existing skill provides DataFrame-level validation for extracted tables
- `/extract-tables` already owns the Rust module (`extract_tables_rs`) — we extend it
- Polars Python is already a dependency in `models.py` — adding Rust Polars is natural

## Crucial Dependencies (Sanity Scripts)

| Library | API/Method | Sanity Script | Status |
|---------|------------|---------------|--------|
| pyo3-polars 0.19+ | `PyDataFrame`, `PySeries` | `sanity/pyo3_polars.rs` | [ ] PENDING |
| polars (Rust) | `DataFrame::new`, `Schema` | `sanity/pyo3_polars.rs` | [ ] PENDING |
| pyo3 0.23 | existing dep | N/A (already working) | [x] PASS |

> All sanity scripts must PASS before proceeding to implementation.

## Questions/Blockers

None — all requirements clear. PyO3 0.23 is already in use; pyo3-polars 0.19 targets PyO3 0.23.

## Tasks

### P0: Setup (Sequential)

- [x] **Task 1**: Add `polars` and `pyo3-polars` to Cargo.toml and verify build
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: none
  - **Details**:
    - Add to `src/rust/Cargo.toml`:
      ```toml
      polars = { version = "0.46", features = ["dtype-struct", "lazy"] }
      pyo3-polars = { version = "0.19" }
      ```
    - Create `src/rust/src/dataframe.rs` with a minimal `#[pyfunction]` that accepts `PyDataFrame` and returns it
    - Register the function in `lib.rs`
    - Run `maturin develop` to verify compilation
  - **Sanity**: Build compiles and Python can `import extract_tables_rs; extract_tables_rs.validate_table(df)`
  - **Definition of Done**:
    - Test: `cd src/rust && cargo test` passes
    - Test: `python -c "import extract_tables_rs"` works
    - Assertion: `pyo3-polars` PyDataFrame round-trips successfully (Python → Rust → Python)

### P1: Core Validation Functions (Parallel)

- [x] **Task 2**: Implement `validate_grid` — rectangular grid enforcement in Rust
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1
  - **Details**:
    - Create `#[pyfunction] validate_grid(data: Vec<Vec<String>>, expected_cols: usize) -> PyResult<PyDataFrame>`
    - Enforce: all rows have exactly `expected_cols` columns (pad or error)
    - Convert `Vec<Vec<String>>` to Polars DataFrame with column names `col_0..col_N`
    - Return as `PyDataFrame` for seamless Python interop
    - Add `#[cfg(test)]` Rust unit tests for: empty grid, ragged rows, valid grid
  - **Definition of Done**:
    - Test: `cargo test test_validate_grid`
    - Assertion: Ragged input `[["a","b"],["c"]]` either pads to `[["a","b"],["c",""]]` or returns error
    - Assertion: Valid input returns a Polars DataFrame with correct schema

- [x] **Task 3**: Implement `validate_cells` — bbox and edge integrity checks in Rust
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1
  - **Details**:
    - Create `#[pyfunction] validate_cells(cells: Vec<(f64,f64,f64,f64,String,bool,bool,bool,bool)>) -> PyResult<PyDataFrame>`
    - Input: list of (x1, y1, x2, y2, text, left, right, top, bottom) tuples
    - Validate: `x1 < x2`, `y1 < y2` (bbox validity)
    - Compute columns: `has_text` (bool), `is_spanning_interior` (bool: !left || !top)
    - Return DataFrame with schema: `{x1: Float64, y1: Float64, x2: Float64, y2: Float64, text: Utf8, left: Boolean, right: Boolean, top: Boolean, bottom: Boolean, has_text: Boolean, is_spanning_interior: Boolean}`
    - Add `#[cfg(test)]` Rust unit tests
  - **Definition of Done**:
    - Test: `cargo test test_validate_cells`
    - Assertion: Invalid bbox (x2 < x1) is flagged or corrected
    - Assertion: Output DataFrame has 11 columns with correct dtypes

- [x] **Task 4**: Implement `compute_accuracy_rs` — fill-ratio metric in Rust
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1
  - **Details**:
    - Create `#[pyfunction] compute_accuracy_rs(cells_df: PyDataFrame) -> PyResult<f64>`
    - Accepts the DataFrame from `validate_cells` (has `has_text`, `is_spanning_interior` columns)
    - Logic: exclude rows where `is_spanning_interior && !has_text`, compute `filled / effective_total * 100`
    - Add structural penalty (single-col/single-row detection) matching Python `compute_accuracy`
    - Also implement header-spanning detection for stream tables (no edge flags): accept optional `data_grid: PyDataFrame` from `validate_grid`
    - Add `#[cfg(test)]` Rust unit tests
  - **Definition of Done**:
    - Test: `cargo test test_compute_accuracy_rs`
    - Assertion: Returns same values as Python `compute_accuracy` for identical inputs
    - Assertion: Handles both lattice (edge-flag) and stream (header-detection) modes

- [x] **Task 4b**: Implement `detect_collapse` — column and header collapse detection in Rust
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1
  - **Details**:
    - Create `#[pyfunction] detect_column_collapse(grid_df: PyDataFrame) -> PyResult<bool>`
      - Returns true if >80% of non-null values are in column 0 (lattice parser failure mode)
      - Uses Polars `null_count()` per column as expression
    - Create `#[pyfunction] detect_header_collapse(grid_df: PyDataFrame) -> PyResult<bool>`
      - Returns true if row 0 has a single cell containing `\n` (headers collapsed into one cell)
    - Reference: `/home/graham/workspace/experiments/extractor/src/extractor/pipeline/utils/tables/metrics.py` (`has_column_collapse`, `has_header_collapse`)
    - Add `#[cfg(test)]` Rust unit tests
  - **Definition of Done**:
    - Test: `cargo test test_detect_column_collapse` and `cargo test test_detect_header_collapse`
    - Assertion: Grid with 90% of data in col_0 returns `true` for column collapse
    - Assertion: Grid with `"A\nB\nC"` in row 0, col 0 returns `true` for header collapse
    - Assertion: Normal grid returns `false` for both

- [x] **Task 4c**: Implement `table_integrity_metrics` — DataFrame-level quality metrics in Rust
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1
  - **Details**:
    - Create `#[pyfunction] table_integrity_metrics(grid_df: PyDataFrame) -> PyResult<PyDataFrame>`
    - Returns a single-row DataFrame with columns:
      - `n_rows: UInt32`, `n_cols: UInt32` (shape)
      - `null_count: UInt32` (total nulls/empty strings across all columns)
      - `data_density: Float64` (non-null cells / total cells)
      - `is_single_column: Boolean` (n_cols == 1 && n_rows > 3)
      - `is_single_row: Boolean` (n_rows == 1 && n_cols > 3)
      - `column_collapse: Boolean` (from detect_column_collapse logic)
      - `header_collapse: Boolean` (from detect_header_collapse logic)
    - Reference: `/home/graham/workspace/experiments/extractor/src/extractor/pipeline/utils/tables/metrics.py` (`generate_pandas_metrics`)
    - Add `#[cfg(test)]` Rust unit tests
  - **Definition of Done**:
    - Test: `cargo test test_table_integrity_metrics`
    - Assertion: Returns correct shape, density, and collapse flags for test grids
    - Assertion: Output DataFrame has exactly 8 columns with correct dtypes

### P2: Python Integration (Sequential after P1)

- [x] **Task 5**: Wire Rust validation into Python `Table` construction
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 2, Task 3, Task 4b, Task 4c
  - **Details**:
    - In `models.py`, optionally call `extract_tables_rs.validate_grid()` when constructing `_data`
    - In `models.py`, optionally call `extract_tables_rs.validate_cells()` when cells are set
    - Call `extract_tables_rs.table_integrity_metrics()` after grid validation and store as `Table._integrity`
    - Call `extract_tables_rs.detect_column_collapse()` and `detect_header_collapse()` — if either returns true, log a warning
    - Guard with `try/except ImportError` so pure-Python fallback works if Rust module unavailable
    - Store the validated `PyDataFrame` as `_df` on the Table, avoiding double-conversion
    - **Do NOT change the public API** — this is internal plumbing
  - **Definition of Done**:
    - Test: `python -m pytest tests/ -x` — all 13 skill tests pass
    - Test: Benchmark script shows same accuracy numbers as before
    - Assertion: `Table._df` is a Polars DataFrame built in Rust when available
    - Assertion: `Table._integrity` contains data_density and collapse flags when Rust available

- [x] **Task 6**: Wire `compute_accuracy_rs` into Python metric
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 4, Task 5
  - **Details**:
    - In `metrics.py`, try `extract_tables_rs.compute_accuracy_rs()` first, fall back to Python
    - Ensure identical results for all 8 benchmark PDFs
    - Add a simple speed comparison print for development (removed later)
  - **Definition of Done**:
    - Test: Benchmark shows identical accuracy for all 8 PDFs
    - Assertion: Rust path produces same accuracy ±0.01 as Python path for every test PDF

### P3: Integration Tests + Benchmarks (After P2)

- [x] **Task 7**: End-to-end validation and performance benchmark
  - Agent: general-purpose
  - Parallel: 3
  - Dependencies: Task 5, Task 6
  - **Details**:
    - Run full benchmark on all 8 test PDFs — verify no regressions
    - Run full Camelot test suite (110 tests) — verify no regressions
    - Run extract-tables skill tests (13 tests) — verify no regressions
    - Verify `Table._integrity` metrics are populated for all 8 benchmark PDFs
    - Verify column/header collapse detection returns `false` for all 8 benchmark PDFs (none are collapsed)
    - Add a new test: extract a 50+ page PDF and time it with/without Rust validation
    - Document performance difference in task output
  - **Definition of Done**:
    - Test: All existing tests pass (Camelot: 110, skill: 13)
    - Test: Benchmark shows identical accuracy for all 8 PDFs
    - Test: All 8 PDFs have `data_density > 0.5` and no collapse flags
    - Assertion: Rust validation path is ≥2x faster than Python for 50+ page PDF
    - Assertion: No accuracy regressions from Rust integration

## Completion Criteria

- [x] All sanity scripts pass
- [x] All tasks marked [x]
- [x] All Definition of Done tests pass
- [x] No regressions in existing tests (Camelot 110 + skill 13)
- [x] Benchmark accuracy identical across all 8 test PDFs

## Notes

- **pyo3-polars version**: Use 0.19.x which targets PyO3 0.23 (matching existing Cargo.toml)
- **Polars features**: Start with `["dtype-struct", "lazy"]`. Add more as needed.
- **Backward compatibility**: All Rust functions are optional — pure Python fallback must work
- **Future phase**: Move `_assign_text_to_cells` and `_build_data_grid` to Rust (not in this plan)
- **Column naming**: Use `col_0`, `col_1`, etc. for grid DataFrames; keep first-row-as-headers in Python layer
- **Match to schema**: Polars `df.match_to_schema()` (unstable) can enforce schema evolution; use explicit `Schema` construction instead for stability
- **pyo3-polars pattern**: Use `PyDataFrame` wrapper — it implements `FromPyObject` and `IntoPy` automatically:
  ```rust
  use pyo3_polars::PyDataFrame;

  #[pyfunction]
  fn my_function(pydf: PyDataFrame) -> PyResult<PyDataFrame> {
      let df: DataFrame = pydf.into();
      // work with native Polars DataFrame
      Ok(PyDataFrame(df))
  }
  ```
