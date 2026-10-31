#!/bin/bash
# Headline benchmark games for a Cursor model, run from the Mac (Cursor CLI logged in here).
# The game runs on the PC; this needs the tunnel: ssh -N -L 7777:localhost:7777 pc
# Usage: scripts/bench-cursor.sh <cursor-model-id> <name-prefix> <games>
#   e.g. scripts/bench-cursor.sh grok-4.7-medium bench-grok47-medium 3
# Writes logs/<prefix>-<n>.out and logs/<prefix>.done; stops early if Cursor reports a usage/limit error.
cd "$(dirname "$0")/../harness" || exit 1
mkdir -p ../logs
model="$1"; prefix="$2"; n="${3:-3}"
for i in $(seq 1 "$n"); do
  out="../logs/$prefix-$i.out"
  curl -s -m 60 -X POST -d '{}' http://localhost:7777/quit > /dev/null   # start from the menu
  .venv/bin/python -u -m play --driver cursor --model "$model" --mode Perfection --difficulty Hard --opponents 2 \
    --map-size 14 --map-preset Lakes --choose-tribe --plan-chars 3000 --compact --turns 30 --turn-timeout 900 \
    --max-minutes 240 --system-prompt ../prompts/system-perfection-multi.md > "$out" 2>&1
  curl -s -m 60 -X POST -d '{}' http://localhost:7777/quit > /dev/null
  echo "exit $? $(date)" > "../logs/$prefix-$i.done"
  if grep -qiE "usage limit|rate limit|quota|out of (credits|usage)|exceeded" "$out"; then
    echo "stopped: limit during game $i $(date)" > "../logs/$prefix.limit"; break
  fi
done
echo "finished $(date)" > "../logs/$prefix.done"
