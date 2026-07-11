# Skill: naming-review

> **When to invoke:** At the end of any session that introduced new public types,
> functions, modules, or fields. Also invoke when a name feels uncertain during writing.
> **Load:** `docs/standards/readable-code.md` Part I, `docs/standards/rust-specifics.md` Part IV

---

## Procedure

### Step 1 — Collect all new names

List every name introduced this session:
- Public types (`struct`, `enum`, `trait`, `type` aliases)
- Public functions and methods
- Public fields and enum variants
- Module names (`mod`)
- Significant local variable names (function-scoped, used across more than ~5 lines)

### Step 2 — Apply the misunderstanding test

For each name, ask: **could this name be reasonably assigned a different meaning by
another programmer reading it without context?**

If yes → rename. The bar is strict. "Probably fine" is not a pass.

### Step 3 — Apply the banned-words check

Scan every name for these words. Each occurrence is a naming failure requiring a rename:

`Manager`, `Handler`, `Processor`, `Helper`, `Utils`, `Data`, `Info`, `Item`,
`Object`, `Thing`, `Wrapper`, `Base`, `Common`, `Misc`, `get` (as a function prefix
where a more specific verb exists), `check` (where `validate`, `verify`, or `detect`
is more precise), `process` (where a specific verb exists), `flag` (for a boolean
that has a domain-specific meaning).

### Step 4 — Apply the scope-proportionality check

For each name, ask: is the name's descriptiveness proportional to its scope?

- Loop counter (2–3 lines): single letter acceptable (`i`, `j`)
- Local variable (one function): short but descriptive (`tag`, `meta`, `entry`)
- Function parameter: describes what is expected (`project_dir`, not `path`)
- Public function: fully descriptive verb phrase (`parse_citation`, `build_archive`)
- Public type: precise noun phrase (`CitationMetadata`, `DepositId`, `PublishTarget`)

### Step 5 — Apply Rust-specific naming rules

From `docs/standards/rust-specifics.md` Part IV, verify:

- Conversion methods follow `as_/to_/into_/from_/try_from_` conventions
- `new()` is infallible; fallible constructors are `parse()` or `try_new()`
- Builder methods use `with_xxx()` and return `Self`
- Boolean variables and functions use `is_`, `has_`, `should_`, `can_` prefixes
- Test function names describe behaviour, not implementation

### Step 6 — Apply the important-information test

For each name that refers to a value with a unit, encoding, state, or constraint: is
that information in the name or the type?

```
timeout: u32        → timeout_secs: u32     (unit in name)
password: String    → password_hash: PasswordHash  (encoding in type)
path: &str          → project_dir: &Path    (meaning in type and name)
```

If neither the name nor the type carries the critical information, one of them must.

### Step 7 — Enumerate and document each name

List every new name introduced this session. For each name, apply the ARC misunderstanding test and scope-proportionality test. Document the result for each.

This step consolidates Steps 2 and 4 into a single enumerated record. The output is a table or list where every name appears exactly once, with a pass/fail result for each test and the rationale for any rename.

### Step 8 — Record in session log

In the `<project>/SESSIONS.md` entry, add a "Naming Review" section:
```
**Naming Review:**
- Names reviewed: [count]
- Renames: [none / list of old → new]
```
