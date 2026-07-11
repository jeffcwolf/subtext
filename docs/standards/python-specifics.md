# docs/standards/python-specifics.md
# Python-Specific Design Standards

> **Scope:** Python applications of the principles in `docs/standards/ousterhout.md` and
> `docs/standards/readable-code.md`. This file does not repeat those principles — it shows how they
> manifest in Python idioms and what Python-specific violations look like.
> **Usage:** Load this file for all Python implementation work, alongside whichever of
> the parent standards files is relevant to the task.

---

## Part I — Types and Data Structures

Python's type system is optional, which makes deliberate use of it a stronger signal
of engineering quality. Type hints, dataclasses, and enums are the primary tools for
Ousterhout's "define errors out of existence" — not because Python enforces them at
runtime, but because they communicate intent, enable tooling (mypy, pyright), and
prevent the class of bugs where a function silently accepts the wrong kind of data.

---

### Rule: Use Type Hints on All Public Functions

Every public function must have type annotations for all parameters and the return
type. This is both documentation and a mechanical check — `mypy --strict` or
`pyright` will catch mismatches that testing might miss.

```python
# UNTYPED: caller must read the implementation to know what to pass
def parse_citation(path):
    ...

# TYPED: the contract is in the signature
def parse_citation(path: Path) -> CitationMetadata:
    ...

# TYPED WITH ERROR: caller knows this can fail and how
def parse_citation(path: Path) -> CitationMetadata:
    """
    Raises:
        FileNotFoundError: if the file does not exist.
        CitationError: if the file is not valid CFF.
    """
    ...
```

Internal/private functions (single underscore prefix) should also have type hints,
but this is a should, not a must.

---

### Rule: Use Dataclasses or NamedTuples for Structured Data

Plain dictionaries with string keys are the Python equivalent of the Shallow Module
Red Flag — they hide nothing, enforce nothing, and expose everything.

```python
# UNSTRUCTURED: no validation, no autocompletion, typos in keys are silent
def load_config(path: str) -> dict:
    return json.loads(Path(path).read_text())

config = load_config("config.json")
name = config["projct_name"]  # typo — KeyError at runtime, not at write time

# STRUCTURED: fields are explicit, defaults are documented, typos are caught
@dataclass(frozen=True)
class ProjectConfig:
    project_name: str
    output_dir: Path
    tag: str | None = None

    @classmethod
    def from_file(cls, path: Path) -> "ProjectConfig":
        raw = json.loads(path.read_text())
        return cls(**raw)
```

Use `frozen=True` on dataclasses unless mutation is genuinely needed. Immutable data
structures are easier to reason about and prevent a class of bugs where shared
references are modified unexpectedly.

Use `NamedTuple` for lightweight, immutable value types that don't need methods:
```python
class SearchResult(NamedTuple):
    score: float
    document_id: str
    snippet: str
```

---

### Rule: Use Enums for Closed Sets of Values

String constants scattered through code are the Python equivalent of boolean parameters
— they are non-obvious at every use site and introduce silent bugs when misspelled.

```python
# STRINGLY-TYPED: typos are silent, no autocompletion, no exhaustiveness check
def set_mode(mode: str) -> None:
    if mode == "sandbox":
        ...
    elif mode == "production":
        ...

set_mode("sandox")  # typo — silently does nothing

# ENUM: typos are caught, autocompletion works, exhaustiveness is visible
class Mode(Enum):
    SANDBOX = "sandbox"
    PRODUCTION = "production"

def set_mode(mode: Mode) -> None:
    match mode:
        case Mode.SANDBOX: ...
        case Mode.PRODUCTION: ...
```

---

### Rule: Use `NewType` for Type Safety Where Confusion Is Possible

Python's `typing.NewType` creates a distinct type at the type-checker level without
runtime overhead. Use it when two values share the same underlying type but must not
be confused.

```python
from typing import NewType

UserId = NewType("UserId", str)
DepositId = NewType("DepositId", str)

def upload_file(deposit_id: DepositId, filename: str) -> None: ...

# A type checker will flag this:
user: UserId = UserId("abc")
upload_file(user, "data.csv")  # type error: expected DepositId, got UserId
```

Note: `NewType` provides no runtime validation. For values that need validation on
construction, use a dataclass or a class with a factory method.

---

## Part II — Error Handling

---

### Rule: Define Custom Exception Hierarchies for Libraries

A library that raises only `ValueError` and `RuntimeError` is the Python equivalent
of Rust's `anyhow` in a library crate — it prevents callers from handling specific
errors programmatically.

