# docs/standards/readable-code.md
# The Art of Readable Code — Executable Rules

> **Source:** Dustin Boswell & Trevor Foucher, *The Art of Readable Code* (2011)  
> **Scope:** Expression-level rules — names, comments, control flow, and individual
> functions. These operate below the design level: they govern how ideas are expressed
> in code, not whether the code is structured correctly.  
> **Compatibility:** Fully compatible with Ousterhout's APOSD. Where APOSD asks
> "is the structure right?", this book asks "is the surface right?" Both are required.  
> **Usage:** Load this file when reviewing names, writing or reviewing comments, or
> simplifying control flow. For design-level rules, see `docs/standards/ousterhout.md`.

---

## Part I — Names

The primary test for a name: **could it be misunderstood?** A name passes if no
reasonable reader would assign it a different meaning than the author intended.

---

### Rule: Choose Words That Cannot Be Misread

Prefer words that have one clear meaning in the domain over words that are slightly
ambiguous. The cost of a misread name is silent bugs or wasted reading time.

```rust
// AMBIGUOUS: "filter" can mean "keep matching" or "remove matching"
pub fn filter_users(users: &[User], pred: impl Fn(&User) -> bool) -> Vec<&User>;

// UNAMBIGUOUS:
pub fn retain_users(users: &[User], pred: impl Fn(&User) -> bool) -> Vec<&User>;
pub fn exclude_users(users: &[User], pred: impl Fn(&User) -> bool) -> Vec<&User>;
```

Common ambiguous words and their less ambiguous replacements:

| Avoid | Prefer |
|---|---|
| `get` | `fetch`, `load`, `read`, `compute`, `find`, `build` |
| `process` | `validate`, `transform`, `normalise`, `archive`, `apply` |
| `handle` | `dispatch`, `reject`, `forward`, `record`, `emit` |
| `check` | `validate`, `verify`, `detect`, `assert`, `is_valid` |
| `data` | the actual type: `metadata`, `payload`, `record`, `config` |
| `info` | the actual content: `statistics`, `report`, `summary` |
| `item` | the actual domain term: `entry`, `token`, `deposit`, `artifact` |
| `flag` | a boolean with a name: `is_sandbox`, `has_failures`, `skip_history` |

---

### Rule: Attach Important Information to Names

If there is something critical a reader must know about a value — its unit, its
encoding, its state, its limits — encode that information in the name rather than
leaving it to a comment that may not be read.

```rust
// MISSING INFORMATION: what unit? what encoding? validated or raw?
let timeout = 30;
let password = get_password();
let path = args[0];

// INFORMATION ATTACHED:
let timeout_secs: u32 = 30;
let password_hash: PasswordHash = hash_password(raw);
let project_dir: PathBuf = PathBuf::from(&args[0]);
```

For Rust specifically, the type often carries the information — but only if the type
is precise. `String` carries no information; `OrcidUri`, `Sha256Hash`, `SemverTag`
carry all the information a reader needs.

---

### Rule: Names Should Be Proportional to Scope

A variable used in two adjacent lines can have a short name. A type used across an
entire codebase must have a precise, unambiguous name. The larger the scope, the more
information the name must carry.

```rust
// SHORT SCOPE: i is fine for a loop counter visible for 3 lines
for i in 0..entries.len() { ... }

// MEDIUM SCOPE: a function-local variable needs a descriptive name
let sorted_entries: Vec<&Entry> = ...;

// WIDE SCOPE: a public type or function needs a fully qualified, precise name
pub struct CitationMetadata { ... }     // not Metadata, not CffData, not Citation
pub fn parse_citation(path: &Path) -> Result<CitationMetadata, MetaError>;
```

**Special case: avoid single-letter names outside loop counters.** `n`, `s`, `t`,
`c` as variable names in functions longer than 5 lines are always wrong.

---

### Rule: Boolean Names Must Read as True/False Assertions

A boolean variable or function name should be readable as a complete statement that is
either true or false. Never name a boolean such that its truthy value is unclear.

