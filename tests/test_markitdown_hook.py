"""Tests for the markitdown UserPromptSubmit hook.

The behaviour that matters most is negative: an image-only PDF must NOT be
reported as converted, must NOT leave a cached artifact, and must NOT be
described to Claude as an empty document. Those cases carry the most weight
here because they are the ones that fail silently in production.
"""
import io
import json
import os
import sys

import pdfgen
import pytest
from conftest import needs_markitdown, needs_pdfminer


# --------------------------------------------------------------------------
# Path detection
# --------------------------------------------------------------------------

def test_finds_quoted_path(mh, tmp_path):
    p = tmp_path / "report.pdf"
    p.write_bytes(pdfgen.text_pdf())
    found = mh.candidate_paths('please read "{}"'.format(p), str(tmp_path))
    assert found == [str(p)]


def test_finds_unquoted_and_at_mention(mh, tmp_path):
    p = tmp_path / "notes.docx"
    p.write_bytes(b"not really a docx, only path detection is under test")
    assert mh.candidate_paths("summarise {}".format(p), str(tmp_path)) == [str(p)]
    assert mh.candidate_paths("summarise @{}".format(p), str(tmp_path)) == [str(p)]


def test_finds_relative_path_against_cwd(mh, tmp_path):
    (tmp_path / "deck.pptx").write_bytes(b"x")
    assert mh.candidate_paths("open deck.pptx", str(tmp_path)) == [
        str(tmp_path / "deck.pptx")
    ]


def test_ignores_unlisted_extension_and_missing_file(mh, tmp_path):
    (tmp_path / "notes.txt").write_text("Claude reads text natively")
    assert mh.candidate_paths("read notes.txt", str(tmp_path)) == []
    assert mh.candidate_paths("read ghost.pdf", str(tmp_path)) == []


def test_deduplicates_repeated_mentions(mh, tmp_path):
    p = tmp_path / "same.pdf"
    p.write_bytes(pdfgen.text_pdf())
    prompt = 'compare "{0}" with {0}'.format(p)
    assert mh.candidate_paths(prompt, str(tmp_path)) == [str(p)]


def test_extension_set_is_configurable(engine, tmp_path):
    m = engine(MARKITDOWN_HOOK_EXTS=".pdf")
    (tmp_path / "a.pdf").write_bytes(pdfgen.text_pdf())
    (tmp_path / "b.docx").write_bytes(b"x")
    found = m.candidate_paths("a.pdf and b.docx", str(tmp_path))
    assert found == [str(tmp_path / "a.pdf")]


@pytest.mark.skipif(os.name != "nt", reason="drive-letter rewrite is Windows-only")
def test_translates_git_bash_path_on_windows(mh, tmp_path):
    p = tmp_path / "doc.pdf"
    p.write_bytes(pdfgen.text_pdf())
    drive, rest = str(p).split(":", 1)
    gitbash = "/{}{}".format(drive.lower(), rest.replace("\\", "/"))
    assert mh.candidate_paths(gitbash, str(tmp_path)) == [str(p)]


@pytest.mark.skipif(os.name == "nt", reason="POSIX-only semantics")
def test_leaves_slash_c_paths_alone_on_posix(mh, tmp_path):
    """On Linux and macOS /c/... is a real path, not a Git Bash drive spec."""
    d = tmp_path / "c" / "Users"
    d.mkdir(parents=True)
    p = d / "real.pdf"
    p.write_bytes(pdfgen.text_pdf())
    assert mh.candidate_paths(str(p), str(tmp_path)) == [str(p)]


# --------------------------------------------------------------------------
# Page counting and grading
# --------------------------------------------------------------------------

@needs_pdfminer
@pytest.mark.parametrize("pages", [1, 2, 5])
def test_page_count(mh, tmp_path, pages):
    p = tmp_path / "multi.pdf"
    p.write_bytes(pdfgen.text_pdf(pages))
    assert mh.pdf_page_count(str(p)) == pages


def test_page_count_returns_none_for_junk(mh, tmp_path):
    p = tmp_path / "broken.pdf"
    p.write_bytes(b"this is not a PDF at all")
    assert mh.pdf_page_count(str(p)) is None


