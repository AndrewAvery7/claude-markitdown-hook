#!/usr/bin/env python3
"""UserPromptSubmit hook: convert documents referenced in a prompt to markdown.

Claude Code reads PDFs by rendering each page as an image, and cannot read
Office formats natively at all. This hook spots document paths in your prompt,
converts them to markdown with markitdown, and injects a *pointer* to the
result -- never the content itself. Claude then Reads or Greps the .md on
demand, so a 200-page PDF costs almost nothing until it is actually needed.

The part that matters: markitdown exits 0 even when it extracts nothing. An
image-only PDF (a screenshot saved as PDF, a scan, a certificate) has no text
layer, and markitdown's pdfminer backend does not OCR. A naive integration
reports "converted!" over an empty file and Claude then states, with complete
confidence, that your document is blank. So every conversion here is graded on
how much text it actually recovered, and a failed extraction says so.

Never blocks the prompt: any unexpected error exits 0 with no output.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

__version__ = "1.0.0"


def _env(default, *names):
    """First non-empty environment variable from names, else default.

    Every setting is readable two ways, because the hook serves two installs.
    As a Claude Code plugin, values chosen in the enable dialog arrive as
    CLAUDE_PLUGIN_OPTION_<KEY>, where KEY is the plugin.json option key
    uppercased. Installed by hand, the plain MARKITDOWN_HOOK_* name applies.
    The plugin-option name is listed first so an explicit choice in the dialog
    wins over a stale shell variable.
    """
    for n in names:
        v = os.environ.get(n, "").strip()
        if v:
            return v
    return default


def _env_int(default, *names):
    try:
        return int(_env("", *names))
    except (TypeError, ValueError):
        return default


# --- Configuration (all overridable by environment variable) ----------------

# Formats Claude cannot read natively (Office, email, archives, audio) or reads
# expensively (PDF renders pages as images). Plain text, images and .ipynb are
# deliberately excluded: Claude reads those directly, and converting them would
# inject duplicate content into the context window.
DEFAULT_EXTS = (
    ".pdf,.docx,.pptx,.xlsx,.xls,.epub,.zip,.msg,.wav,.mp3,.m4a,.mp4"
)
EXTS = {
    e if e.startswith(".") else "." + e
    for e in (
        x.strip().lower()
        for x in _env(DEFAULT_EXTS, "MARKITDOWN_HOOK_EXTS").split(",")
    )
    if e
}

CACHE_DIR = _env(
    os.path.join(os.path.expanduser("~"), ".claude", "markitdown-cache"),
    "MARKITDOWN_HOOK_CACHE",
)

# Audio transcription is the slow case; PDFs and Office files are quick.
PER_FILE_TIMEOUT = _env_int(100, "MARKITDOWN_HOOK_TIMEOUT")
CACHE_MAX_AGE_DAYS = _env_int(30, "MARKITDOWN_HOOK_CACHE_DAYS")

# A PDF with a real text layer yields roughly 650-950 characters per page.
# Image-only PDFs -- browser screenshots, scans, certificates -- yield 0-40.
# 100 sits between those populations with a wide margin on both sides.
MIN_CHARS_PER_PAGE = _env_int(
    100,
    "CLAUDE_PLUGIN_OPTION_MIN_CHARS_PER_PAGE",
    "MARKITDOWN_HOOK_MIN_CHARS_PER_PAGE",
)

# Floor used only when a PDF's page count cannot be determined.
MIN_CHARS_NO_PAGECOUNT = 200

# Sanity bound. Hook output is capped at 10,000 characters by Claude Code and
# each note is ~400, so this is a runaway guard, not a real limit.
MAX_FILES = _env_int(12, "MARKITDOWN_HOOK_MAX_FILES")


# --- markitdown discovery ---------------------------------------------------

def find_markitdown():
    """Locate markitdown, returning an argv prefix or None.

    Checked in order:
      1. The markitdown_bin plugin option, or MARKITDOWN_BIN -- wins always.
      2. markitdown on PATH.
      3. `python -m markitdown` using the interpreter running this hook, which
         is what works inside a virtualenv where no console script is exposed.
    """
    override = _env(
        "", "CLAUDE_PLUGIN_OPTION_MARKITDOWN_BIN", "MARKITDOWN_BIN"
    )
    if override:
        return [override]
    found = shutil.which("markitdown")
    if found:
        return [found]
    try:
        r = subprocess.run(
            [sys.executable, "-c", "import markitdown"],
            capture_output=True, timeout=30,
        )
        if r.returncode == 0:
            return [sys.executable, "-m", "markitdown"]
    except Exception:
        pass
    return None


# --- Path detection ---------------------------------------------------------

def candidate_paths(prompt, cwd):
    """Extract existing document paths from prompt text."""
    cands = set()
    # Quoted paths first: drag-and-drop and shells usually quote, and this is
    # the only form that survives spaces intact.
    for dq, sq in re.findall(r'"([^"\n]+)"|\'([^\'\n]+)\'', prompt):
        cands.add(dq or sq)
    # Then bare whitespace-delimited tokens.
    for tok in re.findall(r"\S+", prompt):
        cands.add(tok.strip("'\",;()[]<>"))

    found = []
    for c in cands:
        c = c.lstrip("@")  # @-mentions
        if os.path.splitext(c)[1].lower() not in EXTS:
            continue
        c = os.path.expanduser(c)
        # Git Bash and WSL render C:\Users\x as /c/Users/x. Translate that back
        # on Windows only -- on Linux and macOS /c/... is a legitimate absolute
        # path and rewriting it would break real lookups.
        if os.name == "nt":
            m = re.match(r"^/([a-zA-Z])/(.+)", c)
            if m:
                c = "{}:/{}".format(m.group(1).upper(), m.group(2))
        p = c if os.path.isabs(c) else os.path.join(cwd, c)
        try:
            if os.path.isfile(p):
                found.append(os.path.abspath(p))
        except (OSError, ValueError):
            continue  # malformed path for this platform
    return sorted(set(found))


# --- Quality grading --------------------------------------------------------

def pdf_page_count(src):
    """Page count for a PDF, or None if it cannot be determined.

    Uses pdfminer, which markitdown already depends on -- so this adds no new
    dependency and keeps the core install free of copyleft components.
    """
    try:
        from pdfminer.pdfpage import PDFPage
        with open(src, "rb") as f:
            return sum(1 for _ in PDFPage.get_pages(f))
    except Exception:
        return None


def grade(src, dst):
    """Classify a conversion by how much text it actually recovered.

    Returns (status, detail) with status in {"ok", "sparse", "empty"}.
    """
    try:
        with open(dst, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return "empty", "output unreadable"
    chars = len(text.strip())
    if chars == 0:
        return "empty", "no text extracted"
    # The density test applies to PDFs ONLY. Other formats legitimately convert
    # to very short output -- a one-line email, a brief voice memo, a nearly
    # empty spreadsheet -- and must never be discarded for being short.
    if os.path.splitext(src)[1].lower() != ".pdf":
        return "ok", "{} chars".format(chars)
    pages = pdf_page_count(src)
    if pages:
        if chars // pages < MIN_CHARS_PER_PAGE:
            return "sparse", "only {} chars across {} page(s)".format(chars, pages)
        return "ok", "{} chars, {} page(s)".format(chars, pages)
    if chars < MIN_CHARS_NO_PAGECOUNT:
        return "sparse", "only {} chars".format(chars)
    return "ok", "{} chars".format(chars)


def pymupdf_extract(src, dst):
    """Optional deep extractor for PDFs pdfminer cannot read.

    PyMuPDF is dual-licensed AGPL-3.0 / commercial, so it is never required:
    if it is not installed this simply returns False and the caller falls back
    to telling Claude to read the original natively. Install it only if that
    licence suits your project.
    """
    try:
        import fitz  # PyMuPDF
        with fitz.open(src) as doc:
            parts = []
            for i, page in enumerate(doc, 1):
                t = page.get_text().strip()
                if t:
                    parts.append("\n\n## Page {}\n\n{}".format(i, t))
        text = "".join(parts).strip()
        if len(text) < MIN_CHARS_NO_PAGECOUNT:
            return False
        with open(dst, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        return True
    except Exception:
        return False


# --- Conversion -------------------------------------------------------------

def _discard(path):
    try:
        os.remove(path)
    except OSError:
        pass


def cache_path(src):
    base = os.path.splitext(os.path.basename(src))[0]
    tag = hashlib.md5(src.lower().encode("utf-8", "replace")).hexdigest()[:8]
    return os.path.join(CACHE_DIR, "{}-{}.md".format(base, tag))


def convert(src, mid):
    """Convert src to markdown. Returns (dst, status, detail).

    dst is None whenever the result is unusable, so the caller can never hand
    Claude a pointer to an empty file. Empty and sparse results are also never
    cached, so a retry genuinely retries instead of replaying a bad artifact.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    dst = cache_path(src)

    # Reuse a cached conversion only if it still holds real content.
    if (os.path.exists(dst)
            and os.path.getmtime(dst) >= os.path.getmtime(src)
            and os.path.getsize(dst) > 0):
        status, detail = grade(src, dst)
        if status == "ok":
            os.utime(dst, None)  # mark recently used so pruning spares it
            return dst, status, detail

    r = subprocess.run(
        mid + [src, "-o", dst],
        capture_output=True, text=True, timeout=PER_FILE_TIMEOUT,
    )
    if r.returncode != 0:
        _discard(dst)
        err = (r.stderr or r.stdout or "unknown error").strip()[:500]
        return None, "failed", err
    if not os.path.exists(dst):
        return None, "failed", "markitdown produced no output file"

    status, detail = grade(src, dst)
    if status != "ok" and os.path.splitext(src)[1].lower() == ".pdf":
        if pymupdf_extract(src, dst):
            status, detail = grade(src, dst)
            if status == "ok":
                detail += " (via PyMuPDF fallback)"
    if status != "ok":
        _discard(dst)  # never leave a misleading empty artifact behind
        return None, status, detail
    return dst, status, detail


