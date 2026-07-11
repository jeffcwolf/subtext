# Skill: review-testing

> **When to invoke:** At the end of every session that added or modified functionality.
> Also invoke when preparing a project for release or portfolio presentation, and as
> part of the v1.0 gate.
> **Load:** `docs/standards/rust-specifics.md` Part IV (test names), Part V (test organisation).
> For Python projects, load `docs/standards/python-specifics.md` testing and organisation sections.

---

## What This Skill Checks

The test suite is a machine-executable specification of the project's behaviour. A
reader — human or agent — should be able to read the test names alone and understand
what the software guarantees. Agent-generated tests fail this standard in predictable
ways: they test happy paths, they assert `is_ok()` without checking the value, they
duplicate each other with cosmetic variations, and they name themselves after
implementation details rather than behaviour.

This skill checks four things:

1. **Existence** — do tests exist for all public contracts?
2. **Correctness** — do the tests actually verify what they claim to?
3. **Quality** — are the tests testing behaviour, not implementation?
4. **Organisation** — are the tests where a reader expects to find them?

---

## Procedure

### Step 1 — Run the full test suite and record the baseline

Every failure is a blocker. Fix before proceeding to any other step.

**Rust:**
```bash
cargo test --workspace 2>&1
```

**Python:**
```bash
uv run pytest --tb=short -q 2>&1
```

Record: total tests, passed, failed, skipped. A project with zero tests is a finding
in itself — skip to Step 6 (organisation), set up the structure, then return to Step 2.

A project with only ignored or skipped tests is the same finding. Skipped tests that
have been skipped for more than one session should be either fixed or deleted.

---

### Step 2 — Measure coverage as a diagnostic

Coverage is not a target. Do not chase a percentage. Use it to find **untested public
functions** — those are the real failures, not uncovered internal lines.

**Rust:**
```bash
cargo tarpaulin --workspace --out stdout 2>&1 | tail -30
```
If `tarpaulin` is not installed, `cargo install cargo-tarpaulin` first. On projects
where tarpaulin has compatibility issues, `cargo llvm-cov` is an alternative.

**Python:**
```bash
uv run pytest --cov=src --cov-report=term-missing -q 2>&1
```
If `pytest-cov` is not installed, `uv add --dev pytest-cov`.

**What to record:**
- Overall percentage (informational only)
- List of **public functions with 0% coverage** — these are the actionable findings
- Any modules with no test coverage at all

Do not add tests to chase coverage numbers. Add tests to verify contracts (Step 3).

---

### Step 3 — Contract coverage audit

This is the most important step. For every public function, check whether its
documented contract has a corresponding test.

**For every public function that returns `Result` or `Option` (Rust), or that raises
exceptions (Python):**

- [ ] Is there at least one test for the success path that checks the returned value,
      not just that it didn't error?
- [ ] Is there at least one test for **each** documented error condition?
- [ ] Does each error-path test verify the **specific** error variant or exception type,
      not just "it errors"?

**Cross-reference with `review-docs`:** if a doc comment or docstring lists three
error conditions, there must be three tests that trigger them. A documented contract
that no test verifies is worse than no documentation — it creates false confidence.

```rust
// Doc comment promises three error conditions:
/// # Errors
/// Returns `MetaError::NotFound` if the file does not exist.
/// Returns `MetaError::InvalidYaml` if the file is not valid YAML.
/// Returns `MetaError::MissingField` if a required field is absent.
pub fn parse_citation(path: &Path) -> Result<CitationMetadata, MetaError>;

// Therefore the test module must contain at minimum:
#[test] fn parse_citation_returns_not_found_for_missing_file() { ... }
#[test] fn parse_citation_returns_invalid_yaml_for_malformed_input() { ... }
#[test] fn parse_citation_returns_missing_field_when_title_absent() { ... }
// Plus at least one success-path test:
#[test] fn parse_citation_returns_metadata_for_valid_cff() { ... }
```

**For functions that accept input — collections, strings, paths, numeric values:**

- [ ] Is the empty/zero/None case tested?
- [ ] Is at least one boundary condition tested (first element, last element, max
      value, minimum valid input)?
- [ ] Is at least one invalid input tested?

Not every function needs exhaustive boundary testing. Apply judgement: the more public
the function and the more complex its input space, the more boundary coverage it needs.
A private helper called from one place needs less than a public API entry point.

---

### Step 4 — Test name audit

Scan every test function name in the project. Each name must describe **observable
behaviour**, not implementation details.

**Failing patterns:**
```
test_parse              — what about parsing?
test_validation         — what is validated? what is the expected outcome?
test_function_name      — repeats the function name, says nothing about behaviour
test_error_handling     — which error? under what conditions?
test_basic              — nothing is communicated
```

**Passing patterns:**
```
parse_citation_returns_err_for_missing_title
empty_input_produces_empty_output
upload_to_nonexistent_bucket_returns_connection_error
invalid_orcid_without_https_scheme_is_rejected
config_with_no_api_key_falls_back_to_env_var
```

