#!/usr/bin/env bash
# Put a still title card on the front of an already-finished promo.
#
#   tools/prepend-title-card.sh PROMO.mp4 POSTER.png OUT.mp4 [CARD_LEN] [XFADE]
#
# Why this exists as its own script rather than a step inside stitch-promo.sh:
# the card was added long after the promo shipped, and the pieces that built it
# - the generative bookends and the music bed - are not in the repository. They
# were never committed, because they are large binaries that can be regenerated.
# So the card is prepended to the finished film. stitch-promo.sh remains the
# tool for a full rebuild from sources; this is the tool for the far more common
# case of having only the released MP4.
#
# What the card is for: GitHub's inline player takes its thumbnail from frame 0
# and offers no `poster` a README can set, and the promo opens on a near-black
# generative shot. The front page therefore showed an empty rectangle.
#
# The audio is delayed by the same amount the picture is pushed back, so the
# card plays silent and the film's own opening still lands on its first frame.
set -euo pipefail

SRC="${1:?finished promo mp4}"
POSTER="${2:?title card png}"
OUT="${3:?output path}"
CARD_LEN="${4:-1.7}"   # seconds the card holds before the film
XFADE="${5:-0.5}"      # card -> film crossfade

calc() { awk "BEGIN{printf \"%.3f\", $1}"; }

SRC_LEN=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$SRC")
SHIFT=$(calc "$CARD_LEN - $XFADE")
TOTAL=$(calc "$SRC_LEN + $SHIFT")

# Some promos have no audio track at all; mapping one that does not exist fails
# the whole render, so ask first rather than assume.
HAS_AUDIO=$(ffprobe -v error -select_streams a -show_entries stream=index -of csv=p=0 "$SRC" | head -1)

echo "card=${CARD_LEN}s  xfade=${XFADE}s  source=${SRC_LEN}s  ->  total=${TOTAL}s"

FILTER="
[1:v]trim=0:${CARD_LEN},setpts=PTS-STARTPTS,scale=1920:1080,fps=24,format=yuv420p[card];
[0:v]scale=1920:1080,fps=24,format=yuv420p[film];
[card][film]xfade=transition=fade:duration=${XFADE}:offset=${SHIFT}[vout]"

if [ -n "$HAS_AUDIO" ]; then
  FILTER="${FILTER};
[0:a]asetpts=N/SR/TB,aresample=48000,
     adelay=$(calc "$SHIFT * 1000")|$(calc "$SHIFT * 1000")[aout]"
  MAP=(-map "[vout]" -map "[aout]" -c:a aac -b:a 192k)
else
  echo "note: source has no audio track; output will be silent"
  MAP=(-map "[vout]")
fi

ffmpeg -y -i "$SRC" -loop 1 -i "$POSTER" -filter_complex "$FILTER" \
  "${MAP[@]}" -c:v libx264 -preset slow -crf 19 -pix_fmt yuv420p \
  -movflags +faststart "$OUT"

echo "wrote $OUT"
ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT"
