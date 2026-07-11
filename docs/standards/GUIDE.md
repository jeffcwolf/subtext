# Livery Standards — A Human Guide

> **What this file is:** A plain-English explanation of how Livery's three standards
> files produce high-quality code, how they relate to each other, and what each one
> covers. Read this before reading the standards files themselves.
>
> **What this file is not:** A reference document. The three standards files
> (`ousterhout.md`, `readable-code.md`, `rust-specifics.md`) are the executable
> reference — structured for agents to load and apply mechanically. This guide is for
> humans who want to understand the philosophy before reading the rules.
>
> **Location:** `docs/standards/GUIDE.md`

---

## The Central Problem

AI coding agents are fluent but amnesiac. They write code that compiles, passes tests,
and looks plausible — but that optimises for local coherence rather than global quality.
Over twenty sessions on a real project, the result is a codebase where every function
was locally defensible and the whole is unmaintainable: shallow abstractions stacked
on shallow abstractions, names that technically describe their function but tell you
nothing about their purpose, Rust types that wrap other types without enforcing
anything.

The three standards files are Livery's answer to this. They encode — precisely enough
to be enforced mechanically — what "good code" means at three distinct levels of
abstraction.

---

## The Three Layers

The standards operate at three levels, from the most architectural to the most
expressive. They are complementary, not overlapping. A session that applies all three
produces code that is well-structured, clearly written, and idiomatically Rust.

```
Layer 1 — Structure:    ousterhout.md
  "Is the design right? Are the modules deep? Is complexity hidden?"

Layer 2 — Expression:   readable-code.md
  "Is the surface right? Are the names clear? Are the comments useful?"

Layer 3 — Language:     rust-specifics.md
  "Are we using Rust correctly? Types, errors, traits, visibility?"
```

The order matters: structure before surface, surface before language idiom. A
well-named function on a poorly-designed module is still a poorly-designed module.
Ousterhout's pass comes first in the refactor cycle for this reason.

---

## Layer 1 — Structure: `ousterhout.md`

**Source:** John Ousterhout, *A Philosophy of Software Design* (2nd ed.)

**What it's for:** Catching design problems at the module and interface level — before
they become entrenched. This is the layer that determines whether your codebase will
still be comprehensible at session 100.

### The Central Metric: Module Depth

Ousterhout's key insight is that **complexity is the enemy of maintainable software**,
and complexity accumulates through shallow abstractions. A module is *deep* if it hides
significant complexity behind a simple interface — if the ratio of (complexity
concealed) to (interface complexity) is high. A module is *shallow* if its interface
is nearly as complex as its implementation: it has created an abstraction without
hiding anything.

Agentic codebases tend toward shallow modules because agents create abstractions
reflexively. Every new concept becomes a struct, every stage in a process becomes a
module. The result is layers of indirection that hide nothing and multiply cognitive
overhead.

The `ousterhout.md` file encodes eight principles for fighting this:

**Deep Modules** — the primary principle. Every module must justify its existence by
answering one question: *what complexity does this hide?* If the answer is "not much,"
the module should not exist or should be collapsed into its parent.

**Information Hiding** — the mechanism of deep modules. Internal representations
must never leak through public interfaces. The moment an internal type appears in a
public function signature, the implementation is frozen: you can never change it
without breaking every caller.

**Different Layer, Different Abstraction** — each module in a layered system should
introduce a distinct level of abstraction. A function that mixes high-level policy
decisions with low-level implementation details is operating at two levels
simultaneously and should be split.

**Minimal Interface** — the smallest public surface that serves all real callers.
Every item you expose becomes a commitment. `pub` in Rust is a contract; most items
in most crates should be `pub(crate)` or private.

**General-Purpose Modules** — slightly more general than you need right now, so they
remain useful as requirements change. Not wildly general (premature abstraction), but
not so specific they can only serve one caller.

**Strategic Programming** — there is no "we'll clean this up later." Every change
should improve the overall design or at minimum not degrade it. This is what prevents
the gradual accumulation of hacks that make a codebase unmaintainable.

**Define Errors Out of Existence** — the best error handling is code that makes the
error condition impossible. This is the Ousterhout principle that most naturally maps
to Rust's type system: a well-designed API makes misuse unrepresentable rather than
returning errors for invalid inputs.

