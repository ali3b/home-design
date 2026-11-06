#!/usr/bin/env bash
# Run a HomeWalk editor method headless:  pipeline/unity.sh HomeWalk.EditorTools.HomeTools.BuildAndShoot [log]
cd "$(dirname "$0")/../HomeWalk"
export DISPLAY=${DISPLAY:-:0}
[ -z "${XAUTHORITY:-}" ] && export XAUTHORITY=$(ls /run/user/$(id -u)/.mutter-Xwaylandauth.* 2>/dev/null | head -1)
LOG=${2:-Logs/$(echo "$1" | awk -F. '{print $NF}').log}
mkdir -p Logs
~/Unity/Hub/Editor/6000.6.0f1/Editor/Unity -batchmode -force-vulkan -projectPath "$PWD" -executeMethod "$1" -quit -logFile "$LOG"
rc=$?
grep -E "\[Home\]|error CS|Exception:|ERROR" "$LOG" | grep -v "Licensing" | head -60
echo "unity exit=$rc"
exit $rc
