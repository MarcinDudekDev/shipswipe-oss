#!/usr/bin/env bash
# Build the publish dir and deploy it to Cloudflare Pages.
#
# Required env: CLOUDFLARE_API_KEY, CLOUDFLARE_EMAIL, CLOUDFLARE_ACCOUNT_ID.
# Optional env: PROJECT_NAME (default "shipswipe").
set -euo pipefail
cd "$(dirname "$0")"

./build.sh

: "${CLOUDFLARE_API_KEY:?set CLOUDFLARE_API_KEY}"
: "${CLOUDFLARE_EMAIL:?set CLOUDFLARE_EMAIL}"
: "${CLOUDFLARE_ACCOUNT_ID:?set CLOUDFLARE_ACCOUNT_ID}"
export CLOUDFLARE_API_KEY CLOUDFLARE_EMAIL CLOUDFLARE_ACCOUNT_ID

npx --yes wrangler@latest pages deploy dist \
  --project-name="${PROJECT_NAME:-shipswipe}" --branch=main --commit-dirty=true
