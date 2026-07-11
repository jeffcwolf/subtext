# docs/standards/ousterhout.md
# A Philosophy of Software Design — Executable Rules

> **Source:** John Ousterhout, *A Philosophy of Software Design* (2nd ed.)  
> **Scope:** Design-level rules — modules, interfaces, abstractions, APIs.  
> **Usage:** Load this file when designing a new module, reviewing an existing one,
> or auditing code after a session. For expression-level rules (naming, comments,
> control flow), see `docs/standards/readable-code.md`. For Rust-specific applications,
> see `docs/standards/rust-specifics.md`.
>
> **Format:** Each rule has a definition, a detection method, a Rust violation, and
> a Rust correction. The Red Flags section follows the same format. A Red Flag is a
> symptom — a pattern in code that signals a design problem. When you see a Red Flag,
> stop and redesign before continuing.

---

## Part I — Core Principles

---

### Principle 1: Deep Modules

**Definition:** A module is deep if it hides significant complexity behind a simple
interface. Depth = (complexity concealed) / (interface complexity). The higher the
ratio, the deeper the module.

**Detection:**
- Write down every public function/method signature. This is the interface.
- Estimate the lines of non-trivial logic that a caller would have to reimplement
  without this module. This is the concealed complexity.
- If the interface is nearly as complex as what it hides, the module is shallow.
- Ask aloud: "What does a caller NOT need to know because this module exists?"
  If the list is short, the module is shallow.

**Violation:**
```rust
pub struct FileReader {
    path: PathBuf,
}

impl FileReader {
    pub fn new(path: PathBuf) -> Self { Self { path } }
    pub fn read_to_string(&self) -> Result<String, io::Error> {
        fs::read_to_string(&self.path)
    }
}
```
This wraps one standard library call with no transformation, no error enrichment,
no caching, no validation. The interface complexity equals the implementation
complexity. It is maximally shallow.

**Correction:**
```rust
/// Reads and caches configuration files, resolving platform-specific search paths
/// and providing structured error context.
pub struct ConfigReader {
    search_paths: Vec<PathBuf>,
    cache: HashMap<PathBuf, Arc<str>>,
}

impl ConfigReader {
    /// Search for `filename` in all configured paths, return the first match.
    /// Caches results so repeated reads do not hit the filesystem.
    pub fn read(&mut self, filename: &str) -> Result<Arc<str>, ConfigError>;
}
```
Now the module hides: path search logic, caching, error enrichment. The interface
(one method) is far simpler than the hidden complexity.

---

### Principle 2: Information Hiding

**Definition:** Every module should hide implementation details from its callers.
Callers should need to know only what the module's interface promises — not how it
delivers that promise. The moment an internal representation leaks through the public
interface, the module's implementation is frozen: changing it breaks callers.

**Detection:**
- Does the return type of a public function expose an internal data structure?
- Does a public function accept a type that only makes sense if you know the
  implementation?
- Can a caller construct the module's internal state directly, bypassing validation?
- Does a doc comment explain how something is implemented rather than what it
  guarantees?

**Violation:**
```rust
pub struct TokenStore {
    pub tokens: HashMap<UserId, Vec<Token>>,  // internal representation exposed
}

pub fn get_active_tokens(store: &TokenStore, user: UserId) -> Vec<Token> {
    store.tokens.get(&user)
        .map(|ts| ts.iter().filter(|t| !t.expired()).cloned().collect())
        .unwrap_or_default()
}
```
The `HashMap<UserId, Vec<Token>>` is now the public API. If the storage changes
to a database or a BTreeMap, every caller breaks.

**Correction:**
```rust
pub struct TokenStore { ... }  // internal representation hidden

impl TokenStore {
    /// Return all non-expired tokens for the given user.
    pub fn active_tokens(&self, user: &UserId) -> Vec<&Token>;
}
```
The interface promises behaviour, not structure. The implementation can change freely.

---

### Principle 3: General-Purpose Modules

**Definition:** Modules should be slightly more general than the immediate use case
demands. A module that is precisely shaped to its first caller is brittle — it will
require changes the moment a second caller appears with a slightly different need.
Design the module to handle the class of problems, not the specific instance.