def prune_cache():
    """Delete cached conversions unused for CACHE_MAX_AGE_DAYS, and any
    zero-byte artifacts left by older versions of this hook."""
    import time
    cutoff = time.time() - CACHE_MAX_AGE_DAYS * 86400
    try:
        entries = os.listdir(CACHE_DIR)
    except OSError:
        return
    for name in entries:
        if not name.endswith(".md"):
            continue
        p = os.path.join(CACHE_DIR, name)
        try:
            if os.path.getsize(p) == 0 or os.path.getmtime(p) < cutoff:
                os.remove(p)
        except OSError:
            pass  # in use or already gone; retry next run


# --- Hook plumbing ----------------------------------------------------------

def read_hook_input(stream=None):
    """Parse the hook payload, tolerating a UTF-8 BOM on stdin.

    Some shells (notably Windows PowerShell 5.1) prepend a BOM when piping to a
    native command. A bare json.load() then raises, and because this hook must
    never block a prompt, the failure would be completely silent.
    """
    stream = stream or sys.stdin
    if hasattr(stream, "buffer"):
        raw = stream.buffer.read().decode("utf-8-sig", errors="replace")
    else:
        raw = stream.read()
    return json.loads(raw.lstrip("\ufeff"))


def build_notes(paths, mid):
    """Convert each path and return (notes, converted, unusable)."""
    notes, converted, unusable = [], [], []
    for src in paths:
        try:
            dst, status, detail = convert(src, mid)
        except Exception as e:  # timeout, permissions, malformed document
            dst, status, detail = None, "failed", str(e)[:500]

        if dst is None:
            unusable.append(os.path.basename(src))
            if status == "failed":
                notes.append(
                    "[markitdown] FAILED to convert {}: {}. "
                    "Read the ORIGINAL file instead.".format(src, detail)
                )
            elif os.path.splitext(src)[1].lower() == ".pdf":
                notes.append(
                    "[markitdown] NO USABLE TEXT extracted from {} ({}). This "
                    "is an image-based/scanned PDF -- text extraction cannot "
                    "see into it and no .md was written. Read the ORIGINAL "
                    "file natively with the Read tool (use the `pages` "
                    "parameter for long PDFs); Claude's vision can read it. "
                    "Do NOT report the document as empty.".format(src, detail)
                )
            else:
                notes.append(
                    "[markitdown] NO TEXT extracted from {} ({}); no .md was "
                    "written. Read the ORIGINAL file instead.".format(src, detail)
                )
            continue

        converted.append(os.path.basename(src))
        size = os.path.getsize(dst)
        with open(dst, encoding="utf-8", errors="replace") as f:
            nlines = sum(1 for _ in f)
        # A pointer, never the content. Claude Reads or Greps this on demand
        # (with offset/limit for large documents), so the speculative context
        # cost of referencing a document stays near zero.
        notes.append(
            "[markitdown] {} was converted to markdown at {} ({} bytes, {} "
            "lines, {}). If this document's content is needed, Read or Grep "
            "the .md file (not the original).".format(
                src, dst, size, nlines, detail)
        )
    return notes, converted, unusable