def _graded(mh, tmp_path, src_bytes, md_text, name="doc.pdf"):
    src = tmp_path / name
    src.write_bytes(src_bytes)
    dst = tmp_path / "out.md"
    dst.write_text(md_text, encoding="utf-8")
    return mh.grade(str(src), str(dst))


def test_grade_empty_output(mh, tmp_path):
    status, _ = _graded(mh, tmp_path, pdfgen.image_only_pdf(), "")
    assert status == "empty"


def test_grade_whitespace_only_output_is_empty(mh, tmp_path):
    status, _ = _graded(mh, tmp_path, pdfgen.image_only_pdf(), "\n\n   \t\n")
    assert status == "empty"


@needs_pdfminer
def test_grade_sparse_pdf(mh, tmp_path):
    status, detail = _graded(mh, tmp_path, pdfgen.sparse_pdf(),
                             "Certificate of Completion")
    assert status == "sparse"
    assert "1 page" in detail


@needs_pdfminer
def test_grade_healthy_pdf(mh, tmp_path):
    status, detail = _graded(mh, tmp_path, pdfgen.text_pdf(2), "x" * 1400)
    assert status == "ok"
    assert "2 page" in detail


@needs_pdfminer
def test_grade_threshold_is_configurable(engine, tmp_path):
    """Lowering the threshold accepts a document the default would reject."""
    strict = engine()
    lenient = engine(MARKITDOWN_HOOK_MIN_CHARS_PER_PAGE=5)
    src = tmp_path / "thin.pdf"
    src.write_bytes(pdfgen.text_pdf(1))
    dst = tmp_path / "thin.md"
    dst.write_text("x" * 50, encoding="utf-8")
    assert strict.grade(str(src), str(dst))[0] == "sparse"
    assert lenient.grade(str(src), str(dst))[0] == "ok"


def test_short_non_pdf_is_never_rejected_for_being_short(mh, tmp_path):
    """A one-line email or a brief voice memo is a successful conversion.

    The density test is PDF-only on purpose: applying it to every format would
    throw away legitimately tiny documents.
    """
    for name in ("note.msg", "memo.m4a", "sheet.xlsx", "doc.docx"):
        src = tmp_path / name
        src.write_bytes(b"irrelevant, only the extension is read here")
        dst = tmp_path / (name + ".md")
        dst.write_text("Thanks, sounds good.", encoding="utf-8")
        assert mh.grade(str(src), str(dst))[0] == "ok", name


def test_non_pdf_with_no_text_is_still_empty(mh, tmp_path):
    src = tmp_path / "silent.mp3"
    src.write_bytes(b"x")
    dst = tmp_path / "silent.md"
    dst.write_text("", encoding="utf-8")
    assert mh.grade(str(src), str(dst))[0] == "empty"


def test_grade_falls_back_to_size_when_page_count_unknown(mh, tmp_path):
    src = tmp_path / "unreadable.pdf"
    src.write_bytes(b"not a PDF")
    dst = tmp_path / "unreadable.md"
    dst.write_text("tiny", encoding="utf-8")
    assert mh.grade(str(src), str(dst))[0] == "sparse"
    dst.write_text("y" * 500, encoding="utf-8")
    assert mh.grade(str(src), str(dst))[0] == "ok"


# --------------------------------------------------------------------------
# markitdown discovery
# --------------------------------------------------------------------------

def test_explicit_override_wins(engine):
    m = engine(MARKITDOWN_BIN="/opt/custom/markitdown")
    assert m.find_markitdown() == ["/opt/custom/markitdown"]


def test_plugin_option_overrides_plain_env(engine):
    m = engine(MARKITDOWN_BIN="/plain/markitdown",
               CLAUDE_PLUGIN_OPTION_MARKITDOWN_BIN="/plugin/markitdown")
    assert m.find_markitdown() == ["/plugin/markitdown"]


def test_plugin_option_sets_threshold(engine):
    assert engine(CLAUDE_PLUGIN_OPTION_MIN_CHARS_PER_PAGE=42).MIN_CHARS_PER_PAGE == 42


# --------------------------------------------------------------------------
# Hook input parsing
# --------------------------------------------------------------------------

class _Stdin:
    def __init__(self, raw):
        self.buffer = io.BytesIO(raw)


def test_reads_plain_json(mh):
    payload = json.dumps({"prompt": "hello", "cwd": "/tmp"}).encode()
    assert mh.read_hook_input(_Stdin(payload))["prompt"] == "hello"