**Design It Twice** — before committing to an interface design, sketch two fundamentally
different alternatives and compare them. The first design is almost never the best
design. This step is reliably skipped under time pressure and is the single biggest
source of avoidable design debt in agentic sessions.

### The Red Flags

The second part of `ousterhout.md` is the Red Flags section — thirteen patterns that
signal a design problem. They are called Red Flags because they are symptoms: when you
see one, something in the design is wrong. You stop and fix the design before continuing.

The most common in agentic Rust codebases:

- **Shallow Module** — an abstraction that hides nothing. The classic Rust form: a
  newtype that wraps one field, adds no invariants, and forwards all methods unchanged.

- **Information Leakage** — the same internal data structure appears in two or more
  modules. Change the structure and you change both. The module that was supposed to
  own this information is not actually owning it.

- **Temporal Decomposition** — code is structured around the sequence of operations
  ("parse, then validate, then transform") rather than around domains of knowledge.
  This produces modules that all know about the same data in different phases — the
  opposite of information hiding.

- **Conjoined Methods** — two methods that must be called in sequence for correct
  behaviour. The runtime constraint should be a compile-time constraint (the type-state
  pattern in Rust).

- **Hard to Describe** — if you cannot say what a module does in one sentence without
  "and," it has two responsibilities. The naming difficulty is a design signal, not a
  naming problem.

The Red Flags are also the input to the `review-for-red-flags` skill — the agent
works through each one explicitly at the end of every session.

---

## Layer 2 — Expression: `readable-code.md`

**Source:** Dustin Boswell & Trevor Foucher, *The Art of Readable Code* (2011)

**What it's for:** Once the structure is right, the surface must be right. This layer
governs how ideas are expressed in code: names, comments, control flow, and function
organisation.

### The Primary Test for Names

The test is: *could this name be misunderstood?* A name passes if no reasonable reader
would assign it a different meaning than the author intended. This is stricter than it
sounds. `filter_users` can mean "keep matching" or "remove matching" — it fails the
test. `retain_users` and `exclude_users` are unambiguous.

The file encodes four naming rules:

**Words That Cannot Be Misread** — prefer words with one clear meaning over words
that are slightly ambiguous. The file provides a table of common offenders and
replacements: `get` → `fetch`, `load`, `read`, `compute`; `process` → `validate`,
`transform`, `normalise`; `handle` → `dispatch`, `reject`, `forward`. In Rust, this
extends to type names: `String` carries no information; `OrcidUri`, `Sha256Hash`,
`SemverTag` carry all the information a reader needs.

**Important Information Attached to Names** — if there is something critical a reader
must know (a unit, an encoding, a state, a limit), encode it in the name, not in a
comment that may not be read. `timeout` tells you nothing; `timeout_secs` tells you
everything you need.

**Names Proportional to Scope** — a short name is fine in a three-line function; it
requires precision in a public API. `i` is fine for a loop counter; `i` is not fine
for a field used across a module.

**Names That Read as True/False Statements** — boolean variables and functions should
be named so that reading them in context is unambiguous: `is_valid`, `has_failures`,
`skip_history` — not `valid` (adjective or verb?), `failures` (count or flag?),
`history` (data or flag?).

### Comments That Add Information

The rule is: **comments explain why, not what.** Code already says what it does.
A comment that restates the code adds noise. A comment that explains *why* this
approach was chosen, *why* this edge case exists, *why* this constraint applies —
that adds information the code cannot convey.

The other side of this: **if a comment is needed to explain what a variable name
means, the variable name is wrong.** Fix the name; delete the comment.

Doc comments on public items follow a different standard. They must describe the
*contract*: what the function guarantees, what preconditions exist, what errors
are returned and when. The test for a doc comment: does it add information that is not
already in the function's name and type signature? If not, it is not a doc comment —
it is a paraphrase of the name, and it should be rewritten or deleted.

### Naming as a Design Probe

This is the most important idea in `readable-code.md`, and it connects directly to
Ousterhout. **Difficulty naming is almost always a symptom of a design problem, not a
naming problem.**