```rust
// UNCLEAR: what does true mean?
let check = validate_orcid(uri);
let mode = config.sandbox;
fn history(config: &Config) -> bool;

// CLEAR: the name is a true/false statement
let orcid_is_valid = validate_orcid(uri);
let is_sandbox = config.sandbox;
fn skip_history(config: &Config) -> bool;
```

Prefer `is_`, `has_`, `should_`, `can_`, `will_` prefixes for booleans.
Avoid negated names: `is_not_ready` requires double-negation reasoning. Use
`is_ready` and invert at the call site: `if !is_ready`.

---

### Rule: Prefer Concrete Names Over Abstract Names

Abstract names describe what a thing is at a high level. Concrete names describe what
it does or what it contains. When in doubt, be more concrete.

```rust
// ABSTRACT: names that could mean almost anything
struct ServerConfig { ... }
fn run_checks(project: &Project);
struct ValidationResult { ... }

// CONCRETE: names that carry specific meaning
struct ZenodoEndpointConfig { ... }
fn check_release_readiness(project: &Project) -> CheckReport;
struct SecurityScanResult { items: Vec<SecurityFinding> }
```

---

### Rule: Don't Use Names That Could Be Confused With Built-ins or Common Types

Names that shadow or closely resemble standard library types cause silent confusion.

```rust
// CONFUSING: shadows common types/traits
struct Result<T> { ... }         // shadows std::result::Result
fn clone(&self) -> Self { ... }  // expected to match Clone semantics
let string = parse_input();      // "string" implies &str or String

// CLEAR:
struct ParseOutcome<T> { ... }
fn deep_copy(&self) -> Self { ... }
let parsed_tag = parse_input();
```

---

## Part II — Comments

The fundamental rule: **comments should add information that cannot be extracted from
reading the code.** A comment that merely restates the code in English is noise. The
reader must now process both the code and the comment, and verify they agree.

---

### Rule: Comments Explain Why, Not What

The *what* is in the code. The *why* — the intention, the constraint, the non-obvious
tradeoff, the historical reason — is not in the code, and belongs in a comment.

This rule governs inline comments — the `//` annotations within function bodies and
at the top of private items. For doc comments on public items (`///` and `//!`),
apply Ousterhout's contract standard instead: describe what is guaranteed, what
preconditions apply, and what errors are returned — never the implementation mechanism
that delivers those guarantees.

```rust
// BAD: restates the code
// Sort entries by filename
entries.sort_by_key(|e| e.filename.clone());

// GOOD: explains the why
// Entries must be sorted by filename for deterministic archive construction.
// The same sort order on all platforms is required for SHA-256 reproducibility.
entries.sort_by_key(|e| e.filename.clone());
```

---

### Rule: Record Surprises and Non-Obvious Decisions

If you made a decision that a future reader (or agent) might question or "fix", explain
it. The comment should pre-answer the question "why is it done this way?"

```rust
// The mtime is set to zero for all archive entries rather than using the git
// commit timestamp. This is intentional: using the commit timestamp makes the
// archive non-reproducible on systems where the timestamp is rounded differently.
// See ADR-001 in ARCHITECTURE.md for the full rationale.
header.set_mtime(0);

// We use saturating_add here rather than checked_add because a counter overflow
// in this context is a benign loss of precision, not a correctness failure.
// Panicking or returning an error on overflow would be a worse outcome.
self.event_count = self.event_count.saturating_add(1);
```

---

### Rule: Announce Flaws and Limitations

If code has a known limitation or a future-work item, state it. An honest comment
about a limitation is better than leaving the next programmer to discover it at 2am.

```rust
// TODO(mint-check): The JOSS word count is computed by splitting on whitespace,
// which undercounts contractions and overcounts hyphenated compounds. A proper
// word count would use a Unicode word-boundary segmenter. This is close enough
// for the 1500-word limit check but not publication-quality.
fn estimate_word_count(text: &str) -> usize {
    text.split_whitespace().count()
}

// FIXME: This regex does not handle base64-encoded secrets embedded in
// multi-line strings. False negatives are possible for obfuscated tokens.
// Tracked in SESSIONS.md Session 5 as a known limitation.
```

---

### Rule: Director Comments for Non-Obvious File/Module Structure

At the top of a module with non-obvious internal organisation, a short "director
comment" that maps the structure saves the reader from having to infer it.