def test_reads_json_with_utf8_bom(mh):
    """PowerShell 5.1 prepends a BOM when piping; without this the hook would
    raise and, because it must never block a prompt, fail completely silently."""
    payload = b"\xef\xbb\xbf" + json.dumps({"prompt": "hi", "cwd": "/tmp"}).encode()
    assert mh.read_hook_input(_Stdin(payload))["prompt"] == "hi"


# --------------------------------------------------------------------------
# Cache behaviour
# --------------------------------------------------------------------------

def test_prune_removes_zero_byte_artifacts(mh):
    os.makedirs(mh.CACHE_DIR, exist_ok=True)
    empty = os.path.join(mh.CACHE_DIR, "stale-00000000.md")
    good = os.path.join(mh.CACHE_DIR, "good-11111111.md")
    open(empty, "w").close()
    with open(good, "w", encoding="utf-8") as f:
        f.write("real content")
    mh.prune_cache()
    assert not os.path.exists(empty)
    assert os.path.exists(good)


def test_cache_path_is_stable_and_unique(mh):
    a = mh.cache_path(os.path.join("dir", "one.pdf"))
    b = mh.cache_path(os.path.join("other", "one.pdf"))
    assert a == mh.cache_path(os.path.join("dir", "one.pdf"))
    assert a != b, "same basename in different folders must not collide"


# --------------------------------------------------------------------------
# End-to-end conversion (requires markitdown)
# --------------------------------------------------------------------------

def _run_main(mod, prompt, cwd):
    stdin, stdout = sys.stdin, sys.stdout
    sys.stdin = io.StringIO(json.dumps({"prompt": prompt, "cwd": cwd}))
    sys.stdout = buf = io.StringIO()
    try:
        mod.main()
    finally:
        sys.stdin, sys.stdout = stdin, stdout
    raw = buf.getvalue().strip()
    return json.loads(raw) if raw else None


@needs_markitdown
def test_converts_text_pdf(mh, tmp_path):
    p = tmp_path / "report.pdf"
    p.write_bytes(pdfgen.text_pdf(2))
    out = _run_main(mh, 'read "{}"'.format(p), str(tmp_path))
    assert "converted report.pdf" in out["systemMessage"]
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert "was converted to markdown" in ctx
    assert os.path.exists(mh.cache_path(str(p)))


@needs_markitdown
def test_image_only_pdf_is_reported_not_converted(mh, tmp_path):
    """The regression this project exists for.

    markitdown exits 0 and writes an empty file; the hook must not call that
    a success, must not keep the artifact, and must tell Claude to use vision.
    """
    p = tmp_path / "screenshot.pdf"
    p.write_bytes(pdfgen.image_only_pdf())
    out = _run_main(mh, 'read "{}"'.format(p), str(tmp_path))

    assert "converted" not in out["systemMessage"]
    assert "no text extracted" in out["systemMessage"]

    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert "NO USABLE TEXT" in ctx
    assert "Read the ORIGINAL" in ctx
    assert "Do NOT report the document as empty" in ctx

    assert not os.path.exists(mh.cache_path(str(p))), \
        "an unusable conversion must never be cached"


@needs_markitdown
def test_sparse_pdf_is_rejected(mh, tmp_path):
    p = tmp_path / "certificate.pdf"
    p.write_bytes(pdfgen.sparse_pdf())
    out = _run_main(mh, 'read "{}"'.format(p), str(tmp_path))
    assert "no text extracted" in out["systemMessage"]
    assert not os.path.exists(mh.cache_path(str(p)))


@needs_markitdown
def test_successful_conversion_is_reused_from_cache(mh, tmp_path):
    p = tmp_path / "reused.pdf"
    p.write_bytes(pdfgen.text_pdf(2))
    _run_main(mh, 'read "{}"'.format(p), str(tmp_path))
    cached = mh.cache_path(str(p))
    marker = "CACHE MARKER, not produced by markitdown"
    with open(cached, "a", encoding="utf-8") as f:
        f.write("\n" + marker + "\n")
    _run_main(mh, 'read "{}"'.format(p), str(tmp_path))
    with open(cached, encoding="utf-8") as f:
        assert marker in f.read(), "second run should have reused the cache"


