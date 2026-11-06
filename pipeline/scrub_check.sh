#!/usr/bin/env bash
# Pre-commit guard: block private site data and paid asset files from the public repo.
set -u
staged=$(git diff --cached --name-only --diff-filter=ACM)
[ -z "$staged" ] && exit 0
fail=0
while IFS= read -r f; do
  case "$f" in
    *Architect_Property_Pack*|*.unitypackage|*.zip|*/Synty/*|*.private.json|"Concepts and Plan/concept"[2-9]*)
      echo "scrub_check: blocked file $f"; fail=1;;
  esac
done <<< "$staged"
# content patterns (coordinates, locality name)
if git diff --cached -U0 -- . ':(exclude)pipeline/scrub_check.sh' | grep -E '^\+' | grep -iE '20\.746|106\.683|Ki[eế]n Th[uụ]y' >/dev/null; then
  echo "scrub_check: staged content contains private site coordinates/locality"; fail=1
fi
[ $fail -eq 0 ] || { echo "Commit blocked by pipeline/scrub_check.sh"; exit 1; }
