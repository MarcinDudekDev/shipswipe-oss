#!/usr/bin/env bash
# Regenerate the clean publish directory (dist/) containing ONLY the shippable
# static site — no build cruft (logs, judge_*, screenshots, spec.json, idea.md).
set -euo pipefail
cd "$(dirname "$0")"

SHIP=(
  index.html discover.html matches.html profile.html
  how-it-works.html faq.html about.html
  app.js styles.css
  favicon.ico favicon.svg og-image.png
  robots.txt sitemap.xml
)

rm -rf dist
mkdir -p dist
cp "${SHIP[@]}" dist/
echo "✔ dist/ built ($(du -sh dist | cut -f1), $(ls dist | wc -l | tr -d ' ') files)"
