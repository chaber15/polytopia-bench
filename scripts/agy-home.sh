#!/bin/bash
# Gives the harness its own Antigravity login (GEMINI_HOME for its ACP server, default ~/.polytopia-agy) by copying the
# one T3 Code made when you signed in to Antigravity there. A copy, because the ACP server deletes its stored login
# whenever a sign-in fails; this way that can never sign T3 out. Re-run it if a game reports "no Antigravity login".
set -e
home="${POLY_AGY_HOME:-$HOME/.polytopia-agy}"
src=$(ls -td "$HOME"/.t3/userdata/providers/antigravity/*/antigravity-acp 2>/dev/null | head -1)
[ -f "$src/acp_token.json" ] || { echo "no T3 Antigravity login found: sign in to Antigravity in T3 Code first"; exit 1; }
mkdir -p "$home/antigravity-acp" && chmod 700 "$home"
cp -p "$src/acp_token.json" "$src/settings.json" "$home/antigravity-acp/"
echo "Antigravity login copied to $home"
