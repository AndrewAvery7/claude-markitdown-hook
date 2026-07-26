<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.png">
    <img src="assets/logo.png" alt="claude-markitdown-hook" width="540">
  </picture>
</p>

<p align="center">
  <b>Cheap, honest document ingestion for Claude Code.</b><br>
  Converts the PDFs and Office files you mention to markdown, hands Claude a pointer instead of the contents &mdash; and never claims a conversion that recovered nothing.
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT license"></a>
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-blue.svg" alt="Windows, macOS, Linux">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+">
  <a href="https://github.com/AndrewAvery7/claude-markitdown-hook/actions/workflows/ci.yml"><img src="https://github.com/AndrewAvery7/claude-markitdown-hook/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
</p>

https://github.com/user-attachments/assets/d1fb58b9-8cda-45e8-b37d-893b938b78c4

<p align="center">
  <i>75 seconds &mdash; press play, and hit &#128266; to unmute (GitHub starts videos silent).</i>
  &nbsp;·&nbsp;
  <a href="https://github.com/AndrewAvery7/claude-markitdown-hook/releases/latest/download/claude-markitdown-hook-promo.mp4">Download the MP4</a>
</p>

---

## The problem

Mention a PDF in a prompt and Claude Code reads it by rendering every page as an
image. That is slow and expensive, and it happens again on the next turn. Office
formats are worse: Claude cannot read `.docx`, `.xlsx` or `.pptx` natively at all.

The obvious fix is to run documents through
[markitdown](https://github.com/microsoft/markitdown) first. The obvious fix has
a trap in it.

**markitdown exits 0 when it extracts nothing.** An image-only PDF — a webpage
screenshot saved as PDF, a scan, a certificate — has no text layer, and
markitdown's pdfminer backend does not OCR. It finds nothing, writes an empty
file, and reports success. Feed that to a model and it will tell you, with total
confidence, that your document is blank.

That is the failure this hook exists to prevent.

## What it does

On every prompt, the hook spots document paths, converts them, and injects a
**pointer** into the context — never the content:

```
[markitdown] /path/report.pdf was converted to markdown at
~/.claude/markitdown-cache/report-a1b2c3d4.md (14973 bytes, 304 lines,
14472 chars, 20 page(s)). If this document's content is needed, Read or
Grep the .md file (not the original).
```

Claude reads or greps that file **only if it turns out to matter**, with
`offset`/`limit` for big documents. Referencing a 200-page PDF costs almost
nothing until its contents are genuinely needed.

And when extraction recovers nothing, the hook says so instead of lying:

```
[markitdown] NO USABLE TEXT extracted from /path/screenshot.pdf (no text
extracted). This is an image-based/scanned PDF -- text extraction cannot
see into it and no .md was written. Read the ORIGINAL file natively with
the Read tool (use the `pages` parameter for long PDFs); Claude's vision
can read it. Do NOT report the document as empty.
```

No file is written, nothing is cached, and Claude is pointed at the one tool
that *can* read the document: its own vision.

## How the grading works

Every conversion is scored on what it actually recovered, not on the exit code.

For PDFs the measure is **characters per page**, which separates the two
populations cleanly. Measured across real documents:

| Document | Pages | Chars/page | Verdict |
| :-- | --: | --: | :-- |
| Webpage screenshot saved as PDF | 1 | 0 | rejected |
| Course certificate (graphic with a title) | 1 | 39 | rejected |
| Two-page text document | 2 | 932 | converted |
| Twenty-page slide deck | 20 | 664 | converted |

The default threshold of **100** sits between those groups with roughly a 6×
margin either way. Fail this test and no `.md` is written at all.

The density test applies to **PDFs only**. Other formats legitimately convert to
very short output — a one-line email, a brief voice memo, a nearly empty
spreadsheet — and are rejected only when they yield literally nothing.

## Install

### Prerequisites

Python 3.10 or newer, and markitdown with the format extras you want. PDF, docx,
pptx and xlsx support each live in an extra, so `[all]` is the usual choice:

```bash
pip install "markitdown[all]"
```

Quote the brackets. `zsh` (the default shell on macOS) treats them as a glob and
the install fails without quotes.

### Option 1 — as a Claude Code plugin (recommended)

```bash
/plugin marketplace add AndrewAvery7/claude-markitdown-hook
```

Then `/plugin install markitdown-hook`. Claude Code prompts for the settings
described below at enable time.

Or non-interactively, which lets you set the interpreter in the same step:

```bash
claude plugin marketplace add AndrewAvery7/claude-markitdown-hook
claude plugin install markitdown-hook@claude-markitdown-hook --config python_bin=python
```

> **Windows users:** set the *Python interpreter* option to `python`. It
> defaults to `python3`, which is correct on macOS and Linux but usually absent
> on Windows. If the hook then stays silent, see
> [the Windows note in TROUBLESHOOTING](docs/TROUBLESHOOTING.md#the-hook-does-nothing-at-all).

Restart Claude Code after installing so the hook loads.

### Option 2 — manual install

Copy `plugins/markitdown-hook/scripts/markitdown_hook.py` anywhere you like, then
add this to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python \"/absolute/path/to/markitdown_hook.py\"",
            "timeout": 120,
            "statusMessage": "Converting referenced documents with markitdown..."
          }
        ]
      }
    ]
  }
}
```

Keep the explicit `timeout`. `UserPromptSubmit` lowers the default for command
hooks to 30 seconds, which is below the hook's own 100-second per-file budget,
so a slow conversion would be killed part-way.

If `hooks.UserPromptSubmit` already exists, add to the array rather than
replacing it.

## Configuration

Every setting is read from the plugin options **or** an environment variable, so
one engine serves both installs. Plugin options win.

| Plugin option | Environment variable | Default | What it does |
| :-- | :-- | :-- | :-- |
| `python_bin` | *(hook command)* | `python3` | Interpreter that runs the hook. Set to `python` on Windows |
| `markitdown_bin` | `MARKITDOWN_BIN` | auto-detect | Explicit markitdown path, for virtualenvs |
| `min_chars_per_page` | `MARKITDOWN_HOOK_MIN_CHARS_PER_PAGE` | `100` | PDF density threshold |
| — | `MARKITDOWN_HOOK_CACHE` | `~/.claude/markitdown-cache` | Where conversions are cached |
| — | `MARKITDOWN_HOOK_EXTS` | 12 formats | Comma-separated extensions to handle |
| — | `MARKITDOWN_HOOK_TIMEOUT` | `100` | Per-file conversion budget, seconds |
| — | `MARKITDOWN_HOOK_CACHE_DAYS` | `30` | Prune conversions unused this long |
| — | `MARKITDOWN_HOOK_MAX_FILES` | `12` | Cap on documents per prompt |

markitdown is located in this order: the explicit setting, then `markitdown` on
`PATH`, then `python -m markitdown` using the interpreter running the hook —
which is what works inside a virtualenv that exposes no console script.

## Something not working?

```bash
python3 /path/to/markitdown_hook.py --doctor
```

Reports which interpreter is running, whether markitdown resolved and how,
whether pdfminer is present, whether the cache is writable, and every setting in
effect with what set it. Exits `0` when the hook can do its job, `1` when it
cannot.

```
markitdown
  resolved        NOT FOUND
  fix             pip install "markitdown[all]"

