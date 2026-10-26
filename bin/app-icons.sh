#!/usr/bin/env bash
# Render the home-screen icons from frontend/icons/app-icon.svg.
#
# The PNGs are committed, so building the image needs no SVG renderer; run this after changing
# the drawing. Needs rsvg-convert (librsvg).
set -euo pipefail

web="$(cd "$(dirname "$0")/../frontend" && pwd)"
source="$web/icons/app-icon.svg"
out="$web/public/icons"
mkdir -p "$out"

# 192 and 512 are the sizes the manifest names; 180 is the size iOS asks of apple-touch-icon.
for size in 192 512; do
  rsvg-convert --background-color "#2f6f5e" --width "$size" --height "$size" "$source" \
    --output "$out/icon-$size.png"
done
rsvg-convert --background-color "#2f6f5e" --width 180 --height 180 "$source" \
  --output "$out/apple-touch-icon.png"
echo "Wrote icon-192.png, icon-512.png and apple-touch-icon.png in $out"
