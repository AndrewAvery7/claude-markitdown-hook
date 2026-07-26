# Troubleshooting

## Start here: run the doctor

```bash
python3 /path/to/markitdown_hook.py --doctor
```

It reports everything this page used to ask you to check by hand — which
interpreter is running, whether markitdown resolved and how, whether pdfminer
is present, whether the cache is writable, and every configuration value
actually in effect along with what set it. It exits `0` when the hook can do
its job and `1` when it cannot, so it is also usable in a script.

Run it with the **same interpreter the hook uses** — on a plugin install, the
one named in the *Python interpreter* option. Running it with a different
Python is itself a common source of confusion, and the first line of output
tells you which one you got.

```
markitdown
  resolved        NOT FOUND
  fix             pip install "markitdown[all]"

NOT READY
```

Most problems are diagnosed and fixed from that output alone. The sections
below explain the causes in more depth.

## The hook does nothing at all

No status message, no context note, as if it were not installed.

**Check the interpreter first.** This is the most common cause by a wide margin.
The plugin's *Python interpreter* option defaults to `python3`, which is correct
on macOS and Linux and usually absent on Windows. If the command cannot be
spawned, the hook never runs and there is nothing to print.

Verify the interpreter your setting names actually exists:

```bash
python3 --version    # macOS, Linux
python --version     # Windows
```

Then set the option accordingly and restart Claude Code. (`/reload-plugins`
also works, but only in the interactive terminal — it is unavailable in the
desktop app, where a full restart is the way.)

**Windows: a passing `--version` is not conclusive.** Plugin hooks run in *exec
form*, which spawns the interpreter directly with no shell. On Windows, `python`
often resolves to a zero-byte app-execution alias in `WindowsApps` rather than a
real executable:

```powershell
(Get-Command python).Source          # ...\WindowsApps\python.exe
(Get-Item (Get-Command python).Source -Force).Length   # 0
```

That alias usually forwards correctly, and a bare `python` is fine on most
machines. But the shell resolves it and the hook does not, so `python --version`
can succeed while the hook stays silent — and if no Python is installed from the
Store, the alias opens the Microsoft Store instead of running anything.

If the hook is silent on Windows and everything else checks out, set the
*Python interpreter* option to the **absolute path** of a real interpreter:

```powershell
python -c "import sys; print(sys.executable)"
```

Use that path verbatim. The trade-off is that an absolute path will not follow a
future Python upgrade, so revisit it if you move or reinstall Python.

**Check the hook fires at all.** Run it by hand with a real payload:

```bash
echo '{"prompt":"read \"/full/path/to/a/real.pdf\"","cwd":"/tmp"}' \
  | python3 /path/to/markitdown_hook.py
```

Expect a JSON object. Nothing at all means no document path was recognised —
check that the file exists, that its extension is in the handled set, and that
the path in your prompt is the path on disk.

**Check for a swallowed exception.** The hook deliberately exits 0 on any
unexpected error so it can never block a prompt. To see what is actually
happening, run the payload through Python without the guard:

```bash
echo '{"prompt":"read \"/path/doc.pdf\"","cwd":"/tmp"}' | python3 -c "
import importlib.util
s = importlib.util.spec_from_file_location('mh', '/path/to/markitdown_hook.py')
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
m.main()
"
```

That version raises instead of exiting quietly.

## "markitdown is not installed" but I installed it

The hook looks for markitdown in this order: the explicit setting, `markitdown`
on `PATH`, then `python -m markitdown` using the interpreter running the hook.

If markitdown lives in a virtualenv the hook's interpreter is not using, none of
those find it. Two fixes:

- Point *Python interpreter* at the virtualenv's own Python, so
  `python -m markitdown` resolves; or
- Set *markitdown path* / `MARKITDOWN_BIN` to the absolute path of the
  executable.

Confirm what the hook can see:

```bash
python3 -c "import shutil; print(shutil.which('markitdown'))"
python3 -c "import markitdown; print(markitdown.__file__)"
```

## Every PDF comes back as "NO USABLE TEXT"

Almost always a missing `[pdf]` extra. The base `markitdown` package has no PDF
backend at all:

```bash
pip install "markitdown[all]"
```

Quote the brackets — `zsh` treats them as a glob and the install silently does
the wrong thing.

Verify:

```bash
python3 -c "import pdfminer; print('pdf support present')"
```

## A document I know has text is rejected

Check what it actually yields per page:

```bash
python3 -c "
from pdfminer.high_level import extract_text
from pdfminer.pdfpage import PDFPage
p = '/path/doc.pdf'
n = sum(1 for _ in PDFPage.get_pages(open(p,'rb')))
c = len(extract_text(p).strip())
print(f'{c} chars over {n} pages = {c//max(1,n)} per page')
"
```

Below 100 per page it is rejected by design. If the document is genuinely sparse
but genuinely useful — a slide deck with a few words per slide — lower
`min_chars_per_page`. If it reports 0, the PDF has no text layer and no setting
will help; Claude's vision is the right tool and the hook is already telling it
so.

## Conversions are slow, or get cut off

Audio and video transcription is the slow path. Two independent limits apply:

- `MARKITDOWN_HOOK_TIMEOUT` (default 100s) — the hook's own per-file budget.
- The hook's `timeout` in the plugin or settings — the ceiling Claude Code
  enforces on the whole hook.

The second must exceed the first, or slow conversions die part-way. Note that
`UserPromptSubmit` lowers Claude Code's default to **30 seconds**, so the
timeout must be set explicitly. The shipped plugin sets 120.

## Stale or wrong cached content

Conversions are cached in `~/.claude/markitdown-cache` (override with
`MARKITDOWN_HOOK_CACHE`), keyed by absolute path, and reused only while the
cached file is newer than the source and still grades as usable.

To force a rebuild, delete the entry — or the whole directory, which is
regenerated on demand:

```bash
rm -rf ~/.claude/markitdown-cache
```

## The status message says converted, but Claude says the file is empty

That combination should no longer be possible: a conversion that recovers
nothing is not reported as converted and writes no file. If you see it, the
`.md` was probably produced by an older version of the hook and is still cached.
Clear the cache as above.

Please also [open an issue](https://github.com/AndrewAvery7/claude-markitdown-hook/issues)
— that is precisely the failure this
project exists to prevent, and a reproducible case is worth having.
