#!/usr/bin/env bash
# Render each mockup in a real browser (Windows Chrome, the one the owner tests
# in) at the surface's measured pixel size, and write a PNG beside it.
#
#   cd apps/fluid-web && python -m http.server 8911 --bind 127.0.0.1 &
#   bash mockups/quiet-mk2/shoot.sh
#
# The window size is the surface's size, measured from the live CSS; see the
# header of mock.css for where each number comes from.
set -euo pipefail

CHROME=${CHROME:-"/c/Program Files/Google/Chrome/Application/chrome.exe"}
BASE=${BASE:-"http://127.0.0.1:8911/mockups/quiet-mk2"}
OUT="$(cd "$(dirname "$0")" && pwd)/shots"
mkdir -p "$OUT"
# A fresh browser profile and a fresh URL each run: nothing is served from a
# cache, so a re-render always shows the edit that was just made.
STAMP=$(date +%s)
PROFILE="C:/tmp/quiet-mk2-shoot-chrome"
rm -rf "$PROFILE"

shot () { # page  width  height
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars \
    --force-device-scale-factor=1 --user-data-dir="$PROFILE" \
    --window-size="$2,$3" --screenshot="$(cygpath -w "$OUT/$1.png")" \
    "$BASE/$1.html?v=$STAMP" >/dev/null 2>&1
  echo "  $1.png  ${2}x${3}"
}

# the composer: a 680px composer inside the 728px reading column (.q2-col)
shot composer-normal              728 560
shot composer-operations          728 760
shot composer-ops-who             728 740
shot composer-ops-where           728 700
# the Activity popup, at its own size (.q2-gdock-panel)
shot capacity-default             360 520
shot capacity-expanded            360 520
shot capacity-diagnostics         360 520
