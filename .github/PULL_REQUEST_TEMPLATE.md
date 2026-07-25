## What this changes

<!-- One or two sentences. Link the issue if there is one. -->

## Why

<!-- The problem being solved, not just the mechanism. -->

## Checklist

- [ ] `python -m pytest tests/ -q` passes with `markitdown[all]` installed
- [ ] It also passes on a bare interpreter with only `pytest` — dependency-specific
      tests are guarded with `needs_markitdown` / `needs_pdfminer` so they skip
      rather than fail
- [ ] The engine still imports with nothing installed (standard library only)
- [ ] No new required dependency, and nothing copyleft in the core path
- [ ] No real document committed as a test fixture — synthesise it in `tests/pdfgen.py`
- [ ] If a version changed, both manifests were updated together
- [ ] Docs updated if behaviour or configuration changed

## Grading impact

<!--
If this touches grading, say what it does to the two failure directions.
Rejecting a usable document costs tokens. Accepting an empty one loses content
silently, and is the failure this project exists to prevent — so changes that
make acceptance more likely need the stronger argument.

Write "none" if this does not touch grading.
-->