When you cannot find a clear, precise name for a function without resorting to
`Manager`, `Handler`, `Processor`, or a compound phrase with "and" — stop writing
code. The naming difficulty is telling you something. The checklist in the file makes
the diagnosis mechanical:

- Name requires "and" → two responsibilities → split into two functions
- Only vague word fits (`Manager`, `Helper`) → no clear single purpose → redefine what the module owns
- Name describes a sequence → temporal decomposition → merge into one function that hides the sequence
- Name sounds like a wrapper → shallow module → add invariants or delete the wrapper

This is the reason Refactor Pass 2 (ARC names) happens *after* Refactor Pass 1
(Ousterhout structure). You cannot name something well if the structure is wrong.
Once the structure is right, the names follow.

---

## Layer 3 — Language: `rust-specifics.md`

**What it's for:** Applying the design principles from Layers 1 and 2 in the specific
idioms of Rust. This file does not repeat Ousterhout or ARC — it shows how those
principles manifest in Rust's type system, error handling, trait design, and naming
conventions.

### The Type System as a Design Tool

Rust's type system is the implementation of Ousterhout's "define errors out of
existence." The language gives you tools that most languages lack, and using them
correctly is the difference between a Rust codebase that is safe and one that is
merely Rust.

**Newtypes that enforce invariants** — a newtype is only justified if it enforces
a constraint, restricts an interface, or makes distinct things distinguishable. A
newtype that wraps a `String` and forwards all its methods is the Shallow Module
Red Flag expressed in Rust. A newtype that validates its input on construction,
restricts the operations available, and makes transposition errors a compile error
is applying Ousterhout's principles correctly.

