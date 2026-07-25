# Design

Why this hook is shaped the way it is, and the measurements behind its one
magic number.

## The failure that started it

A 4.5 MB PDF — a full-page GitHub screenshot exported from a browser — was
referenced in a prompt. The conversion reported success. The output was zero
bytes.

Reproduced directly:

```
$ markitdown screenshot.pdf -o out.md
$ echo $?
0
$ wc -c out.md
0 out.md
```

Exit code 0. Empty file. No warning of any kind.

The cause is not a bug in markitdown. A browser screenshot saved as PDF contains
raster images and no text layer at all — `pdfminer` reported 0 characters, and
so did PyMuPDF. markitdown's PDF backend extracts embedded text and does not
OCR, so there was genuinely nothing to find. Finding nothing is not an error, so
it exits 0.

The bug is in every integration that treats exit code as truth. The consequence
is specific and bad: the model is told the document converted, reads an empty
file, and reports that the document is empty. The user believes it.

## The rule

**Never measure success by exit code. Measure it by yield.**

Everything else follows. A conversion that recovered nothing is not a success
with an unusual result; it is a different outcome that needs its own message,
its own absence of a cached artifact, and its own instruction to the model.

## Choosing the threshold

Distinguishing "extracted nothing" from "extracted something" is trivial. The
harder case is the near-miss: a certificate whose only real content is a
graphic, which yields a handful of characters and would otherwise pass.

Raw byte count is a poor discriminator because it conflates document length with
extraction quality — 800 bytes is plenty for a one-page memo and nearly nothing
for a 200-page report. **Characters per page** normalises that away.

Measured across real documents:

| Document | Pages | Chars | Chars/page |
| :-- | --: | --: | --: |
| Webpage screenshot saved as PDF | 1 | 0 | 0 |
| Course certificate (graphic + title) | 1 | 39 | 39 |
| Two-page text document | 2 | 1 864 | 932 |
| Twenty-page slide deck | 20 | 13 289 | 664 |

Two populations, no overlap, an order of magnitude apart. The default threshold
of **100** sits between them with roughly a 6× margin on both sides — far enough
from either that small variations in document style cannot cross it.

The synthetic fixtures in `tests/pdfgen.py` were built to land in the same
places: 674 chars/page for the text fixture, 25 for the sparse one, 0 for the
image-only one.

### Why the test is PDF-only

Applying a density floor to every format looks consistent and is wrong. A
one-line email, a ten-second voice memo, and a spreadsheet with four cells all
convert correctly to very little text. Rejecting those would discard good
conversions to guard against a failure mode they do not have — only PDFs carry a
text extractor meeting a picture.

So non-PDF formats are rejected only when they yield literally zero characters.

### Which way to fail

A false positive means a legitimately sparse PDF is treated as image-based, and
Claude reads the original with vision. That costs more tokens and loses nothing.

A false negative means an empty conversion is presented as real, and the model
confidently reports an empty document. That loses the content entirely and the
user has no signal anything went wrong.

The threshold is set to prefer the first failure.

## Pointers, not content

The hook injects a path and a size, never the document text. Claude reads or
greps the `.md` on demand, with `offset`/`limit` for large files.

This matters more than it first appears. Prompts mention documents
speculatively — "compare these three reports" may only need one of them. Loading
all three into context costs tokens on every subsequent turn of the
conversation, whether or not they were ever used. A pointer costs about 400
characters and is paid once.

## Never cache a bad result

The original implementation cached by modification time alone. A zero-byte
result was therefore served for every future reference to that document —
permanently, with no retry, even after the underlying cause was fixed.

Cache reads now re-grade before reuse, and unusable results are deleted rather
than stored. Zero-byte artifacts from earlier versions are swept on the next
run, so an upgrade heals the cache without manual intervention.

## Degrading honestly

Two dependency states are handled explicitly rather than silently:

- **markitdown missing** — reported in context with the install command. A
  silent no-op here is indistinguishable from "this document is empty", which is
  the exact failure this project exists to prevent.
- **pdfminer missing** — arrives with markitdown's `[pdf]`/`[all]` extras, not
  the base package. Without it, page counting is unavailable and grading falls
  back to a flat character floor. Empty output is still caught; only the
  near-miss cases lose precision.

The same reasoning drove BOM-tolerant input parsing. Windows PowerShell 5.1
prepends a UTF-8 BOM when piping to a native command, which made `json.load`
raise — and because the hook must never block a prompt, that exception was
swallowed and the hook did nothing at all, with no message. Silence is the one
outcome this design does not permit.

## Optional deep extraction

PyMuPDF reads some PDFs that pdfminer cannot. When it is installed, it is tried
before giving up on a PDF.

It is never required. PyMuPDF is dual-licensed AGPL-3.0/commercial, which does
not belong in the dependency set of an MIT project. Page counting — which the
core grading needs — uses pdfminer instead, which markitdown already depends on,
so the core path adds no dependency and no copyleft.
