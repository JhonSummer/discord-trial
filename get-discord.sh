#!/usr/bin/env bash
# Downloads the latest Discord macOS installer straight from Discord's official link.
set -euo pipefail
URL="https://discord.com/api/download?platform=osx"
OUT="${1:-Discord.dmg}"
echo "Downloading Discord from $URL"
curl -fL "$URL" -o "$OUT"
echo "Saved to $OUT"