**Type-state for lifecycle phases** — when a type has phases where some operations
are only valid in certain phases, encode the phase in the type parameter. The pattern
uses phantom types to move a runtime constraint (`if !self.files_uploaded { return Err(...) }`)
to compile time (calling `publish()` on a `Deposit<Draft>` doesn't compile). This is
the most powerful application of "define errors out of existence" in Rust.

**Enums over boolean parameters** — a boolean at a call site is unreadable. `publish(config, true, false)` requires reading the function signature to understand. An enum is self-documenting at every call site. Any function with two or more boolean parameters must use an options struct or enum; this is a hard rule.

### Error Handling

**Library crates use `thiserror`; binary crates use `anyhow`.** This is a hard rule,
not a preference. Library crates must expose structured errors that callers can match
on. Binary crates convert all errors to human-readable strings for the user.

**Every error variant must carry enough context to diagnose without reading source
code.** An error that says "validation failed" requires a debugger to diagnose. An
error that says "field 'title' in CITATION.cff has value '' but must be non-empty"
diagnoses itself. This is Ousterhout's information hiding applied to errors: the error
type hides how the error was detected but exposes everything needed to understand and
fix it.

**No `.unwrap()` in library code without a safety comment** explaining why the panic
is logically impossible. `.expect()` is preferred over `.unwrap()` — the message
documents the invariant. In tests, `.unwrap()` is fine.

### Trait Design

**Do not define a trait without multiple implementors.** A trait with one implementor
is indirection without benefit. It adds a layer of dispatch complexity that contributes
nothing to information hiding and makes the code harder to follow. The one exception:
traits used for test mocking. A trait with two implementors — the real HTTP client and
a mock client — is justified by the testing requirement.

The corollary: **traits should be as narrow as possible.** A trait that bundles five
methods together forces every implementor to provide all five, even if they only need
three. Split the trait; callers can name what they actually need.

### Visibility

**`pub(crate)` is the default for non-public items.** `pub` in Rust is a contract. It
extends an item into the public API, constrains future changes, and requires a doc
comment. Most items in most library crates are `pub(crate)`. `pub` is reserved for
items that are genuinely part of the crate's external contract with at least two real
callers. This was the central lesson of the Prism `pub(crate)` work and the Scribe
pub_ratio conversion: most `pub` items in agentic codebases should be `pub(crate)`,
and the compiler will tell you when you've gone too far.

### Testing Organisation

Unit tests co-locate with the code they test in `#[cfg(test)] mod tests` at the bottom
of the same file. Property tests live in a separate `#[cfg(test)] mod proptests` block
in the same file. Integration tests live in `tests/` at the crate root. This makes the
relationship between code and test visible and ensures they are updated together.

Test names describe behaviour, not implementation. `test_parse_function` tells you
what the test does; `parse_citation_returns_err_for_missing_required_fields` tells you
what the code is supposed to do. The test suite is a machine-executable specification
of the module's behaviour — it should read that way.

---

## How the Three Layers Work Together

In the Livery TDD cycle, the three layers are applied in sequence during the Refactor
phase:

**Pass 1 — Ousterhout (structure):** Load `ousterhout.md`. Apply the Design Process
Checklist to every new or modified module. Work through the Red Flags. Fix any
structural problems before touching names or Rust idioms. Structure is the foundation;
everything else rests on it.

**Pass 2 — ARC names (surface):** Load `readable-code.md`. Apply the naming rules to
every new name introduced this session. Use the "Can't Name It" signal — if a name is
hard to choose, go back to Pass 1. The naming difficulty is a design signal, not a
naming problem.

**Pass 3 — ARC expression (surface):** Still `readable-code.md`. Strip every comment
that restates the code. Add comments for every non-obvious decision. Apply guard
clauses. Extract explaining variables. Verify every function does one thing at one
level of abstraction.

After the three refactor passes, the `rust-specifics.md` checklist is the final
mechanical gate: types, errors, traits, visibility, naming conventions. This confirms
that the structural and expressive decisions made above are correctly encoded in Rust's
type system.

---

## What This Produces

A codebase governed by these three layers has a specific, recognisable character:

**Modules are deep.** There is real abstraction happening. Each module hides something
meaningful, and callers are genuinely insulated from implementation details. When you
change an implementation, the callers don't break.

**Names are load-bearing.** Every name tells you exactly what you need to know. There
are no `Manager` types, no `process` functions, no `data` variables. The type name
`OrcidUri` tells you as much as the doc comment; the function name
`parse_citation_rejects_missing_title` is a specification.

**Errors are self-diagnosing.** When something goes wrong, the error message tells you
what happened, where, and why — not "validation failed." The error types are structured
enough to match on programmatically; the messages are clear enough for a user.

**The type system prevents mistakes.** Invalid states are unrepresentable. You cannot
call `publish()` before `upload_file()` — it doesn't compile. You cannot pass a
`DepositId` where a `UserId` is expected — the types are different. The compiler
catches errors that would be silent bugs in less carefully-typed code.

**Tests are specifications.** The test suite reads like a description of what the
software does. A new developer (or a new agent session, six months later) can read the
tests and understand the system's behaviour without reading the implementation.

---

## The Enforcement Chain

These standards are not advisory. Each layer is enforced at multiple points:

| Layer | Enforced during | Mechanism |
|---|---|---|
| Ousterhout | Refactor Pass 1 (every session) | Agent applies Design Process Checklist |
| Ousterhout | Post-session (every session) | `review-for-red-flags` skill — all 13 Red Flags explicitly checked |
| Ousterhout | Continuous | `prism audit` measures module depth ratios; `prism check --strict` enforces complexity thresholds |
| ARC names | Refactor Pass 2 (every session) | Agent applies naming rules to all new names |
| ARC names | Post-session (every session) | `naming-review` skill — enumeration of every new name |
| ARC expression | Refactor Pass 3 (every session) | Agent applies control flow and comment rules |
| ARC expression | Post-session (every session) | `review-docs` skill — doc coverage and quality |
| ARC expression | Continuous | `RUSTDOCFLAGS="-D warnings" cargo doc` enforces doc correctness (broken links, doctests); library crates add `-D missing_docs` for presence |
| Rust-specifics | Refactor (every session) | Agent applies Rust Standards Checklist |
| Rust-specifics | Continuous | `cargo clippy -- -D warnings`; `prism check --strict` (pub_ratio, complexity) |

The result is a system where each principle is stated in a human-readable document,
encoded in an agent-executable rule, and verified by a mechanical gate. None of these
layers stands alone. The philosophy without the rules is advisory. The rules without
the mechanical gates are aspirational. All three together make quality measurable and
non-negotiable.

---

*This guide covers the three standards files as of Livery v1.0. For the rationale
behind choosing these sources over alternatives, see the original Livery project
for the original design rationale.*