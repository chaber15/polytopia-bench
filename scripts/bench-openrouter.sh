#!/bin/bash
# Headline benchmark games for a model reached directly through OpenRouter, run from the Mac.
# The game runs on the PC; this needs the tunnel: ssh -N -L 7777:localhost:7777 pc
# Usage: scripts/bench-openrouter.sh <openrouter-model-id> <effort> <name-prefix> <games>
#   e.g. scripts/bench-openrouter.sh google/gemini-4-argon medium bench-argon-openrouter 2
# Writes logs/<prefix>-<n>.out and logs/<prefix>.done; stops early if OpenRouter reports a usage/limit error.
cd "$(dirname "$0")/../harness" || exit 1
# keep the Mac awake until this script ends (idle sleep drops the tunnel and the model's connection; a closed lid still sleeps)
command -v caffeinate > /dev/null && caffeinate -i -w $$ &
mkdir -p ../logs
# API key: $OPENROUTER_API_KEY, else the file ~/.polytopia-openrouter-key (set a credit limit on the key itself)
[ -n "$OPENROUTER_API_KEY" ] || export OPENROUTER_API_KEY_FILE="${OPENROUTER_API_KEY_FILE:-$HOME/.polytopia-openrouter-key}"
model="$1"; effort="$2"; prefix="$3"; n="${4:-3}"
for i in $(seq 1 "$n"); do
  out="../logs/$prefix-$i.out"
  curl -s -m 60 -X POST -d '{}' http://localhost:7777/quit > /dev/null   # start from the menu
  .venv/bin/python -u -m play --driver openrouter --effort "$effort" --model "$model" --mode Perfection --difficulty Hard --opponents 2 \
    --map-size 14 --map-preset Lakes --choose-tribe --plan-chars 3000 --compact --turns 30 --turn-timeout 900 \
    --max-minutes 240 --system-prompt ../prompts/system-perfection-multi.md > "$out" 2>&1
  curl -s -m 60 -X POST -d '{}' http://localhost:7777/quit > /dev/null
  echo "exit $? $(date)" > "../logs/$prefix-$i.done"
  if grep -qiE "usage limit|rate limit|quota|out of (credits|usage)|exceeded" "$out"; then
    echo "stopped: limit during game $i $(date)" > "../logs/$prefix.limit"; break
  fi
done
echo "finished $(date)" > "../logs/$prefix.done"
