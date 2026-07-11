# docs/standards/rust-specifics.md
# Rust-Specific Design Standards

> **Scope:** Rust language applications of the principles in `docs/standards/ousterhout.md` and
> `docs/standards/readable-code.md`. This file does not repeat those principles — it shows how they
> manifest in Rust idioms and what Rust-specific violations look like.  
> **Usage:** Load this file for all Rust implementation work, alongside whichever of
> the parent standards files is relevant to the task.

---

## Part I — The Type System as Design Tool

Rust's type system is the primary mechanism for Ousterhout's "define errors out of
existence" and for information hiding. These are not suggestions — they are the
first-line tool before runtime validation or documentation.

---

### Rule: Use Newtypes to Encode Meaning, Not Just Wrapping

A newtype is only justified if it enforces an invariant, restricts an interface, or
makes distinct things that share a representation distinguishable. A newtype that adds
no constraint is a Shallow Module (see `docs/standards/ousterhout.md`).

```rust
// UNJUSTIFIED: wraps String, adds nothing
pub struct ProjectName(pub String);

// JUSTIFIED: enforces non-empty, restricted character set, max length
pub struct ProjectName(String);
impl ProjectName {
    pub fn new(raw: &str) -> Result<Self, InvalidProjectName> {
        if raw.is_empty() || raw.len() > 64 {
            return Err(InvalidProjectName::BadLength(raw.len()));
        }
        if raw.contains(|c: char| !c.is_ascii_alphanumeric() && c != '-' && c != '_') {
            return Err(InvalidProjectName::InvalidCharacters);
        }
        Ok(Self(raw.to_owned()))
    }
    pub fn as_str(&self) -> &str { &self.0 }
}
```

**Also justified:** newtypes that prevent confusing values that share a representation.
```rust
// Without newtypes: easy to accidentally pass user_id where deposit_id is expected
fn upload_file(deposit_id: &str, filename: &str) -> Result<(), PublishError>;

// With newtypes: the compiler catches transpositions
fn upload_file(deposit_id: &DepositId, filename: &FileName) -> Result<(), PublishError>;
```

---

### Rule: Use the Type-State Pattern for Lifecycle Phases

When a type has lifecycle phases where some operations are only valid in certain phases,
encode the phase in the type. This is Ousterhout's "define errors out of existence"
applied to temporal constraints (see also: Red Flag: Conjoined Methods).

```rust
// RUNTIME ERROR: calling publish before uploading files
pub struct Deposit {
    id: String,
    files_uploaded: bool,  // runtime flag — wrong tool
}
impl Deposit {
    pub fn publish(&self) -> Result<(), PublishError> {
        if !self.files_uploaded { return Err(PublishError::NoFiles); }
        // ...
    }
}

// COMPILE-TIME ENFORCEMENT: invalid sequences cannot compile
pub struct Draft;
pub struct Uploaded;

pub struct Deposit<State> {
    id: DepositId,
    _state: std::marker::PhantomData<State>,
}

impl Deposit<Draft> {
    pub fn upload_file(self, file: &[u8]) -> Result<Deposit<Uploaded>, PublishError>;
}

impl Deposit<Uploaded> {
    pub fn publish(self) -> Result<PublishedDeposit, PublishError>;
    // upload_file not available in Uploaded state
}
```

Use type-state when: (a) there are exactly 2–4 states, (b) the state transitions are
linear or tree-shaped, (c) calling a method in the wrong state is always a programming
error. Do not use type-state for runtime-variable states or states that depend on
external data.

---

### Rule: Prefer Enums Over Boolean Parameters

A boolean parameter at a call site is a Nonobvious Code smell (see `docs/standards/ousterhout.md`).
The reader sees `true` or `false` with no context. An enum is self-documenting at the
call site.

```rust
// NONOBVIOUS: what does true mean?
publish(config, true, false);

// SELF-DOCUMENTING:
publish(config, Target::Sandbox, Confirm::Draft);

// SIMPLE CASE: if there's only one boolean and its name is at the call site, it may
// be acceptable — use judgment
let report = check_project(&ctx, SkipHistory(true));
// This is borderline; prefer an options struct for 2+ booleans
```

**The rule for function parameters:** Any function with two or more boolean parameters
must use an options struct or an enum. One boolean parameter is acceptable only if its
name makes the meaning unambiguous at every call site.

