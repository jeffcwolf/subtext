# Skill: review-project-readiness

> **When to invoke:** Before publishing a project to a portfolio, making a repository
> public, or submitting code as part of a job application. This is the final gate —
> run it after all other review skills have passed.
> **Load:** No standards file required. This skill checks project-level presentation
> and infrastructure that sits above the code itself.

---

## What This Skill Checks

A hiring manager or senior engineer evaluating a portfolio project will spend less
than five minutes on it. In that time they will: read the README, check for a CI
badge, glance at the code structure, look at a few files, and check the commit
history. This skill ensures that those five minutes produce the right impression —
not that the code is perfect, but that the developer thinks carefully about their
work and maintains it professionally.

This skill checks six things:

1. **README** — does the project explain itself?
2. **CI** — does the project verify itself?
3. **Licensing and metadata** — is the project properly identified?
4. **Dependency hygiene** — is the project responsibly maintained?
5. **Formatting and lint** — is the project consistently presented?
6. **Git hygiene** — does the project's history reflect care?

---

## Procedure

### Step 1 — README audit

The README is the first thing anyone sees. It must answer three questions in under
thirty seconds of reading: **what** is this, **why** does it exist, and **how** do I
use it.

**Required sections:**

- [ ] **Title and one-line description.** What the project is, in one sentence. Not
      what it does internally — what problem it solves for the user.
- [ ] **Motivation or context.** Why this project exists. One paragraph is sufficient.
      For a portfolio project, this is where you demonstrate that you understood the
      problem before writing code.
- [ ] **Installation or setup.** How to get it running. Exact commands. If there are
      prerequisites (Rust toolchain, Python version, system dependencies), list them.
- [ ] **Usage.** At least one concrete example. A CLI tool needs a command with
      expected output. A library needs a code snippet. A web app needs either a
      screenshot or a link to a live instance.
- [ ] **Project status.** Is this in active development, stable, or a prototype?
      Employers understand prototypes — they do not understand ambiguity about what
      stage a project is in.

**Recommended but not required:**

- Architecture overview (one paragraph or a simple diagram for complex projects)
- Contributing guidelines (even a one-liner: "Issues and PRs welcome")
- Acknowledgements or references (especially for academic-adjacent projects)

**What to avoid:**

- Auto-generated README content that has not been edited
- Placeholder sections ("TODO: add usage examples")
- Excessive badges that obscure the content
- Marketing language ("revolutionary", "blazing fast", "next-generation")

---

### Step 2 — CI pipeline

CI is the mechanical enforcement layer. The review skills are the judgement layer;
CI automates the subset of those checks that can run without human evaluation. A
green CI badge signals to any visitor that the code at least builds and passes its
own tests.

**Minimum viable CI (GitHub Actions):**

Most projects use both Rust (web app) and Python (data pipeline). The hybrid
template runs both checks as parallel jobs:

**Hybrid Rust + Python — `.github/workflows/ci.yml`:**
```yaml
name: CI
on: [push, pull_request]

env:
  CARGO_TERM_COLOR: always

jobs:
  rust:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
        with:
          components: rustfmt, clippy
      - run: cargo fmt --check
      - run: cargo clippy --workspace -- -D warnings
      - run: cargo test --workspace
      # Doc correctness (broken intra-doc links, doctests). Library crates that
      # require a doc comment on every public item append `-D missing_docs`.
      - run: RUSTDOCFLAGS="-D warnings" cargo doc --no-deps --workspace

  python:
    runs-on: ubuntu-latest
    # If the uv project lives in a subfolder (e.g. pipeline/), scope the run
    # steps to it: defaults: { run: { working-directory: pipeline } }
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv sync
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run pytest -q
```

For Rust-only or Python-only projects, use the single-language templates in
`templates/` — they contain one job each, following the same pattern.

**What CI must include:**
- [ ] Build/compile step
- [ ] Lint check (`cargo clippy` / `uv run ruff check`)
- [ ] Format check (`cargo fmt --check` / `uv run ruff format --check`)
- [ ] Test suite (`cargo test` / `uv run pytest`)

**What CI should include (if the project warrants it):**
- [ ] Doc presence enforced for library crates (`RUSTDOCFLAGS="-D warnings -D missing_docs"`)
- [ ] Security audit (`cargo audit` / `uv run pip-audit`)
- [ ] Type checking for Python (`uv run mypy --strict` or `pyright`)

**What CI should not include (for portfolio projects):**
- Coverage thresholds (coverage is a diagnostic, not a gate)
- Deployment steps (unless the project is actually deployed)
- Complex matrix builds across many OS/version combinations (one target is fine)

**After setting up CI:**
- [ ] Add a badge to the README: `![CI](https://github.com/USER/REPO/actions/workflows/ci.yml/badge.svg)`
- [ ] Verify the badge is green. A red badge is worse than no badge.

---

### Step 3 — License and metadata