```rust
//! CITATION.cff parser and format transformation.
//!
//! Entry point: `parse_citation` — validates and returns `CitationMetadata`.
//! Transformations: `to_codemeta`, `to_bibtex`, `to_zenodo_metadata`.
//! All transformations take `&CitationMetadata`; they never re-parse the file.
//!
//! Internal structure:
//!   parse   — YAML → raw fields → CitationMetadata (validation here)
//!   schema  — CFF 1.2.x required/optional field rules
//!   codemeta — CFF → CodeMeta crosswalk
//!   bibtex   — CFF → BibTeX @software entry
```

---

### Rule: Do Not Comment Bad Names — Fix the Names

If a comment is needed to explain what a variable name means, the variable name is
wrong. Fix the name; delete the comment.

```rust
// BAD: comment compensates for a bad name
let d = duration_secs * 1000;  // d is duration in milliseconds

// GOOD: the name is self-explanatory
let duration_ms = duration_secs * 1000;
```

---

## Part III — Control Flow

The fundamental rule: **arrange code so that the reader's mental model of what is
happening is as simple as possible.** The primary enemy is nesting, which forces the
reader to maintain a stack of conditions.

---

### Rule: Return Early to Eliminate Nesting (The Guard Clause)

Handle error conditions and edge cases at the top of a function and return immediately.
The "happy path" then runs at the lowest indentation level, unencumbered by nested
conditions.

```rust
// NESTED — reader must track two levels of condition simultaneously
fn process_archive(config: &ArchiveConfig) -> Result<ArchiveBundle, ArchiveError> {
    if config.project_dir.exists() {
        if let Some(tag) = &config.tag {
            if !tag.is_empty() {
                // ... 30 lines of happy path
            } else {
                Err(ArchiveError::EmptyTag)
            }
        } else {
            Err(ArchiveError::MissingTag)
        }
    } else {
        Err(ArchiveError::ProjectDirNotFound)
    }
}

// FLAT — reader sees the conditions once, then reads the happy path linearly
fn process_archive(config: &ArchiveConfig) -> Result<ArchiveBundle, ArchiveError> {
    if !config.project_dir.exists() {
        return Err(ArchiveError::ProjectDirNotFound);
    }
    let tag = config.tag.as_deref().filter(|t| !t.is_empty())
        .ok_or(ArchiveError::MissingTag)?;

    // ... 30 lines of happy path at zero nesting
}
```

---

### Rule: Minimise the Variables a Reader Must Track

Every variable in scope is a cognitive burden. Limit variables to the smallest scope
in which they are needed. Prefer `let` inside blocks over `let mut` at the top of a
function. Delete variables that are used only once.

```rust
// BURDEN: three intermediate variables the reader must track
let raw = fs::read_to_string(&path)?;
let parsed = serde_yaml::from_str::<RawCff>(&raw)?;
let validated = validate_cff(parsed)?;
to_citation_metadata(validated)

// LIGHTER: chain the transformations; only one "current state" to track
fs::read_to_string(&path)
    .map_err(|e| MetaError::FileRead { path: path.display().to_string(), source: e })
    .and_then(|raw| serde_yaml::from_str::<RawCff>(&raw).map_err(MetaError::Parse))
    .and_then(validate_cff)
    .and_then(to_citation_metadata)
```

Use judgement: a chain of five `and_then`s is not always clearer than five `let`
bindings. The goal is to minimise the reader's tracking burden, not to maximise the
use of combinators.

---

### Rule: Prefer Positive Conditions

Positive conditions (`if is_valid`) are easier to read than negative conditions
(`if !is_invalid`). Double negatives (`if !is_not_ready`) are always wrong.

```rust
// HARD: double negation
if !check_report.has_no_failures() { ... }

// EASY: positive assertion
if check_report.has_failures() { ... }
```

---

### Rule: One Action Per Line in Complex Conditions

When a boolean expression has more than two terms, split it across lines with the
operator at the start of each continuation. Add a comment if the overall condition is
non-obvious.

