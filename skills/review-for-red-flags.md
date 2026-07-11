# Skill: review-for-red-flags

> **When to invoke:** At the end of every session, as part of the session contract.
> Also invoke before declaring any new module design complete.
> **Load:** `docs/standards/ousterhout.md`

---

## Procedure

Run this procedure against every module, struct, trait, and public function created or
modified in the current session. Work through each step in order. Do not skip steps.

### Step 1 — Identify scope

List every file touched this session. For each file, identify:
- New public functions or types added
- Existing public functions or types modified
- New internal modules created

### Step 2 — Run the Design Process Checklist

From `docs/standards/ousterhout.md` Part III, apply every question to each item in scope.

**Before-implementation questions** (apply to new modules/types designed this session):
- Can you state in one sentence what complexity this module hides?
- Were at least two alternative designs considered? (Design it twice)
- Is every public item truly public — does it have at least two callers?
- Are there error conditions that could be eliminated by type constraints?

**After-implementation questions** (apply to all code written this session):
- Does any public function leak internal types or structures?
- Does every function do one thing, describable without "and"?
- Is there any repeated logic that belongs in a new method?
- Does any module have temporal decomposition — sequential stages that share data and
  should be a single module?
- Are there any pass-through methods?
- Are there any conjoined methods that require a call sequence?

**Documentation questions:**
- Do all doc comments describe contracts, not implementations?
- Does every public item have a doc comment that adds information beyond the name?
- Are non-obvious decisions explained with comments that say *why*, not *what*?

### Step 3 — Check every Red Flag explicitly

For each Red Flag from `docs/standards/ousterhout.md` Part II, scan the session's
code and report a specific finding. Every item must have either a concrete finding with
file and function, or an explicit "not applicable, because..." with a reason tied to the
session's actual code. Never report "I checked and found nothing."

**Red Flag 1 — Shallow Module**
Scan for: structs that wrap a single field and forward all methods unchanged; functions
whose entire body is a single call to another function; traits with one implementor that
add no behaviour; newtypes with no validation, invariants, or restricted interface.
- Finding: [specific finding with file:function, OR "not applicable, because [reason]"]

**Red Flag 2 — Information Leakage**
Scan for: the same data structure or format appearing in two or more modules with no
abstraction separating them; a design decision reflected in multiple places such that
changing it requires changes in multiple modules.
- Finding: [specific finding with file:function, OR "not applicable, because [reason]"]

**Red Flag 3 — Temporal Decomposition**
Scan for: module structure that reflects the order of operations (read, validate, apply)
rather than the information they share; multiple modules that all operate on the same
data in different phases.
- Finding: [specific finding with file:function, OR "not applicable, because [reason]"]

**Red Flag 4 — Overexposure**
Scan for: types or functions that are `pub` but only called from within the same crate
(should be `pub(crate)`); items that are `pub(crate)` but only called from within the
same module (should be private).
- Finding: [specific finding with file:function, OR "not applicable, because [reason]"]

**Red Flag 5 — Pass-Through Methods**
Scan for: methods that do nothing except forward arguments to another method with the
same signature; layers of indirection that contribute nothing to the abstraction.
- Finding: [specific finding with file:function, OR "not applicable, because [reason]"]

**Red Flag 6 — Repetition**
Scan for: the same code pattern, logic, or sequence appearing in multiple places; the
same sequence of method calls on the same type in multiple functions; the same match
arm logic in multiple match expressions.
- Finding: [specific finding with file:function, OR "not applicable, because [reason]"]

**Red Flag 7 — Special-General Mixture**
Scan for: general-purpose modules containing special-case logic for a specific caller;
boolean parameters that activate caller-specific behaviour inside a general module.
- Finding: [specific finding with file:function, OR "not applicable, because [reason]"]

**Red Flag 8 — Conjoined Methods**
Scan for: two methods that can only be used correctly together and in a specific order;
required call sequences that could be encapsulated; runtime ordering constraints that
should be compile-time constraints.
- Finding: [specific finding with file:function, OR "not applicable, because [reason]"]

**Red Flag 9 — Comment Repeats Code**
Scan for: comments that describe what the code does in the same terms as the code itself;
doc comments that restate the function name; inline comments that merely translate code
to English.
- Finding: [specific finding with file:function, OR "not applicable, because [reason]"]

**Red Flag 10 — Implementation Documentation Contaminates Interface**
Scan for: public doc comments that describe how a function works internally rather than
what it guarantees to callers; doc comments that mention internal data structures,
algorithms, or implementation steps.
- Finding: [specific finding with file:function, OR "not applicable, because [reason]"]

**Red Flag 11 — Vague Name**
Scan for: names that could apply to many different things in the codebase: `Manager`,
`Handler`, `Processor`, `Helper`, `Utils`, `Data`, `Info`, `Item`, `Object`, `Thing`.
- Finding: [specific finding with file:function, OR "not applicable, because [reason]"]

**Red Flag 12 — Hard to Describe**
Scan for: modules or functions that cannot be described in one sentence without "and";
items whose responsibility cannot be stated as a single purpose.
- Finding: [specific finding with file:function, OR "not applicable, because [reason]"]

**Red Flag 13 — Nonobvious Code**
Scan for: code whose behaviour cannot be understood by reading it once; functions that
mutate via interior mutability without obvious call-site indication; `Default`
implementations with non-obvious sentinel values; `From`/`Into` implementations that
validate or can panic; boolean parameters where true/false meanings are unclear at the
call site.
- Finding: [specific finding with file:function, OR "not applicable, because [reason]"]

### Step 4 — Resolve findings

For each Red Flag found to be present:
1. State which file and function contains it
2. State which Red Flag it triggers and why
3. Fix it before the session ends
4. If the fix requires a structural change large enough to be its own session, record it
   as a design debt item in `<project>/SESSIONS.md` with a clear description of what needs to change

### Step 5 — Record in session log

In the `<project>/SESSIONS.md` entry for this session, add a "Red Flag Audit" section:
```
**Red Flag Audit:**
- Ran review-for-red-flags against: [list files]
- Findings: [none / list of findings and resolutions]
- Design debt recorded: [none / list of deferred items]
```