---

### Rule: Use `#[non_exhaustive]` for Public Enums That Will Grow

Public enums that represent extensible sets (error categories, check result types,
supported ecosystems) should be marked `#[non_exhaustive]` to allow adding variants
without breaking downstream code. Do not mark enums as `#[non_exhaustive]` if they
are intended to be exhaustively matched — that would defeat the purpose of the enum.

```rust
// CORRECT: check categories will grow in v2+
#[non_exhaustive]
pub enum CategoryName {
    Git, Files, Citation, Security, Gitignore, Size, Joss,
}

// INCORRECT: these states are definitionally exhaustive; non_exhaustive would
// prevent callers from writing complete match expressions
pub enum CheckStatus { Pass, Warn, Fail }  // no #[non_exhaustive]
```

---

## Part II — Error Handling

---

### Rule: Library Crates Use `thiserror`; Binary Crates Use `anyhow`

This is a hard rule, not a preference.

- **Library crates** define structured error types with `thiserror`. Each variant carries
  enough context to diagnose the problem without reading source code. Callers can match
  on specific variants to handle recoverable errors.
- **Binary crates** (`mint-cli`) use `anyhow` for application-level propagation where
  the error will be presented to a user, not matched programmatically.

```rust
// LIBRARY CRATE (mint-meta): structured, matchable, informative
#[derive(Debug, thiserror::Error)]
pub enum MetaError {
    #[error("CITATION.cff not found at {path}")]
    NotFound { path: String },

    #[error("invalid YAML in {path}: {message}")]
    InvalidYaml { path: String, message: String },

    #[error("missing required field '{field}' in CITATION.cff")]
    MissingField { field: &'static str },

    #[error("invalid ORCID URI '{uri}': must start with https://orcid.org/")]
    InvalidOrcid { uri: String },
}

// BINARY CRATE (mint-cli): propagates with context added at each layer
fn run_check(project_dir: &Path) -> anyhow::Result<()> {
    let ctx = build_context(project_dir, config)
        .context("failed to analyse project directory")?;
    // ...
}
```

---

### Rule: Error Variants Must Carry Diagnosis-Enabling Context

An error message that says "parse failed" is useless. The reader cannot diagnose it
without reading source code. Every error variant must name the file, the field, the
value, or the constraint that was violated.

```rust
// USELESS: cannot diagnose without a debugger
#[error("validation failed")]
ValidationFailed,

// DIAGNOSABLE: tells you exactly what failed and where
#[error("field '{field}' in {file} has value '{value}' but must match {pattern}")]
FieldValidationFailed {
    field: &'static str,
    file: String,
    value: String,
    pattern: &'static str,
},
```

---

### Rule: Never Use `.unwrap()` Without a Safety Comment

`.unwrap()` on `Option` or `Result` panics at runtime. In library code, panics are
never acceptable for recoverable errors. The only permitted uses of `.unwrap()` are
where the panic is logically impossible and that fact is documented:

```rust
// FORBIDDEN in library code
let name = config.name.unwrap();

// PERMITTED: logically impossible case, documented
let first = segments.first()
    .expect("segments is non-empty: split_once matched, guaranteeing at least two parts");

// PERMITTED in tests (not library code)
#[test]
fn parses_valid_orcid() {
    let result = parse_orcid("https://orcid.org/0000-0002-1234-5678").unwrap();
    assert_eq!(result.as_str(), "https://orcid.org/0000-0002-1234-5678");
}
```

`.expect()` is preferred over `.unwrap()` in all cases where a panic is genuinely
justified — the message documents the invariant.

---

### Rule: `?` Should Be the Primary Error Propagation Mechanism

Avoid `match` on `Result` just to return `Err` — use `?` with `.map_err()` if the
error type needs conversion. Reserve explicit `match` for cases where the `Ok` and
`Err` branches have genuinely different handling logic.

```rust
// VERBOSE: match just to propagate
let content = match fs::read_to_string(&path) {
    Ok(c) => c,
    Err(e) => return Err(MetaError::FileRead { path: path.display().to_string(), source: e }),
};

// IDIOMATIC: map_err then ?
let content = fs::read_to_string(&path)
    .map_err(|e| MetaError::FileRead { path: path.display().to_string(), source: e })?;
```

---

## Part III — Trait Design

---

### Rule: Do Not Define a Trait Without Multiple Implementors