@needs_markitdown
def test_stale_empty_cache_entry_is_not_served(mh, tmp_path):
    """An artifact left by an older, buggier version must not be replayed."""
    p = tmp_path / "screenshot.pdf"
    p.write_bytes(pdfgen.image_only_pdf())
    os.makedirs(mh.CACHE_DIR, exist_ok=True)
    open(mh.cache_path(str(p)), "w").close()  # 0-byte leftover
    out = _run_main(mh, 'read "{}"'.format(p), str(tmp_path))
    assert "no text extracted" in out["systemMessage"]
    assert not os.path.exists(mh.cache_path(str(p)))


@needs_markitdown
def test_mixed_batch_reports_each_outcome(mh, tmp_path):
    good = tmp_path / "good.pdf"
    good.write_bytes(pdfgen.text_pdf(2))
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(pdfgen.image_only_pdf())
    out = _run_main(mh, 'compare "{}" and "{}"'.format(good, bad), str(tmp_path))
    msg = out["systemMessage"]
    assert "converted good.pdf" in msg
    assert "no text extracted from bad.pdf" in msg


def test_no_output_when_prompt_has_no_documents(mh, tmp_path):
    assert _run_main(mh, "what is the syntax for a dict comprehension?",
                     str(tmp_path)) is None


def test_reports_when_markitdown_is_missing(engine, tmp_path):
    m = engine(MARKITDOWN_BIN="")
    m.find_markitdown = lambda: None
    p = tmp_path / "doc.pdf"
    p.write_bytes(pdfgen.text_pdf())
    out = _run_main(m, 'read "{}"'.format(p), str(tmp_path))
    assert "not installed" in out["systemMessage"]
    assert "pip install markitdown" in \
        out["hookSpecificOutput"]["additionalContext"]


# --------------------------------------------------------------------------
# Diagnostics
# --------------------------------------------------------------------------

def _doctor(mod):
    out = io.StringIO()
    stdout, sys.stdout = sys.stdout, out
    try:
        code = mod.doctor()
    finally:
        sys.stdout = stdout
    return code, out.getvalue()


def test_doctor_reports_every_section(mh):
    _, text = _doctor(mh)
    for section in ("interpreter", "markitdown", "pdf support", "cache",
                    "configuration"):
        assert section in text, section
    assert mh.__version__ in text


def test_doctor_fails_when_markitdown_is_missing(mh):
    """The case a stuck user is actually in, and it must exit non-zero."""
    mh.find_markitdown = lambda: None
    code, text = _doctor(mh)
    assert code == 1
    assert "NOT FOUND" in text
    assert "NOT READY" in text
    assert 'pip install "markitdown[all]"' in text


@needs_markitdown
def test_doctor_succeeds_when_markitdown_is_present(mh):
    code, text = _doctor(mh)
    assert code == 0
    assert "READY" in text
    assert "NOT READY" not in text


def test_doctor_shows_where_a_setting_came_from(engine):
    """A wrong value is only debuggable if you can see what set it."""
    m = engine(MARKITDOWN_HOOK_MIN_CHARS_PER_PAGE=250)
    _, text = _doctor(m)
    assert "250" in text
    assert "MARKITDOWN_HOOK_MIN_CHARS_PER_PAGE" in text
    plain = engine()
    _, text2 = _doctor(plain)
    assert "(default)" in text2


def test_doctor_reports_an_unwritable_cache(engine, tmp_path):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("this is a file, so makedirs must fail")
    m = engine(MARKITDOWN_HOOK_CACHE=str(blocker / "cache"))
    code, text = _doctor(m)
    assert "writable" in text
    assert code == 1, "an unusable cache directory is not a ready state"


def test_excess_files_are_reported_not_dropped_silently(engine, tmp_path):
    m = engine(MARKITDOWN_HOOK_MAX_FILES=2)
    m.find_markitdown = lambda: None  # discovery result is irrelevant here
    paths = []
    for i in range(4):
        p = tmp_path / "doc{}.pdf".format(i)
        p.write_bytes(pdfgen.text_pdf())
        paths.append('"{}"'.format(p))
    out = _run_main(m, "read " + " ".join(paths), str(tmp_path))
    assert out is not None
    # With markitdown absent the engine reports that first, but the cap must
    # still have been applied to the path list it reported on.
    assert "2 referenced document(s)" in \
        out["hookSpecificOutput"]["additionalContext"]