```rust
// UNREADABLE in one line
if path.exists() && path.is_file() && path.extension().map(|e| e == "cff").unwrap_or(false) && metadata(path).map(|m| m.len() > 0).unwrap_or(false) { ... }

// READABLE
let is_valid_cff_file =
    path.exists()
    && path.is_file()
    && path.extension().is_some_and(|e| e == "cff")
    && path.metadata().is_ok_and(|m| m.len() > 0);

if is_valid_cff_file { ... }
```

---

### Rule: Arrange Code in Decreasing Order of Importance

Within a function or module, put the most important or central logic first. Readers
scan from top to bottom; they form a mental model from what they read first. Utility
functions, error helpers, and edge cases belong at the bottom.

```rust
// In a module file: lead with the primary public function,
// follow with its direct helpers, end with utilities.

pub fn check_project(ctx: &ProjectContext) -> Result<CheckReport, CheckError> { ... }

fn run_categories(ctx: &ProjectContext, categories: &[Box<dyn CheckCategory>]) -> Vec<CategoryResult> { ... }

fn build_category_list() -> Vec<Box<dyn CheckCategory>> { ... }

// private utility — last
fn to_check_status(has_failures: bool, has_warnings: bool) -> CheckStatus { ... }
```

---

## Part IV — Functions

---

### Rule: Functions Should Do One Thing at One Level of Abstraction

A function that mixes high-level orchestration with low-level detail is hard to read
because the reader must switch abstraction levels mid-function.

```rust
// MIXED LEVELS: orchestration and detail in the same function
pub fn build_release(config: &ArchiveConfig) -> Result<ArchiveBundle, ArchiveError> {
    // High-level: what we're doing
    let files = list_tracked_files(&config.project_dir)?;

    // Low-level detail: how we build the tar
    let mut archive = tar::Builder::new(GzEncoder::new(Vec::new(), Compression::best()));
    let mut sorted = files.clone();
    sorted.sort();
    for path in &sorted {
        let mut header = tar::Header::new_gnu();
        header.set_mtime(0);
        // ... 15 more lines of tar construction detail
    }
    // Back to high-level
    let sha256 = compute_checksum(&archive_bytes);
    write_bundle(&config.output_dir, &archive_bytes, &sha256)
}

// SEPARATED: each function operates at one level
pub fn build_release(config: &ArchiveConfig) -> Result<ArchiveBundle, ArchiveError> {
    let files = list_tracked_files(&config.project_dir)?;
    let archive_bytes = create_deterministic_archive(&files)?;  // detail hidden
    let sha256 = compute_sha256(&archive_bytes);                // detail hidden
    write_bundle(&config.output_dir, archive_bytes, sha256)
}
```

---

### Rule: Prefer Fewer Function Parameters

Every parameter is a burden on the caller. Functions with more than four parameters
are almost always doing too much, or combining what should be separate concepts.

**Solutions for too many parameters:**
1. Group related parameters into a config struct
2. Split the function into two functions
3. Move parameters into `self` (make it a method)

```rust
// TOO MANY PARAMETERS
pub fn publish(
    zenodo_token: &str,
    sandbox: bool,
    bundle_path: &Path,
    metadata: &ZenodoMetadata,
    confirm: bool,
    software_heritage: bool,
    repo_url: &str,
) -> Result<PublishResult, PublishError>;

// GROUPED: related parameters become config structs
pub fn publish(
    client: &dyn ZenodoClient,
    swh: &dyn SwhClient,
    bundle: &ArchiveBundle,
    metadata: &ZenodoMetadata,
    options: &PublishOptions,
) -> Result<PublishResult, PublishError>;
```

---

### Rule: Use Explaining Variables for Complex Expressions

If a sub-expression is non-obvious, extract it into a named variable before using it.
The name explains what the expression computes; the code explains how.

```rust
// OPAQUE
if meta.authors.iter().any(|a| a.orcid.as_ref().map(|o| o.starts_with("https://orcid.org/")).unwrap_or(false)) { ... }

// EXPLAINED
let any_author_has_orcid = meta.authors.iter()
    .any(|a| a.orcid.as_ref().is_some_and(|o| o.starts_with("https://orcid.org/")));

if any_author_has_orcid { ... }
```

---

## Part V — Naming as a Design Probe