A trait with one implementor is indirection without benefit. It adds a layer of dynamic
dispatch (or generic complexity) that contributes nothing to information hiding and
makes the code harder to follow. Use a concrete type until a second implementor exists
or is definitively planned.

**The one exception:** Traits used for test mocking. A trait that has exactly two
implementors — the real HTTP client and a mock client — is justified by the testing
requirement. This is the standard Rust pattern for testable external I/O.

```rust
// UNJUSTIFIED: only one implementor, no test-mock need
pub trait ArchiveWriter {
    fn write(&mut self, path: &Path, data: &[u8]) -> io::Result<()>;
}
pub struct DiskArchiveWriter;
impl ArchiveWriter for DiskArchiveWriter { ... }
// → Delete the trait, use DiskArchiveWriter directly.

// JUSTIFIED: real and mock implementors
pub trait ZenodoClient {
    fn create_draft(&self, ...) -> Result<DepositId, PublishError>;
    fn upload_file(&self, ...) -> Result<(), PublishError>;
    fn publish_draft(&self, ...) -> Result<Doi, PublishError>;
}
pub struct HttpZenodoClient;     // production
pub struct MockZenodoClient;     // tests
```

---

### Rule: Traits Should Be Narrow

A trait that combines unrelated capabilities is a violation of the single-responsibility
principle at the interface level. Narrow traits are more composable and easier to mock.

```rust
// TOO WIDE: combines reading, writing, and querying
pub trait Repository {
    fn find_by_id(&self, id: &Id) -> Option<Record>;
    fn save(&mut self, record: Record) -> Result<(), DbError>;
    fn count(&self) -> usize;
    fn delete(&mut self, id: &Id) -> Result<(), DbError>;
}

// NARROWER: separate reading from writing (if callers only need one)
pub trait RecordReader {
    fn find_by_id(&self, id: &Id) -> Option<Record>;
    fn count(&self) -> usize;
}
pub trait RecordWriter {
    fn save(&mut self, record: Record) -> Result<(), DbError>;
    fn delete(&mut self, id: &Id) -> Result<(), DbError>;
}
```

Apply the narrowing only if callers actually differ in which capabilities they need.
If every caller uses all four methods, a narrow split adds abstraction without value.

---

### Rule: Avoid Premature Generics

Generic type parameters ("generics for flexibility") are often added speculatively and
almost always at the wrong time. Every generic parameter adds mental overhead for every
reader. Start concrete; generalise when a second concrete use case exists and the
generalisation simplifies the overall design.

```rust
// PREMATURE: generic for flexibility that no second use case requires
pub fn build_archive<W: Write + Seek>(config: &ArchiveConfig, writer: W)
    -> Result<ArchiveBundle, ArchiveError>;

// CONCRETE: writes to a Vec<u8> in memory; caller decides what to do with the bytes
pub fn build_archive(config: &ArchiveConfig) -> Result<ArchiveBundle, ArchiveError>;
// If a streaming-to-disk variant is needed later, add it then.
```

---

## Part IV — Naming Conventions (Rust-Specific)

These extend the general naming rules in `docs/standards/readable-code.md` with Rust-specific patterns.

---

### Rule: Conversion Methods Follow Standard Naming

| Pattern | Meaning | Example |
|---|---|---|
| `as_xxx()` | Cheap borrow, no allocation | `as_str()`, `as_bytes()` |
| `to_xxx()` | Potentially expensive, may allocate | `to_string()`, `to_owned()` |
| `into_xxx()` | Consumes self, transfers ownership | `into_string()`, `into_bytes()` |
| `from_xxx(x)` | Construct from x, associated fn | `from_str()`, `from_path()` |
| `try_from_xxx(x)` | Fallible construction | `try_from_str()` |

Violating these conventions causes readers to misunderstand the cost and ownership
semantics of a call.

---

### Rule: Builder Methods Return `Self` and Use Method Chaining Style

Builder-pattern methods that set optional configuration should return `Self` for
chaining. Do not use `&mut self` returning `()` for builder methods — this forces
callers to use imperative mutation syntax.

```rust
// IMPERATIVE BUILDER: inconsistent with standard Rust conventions
let mut config = ArchiveConfig::new(path);
config.set_output_dir(output);
config.set_tag("v1.0.0");

// CHAINING BUILDER: idiomatic Rust
let config = ArchiveConfig::new(path)
    .with_output_dir(output)
    .with_tag("v1.0.0");
```

