#!/bin/bash
# Renders highlights.html to highlights.png (2x, for posting) and highlights.pdf with headless Chrome.
# Works from a temporary copy, since file:// URLs can't contain characters like "?" in the folder path.
set -e
cd "$(dirname "$0")"
CH="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
tmp=$(mktemp -d); cp -R highlights.html data.js polymap.js diorama.js img "$tmp/"
"$CH" --headless --disable-gpu --hide-scrollbars --force-device-scale-factor=2 --window-size=1200,1660 \
  --virtual-time-budget=3000 --screenshot="$PWD/highlights.png" "file://$tmp/highlights.html" 2>/dev/null
"$CH" --headless --disable-gpu --no-pdf-header-footer --virtual-time-budget=3000 \
  --print-to-pdf="$PWD/highlights.pdf" "file://$tmp/highlights.html" 2>/dev/null
rm -rf "$tmp"; ls -la highlights.png highlights.pdf
