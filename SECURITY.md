# Security policy

## Reporting a vulnerability

Please report security issues privately through
[GitHub's private vulnerability reporting](https://github.com/AndrewAvery7/claude-markitdown-hook/security/advisories/new)
rather than opening a public issue. I aim to acknowledge reports within a few
days.

## What this tool touches

Worth knowing before you install it, because it acts on file paths it finds in
your prompts:

| Resource | Access | Why |
|---|---|---|
| Any file path mentioned in your prompt, with a handled extension | read | The document being converted |
| `~/.claude/markitdown-cache/` (configurable) | write | Where conversions are stored |
| `markitdown` executable | executed as a subprocess | Performs the conversion |

The hook makes **no network requests** of its own. markitdown may, depending on
which extras you install and what a document contains — its YouTube and Azure
Document Intelligence extras are network-backed by design. Install only the
extras you need.

## Things worth understanding before you install

**Converted documents are written to disk in plain text.** Reference a
confidential PDF and a readable markdown copy of it lands in the cache
directory, persisting for 30 days by default. If that is unacceptable for your
material, point `MARKITDOWN_HOOK_CACHE` somewhere encrypted, shorten
`MARKITDOWN_HOOK_CACHE_DAYS`, or narrow `MARKITDOWN_HOOK_EXTS` so sensitive
formats are never converted.

**Document parsers are an attack surface.** Converting a document means parsing
untrusted, structurally complex input — PDF, OOXML, and archive formats all have
had parser vulnerabilities. That exposure belongs to markitdown and its
dependencies, not to this hook, but installing this hook means those parsers now
run automatically on documents you merely *mention*. Keep markitdown updated,
and consider dropping `.zip` from `MARKITDOWN_HOOK_EXTS` if you handle archives
from untrusted sources.

**`.zip` conversion walks archive contents.** Mentioning an archive causes its
members to be extracted and converted. Bear that in mind for large or hostile
archives.

**Configuration can redirect execution.** `MARKITDOWN_BIN` and the
`markitdown_bin` plugin option name a binary this hook will execute. Anything
able to set those, or to write to the file they point at, can run code in your
session. That is the same trust level as any hook, but it is worth stating
plainly.

## Design choices that matter for security

- **Conversion is opt-in per file.** Only paths that appear in your prompt and
  already exist on disk are touched. The hook never scans directories, follows
  links out of a document, or converts anything you did not name.
- **Output is a pointer, not content.** The hook injects a file path and a size
  into context, not the document text, so a converted document does not enter
  the model's context until Claude explicitly reads it.
- **No document content is written to the status line or logs**, only file names
  and sizes.
- **Failures fail closed.** An unusable conversion produces no cached file and
  no pointer, so Claude cannot be handed a path to a partially written artifact.
- **The hook never blocks a prompt**, so a failure here cannot be used to
  suppress your input.

## Supported versions

The latest release on `main` receives fixes. Given the size of the project,
older versions are not separately maintained — upgrade to the current version.