Use the builder pattern only when a struct has three or more optional fields.
For structs with two or fewer optional fields, plain constructors are simpler.

---

### Rule: `new()` Is Always Infallible; Use `try_new()` or a Named Constructor for Fallible Construction

```rust
// WRONG: new() that can fail violates the convention
pub fn new(raw: &str) -> Result<Self, InvalidOrcid>;

// CORRECT: named fallible constructor
pub fn parse(raw: &str) -> Result<Self, InvalidOrcid>;
// or:
pub fn try_new(raw: &str) -> Result<Self, InvalidOrcid>;

// CORRECT: infallible new
pub fn new(value: String) -> Self;  // no validation, guaranteed to succeed
```

---

### Rule: Test Function Names Describe Behaviour, Not Implementation

Test names should read as specifications: "given X, when Y, then Z". They should
describe the observable behaviour being verified, not the internal mechanism.

```rust
// IMPLEMENTATION-FOCUSED (bad): what the test does
#[test] fn test_parse_function() { ... }
#[test] fn test_orcid_regex() { ... }

// BEHAVIOUR-FOCUSED (good): what the test proves
#[test] fn parse_citation_returns_err_for_missing_required_fields() { ... }
#[test] fn orcid_without_https_scheme_is_rejected() { ... }
#[test] fn version_mismatch_between_cff_and_git_tag_is_a_fail() { ... }
```

---

## Part V — Module Organisation

---

### Rule: `pub(crate)` Is the Default Visibility for Non-Public Items

In any library crate, the default visibility for items that are used within the crate
but not by external callers should be `pub(crate)`, not `pub`. `pub` is a commitment —
it extends the item into the public API, constrains future changes, and requires a doc
comment. Reserve `pub` for items that are genuinely part of the crate's external
contract.

```rust
// OVER-EXPOSED: pub on an internal helper
pub fn compute_archive_entry_path(root: &Path, file: &Path) -> PathBuf { ... }

// CORRECTLY SCOPED:
pub(crate) fn compute_archive_entry_path(root: &Path, file: &Path) -> PathBuf { ... }
```

---

### Rule: Tests Live Co-Located in the Same File

Unit tests for a function live in a `#[cfg(test)] mod tests` block at the bottom of
the same file as the function. Property tests live in a separate `#[cfg(test)] mod
proptests` block in the same file. Integration tests live in `tests/` at the crate root.

```
src/
  meta/
    parse.rs          ← parse_citation + mod tests { } + mod proptests { }
    codemeta.rs       ← to_codemeta + mod tests { }
    bibtex.rs         ← to_bibtex + mod tests { }
tests/
  integration.rs      ← full end-to-end via CLI subprocess
```

Do not create separate `tests/unit/` directories for unit tests. Co-location makes
the relationship between code and test visible and ensures they are updated together.

---

## Part VI — The Rust Standards Checklist

Apply after writing any non-trivial Rust code in a session.

**Types:**
- [ ] Does every newtype enforce an invariant or prevent type confusion?
- [ ] Are there any lifecycle phases that should be encoded as type-state?
- [ ] Are there boolean function parameters that should be enums or option structs?
- [ ] Are public enums that will grow marked `#[non_exhaustive]`?

**Errors:**
- [ ] Does this crate use `thiserror` (library) or `anyhow` (binary), not both?
- [ ] Does every error variant carry enough context to diagnose without reading source?
- [ ] Are there any `.unwrap()` calls without a safety comment?
- [ ] Is `?` used consistently for propagation, with `.map_err()` for type conversion?

**Traits:**
- [ ] Does every trait have at least two implementors (or one real + one mock)?
- [ ] Is every trait as narrow as it can be while still serving its callers?
- [ ] Are there any generic parameters that have only one concrete instantiation?

**Naming:**
- [ ] Do conversion methods follow `as_/to_/into_/from_` conventions?
- [ ] Is `new()` infallible? Are fallible constructors named `parse()` or `try_new()`?
- [ ] Do test names describe behaviour, not implementation?

**Organisation:**
- [ ] Is `pub(crate)` used for all intra-crate items that are not public API?
- [ ] Are unit tests co-located in the same file as the code they test?
- [ ] Is there a module-level `//!` doc comment explaining the module's role?
