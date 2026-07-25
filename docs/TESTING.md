# Testing

```bash
pip install pytest "markitdown[all]"
python -m pytest tests/ -q
```

## What the suite covers

| Area | Cases |
| :-- | :-- |
| Path detection | quoted, unquoted, `@`-mentions, relative paths, deduplication, unlisted extensions, missing files, platform-specific drive rewriting |
| Page counting | 1/2/5-page documents, unreadable input |
| Grading | empty, whitespace-only, sparse, healthy, configurable threshold, short non-PDF acceptance, size fallback |
| Discovery | explicit override, plugin option beating plain environment |
| Input parsing | plain JSON and UTF-8 BOM |
| Cache | zero-byte pruning, key stability, reuse of good results, rejection of stale empties |
| End to end | text PDF converts, image-only PDF is refused, sparse PDF is refused, mixed batches report per file, missing markitdown is announced |

The negative cases carry the most weight. An image-only PDF must not be reported
as converted, must not leave a cached artifact, and must not be described to
Claude as an empty document — those are the behaviours that fail silently in
production, so they are asserted explicitly rather than implied.

## Fixtures are synthesised, never shipped

`tests/pdfgen.py` builds valid PDFs byte by byte in pure Python:

- `text_pdf(pages)` — a real text layer, ~674 chars/page
- `image_only_pdf()` — drawn shapes, zero extractable text
- `sparse_pdf()` — a real but far too thin text layer, ~25 chars/page

Those land either side of the 100 chars/page threshold, matching the real
documents measured in [DESIGN.md](DESIGN.md).

Two reasons for building them rather than committing samples. Publishing real
documents publishes whatever they contain, and the bug was found in personal
files. And hand-built PDFs need no `reportlab`, so the suite runs on a bare CI
image with nothing but `pytest` installed.

`image_only_pdf()` reproduces the original failure exactly: markitdown exits 0
and writes 0 bytes.

## Skips are meaningful

Tests requiring markitdown or pdfminer skip cleanly when those are absent, so
the suite passes on a bare interpreter (29 passed, 7 skipped) as well as a full
install (35 passed, 1 skipped on Windows).

Because a skip proves nothing, CI installs `markitdown[all]` and asserts the
import succeeds *before* running the suite — otherwise a broken dependency would
look like a green build full of quiet skips.

One test is platform-gated in both directions: Git Bash renders `C:\Users\x` as
`/c/Users/x`, so the hook rewrites that form on Windows. On Linux and macOS
`/c/...` is a legitimate path and rewriting it would break real lookups, so each
platform asserts the behaviour the other must not have.

## CI

`.github/workflows/ci.yml` runs four jobs:

- **tests** — the suite on Windows, macOS and Linux against Python 3.10 and 3.12
- **no-markitdown** — the suite on a bare interpreter, proving honest degradation
- **lint** — `py_compile`, plus an import check on an interpreter with no dependencies
- **manifests** — JSON validity, version agreement across manifests, and hook shape (exec form, `CLAUDE_PLUGIN_ROOT`, timeout above the per-file budget)