**Detection:**
- Would a second, slightly different caller need to call private functions or
  duplicate logic?
- Does the module's API have parameters that only make sense for the current caller?
- Does the module name describe a specific feature rather than a capability?

**Violation:**
```rust
/// Saves a user profile to the database after a web form submission.
pub fn save_profile_from_form(conn: &DbConn, form: &ProfileForm) -> Result<(), DbError>;
```
The "from form" coupling means this can never be called from a CLI, an import job,
or a test without creating a fake `ProfileForm`.

**Correction:**
```rust
/// Persist a user profile. Callers are responsible for constructing a valid Profile.
pub fn save_profile(conn: &DbConn, profile: &Profile) -> Result<(), DbError>;
```
The module is now general enough to serve any caller that can produce a `Profile`.

---

### Principle 4: Different Layer, Different Abstraction

**Definition:** Each layer in a system should have a distinct vocabulary and operate
at a distinct level of abstraction. If adjacent layers use the same concepts, the same
names, and perform the same operations, the layering adds overhead without adding value.

**Detection:**
- Do two adjacent functions/modules use the same variable names and types?
- Does a function in layer N simply call a function in layer N-1 with the same
  arguments and the same semantics?
- Could you describe what layer N does in terms that are meaningfully different from
  how you describe layer N-1?

**Violation:**
```rust
// Layer 2
pub fn get_user_record(db: &Db, id: UserId) -> Result<UserRecord, DbError> {
    db.fetch_user_record(id)  // Layer 1 — same name, same type, same abstraction
}
```
Layer 2 adds nothing. It is a pass-through.

**Correction:**
```rust
// Layer 1: database vocabulary
fn fetch_row(db: &Db, table: &str, id: i64) -> Result<Row, DbError>;

// Layer 2: domain vocabulary
pub fn find_user(db: &Db, id: UserId) -> Result<User, UserError> {
    let row = fetch_row(db, "users", id.into())?;
    User::from_row(row).map_err(UserError::InvalidData)
}
```
Layer 2 translates between database primitives (`Row`, `i64`) and domain types
(`User`, `UserId`, `UserError`). Different abstraction, different vocabulary.

---

### Principle 5: Pull Complexity Downward

**Definition:** When a module could handle complexity itself or push it to its callers,
it should handle it. A simple interface is worth significant implementation complexity.
The caller should never have to understand the module's internal complexity in order
to use it correctly.

**Detection:**
- Does the caller have to perform setup, validation, or cleanup that logically belongs
  to the module?
- Is there a "correct call sequence" that the caller must follow?
- Do callers frequently duplicate the same pre-call or post-call logic?

**Violation:**
```rust
pub fn write_file(path: &Path, content: &[u8]) -> Result<(), io::Error>;
// Callers must always:
// 1. Check the parent dir exists
// 2. Create it if not
// 3. Call write_file
// 4. Sync the file to disk
// This sequence is never optional, so it belongs inside write_file.
```

**Correction:**
```rust
/// Write content to path, creating parent directories if needed.
/// Syncs to disk before returning. Returns Err if the write or sync fails.
pub fn write_file(path: &Path, content: &[u8]) -> Result<(), WriteError>;
```

---

### Principle 6: Strategic vs Tactical Programming

**Definition:** Tactical programming means solving the immediate problem as fast as
possible. Strategic programming means investing in a design that will make future
changes cheaper. The working code that takes 30% longer to write correctly is the right
investment; the quick hack that "we'll clean up later" is a debt that compounds.

**Detection (tactical drift warning signs):**
- A function is growing a third responsibility because "it's already in here"
- A type is gaining a field to "thread through" information it does not own
- A TODO comment is added instead of stopping to redesign
- A new flag parameter is added to an existing function to handle a new case

**The rule:** When you find yourself wanting to add a quick hack, stop. Identify the
minimal redesign that eliminates the hack. Implement the redesign first, then the
feature. If the redesign is too large for this session, raise it in the session log
as a design debt item — do not implement the hack.

---

### Principle 7: Define Errors Out of Existence

**Definition:** The best error handling is no error handling. Design APIs so that the
inputs that would cause errors cannot be expressed. Use the type system to make invalid
states unrepresentable rather than validating them at runtime and returning errors.

