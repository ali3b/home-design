#!/usr/bin/env bash
# Commit + push any changes every INTERVAL seconds (default 600). Stop with: touch .autopush.stop
cd "$(dirname "$0")/.."
INTERVAL=${INTERVAL:-600}
rm -f .autopush.stop
while [ ! -f .autopush.stop ]; do
  git add -A
  if ! git diff --cached --quiet; then
    stage=$(tail -n1 docs/progress.md 2>/dev/null | sed 's/^[-* ]*//' | cut -c1-60)
    git commit -q -m "WIP $(date '+%Y-%m-%d %H:%M'): ${stage:-progress}" && echo "[autopush] committed $(date +%T)"
  fi
  git push -q origin main 2>&1 | sed 's/^/[autopush] /'
  for i in $(seq 1 $INTERVAL); do [ -f .autopush.stop ] && break; sleep 1; done
done
echo "[autopush] stopped"
