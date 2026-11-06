#!/usr/bin/env bash
# Full pipeline for one concept:  pipeline/make.sh c1_courtyard_house c1 [--fast] [--no-unity]
set -e
cd "$(dirname "$0")/.."
NAME=${1:-c1_courtyard_house}; KEY=${2:-c1}
C=concepts/$NAME.json; OUT=out/$KEY
FAST=""; [[ " $* " == *" --fast "* ]] && FAST="--fast"
python3 pipeline/validate.py "$C" --json $OUT/validate.json
python3 pipeline/sheets.py "$C" $OUT/sheets --dpi 150
python3 pipeline/textures.py HomeWalk/Assets/Home/Textures >/dev/null
blender -b --factory-startup --python pipeline/blender/build.py -- "$C" $OUT/render $FAST \
    --fbx HomeWalk/Assets/Home/Models/${KEY}_architecture.fbx | grep -E "FBX_OK|RENDER_|Traceback"
if [[ " $* " != *" --no-unity "* ]]; then
  pipeline/unity.sh HomeWalk.EditorTools.HomeTools.ReleaseAll Logs/release.log
fi
python3 pipeline/review.py "$C" $OUT
python3 pipeline/publish_docs.py $OUT $KEY
echo MAKE_DONE
