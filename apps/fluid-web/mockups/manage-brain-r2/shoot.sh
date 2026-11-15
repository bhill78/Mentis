#!/usr/bin/env bash
# Render each Manage Brain mockup in Chrome, dark and light, at its page size.
#   cd apps/fluid-web && python -m http.server 8912 --bind 127.0.0.1 &
#   bash mockups/manage-brain/shoot.sh
set -euo pipefail
CHROME=${CHROME:-"/c/Program Files/Google/Chrome/Application/chrome.exe"}
BASE=${BASE:-"http://127.0.0.1:8912/mockups/manage-brain-r2"}
OUT="$(cd "$(dirname "$0")" && pwd)/shots"
mkdir -p "$OUT"
STAMP=$(date +%s)
PROFILE="C:/tmp/manage-brain-r2-shoot"
rm -rf "$PROFILE"
shot () { # page width height theme
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1 --user-data-dir="$PROFILE" \
    --window-size="$2,$3" --screenshot="$(cygpath -w "$OUT/$1-$4.png")" "$BASE/$1.html?theme=$4&v=$STAMP" >/dev/null 2>&1
  echo "  $1-$4.png ${2}x${3}"
}
for t in dark light; do
  shot 1-brain-rail 1440 900 $t
  shot 2-record 1440 900 $t
  shot 3-record-details 1440 900 $t
  shot 4-decision 1440 900 $t
  shot 5-beside-conversation 1440 900 $t
  shot 6-phone-list 390 844 $t
  shot 6-phone-record 390 844 $t
done
