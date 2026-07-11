# Skill: review-docs

> **When to invoke:** At the end of every session that added or modified public items.
> Also invoke before declaring any milestone complete, and as part of the v1.0 gate.
> **Load:** `docs/standards/ousterhout.md` (Red Flags: Comment Repeats Code,
> Implementation Documentation Contaminates Interface),
> `docs/standards/readable-code.md` (Part II — Comments)

---

## What This Skill Checks

Documentation review has three layers, each catching different failure modes:

1. **Coverage** — every public item has a doc comment (mechanical, tool-assisted)
2. **Quality** — every doc comment describes a contract, not an implementation (judgment)
3. **Completeness** — every non-trivial function has a working example (tool-assisted)

All three layers are required. A codebase that passes coverage but fails quality is
worse than one that fails coverage honestly — it creates false confidence.

---

## Procedure

### Step 1 — Run the coverage check

```bash
RUSTDOCFLAGS="-D missing_docs" cargo doc --no-deps --workspace 2>&1 | grep -E "warning|error"
```

Every `missing documentation` warning is a coverage failure. List them all.
Fix every one before proceeding to Step 2 — quality review of a missing doc comment
is impossible.

Also run:
```bash
cargo test --doc --workspace
```

Any failing doctest is a correctness failure — the example no longer matches the
implementation. Fix immediately.

### Step 2 — Quality review of module-level comments

For every module (`//!` comments in `lib.rs` or `mod.rs`) created or modified this
session, verify:

- [ ] States the module's single responsibility in one sentence
- [ ] Names the primary public entry point(s)
- [ ] Explains the module's role in the larger architecture (which crate does it serve?)
- [ ] Does NOT describe implementation details (data structures used, algorithms chosen)

**Quality test:** Read the `//!` comment in isolation. Could an agent starting a new
session understand what this module does and how to use it, without reading any code?
If no, rewrite.

**Red Flag check:** Apply the "hard to describe" test from `docs/standards/ousterhout.md`.
If the one-sentence description requires "and", the module has more than one
responsibility. This is a design finding, not just a documentation finding — record
it in `<project>/SESSIONS.md` and consider whether the module should be split.

### Step 3 — Quality review of function doc comments

For every `pub fn` created or modified this session, verify each doc comment against
these criteria:

**Must describe:**
- What the function returns or produces (the observable output)
- What conditions cause `Err` or `None` (the failure contract)
- Any non-obvious preconditions the caller must satisfy

**Must NOT describe:**
- How the function is implemented internally
- Which other functions it calls
- What data structures it uses

**Template for a good function doc comment:**
```rust
/// [One sentence: what does this return/produce?]
///
/// [Optional second paragraph: non-obvious contract details, edge cases,
///  relationship to other functions.]
///
/// # Errors
///
/// Returns [`ErrorType::Variant`] if [specific condition].
/// Returns [`ErrorType::OtherVariant`] if [other specific condition].
///
/// # Examples
///
/// ```
/// [working example for non-trivial functions]
/// ```
pub fn the_function(...) -> Result<...> { ... }
```

**Quality test for each doc comment:** Read it without looking at the implementation.
Does it tell you everything you need to know to call this function correctly? Does it
tell you anything about *how* it works that you do not need to know? If yes to the
second question, remove those sentences.

### Step 4 — Quality review of type doc comments

For every `pub struct`, `pub enum`, and `pub trait` created or modified this session:

- [ ] Explains what the type *represents*, not how it is stored
- [ ] States any invariants the type upholds (what is always true about a value of
      this type?)
- [ ] For enums: each variant has a doc comment explaining when it occurs
- [ ] For traits: explains the contract implementors must uphold

```rust
// BAD: describes storage
/// A HashMap from UserId to a Vec of Token values.
pub struct TokenStore { ... }

// GOOD: describes what the type represents and its invariant
/// All active authentication tokens for the current session.
/// Tokens are guaranteed non-expired at the time of insertion;
/// use `prune_expired` to remove tokens that have since expired.
pub struct TokenStore { ... }
```

### Step 5 — Check for missing doctests

For every `pub fn` that is non-trivial (more than one logical step, or with non-obvious
usage), verify a `# Examples` section exists with a runnable example.

Exceptions (doctests not required):
- Functions where the usage is completely obvious from the signature
  (`fn as_str(&self) -> &str` on a newtype)
- Functions that require external state (network, filesystem) that cannot be mocked
  in a doctest — document this explicitly: `/// Note: see integration tests for usage examples.`

For all others: missing doctest = documentation coverage failure.

### Step 6 — The "design signal" pass

This step uses documentation as a design probe, not just a quality check. For every
function you struggled to write a clear one-sentence doc comment for, ask:

- Could not state what it returns without listing multiple unrelated things?
  → Likely violates single responsibility. Flag for `review-for-red-flags`.
- Had to describe implementation details because the contract is not expressible
  without them? → The abstraction is leaking. Flag for redesign.
- Needed more than two sentences to explain when it returns Err?
  → Too many error conditions. Consider splitting or simplifying the error type.

Record any design signals found in `<project>/SESSIONS.md` under "Design signals from docs review."

### Step 7 — Record in session log

```
**Docs Review:**
- Coverage: [X missing doc comments found and fixed / none]
- Doctest failures: [none / list]
- Quality rewrites: [none / list of functions whose comments were rewritten and why]
- Design signals: [none / list of design issues surfaced by documentation difficulty]
```