def main():
    data = read_hook_input()
    prompt = data.get("prompt", "") or ""
    cwd = data.get("cwd") or os.getcwd()

    paths = candidate_paths(prompt, cwd)
    if not paths:
        return

    dropped = []
    if len(paths) > MAX_FILES:
        dropped = paths[MAX_FILES:]
        paths = paths[:MAX_FILES]

    mid = find_markitdown()
    if mid is None:
        # Say so rather than doing nothing: a silent no-op here looks exactly
        # like "this document has no content", which is the failure mode this
        # whole project exists to prevent.
        print(json.dumps({
            "suppressOutput": True,
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": (
                    "[markitdown] markitdown is not installed, so {} referenced "
                    "document(s) were NOT converted. Read the original file(s) "
                    "natively. To enable conversion: pip install markitdown[all]"
                    .format(len(paths))
                ),
            },
            "systemMessage": "markitdown: not installed - skipping conversion",
        }))
        return

    prune_cache()
    notes, converted, unusable = build_notes(paths, mid)

    if dropped:
        notes.append(
            "[markitdown] {} further document(s) referenced in this prompt were "
            "not converted (limit {}): {}. Read them natively if needed.".format(
                len(dropped), MAX_FILES,
                ", ".join(os.path.basename(d) for d in dropped))
        )

    out = {
        "suppressOutput": True,
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "\n\n".join(notes),
        },
    }
    msg = []
    if converted:
        msg.append("converted " + ", ".join(converted))
    if unusable:
        msg.append("no text extracted from " + ", ".join(unusable)
                   + " (reading original)")
    if msg:
        out["systemMessage"] = "markitdown: " + "; ".join(msg)
    print(json.dumps(out))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)  # never block the prompt
