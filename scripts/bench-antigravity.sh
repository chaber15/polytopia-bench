#!/bin/bash
# Headline benchmark games for an Antigravity (Gemini) model, run from a second machine (an Antigravity ACP server signed in here, e.g. the one T3 Code installs; run scripts/agy-home.sh once).
# The game runs on the Windows PC; from another machine this needs a tunnel: ssh -N -L 7777:localhost:7777 <pc-host> (docs/SETUP.md)
# Usage: scripts/bench-antigravity.sh <model-id> <effort> <name-prefix> <games>
#   e.g. scripts/bench-antigravity.sh gemini-3.8-flash medium bench-flash38-medium 3
# Writes logs/<prefix>-<n>.out and logs/<prefix>.done; stops early if Antigravity reports a usage/limit error.
cd "$(dirname "$0")/../harness" || exit 1
# on macOS, keep the machine awake until this script ends (idle sleep drops the tunnel and the model's connection; a closed lid still sleeps)
command -v caffeinate > /dev/null && caffeinate -i -w $$ &
mkdir -p ../logs
model="$1"; effort="$2"; prefix="$3"; n="${4:-3}"
for i in $(seq 1 "$n"); do
  out="../logs/$prefix-$i.out"
  curl -s -m 60 -X POST -d '{}' http://localhost:7777/quit > /dev/null   # start from the menu
  .venv/bin/python -u -m play --driver antigravity --effort "$effort" --model "$model" --mode Perfection --difficulty Hard --opponents 2 \
    --map-size 14 --map-preset Lakes --choose-tribe --plan-chars 3000 --compact --turns 30 --turn-timeout 900 \
    --max-minutes 240 --system-prompt ../prompts/system-perfection-multi.md > "$out" 2>&1
  curl -s -m 60 -X POST -d '{}' http://localhost:7777/quit > /dev/null
  echo "exit $? $(date)" > "../logs/$prefix-$i.done"
  if grep -qiE "usage limit|rate limit|quota|out of (credits|usage)|quota exceeded" "$out"; then
    echo "stopped: limit during game $i $(date)" > "../logs/$prefix.limit"; break
  fi
done
echo "finished $(date)" > "../logs/$prefix.done"