NOT READY
```

More depth in [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

## Good to know

- **Handled by default:** `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.xls`, `.epub`,
  `.zip`, `.msg`, `.wav`, `.mp3`, `.m4a`, `.mp4`.
- **Deliberately not handled:** plain text, images, `.ipynb`. Claude reads those
  natively, so converting them would inject duplicate content.
- **Nothing is cached unless it holds real content**, so a retry genuinely
  retries instead of replaying a bad result. Zero-byte artifacts left by earlier
  versions are swept automatically.
- **The hook never blocks a prompt.** Any unexpected error exits 0 silently —
  except a missing markitdown, which is reported, because a silent no-op looks
  exactly like "this document is empty".

## Documentation

- [docs/DESIGN.md](docs/DESIGN.md) — why grading works this way, and the data behind the threshold
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — the hook does nothing, wrong interpreter, virtualenvs
- [docs/TESTING.md](docs/TESTING.md) — running the suite, and how the synthetic PDFs are built

## Caveats (honest edges)

- **A genuinely sparse PDF gets rejected.** A 40-page deck with three words per
  slide falls below the threshold and Claude reads the original natively
  instead. That costs more tokens but loses nothing — the failure direction is
  deliberate. Lower `min_chars_per_page` if it bothers you.
- **No OCR.** For image-based PDFs the hook hands off to Claude's vision rather
  than shipping an OCR engine. If you need grep-able offline text from scans,
  run them through OCR before Claude sees them.
- **PyMuPDF is optional and never required.** If installed, it is used as a
  deeper extractor for PDFs pdfminer cannot read. It is dual-licensed
  AGPL-3.0/commercial, so it is deliberately not a dependency of this MIT
  project — decide for yourself whether that licence suits you.
- **The interpreter default cannot be right everywhere.** `python3` is correct
  on macOS and Linux, `python` on Windows. The plugin asks at enable time.
- **Audio and video conversion needs markitdown's transcription extras** and can
  be slow. Raise `MARKITDOWN_HOOK_TIMEOUT` if those matter to you.

## Acknowledgements

Built on [markitdown](https://github.com/microsoft/markitdown) by Microsoft. This
project is an independent companion to it and is not affiliated with or endorsed
by Microsoft or Anthropic.

## License

MIT — see [LICENSE](LICENSE).