**Detection:**
- Is there a function that can only fail because the caller passed invalid input?
- Is there a runtime check that could have been a compile-time constraint?
- Does an error variant represent a caller mistake rather than an environmental failure?

**Violation:**
```rust
pub fn set_retry_count(count: i32) -> Result<(), ConfigError> {
    if count < 0 {
        return Err(ConfigError::NegativeRetryCount);
    }
    // ...
}
```
A negative retry count is a caller mistake, not an environmental failure. The type
system can make it impossible.

**Correction:**
```rust
pub fn set_retry_count(count: u32) {  // u32 cannot be negative — no error possible
    // ...
}
```

---

### Principle 8: Design It Twice

**Definition:** Before committing to a design, sketch at least two fundamentally
different alternatives. The first design is rarely optimal. The act of designing a
second alternative forces you to understand the tradeoffs and almost always reveals
improvements to both options. This applies to every non-trivial interface.

**Application in agentic sessions:**
Before an agent writes any new module's implementation, it should be explicitly asked:
"Propose two alternative designs for this interface. State the tradeoffs. Then
implement the better one." This step is easily skipped under time pressure and is the
single biggest source of avoidable design debt in agentic codebases.

---

## Part II — Red Flags

Each Red Flag is a specific code pattern that signals a design problem. When any Red
Flag appears, do not proceed. Identify the root cause and redesign.

---

### Red Flag: Shallow Module

**Signal:** A module, struct, or function whose public interface is nearly as complex
as its implementation. It is creating an abstraction without hiding significant
complexity.

**Rust patterns that are always shallow:**
- A struct that wraps a single field and forwards all methods unchanged
- A function whose entire body is a single call to another function
- A trait with one implementor that adds no behaviour over a concrete type
- A newtype with no validation, no invariants, and no restricted interface

```rust
// SHALLOW — wraps String, adds nothing
pub struct ProjectName(pub String);
impl ProjectName {
    pub fn new(s: String) -> Self { Self(s) }
    pub fn value(&self) -> &str { &self.0 }
}

// DEEP — wraps String, enforces invariant, hides validation
pub struct ProjectName(String);
impl ProjectName {
    /// Returns Err if the name is empty, longer than 64 characters,
    /// or contains characters outside [a-z0-9-_].
    pub fn new(raw: &str) -> Result<Self, InvalidProjectName>;
    pub fn as_str(&self) -> &str;
}
```

---

### Red Flag: Information Leakage

**Signal:** A design decision is reflected in two or more modules. A change to the
decision requires changes in multiple places. The most common form: the same data
structure or format appears in both the module that produces it and the module that
consumes it, with no abstraction separating them.

```rust
// LEAKS: the Vec<(String, String)> header format appears in both
// the HTTP parsing module and the auth module.
pub fn parse_headers(raw: &str) -> Vec<(String, String)>;
pub fn extract_bearer_token(headers: &Vec<(String, String)>) -> Option<&str>;

// FIXED: the HTTP module owns the header type
pub struct Headers(/* opaque */);
impl Headers {
    pub fn get(&self, name: &str) -> Option<&str>;
}
pub fn parse_headers(raw: &str) -> Headers;
pub fn extract_bearer_token(headers: &Headers) -> Option<&str>;
```

---

### Red Flag: Temporal Decomposition

**Signal:** A module's structure reflects the order in which operations happen rather
than the information they share or the complexity they hide. "First we read the config,
then we validate it, then we apply it" becomes three modules — but the three stages all
operate on the same data and have shared knowledge. They should be one module.

```rust
// TEMPORAL DECOMPOSITION: three modules that share detailed config knowledge
mod config_reader   { pub fn read(path: &Path) -> RawConfig; }
mod config_validator{ pub fn validate(c: &RawConfig) -> Result<(), ConfigError>; }
mod config_applier  { pub fn apply(c: &RawConfig) -> RuntimeConfig; }
// Every module knows RawConfig internals. A new field requires changes in all three.

// FIXED: one module that hides all three stages
mod config {
    /// Load, validate, and resolve config from the given path.
    pub fn load(path: &Path) -> Result<RuntimeConfig, ConfigError>;
}
```

