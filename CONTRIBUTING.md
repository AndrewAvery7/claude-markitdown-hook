# Contributing

Issues and PRs welcome. The most valuable contributions right now:

- **Threshold evidence.** The 100 chars/page default was derived from a small
  sample of real documents (see [docs/DESIGN.md](docs/DESIGN.md)). Measurements
  from document types I did not have — CJK text, heavy tables, academic PDFs
  with two-column layouts, OCR'd scans — are genuinely useful, especially any
  that land near the boundary.
- **Formats that convert but grade wrongly.** If a document is usable and gets
  rejected, or unusable and gets accepted, that is the bug worth reporting.
  Include the chars/page figure from the recipe in
  [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).
- **Platform reports.** CI covers Windows, macOS and Linux, but not every
  Python or markitdown install shape. Virtualenv, pipx, conda and system-package
  installs all resolve markitdown differently.

House rules for engine changes:

- **Python 3.10+, standard library only.** The engine must import and run on a
  bare interpreter with nothing installed. Anything optional — pdfminer,
  PyMuPDF — goes behind a guarded import with a working fallback.
- **Never add a copyleft dependency to the core path.** PyMuPDF is optional
  precisely because it is AGPL; keep the required set permissive.
- **The hook must never block a prompt.** Unexpected errors exit 0. The one
  exception is a missing markitdown, which is announced — because a silent
  no-op is indistinguishable from "this document is empty", the exact failure
  this project exists to prevent.
- **Never report a conversion that recovered nothing.** Everything else is
  negotiable; this is not.
- **No real documents in the test suite.** Fixtures are synthesised in
  `tests/pdfgen.py`. Committing a sample document publishes whatever it
  contains.
- **Tests must pass with and without markitdown installed.** Guard
  dependency-specific cases with the `needs_markitdown` / `needs_pdfminer`
  markers so a bare install skips cleanly rather than failing.

Run the suite both ways before opening a PR:

```bash
python -m pytest tests/ -q                       # full install
python -m venv /tmp/bare && /tmp/bare/bin/python -m pip install pytest
/tmp/bare/bin/python -m pytest tests/ -q          # bare interpreter
```

If you change a version, change it in `.claude-plugin/marketplace.json` and
`plugins/markitdown-hook/.claude-plugin/plugin.json` together — CI checks they
agree.