This is the connection between ARC and Ousterhout that is easy to miss: **difficulty
naming is a symptom of a design problem, not a naming problem.** ARC is a book about
expression — but its naming rules are a diagnostic tool for design, not just a style
guide.

---

### The "Can't Name It" Signal

When you cannot name a function, module, or type without resorting to vague words
(`Manager`, `Handler`, `Processor`) or compound phrases with "and", stop writing code.
The naming difficulty is telling you something about the design.

**What it usually means:**

| Symptom | Likely cause | Remedy |
|---|---|---|
| Name requires "and" | Two responsibilities | Split into two functions or types |
| Only vague word fits (`Manager`) | No clear single purpose | Redefine what the module owns |
| Name is a verb phrase describing a sequence | Temporal decomposition | Merge into one function that hides the sequence |
| Name sounds like a wrapper (`UserWrapper`) | Shallow module | Add invariants or delete the wrapper |
| Name describes the implementation, not the result | Abstraction leaking | Redesign the interface |

**The one-sentence test:**
Before naming anything non-trivial, write the one-sentence description of what it does.
If the sentence contains "and", the name will always be wrong — not because you lack
the right word, but because no single word can describe two responsibilities. Fix the
design; the name will follow.

```rust
// CANNOT BE NAMED — does two unrelated things
fn validate_and_transform(input: &str) -> Result<Output, Error> {
    // 1. validates the input
    // 2. transforms it into Output
    // Any name for this is either vague ("process") or compound ("validate_then_transform")
}

// CAN BE NAMED — each function has one responsibility
fn validate_citation(input: &str) -> Result<ValidatedCitation, CitationError> { ... }
fn to_zenodo_metadata(citation: &ValidatedCitation) -> ZenodoMetadata { ... }
```

---

### The Connection to Ousterhout

Ousterhout's "hard to describe" Red Flag and ARC's naming rules converge on the same
diagnostic:

- Ousterhout: *"If you cannot describe what a module does in one sentence without 'and',
  it is doing too much."*
- ARC: *"If you cannot find a clear, precise name for a function, the function is
  doing too much."*

They are the same observation from different angles. Load `docs/standards/ousterhout.md`
when naming is difficult — the Red Flag section will identify which design problem
is causing the naming difficulty.

---

### Using Naming Difficulty During Refactor

In the Refactor phase, when you encounter a name you cannot improve:

1. Write the one-sentence description of what the item does
2. If it contains "and" → go to `docs/standards/ousterhout.md` and split
3. If it contains only vague words → ask "what exactly does this hide?" (deep-module
   test); if the answer is "not much," delete the abstraction
4. If the description is clear but no single word captures it → the item may be
   genuinely novel; invent a precise domain-specific name and document it with a
   doc comment that defines what it means

Only reach step 4 after ruling out steps 1–3. Most naming difficulties are design
difficulties in disguise.

---

## Part VI — The Surface Area Checklist

Apply before finalising any function, type, or module for a session.

**Names:**
- [ ] Can every name be misunderstood? If yes, rename.
- [ ] Do boolean names read as true/false statements?
- [ ] Are names proportional to their scope? Short in narrow scope, precise in wide scope.
- [ ] Have you replaced any of these words: `get`, `process`, `handle`, `data`, `info`,
  `item`, `flag`, `check`, `manager`, `helper`, `utils`?
- [ ] Was any name difficult to choose? If yes — was that difficulty a design signal?
  Did you consult `docs/standards/ousterhout.md` before settling on the name?

**Comments:**
- [ ] Does every comment say *why*, not *what*?
- [ ] Is there any comment that could be eliminated by renaming the variable it describes?
- [ ] Are all non-obvious decisions annotated?
- [ ] Does every public item have a doc comment that adds information beyond its name?

**Control flow:**
- [ ] Do all error/edge cases return early (guard clauses)?
- [ ] Is nesting deeper than two levels anywhere? If yes, extract a function.
- [ ] Are all boolean conditions positive? No double negatives?
- [ ] Is complex logic extracted into named explaining variables?

**Functions:**
- [ ] Does every function do one thing at one level of abstraction?
- [ ] Does any function have more than four parameters? If yes, group into a config struct.
- [ ] Is every variable scoped as tightly as possible?