---

### Red Flag: Overexposure

**Signal:** A module that is only needed by one other module is exported publicly,
making it part of the package's API. The caller count does not justify the exposure.

**In Rust:** If a type or function is `pub` but is only ever called from within the
same crate, it should be `pub(crate)`. If it is only called from within the same
module, it should be private. Visibility should be the minimum required.

```rust
// OVEREXPOSED: internal parsing type made public
pub struct RawCitationYaml { pub fields: HashMap<String, serde_yaml::Value> }

// CORRECT: internal type stays private; only the result is public
struct RawCitationYaml { ... }  // private
pub struct CitationMetadata { ... }  // public
pub fn parse_citation(path: &Path) -> Result<CitationMetadata, MetaError>;
```

---

### Red Flag: Pass-Through Methods

**Signal:** A method that does nothing except forward its arguments to another method
with the same signature. It adds a layer of indirection that contributes nothing to
the abstraction.

```rust
// PASS-THROUGH — this method adds nothing
impl ProjectManager {
    pub fn save_project(&self, p: &Project) -> Result<(), DbError> {
        self.repository.save_project(p)  // identical signature, no transformation
    }
}

// JUSTIFIED — this method adds transformation and owns coordination
impl ProjectManager {
    pub fn save_project(&self, p: &Project) -> Result<(), ProjectError> {
        self.validator.validate(p)?;
        self.repository.save(p).map_err(ProjectError::Storage)?;
        self.event_bus.publish(ProjectSaved { id: p.id() });
        Ok(())
    }
}
```

---

### Red Flag: Repetition

**Signal:** The same code pattern, logic, or sequence appears in multiple places. Each
copy must be maintained in sync. A bug fix in one copy is silently missed in the others.
This is not just a DRY concern — repeated code signals a missing abstraction that would
hide the repeated complexity behind a name.

**Detection in Rust:** If you see the same sequence of method calls on the same type
appearing in multiple functions, that sequence belongs in the type as a method. If the
same `match` arm logic appears in multiple match expressions, it belongs in a method on
the matched type.

---

### Red Flag: Special-General Mixture

**Signal:** A general-purpose module contains special-case logic for a specific caller.
The general module now knows about its caller — a dependency inversion. The caller
must understand the special-case conditions to use the module correctly.

```rust
// MIXED: the general archive builder has special logic for JOSS projects
pub fn build_archive(config: &ArchiveConfig, is_joss: bool) -> Result<ArchiveBundle, ArchiveError> {
    if is_joss {
        // JOSS-specific file inclusion logic here
    }
    // ...
}

// FIXED: general module is general; caller provides the policy
pub fn build_archive(config: &ArchiveConfig) -> Result<ArchiveBundle, ArchiveError>;
// Caller controls what files are included via ArchiveConfig
```

---

### Red Flag: Conjoined Methods

**Signal:** Two methods that can only be used correctly together and in a specific
order. The caller must know the required sequence — complexity that belongs inside the
module has leaked out.

```rust
// CONJOINED: must call begin() before write(), must call end() after
pub fn begin_transaction(&mut self);
pub fn write_record(&mut self, r: &Record) -> Result<(), DbError>;
pub fn end_transaction(&mut self) -> Result<(), DbError>;

// FIXED: the sequence is encapsulated
pub fn write_records(&mut self, records: &[Record]) -> Result<(), DbError>;
// Or with a closure to keep the transaction boundary explicit but safe:
pub fn in_transaction<F>(&mut self, f: F) -> Result<(), DbError>
where F: FnOnce(&mut Transaction) -> Result<(), DbError>;
```

---

### Red Flag: Comment Repeats Code

**Signal:** A comment describes what the code does in the same terms as the code
itself. Reading the comment adds zero information beyond reading the code. The
comment is not wrong — it is useless.

