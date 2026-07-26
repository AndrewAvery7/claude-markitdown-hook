# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- CI also runs on a weekly schedule (Mondays), not only on pushes. The suite
  installs the latest markitdown release, so upstream breakage surfaces within
  a week even when this repository is untouched — and the public Actions
  history becomes a living record that the tests keep passing, not a snapshot
  of the last push.

### Fixed

- `docs/TESTING.md` reported test counts from before the `--doctor` work landed
  (35/1 full install, 29/7 bare) and described four CI jobs. Re-measured: 40
  passed and 1 skipped with a full install, 34 passed and 7 skipped on a bare
  interpreter, across five jobs. The doctor's own six tests had no entry in the
  coverage table. A project whose entire argument is "measure it, don't assert
  it" cannot ship stale numbers in its own documentation.

## [1.1.0] — 2026-07-25

### Added

- **`--doctor`.** One command reporting everything the troubleshooting guide
  previously asked you to check by hand: which interpreter is running, whether
  markitdown resolved and how, whether pdfminer is present, whether the cache is
  writable, and every configuration value in effect along with what set it.
  Exits `0` when the hook can do its job and `1` when it cannot, so it works in
  a script — and it runs on a bare interpreter, where reporting what is missing
  is the entire point.
- **`--version`.**
- CI now runs the doctor on all three platforms as a genuine smoke test of
  discovery, imports and cache access, and asserts it fails loudly with an
  actionable fix when markitdown is absent.
- CI checks the engine's `__version__` against both manifests. The doctor prints
  it, so drift would mislead anyone reporting a bug.
- `dependabot.yml` keeps the workflow actions current. Left alone they rot
  quietly: a pinned major eventually loses its runtime and the badge goes red
  without anyone touching the code.

### Changed

- Workflow actions moved to `actions/checkout@v7` and `actions/setup-python@v7`.
  The previous pins were being force-migrated off a deprecated Node runtime.
- `docs/TROUBLESHOOTING.md` now leads with the doctor instead of hand-run
  Python snippets.

## [1.0.0] — 2026-07-25

First public release.

### Added

- **Yield-based grading.** Every conversion is scored on the text it actually
  recovered rather than on markitdown's exit code, which is `0` even when
  extraction returns nothing. PDFs are measured in characters per page against a
  configurable threshold (default 100); other formats are rejected only at zero
  characters, so a one-line email or a short voice memo still converts.
- **Honest reporting of image-based PDFs.** A PDF with no text layer produces no
  `.md` and no success message. Claude is told the document is image-based, that
  no conversion exists, and to read the original with vision instead.
- **Pointer injection.** The hook injects a path and a size into context, never
  the document text, so referencing a large document costs almost nothing until
  its contents are actually needed.
- **Cross-platform markitdown discovery** — explicit setting, then `PATH`, then
  `python -m markitdown` — with no hardcoded paths. Verified on Windows, macOS
  and Linux in CI.
- **Claude Code plugin packaging** with `userConfig` options for the interpreter,
  the markitdown path, and the density threshold. Every setting is also readable
  from an environment variable, so one engine serves both plugin and manual
  installs.
- **Cache correctness.** Results are re-graded before reuse, unusable results are
  never stored, and zero-byte artifacts left by earlier runs are pruned
  automatically.
- **BOM-tolerant input parsing.** Windows PowerShell 5.1 prepends a UTF-8 BOM
  when piping to a native command, which made JSON parsing raise and — because
  the hook must never block a prompt — fail completely silently.
- **Explicit hook timeout of 120s.** `UserPromptSubmit` lowers the default for
  command hooks to 30s, below the engine's own 100s per-file budget, so slow
  conversions were at risk of being killed part-way.
- Test suite with synthetic PDF fixtures built in pure Python, so no real
  document is ever committed and the suite runs on a bare interpreter.

[1.1.0]: https://github.com/AndrewAvery7/claude-markitdown-hook/releases/tag/v1.1.0
[1.0.0]: https://github.com/AndrewAvery7/claude-markitdown-hook/releases/tag/v1.0.0
