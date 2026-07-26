#!/usr/bin/env bash
# Stitch the claude-markitdown-hook promo from its sources:
#
#   [ AI hero shot + lower-third title ] -> [ motion-graphics core ] -> [ AI end card + logo ]
#
# The bookends are generative-video clips (abstract light and haze - what those
# models do well). The core is tools/make-promo.py output, where every command
# string is rendered from source so it is always exact; generative models garble
# long strings and the whole point of this video is text being read correctly.
#
# Audio is staged in two parts:
#   * The opening plays the hero clip's OWN native audio, alone - no music over it.
#   * The music bed starts as the opening crossfades into the story and carries
#     the rest of the piece.
# The bed runs through loudnorm and dynaudnorm because generated music tends to
# ramp or dip mid-track; normalising guarantees a steady level rather than a bed
# that appears to "kick in" halfway through.
#
# Usage:
#   tools/stitch-promo.sh HERO.mp4 CORE.mp4 ENDCARD.mp4 OVERLAY.png LOGO.png BED.mp3 OUT.mp4
set -euo pipefail

HERO="${1:?hero clip}"
CORE="${2:?core clip}"
END="${3:?end card clip}"
OVERLAY="${4:?lower-third png}"
LOGO="${5:?logo png for the end card}"
BED="${6:?music bed}"
OUT="${7:?output path}"

HERO_LEN=6.2      # seconds of the hero shot to keep
END_LEN=3.6       # seconds of the end card to keep
XF1=0.7           # hero -> core crossfade
XF2=0.6           # core -> end card crossfade
TITLE_IN=1.0      # lower-third fade in
TITLE_OUT=4.4     # lower-third fade out (clears before the crossfade)
LOGO_IN=0.5       # end-card logo fade in
HERO_VOL=1.00     # native hero audio owns the opening on its own
BED_VOL=0.90      # trim after loudnorm has already set the bed's loudness

# awk for arithmetic - bc is not present in Git Bash or minimal images
calc() { awk "BEGIN{printf \"%.3f\", $1}"; }

CORE_LEN=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$CORE")
OFF1=$(calc "$HERO_LEN - $XF1")
MID_LEN=$(calc "$HERO_LEN + $CORE_LEN - $XF1")
OFF2=$(calc "$MID_LEN - $XF2")
TOTAL=$(calc "$MID_LEN + $END_LEN - $XF2")
MUSIC_START="$OFF1"   # bed enters exactly as the opening starts crossfading out
BED_LEN=$(calc "$TOTAL - $MUSIC_START")

echo "core=${CORE_LEN}s  xfade1@${OFF1}s  xfade2@${OFF2}s  music@${MUSIC_START}s  total=${TOTAL}s"

ffmpeg -y -i "$HERO" -i "$CORE" -i "$END" \
       -loop 1 -i "$OVERLAY" -loop 1 -i "$LOGO" -i "$BED" -filter_complex "
[0:v]trim=0:${HERO_LEN},setpts=PTS-STARTPTS,scale=1920:1080,fps=24,format=yuva420p[hv];
[3:v]trim=0:${HERO_LEN},setpts=PTS-STARTPTS,scale=1920:1080,fps=24,format=yuva420p,
     fade=t=in:st=${TITLE_IN}:d=0.8:alpha=1,fade=t=out:st=${TITLE_OUT}:d=0.8:alpha=1[ov];
[hv][ov]overlay=0:0:format=auto,format=yuv420p[v0];
[1:v]scale=1920:1080,fps=24,format=yuv420p[v1];
[2:v]trim=0:${END_LEN},setpts=PTS-STARTPTS,
     crop=iw*0.94:ih*0.94,scale=1920:1080,fps=24,format=yuva420p[ev];
[4:v]trim=0:${END_LEN},setpts=PTS-STARTPTS,scale=1040:-1,fps=24,format=yuva420p,
     fade=t=in:st=${LOGO_IN}:d=0.9:alpha=1[lg];
[ev][lg]overlay=(W-w)/2:(H-h)/2:format=auto,format=yuv420p[v2];
[v0][v1]xfade=transition=fade:duration=${XF1}:offset=${OFF1}[x1];
[x1][v2]xfade=transition=fade:duration=${XF2}:offset=${OFF2}[vout];
[0:a]atrim=0:${HERO_LEN},asetpts=N/SR/TB,volume=${HERO_VOL},
     afade=t=out:st=$(calc "$HERO_LEN - 0.9"):d=0.9,aresample=48000,apad[ha];
[5:a]atrim=0:${BED_LEN},asetpts=N/SR/TB,
     acompressor=threshold=0.15:ratio=4:attack=20:release=250:makeup=2,
     loudnorm=I=-15:TP=-1.2:LRA=6,dynaudnorm=f=200:g=13:p=0.9:m=8,
     alimiter=limit=0.95,volume=${BED_VOL},
     afade=t=in:st=0:d=1.2,afade=t=out:st=$(calc "$BED_LEN - 2.8"):d=2.8,
     aresample=48000,adelay=$(calc "$MUSIC_START * 1000")|$(calc "$MUSIC_START * 1000")[ma];
[ha][ma]amix=inputs=2:duration=longest:normalize=0,atrim=0:${TOTAL}[aout]
" -map "[vout]" -map "[aout]" \
  -c:v libx264 -preset slow -crf 19 -pix_fmt yuv420p \
  -c:a aac -b:a 192k -movflags +faststart "$OUT"

echo "wrote $OUT"
ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT"