```rust
// BAD: comment restates the code
// Increment the counter by 1
counter += 1;

// BAD: doc comment restates the function name
/// Returns the user's name.
pub fn user_name(&self) -> &str { &self.name }

// GOOD: comment explains why, not what
// Rate-limit counter uses saturating add to avoid panicking under
// thundering-herd conditions where counts briefly overflow u32.
self.request_count = self.request_count.saturating_add(1);

// GOOD: doc comment explains the contract, not the implementation
/// The user's display name as entered during registration.
/// Guaranteed non-empty; at most 64 Unicode grapheme clusters.
pub fn display_name(&self) -> &str { &self.name }
```

---

### Red Flag: Implementation Documentation Contaminates Interface

**Signal:** A public-facing doc comment describes how the function works internally
rather than what it guarantees to callers. The caller now depends on implementation
details they should not know.

```rust
// BAD: exposes the implementation
/// Reads the CITATION.cff file by opening it with fs::read_to_string,
/// then parses it using serde_yaml::from_str into a CitationMetadata struct.
pub fn parse_citation(path: &Path) -> Result<CitationMetadata, MetaError>;

// GOOD: describes the contract
/// Parse and validate a CITATION.cff file at the given path.
/// Returns Err if the file is missing, not valid YAML, or fails CFF 1.2.x
/// schema validation (missing required fields, invalid ORCID format, etc.).
pub fn parse_citation(path: &Path) -> Result<CitationMetadata, MetaError>;
```

---

### Red Flag: Vague Name

**Signal:** A name that could apply to many different things in the codebase. Vague
names include: `Manager`, `Handler`, `Processor`, `Helper`, `Utils`, `Data`, `Info`,
`Item`, `Object`, `Thing`. Each of these names describes almost nothing.

```rust
// VAGUE
struct DataProcessor;
fn handle(input: &str) -> Result<(), Error>;
struct UserInfo { ... }

// PRECISE
struct CitationTransformer;
fn validate_orcid(uri: &str) -> Result<OrcidUri, InvalidOrcid>;
struct UserRegistration { ... }
```

---

### Red Flag: Hard to Describe

**Signal:** If you cannot describe what a module or function does in one or two
sentences without using the word "and", it has more than one responsibility and should
be split.

**Test:** Write the one-sentence module description. If you wrote "and", you found the
split point.

```
"This module parses CITATION.cff files and validates ORCID URIs and generates
CodeMeta output."
→ Three responsibilities. Split into: parser, ORCID validator, CodeMeta generator.
Or: keep them together if they all operate on the same data model (CitationMetadata)
and the "and" is a list of transformations on a single type, not unrelated domains.
```

---

### Red Flag: Nonobvious Code

**Signal:** Code whose behaviour cannot be understood by reading it once. The reader
must trace through multiple layers, hold global state in their head, or consult external
documentation to understand what will happen at runtime.

**Common causes in Rust:**
- A function that mutates a parameter that is passed by shared reference via interior
  mutability, where the mutation is not obvious from the call site
- A `Default` implementation that sets fields to non-obvious sentinel values
- A `From` or `Into` implementation that performs validation or can panic
- A boolean parameter where `true` and `false` have non-obvious meanings at the call site

```rust
// NONOBVIOUS: what does true mean here?
config.set_mode(true);

// OBVIOUS: the meaning is at the call site
config.set_mode(OperationMode::Sandbox);
```

---

## Part III — The Design Process Checklist

Apply this checklist when designing any new module, reviewing a pull request, or
auditing code after an agent session.

**Before writing implementation:**
- [ ] Can you state in one sentence what complexity this module hides?
- [ ] Have you designed at least two alternative interfaces? (Design it twice)
- [ ] Is every public item truly public — i.e., does it have at least two callers?
- [ ] Are there any error conditions that could be eliminated by type constraints?

**After writing implementation:**
- [ ] Does any public function leak internal types or structures?
- [ ] Does every function do one thing, describable without "and"?
- [ ] Is there any repeated logic that belongs in a new method?
- [ ] Does any module have temporal decomposition — stages that share data and should
  be merged?
- [ ] Are there any pass-through methods?
- [ ] Are there any conjoined methods that require a call sequence?

**Documentation:**
- [ ] Do doc comments describe contracts, not implementations?
- [ ] Does every public item have a doc comment that adds information beyond the name?
- [ ] Are non-obvious decisions explained with comments that say *why*, not *what*?