**The specification test:** read only the test names, without reading the test bodies.
Can you understand what the software guarantees? If a test name requires reading the
body to understand what it checks, rename it.

**Rust-specific:** test names should not start with `test_`. The `#[test]` attribute
already marks them as tests. Starting with `test_` wastes the most informative word
position.

**Python-specific:** test names must start with `test_` (pytest convention), but the
remainder should describe behaviour: `test_parse_citation_rejects_missing_title`,
not `test_parse_1`.

---

### Step 5 — Test quality scan

For each test, check for these common agent-generated failures:

**5a — Tests that assert nothing meaningful:**
```rust
// USELESS: asserts construction, not behaviour
#[test]
fn creates_config() {
    let config = Config::new(path);
    assert!(config.is_ok());  // does not check the value
}

// MEANINGFUL: asserts the contract
#[test]
fn config_from_valid_path_contains_expected_fields() {
    let config = Config::new(path).unwrap();
    assert_eq!(config.output_dir(), expected_output);
    assert_eq!(config.project_name(), "my-project");
}
```

**5b — Tests that are duplicates with different variable names:**
If two tests exercise the same code path with cosmetically different inputs and the
same assertions, they are one test. Delete the duplicate. If the inputs represent
meaningfully different categories (valid ASCII vs. valid Unicode, small file vs. large
file), they are different tests — but make the category explicit in the name.

**5c — Tests that depend on execution order:**
Each test must be independent. No test should rely on state left by a previous test.
In Rust, `cargo test` runs tests in parallel by default — order-dependent tests will
fail intermittently. In Python, `pytest` does not guarantee order either.

**5d — Tests that test implementation, not behaviour:**
A test that asserts on internal data structures, private fields, or the number of
times an internal function was called is testing implementation. When the
implementation changes, these tests break even though the behaviour is unchanged.

```rust
// IMPLEMENTATION TEST: breaks if internal storage changes from Vec to HashMap
#[test]
fn stores_entries_in_order() {
    let store = Store::new();
    store.add("a");
    store.add("b");
    assert_eq!(store.entries[0], "a");  // directly accessing internal field
}

// BEHAVIOUR TEST: survives any internal change that preserves the contract
#[test]
fn entries_are_retrievable_after_insertion() {
    let store = Store::new();
    store.add("a");
    store.add("b");
    assert!(store.contains("a"));
    assert!(store.contains("b"));
}
```

**5e — Tests that test the language or framework:**
A test that verifies `Vec::push` adds an element, or that `json.loads` parses valid
JSON, is testing the standard library. Delete it.

---

### Step 6 — Test organisation check

**Rust:**
- [ ] Unit tests are in `#[cfg(test)] mod tests` at the bottom of the source file
      they test — not in a separate `tests/unit/` directory
- [ ] Integration tests are in `tests/` at the crate root
- [ ] No unit tests have migrated to `tests/` (they belong with the code they test)
- [ ] No integration-style tests are inside `mod tests` blocks (if they require
      the binary or external state, they belong in `tests/`)
- [ ] Property tests, if present, are in a separate `#[cfg(test)] mod proptests`
      block in the same file as the code they test
- [ ] Test helper functions shared across multiple test modules are in a
      `tests/common/mod.rs` or a `#[cfg(test)]` helper module, not duplicated

**Python:**
- [ ] Tests mirror the source structure: `src/module.py` → `tests/test_module.py`
- [ ] All test files use the `test_` prefix
- [ ] Shared fixtures are in `conftest.py`, not duplicated across test files
- [ ] No test logic in `__init__.py`
- [ ] Test data (fixture files, sample inputs) is in a `tests/data/` or
      `tests/fixtures/` directory, not scattered

---

### Step 7 — The "missing test" pass

This is the final check, applied after all other steps. Go through the project's
public API surface one more time and ask: **if I deleted the implementation of this
function and replaced it with `todo!()` or `raise NotImplementedError`, would any
test fail?**

If the answer is no for any public function, that function is untested regardless
of what the coverage report says. A test that calls the function as part of a larger
integration flow does not count — the function must have a test that isolates its
specific behaviour.

Exceptions:
- Trivial accessor methods (`fn as_str(&self) -> &str` on a newtype) do not need
  dedicated tests if they are exercised as part of other tests
- Functions whose only purpose is to coordinate other tested functions (orchestrators)
  may be covered by integration tests rather than unit tests
- Functions that require external state (network, database, filesystem) that cannot be
  reasonably mocked — document this: `// Tested in integration tests: tests/integration.rs`

---

### Step 8 — Record in session log

In the `<project>/SESSIONS.md` entry for this session, add a "Testing Review" section:
```
**Testing Review:**
- Test suite: [X passed, Y failed, Z skipped]
- Coverage: [X% overall; untested public functions: list or "none"]
- Contract gaps: [none / list of functions missing error-path tests]
- Name fixes: [count renamed, or "none"]
- Quality issues: [none / list of findings and fixes]
- Organisation fixes: [none / list]
- Missing tests added: [count, or "none needed"]
```