```python
# UNSTRUCTURED: caller cannot distinguish errors without parsing the message string
def parse_citation(path: Path) -> CitationMetadata:
    if not path.exists():
        raise ValueError(f"File not found: {path}")
    # ...
    raise ValueError("Invalid YAML")

# STRUCTURED: caller can catch specific conditions
class CitationError(Exception):
    """Base exception for citation parsing."""
    pass

class CitationNotFound(CitationError):
    def __init__(self, path: Path):
        self.path = path
        super().__init__(f"CITATION.cff not found at {path}")

class InvalidCitationYaml(CitationError):
    def __init__(self, path: Path, detail: str):
        self.path = path
        self.detail = detail
        super().__init__(f"Invalid YAML in {path}: {detail}")
```

**The rule:** library modules define a base exception class and specific subclasses.
Application/script code may use `ValueError`, `RuntimeError`, etc. directly.

---

### Rule: Exception Messages Must Be Diagnosable

Same principle as Rust's error context rule: every exception message must contain
enough information to diagnose the problem without reading source code.

```python
# USELESS
raise ValueError("Validation failed")

# DIAGNOSABLE
raise ValueError(
    f"Field 'title' in {path} is empty but must be non-empty per CFF 1.2.x"
)
```

---

### Rule: Never Use Bare `except:`

A bare `except:` catches `SystemExit`, `KeyboardInterrupt`, and `GeneratorExit` —
conditions that should almost never be silently swallowed. At minimum, catch
`Exception`. In most cases, catch the specific exception types you expect.

```python
# DANGEROUS: swallows KeyboardInterrupt, SystemExit
try:
    result = compute()
except:
    log.error("Something went wrong")

# ACCEPTABLE: catches expected errors specifically
try:
    result = compute()
except (ValueError, IOError) as e:
    log.error("Computation failed: %s", e)

# ACCEPTABLE: catches all non-system exceptions when genuinely needed
try:
    result = compute()
except Exception as e:
    log.error("Unexpected error in computation: %s", e)
    raise  # re-raise after logging
```

---

### Rule: Log or Raise, Never Both Silently

If you catch an exception and log it, either re-raise it or handle it completely.
Logging and swallowing is almost always a bug — the caller believes the operation
succeeded when it did not.

---

## Part III — Naming Conventions

Python naming conventions are established by PEP 8. These rules supplement PEP 8
with the ARC principles from `docs/standards/readable-code.md`.

---

### Rule: Follow PEP 8 Naming Conventions

| Item | Convention | Example |
|---|---|---|
| Module | `snake_case` | `citation_parser.py` |
| Class | `PascalCase` | `CitationMetadata` |
| Function/method | `snake_case` | `parse_citation()` |
| Variable | `snake_case` | `output_dir` |
| Constant | `SCREAMING_SNAKE_CASE` | `MAX_FILE_SIZE` |
| Private | `_leading_underscore` | `_validate_field()` |
| "Truly private" | `__double_underscore` | Almost never needed; avoid |

---

### Rule: `__all__` Controls the Public API

Every module that is imported from outside its package should define `__all__`.
This is the Python equivalent of Rust's `pub` vs. `pub(crate)` — it makes the
public/private boundary explicit rather than leaving it to convention.

```python
# At the top of the module, immediately after imports:
__all__ = [
    "parse_citation",
    "CitationMetadata",
    "CitationError",
]
```

Items not in `__all__` are internal. A user who imports them is reaching past the
public API and should expect breakage.

---

### Rule: Factory Methods Use `from_*` Naming

Class methods that construct an instance from a specific input type should follow
the `from_*` convention, matching Python's existing patterns (`dict.fromkeys`,
`datetime.fromtimestamp`).

```python
class CitationMetadata:
    @classmethod
    def from_file(cls, path: Path) -> "CitationMetadata": ...

    @classmethod
    def from_yaml(cls, raw: str) -> "CitationMetadata": ...

    @classmethod
    def from_dict(cls, data: dict) -> "CitationMetadata": ...
```

---

### Rule: Boolean Parameters Use Keyword-Only Arguments

Boolean parameters in Python have the same call-site readability problem as in Rust.
Make them keyword-only to force the name to appear at every call site.

```python
# NONOBVIOUS: what does True mean?
publish(config, True, False)

# SELF-DOCUMENTING: keyword-only parameters (after the *)
def publish(config: Config, *, sandbox: bool = False, dry_run: bool = False) -> None:
    ...

publish(config, sandbox=True, dry_run=False)
```

---

## Part IV — Testing

---

### Rule: Use pytest, Not unittest

`pytest` is the standard. Its assertion introspection, fixture system, and
parametrize decorator produce cleaner, more maintainable tests than `unittest`'s
class-based approach.

```python
# AVOID: unittest style
class TestParser(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse("input"), expected)

# PREFER: pytest style
def test_parse_citation_returns_metadata_for_valid_input():
    result = parse_citation(VALID_CFF_PATH)
    assert result.title == "My Project"
```

