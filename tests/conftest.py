"""Shared fixtures: load the hook engine with a controlled environment."""
import importlib.util
import os
import shutil
import sys

import pytest

ENGINE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "plugins", "markitdown-hook", "scripts", "markitdown_hook.py",
)

# Every setting the engine reads. Cleared before each load so a developer's
# own shell cannot change what the suite measures.
OWNED_VARS = (
    "MARKITDOWN_BIN",
    "MARKITDOWN_HOOK_CACHE",
    "MARKITDOWN_HOOK_EXTS",
    "MARKITDOWN_HOOK_TIMEOUT",
    "MARKITDOWN_HOOK_CACHE_DAYS",
    "MARKITDOWN_HOOK_MIN_CHARS_PER_PAGE",
    "MARKITDOWN_HOOK_MAX_FILES",
    "CLAUDE_PLUGIN_OPTION_MARKITDOWN_BIN",
    "CLAUDE_PLUGIN_OPTION_MIN_CHARS_PER_PAGE",
)


def _load(env):
    for k in OWNED_VARS:
        os.environ.pop(k, None)
    os.environ.update({k: str(v) for k, v in env.items()})
    spec = importlib.util.spec_from_file_location("markitdown_hook", ENGINE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def engine(tmp_path):
    """The engine, configured with a cache directory unique to this test."""
    def _make(**env):
        env.setdefault("MARKITDOWN_HOOK_CACHE", str(tmp_path / "cache"))
        return _load(env)
    yield _make
    for k in OWNED_VARS:
        os.environ.pop(k, None)


@pytest.fixture
def mh(engine):
    """The engine with default settings."""
    return engine()


def markitdown_available():
    if shutil.which("markitdown"):
        return True
    try:
        import markitdown  # noqa: F401
        return True
    except Exception:
        return False


needs_markitdown = pytest.mark.skipif(
    not markitdown_available(),
    reason="markitdown is not installed; end-to-end conversion cannot run",
)


def pdfminer_available():
    try:
        from pdfminer.pdfpage import PDFPage  # noqa: F401
        return True
    except Exception:
        return False


# pdfminer arrives with markitdown's [pdf] / [all] extras, not the base
# package, so a bare install has no page counting. The engine degrades to a
# size check in that case; these tests cover the density path specifically.
needs_pdfminer = pytest.mark.skipif(
    not pdfminer_available(),
    reason="pdfminer is not installed; PDF page counting is unavailable",
)
