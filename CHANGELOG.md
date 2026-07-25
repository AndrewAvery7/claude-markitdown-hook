# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[1.0.0]: https://github.com/AndrewAvery7/claude-markitdown-hook/releases/tag/v1.0.0
