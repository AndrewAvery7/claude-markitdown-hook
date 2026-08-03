# The promo video

`claude-markitdown-hook-promo.mp4` — 1:15, 1920×1080, shipped as a **release
asset** rather than committed. `assets/*.mp4` is gitignored: at ~9 MB the file
would be by far the heaviest thing here, and every rebuild would add another
copy to history forever.

```
[ title card 1.7s ] → [ AI hero shot ] → [ motion-graphics core ] → [ AI end card ]
```

## The title card

The card is frame 0, and **frame 0 is the README thumbnail**.

GitHub's inline player is generated from a bare `user-attachments` URL, and its
markdown sanitiser strips author-written `<video>` — so there is no `poster`
attribute a README can set. The browser simply shows the first frame. This promo
opens on a generative hero clip that begins near-black while the light builds,
which rendered as an empty rectangle on the repository front page.

A designed card fixes the thumbnail and reads as a title rather than as a
workaround. It composites `assets/endcard-logo.png` instead of redrawing the
mark, so it cannot drift from the logo the rest of the project uses, and it
takes its palette and typefaces from `tools/make-promo.py` so the card and the
film that follows are one piece of design. Every line on it is a claim the
README already makes — the tagline is the README's subtitle, the strip is the
badge row.

```bash
python tools/make-title-card.py          # -> assets/poster.png
bash tools/prepend-title-card.sh PROMO.mp4 assets/poster.png OUT.mp4
```

## Why the card is prepended rather than stitched

`tools/stitch-promo.sh` builds the film from its sources — the generative
bookends and the music bed. Those are **not in the repository**; they are large
binaries that were never committed. The card was added long after the promo
shipped, so it is applied to the finished film instead.

`stitch-promo.sh` remains the tool for a full rebuild from sources.
`prepend-title-card.sh` is the tool for the far more common case of having only
the released MP4. It shifts the audio by exactly the amount it pushes the
picture back, so the card plays silent and the film's own opening still lands on
its first frame.

## Publishing

1. `gh release upload vX.Y.Z assets/claude-markitdown-hook-promo.mp4 --clobber`.
   The README links `releases/latest/download/…`, so **every release must carry
   the file** or that link 404s.
2. The inline player needs a `user-attachments` URL, which only comes from
   dragging the file into an issue or pull-request comment in the web UI **and
   submitting that comment** — an abandoned draft uploads the file but does not
   retain it, and the URL then 404s. There is no API for this.

   Attachments are immutable, so **changing the video means a new upload and a
   new URL**; the old one keeps serving the old cut forever.

   Verify before committing a URL — a live attachment answers an unsigned
   request with **302 or 403**, a dead one with **404**:

   ```bash
   curl -sS -o /dev/null -w '%{http_code}\n' -I https://github.com/user-attachments/assets/<uuid>
   ```
