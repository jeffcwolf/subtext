---
description: Run the full code-polish review — all five passes, in order
---
Run the complete code-polish review on this project, in this exact order.
After each pass, summarise findings and wait for my go-ahead before the next —
each pass can surface work that affects later ones.

First make the project green — build, tests, linter, and formatter all passing — fixing any failures before starting Pass 1. Then, in order:

1. Load `docs/standards/ousterhout.md`, then run `skills/review-for-red-flags.md` in full.
2. Load `docs/standards/readable-code.md` (Part I) + the naming section of the relevant `docs/standards/*-specifics.md`, then run `skills/naming-review.md`.
3. Load the testing sections of the relevant `docs/standards/*-specifics.md`, then run `skills/review-testing.md`.
4. Load `docs/standards/ousterhout.md` (Red Flags) + `docs/standards/readable-code.md` (Part II), then run `skills/review-docs.md`.
5. Run `skills/review-project-readiness.md` (self-contained).

Work through every step of each skill; do not skip steps.