---

### Rule: Test Names Describe Behaviour

Same principle as Rust. Test names are specifications.

```python
# IMPLEMENTATION-FOCUSED (bad)
def test_parse(): ...
def test_error(): ...
def test_validation_1(): ...

# BEHAVIOUR-FOCUSED (good)
def test_parse_citation_returns_metadata_for_valid_cff(): ...
def test_parse_citation_raises_citation_not_found_for_missing_file(): ...
def test_empty_title_field_raises_missing_field_error(): ...
```

---

### Rule: Use Fixtures for Setup, Not Repeated Code

If multiple tests need the same setup (temporary directories, sample data, mock
objects), extract it to a pytest fixture in `conftest.py`.

```python
# conftest.py
@pytest.fixture
def sample_cff_path(tmp_path: Path) -> Path:
    cff = tmp_path / "CITATION.cff"
    cff.write_text(VALID_CFF_CONTENT)
    return cff

# test_parser.py
def test_parse_citation_returns_title(sample_cff_path: Path):
    result = parse_citation(sample_cff_path)
    assert result.title == "My Project"
```

---

### Rule: Use `pytest.raises` With Match for Error Path Tests

Error-path tests must verify the specific exception type and, where relevant, the
message content. `pytest.raises` without `match` only checks the type.

```python
def test_missing_file_raises_citation_not_found():
    with pytest.raises(CitationNotFound, match="not found"):
        parse_citation(Path("/nonexistent/CITATION.cff"))
```

---

## Part V — Module Organisation

---

### Rule: One Module, One Responsibility

Same principle as Ousterhout. A Python module (`.py` file) should have one clear
responsibility, statable in one sentence without "and".

---

### Rule: Use `pyproject.toml` for Project Configuration

`pyproject.toml` is the standard for Python project metadata, build configuration,
and tool settings. Do not use `setup.py` or `setup.cfg` for new projects.

All tool configuration (`pytest`, `ruff`, `mypy`, `black`) should live in
`pyproject.toml` under the appropriate `[tool.*]` section, not in separate config
files.

---

### Rule: Use `uv` for Dependency Management

`uv` is the default Python package manager for these projects. It handles virtual
environment creation, dependency resolution, and lockfile generation in a single
tool.

```bash
uv init              # new project: creates pyproject.toml and uv.lock
uv add <package>     # add a dependency
uv add --dev <pkg>   # add a dev dependency (ruff, pytest, mypy, etc.)
uv sync              # install all dependencies from uv.lock
uv run <command>     # run a command inside the managed environment
```

**Application/script projects:** commit `uv.lock` to version control. It pins
exact versions for reproducible installs. `uv sync` restores the exact environment.

**Library projects:** use version ranges (`>=1.0,<2.0`) in `pyproject.toml`. Let
the consuming application resolve exact versions. Still commit `uv.lock` for your
own development reproducibility, but downstream users will not use it.

**Note:** `pip` still works inside a `uv`-managed environment (`uv run pip install ...`)
for cases where a package needs special handling. Prefer `uv add` for all normal
dependency management.

---

## Part VI — The Python Standards Checklist

Apply after writing any non-trivial Python code in a session.

**Types:**
- [ ] Do all public functions have type annotations for parameters and return type?
- [ ] Are structured data types using dataclasses or NamedTuples, not plain dicts?
- [ ] Are closed sets of values using Enums, not string constants?
- [ ] Are confusable values distinguished with NewType or distinct classes?

**Errors:**
- [ ] Do library modules define a custom exception hierarchy?
- [ ] Does every exception message carry enough context to diagnose without source?
- [ ] Are there any bare `except:` clauses? (Must be `except Exception:` at minimum)
- [ ] Are caught exceptions either re-raised or fully handled, never silently swallowed?

**Naming:**
- [ ] Does the module define `__all__` listing its public API?
- [ ] Do factory methods follow `from_*` naming?
- [ ] Are boolean parameters keyword-only (`*` in the signature)?
- [ ] Do test names describe behaviour, not implementation?

**Organisation:**
- [ ] Is `pyproject.toml` the single source of project metadata and tool config?
- [ ] Are dependencies pinned appropriately for the project type?
- [ ] Do tests mirror the source structure (`src/x.py` → `tests/test_x.py`)?
- [ ] Are shared fixtures in `conftest.py`?

**Tooling (must pass before session ends):**
- [ ] `uv run ruff check .` — no lint errors
- [ ] `uv run ruff format --check .` — formatting is consistent
- [ ] `uv run mypy --strict .` or `pyright` — no type errors (if type checking is adopted)
- [ ] `uv run pytest` — all tests pass