**License:**
- [ ] A `LICENSE` or `LICENSE.md` file exists in the repository root
- [ ] The license is a recognised open-source license (MIT, Apache-2.0, GPL-3.0,
      etc.) — not "License TBD"
- [ ] The license is referenced in `Cargo.toml` (`license = "MIT"`) or
      `pyproject.toml` (`license = "MIT"`)

If you are unsure which license to use: MIT is the simplest and most permissive.
Apache-2.0 adds patent protection. For academic projects, both are common and
appropriate.

**Metadata:**
- [ ] `Cargo.toml` or `pyproject.toml` has accurate `name`, `version`,
      `description`, `authors`, and `license` fields
- [ ] For Rust: `repository` field points to the GitHub URL
- [ ] For Python: `[project.urls]` includes the repository URL
- [ ] Version follows semantic versioning. Pre-1.0 projects use `0.x.y`.
      Do not use `0.0.1` indefinitely — increment the version as you ship.

---

### Step 4 — Dependency hygiene

**Rust:**
- [ ] `Cargo.lock` is committed for binary/application projects (not for libraries)
- [ ] `cargo update --dry-run` does not show critically outdated dependencies
- [ ] `cargo audit` reports no known vulnerabilities (install with
      `cargo install cargo-audit` if needed)
- [ ] No unused dependencies: `cargo machete` or manual review of `Cargo.toml`

**Python (uv):**
- [ ] Dependencies are specified in `pyproject.toml` and locked in `uv.lock`
- [ ] `uv.lock` is committed to version control
- [ ] `uv run pip-audit` reports no known vulnerabilities
- [ ] No unused dependencies in the dependency list
- [ ] Dev dependencies are separated from runtime dependencies
      (`uv add --dev` places them under `[tool.uv]` dev-dependencies)

---

### Step 5 — Formatting and lint

This is not about style preferences. It is about consistency. A codebase where some
files use tabs and others use spaces, or where half the functions have type hints and
half do not, signals that no one is paying attention.

**Rust:**
- [ ] `cargo fmt --check` passes with no changes needed
- [ ] `cargo clippy --workspace -- -D warnings` passes with no warnings
- [ ] No `#[allow(dead_code)]` or `#[allow(unused)]` on items that are genuinely
      dead — delete the dead code instead of suppressing the warning

**Python:**
- [ ] `uv run ruff check .` passes
- [ ] `uv run ruff format --check .` passes
- [ ] No `# noqa` comments suppressing warnings on code that should be fixed
- [ ] `# type: ignore` comments are rare and each has a justification

**Both languages:**
- [ ] No TODO or FIXME comments that have been there for more than one release cycle.
      Either do the TODO, create an issue for it and reference the issue number in the
      comment, or delete it.
- [ ] No commented-out code. If it might be needed later, it is in version control
      history. Delete it from the current source.

---

### Step 6 — Git hygiene

**Repository basics:**
- [ ] `.gitignore` exists and covers the language's standard artifacts
      (Rust: `/target`; Python: `__pycache__`, `*.pyc`, `.venv`, `*.egg-info`)
- [ ] No build artifacts, IDE config files (`.vscode/`, `.idea/`), or OS files
      (`.DS_Store`, `Thumbs.db`) are tracked
- [ ] No secrets, API keys, tokens, or credentials in the repository — including
      in the git history. Run a scan: `git log --all -p | grep -iE "(api.key|token|secret|password)" | head -20`
      (or use a dedicated tool like `gitleaks` or `trufflehog`)
- [ ] No large binary files (images, datasets, compiled artifacts) committed to git.
      If the project needs test data, keep it small or use git-lfs.

**Commit history:**
- [ ] Recent commits have meaningful messages that describe what changed and why —
      not "fix", "update", "wip", "stuff", or "asdf"
- [ ] Commits are reasonably atomic — one logical change per commit, not a single
      commit with 50 files changed across unrelated concerns

A hiring manager will not read your full commit history, but they will glance at the
last 5-10 commits. Those commits should look intentional.

---

### Step 7 — The five-minute test

This is the meta-check. Clone the repository fresh into a temporary directory (or
ask a friend to) and attempt to:

1. **Understand what the project does** by reading the README (< 30 seconds)
2. **Install/build it** by following the README instructions (< 2 minutes)
3. **Run the tests** (< 1 minute)
4. **See it work** — run the CLI, open the web app, execute the example (< 2 minutes)

If any of these steps fails or requires knowledge not in the README, fix the README.
The project must be self-contained enough that someone with the right toolchain
installed can go from clone to working in under five minutes.

---

### Step 8 — Record in session log

```
**Project Readiness Review:**
- README: [complete / missing sections: list]
- CI: [passing / not set up / failing: reason]
- License: [present and valid / missing / TBD]
- Dependencies: [clean / audit findings: list]
- Formatting: [clean / fixes applied: count]
- Git hygiene: [clean / findings: list]
- Five-minute test: [passed / failed at step: which]
```
