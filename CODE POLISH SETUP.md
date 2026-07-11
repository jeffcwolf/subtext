# Polish Kit — Setup & Usage

> **What this is:** A portable quality engineering kit. Drop it into any project to
> give a coding agent the standards, review skills, and project infrastructure needed
> to produce professional-quality output — not just code that works, but code that
> demonstrates engineering judgement.
>
> **What this is not:** A framework, a build tool, or a runtime dependency. These are
> documents that agents read and procedures they follow. Nothing here runs as code.

---

## Quick Start: Adding the Kit to a Project

### 1. Copy the kit into your project root

```bash
# From the directory containing this kit:
cp -r docs/ /path/to/your-project/docs/
cp -r skills/ /path/to/your-project/skills/
cp LICENSE /path/to/your-project/LICENSE
```

### 2. Configure for your language

**Hybrid project (Rust + Python) — most common case:**
```bash
# CI — both languages checked in parallel jobs
mkdir -p /path/to/your-project/.github/workflows
cp templates/ci-hybrid.yml /path/to/your-project/.github/workflows/ci.yml

# .gitignore — merge both; Rust and Python artifacts differ
cat templates/gitignore-rust templates/gitignore-python | sort -u > /path/to/your-project/.gitignore
```
Keep both `rust-specifics.md` and `python-specifics.md` in `docs/standards/`.

**Rust-only project:**
```bash
mkdir -p /path/to/your-project/.github/workflows
cp templates/ci-rust.yml /path/to/your-project/.github/workflows/ci.yml
cp templates/gitignore-rust /path/to/your-project/.gitignore
```

**Python-only project:**
```bash
mkdir -p /path/to/your-project/.github/workflows
cp templates/ci-python.yml /path/to/your-project/.github/workflows/ci.yml
cp templates/gitignore-python /path/to/your-project/.gitignore
```

### 3. Configure per-project details

**LICENSE:** Already set to MIT with your name. If a project was started in an
earlier year, update the copyright year:
```
Copyright (c) 2024 Jeffrey C. Wolf
```

**CI:** Open `.github/workflows/ci.yml` and verify:
- The Rust toolchain channel is correct (stable/nightly)
- The Python version in `pyproject.toml` `requires-python` is correct (`uv`
  reads this automatically — no version hardcoded in CI)
- For hybrid projects: both the `rust` and `python` jobs are present
- For single-language projects: delete the job you don't need

**README:** If the project doesn't have a README, copy `templates/README-template.md`
to the project root as `README.md` and fill it in. If it has a README, check it
against the template's sections.

**Cargo.toml / pyproject.toml:** Add the license field if not present:
```toml
# Cargo.toml
license = "MIT"

# pyproject.toml
[project]
license = "MIT"
```

mkdir -p /path/to/your-project/.claude/commands
cp -r commands/polish /path/to/your-project/.claude/commands/polish


### 4. Verify the setup

```bash
cd /path/to/your-project

# Does it build?
cargo build              # Rust
uv sync                  # Python (installs all deps from uv.lock)

# Do the tests pass?
cargo test               # Rust
uv run pytest            # Python

# Does the linter pass?
cargo clippy -- -D warnings      # Rust
uv run ruff check .               # Python

# Is formatting consistent?
cargo fmt --check         # Rust
uv run ruff format --check .  # Python
```

If any of these fail, fix them before running the review skills. The skills assume
a working, compilable codebase.

---

## The Review Sequence

Run these skills in order. Each pass may surface work that affects subsequent
passes, so the order matters.

```
Pass 1 │ review-for-red-flags  │ Fix structural problems first
Pass 2 │ naming-review         │ Fix the surface once structure is stable
Pass 3 │ review-testing        │ Verify contracts are actually tested
Pass 4 │ review-docs           │ Document the final interfaces
Pass 5 │ review-project-readiness │ README, CI, license, git hygiene
```

### How to run a skill

Tell your coding agent to load and execute the skill. The exact phrasing depends
on the agent, but the pattern is:

```
Read skills/review-for-red-flags.md and execute the full procedure
against this project's codebase. Work through every step. Do not skip
steps. Record findings as specified in the skill.
```

For skills that reference standards files, the agent should load those too:

```
Read docs/standards/ousterhout.md and then execute
skills/review-for-red-flags.md against this codebase.
```

### Standards → Skills reference

| Skill | Loads these standards |
|---|---|
| review-for-red-flags | `docs/standards/ousterhout.md` |
| naming-review | `docs/standards/readable-code.md` Part I, language-specifics Part IV |
| review-testing | Language-specifics (testing sections) |
| review-docs | `docs/standards/ousterhout.md` (Red Flags), `docs/standards/readable-code.md` (Part II) |
| review-project-readiness | None (self-contained) |

---

## Per-Project Checklist

Use this checklist to track progress across your projects. Copy it into a tracking
document or use it as-is.

### Project: _______________

**Language:** [ ] Rust  [ ] Python  [ ] Mixed

**Setup:**
- [ ] `docs/standards/` copied in
- [ ] `skills/` copied in
- [ ] `LICENSE` in place (MIT, correct year)
- [ ] `.github/workflows/ci.yml` configured and passing
- [ ] `.gitignore` covers language artifacts and IDE/OS files
- [ ] `Cargo.toml` / `pyproject.toml` has license, repository, version fields
- [ ] README has: title, motivation, installation, usage, status, license sections

**Review passes:**
- [ ] Pass 1: `review-for-red-flags` — findings resolved or recorded as design debt
- [ ] Pass 2: `naming-review` — all new/modified names pass misunderstanding test
- [ ] Pass 3: `review-testing` — contract coverage verified, test names describe behaviour
- [ ] Pass 4: `review-docs` — doc coverage complete, quality verified, doctests pass
- [ ] Pass 5: `review-project-readiness` — five-minute test passed

**Final gate:**
- [ ] CI is green
- [ ] `git log --oneline -10` shows meaningful commit messages
- [ ] No secrets in git history
- [ ] No TODO/FIXME without issue references
- [ ] No commented-out code
- [ ] No `#[allow(dead_code)]` / `# noqa` on genuinely dead code

---

## What Does Not Go in the Kit

The following are project-specific and should not be templated:

- **SESSIONS.md** — each project's session log is its own history
- **ARCHITECTURE.md** — each project's architecture is unique
- **CHANGELOG.md** — create one per project when you start tagging releases
- **CONTRIBUTING.md** — add if/when the project accepts external contributions

---

## Adapting the Kit

### Adding a new language

To support a language beyond Rust and Python:

1. Create `docs/standards/<language>-specifics.md` following the structure of
   the existing language files: types, errors, naming, testing, organisation,
   and a checklist
2. Create a CI template in `templates/ci-<language>.yml`
3. Create a gitignore template in `templates/gitignore-<language>`
4. Update `review-testing.md` and `review-docs.md` with language-specific
   commands if they differ from the Rust/Python examples

### Adding a new skill

Follow the existing skill format:
1. Header with "When to invoke" and "Load" references
2. "What This Skill Checks" section explaining the rationale
3. Numbered procedure steps, each with concrete checks
4. Final "Record in session log" step with a template

Place the new skill in `skills/` and add it to the review sequence in this
document at the appropriate position.
