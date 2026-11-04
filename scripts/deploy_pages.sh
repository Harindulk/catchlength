#!/bin/sh
# Publish web/ as the live demo on GitHub Pages (free, no extra account; the repo must be public).
# Rerun after every change to web/. The site is static: it replays the recorded runs.
set -e
cd "$(dirname "$0")/.."
git branch -D gh-pages 2>/dev/null || true
git subtree split --prefix web -b gh-pages
git push -f origin gh-pages
gh api -X POST repos/Harindulk/catchlength/pages -f 'source[branch]=gh-pages' -f 'source[path]=/' >/dev/null 2>&1 \
  || gh api -X PUT repos/Harindulk/catchlength/pages -f 'source[branch]=gh-pages' -f 'source[path]=/' >/dev/null
echo "Pages builds in about a minute: https://links.harindu.dev/catchlength/"
