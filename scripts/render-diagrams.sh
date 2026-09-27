#!/usr/bin/env bash
# Render docs/diagrams/*.mmd to PNG with mermaid-cli.
# Chrome has no linux-arm64 build, so on the DGX Spark this uses Playwright's Chromium.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIAGRAMS="$ROOT/docs/diagrams"
TOOLS="${MERMAID_TOOLS_DIR:-$HOME/.cache/talent-chat-mermaid}"

mkdir -p "$TOOLS"
if [ ! -x "$TOOLS/node_modules/.bin/mmdc" ]; then
  (cd "$TOOLS" && npm init -y >/dev/null && PUPPETEER_SKIP_DOWNLOAD=1 npm install --silent @mermaid-js/mermaid-cli playwright)
fi

CHROME="${CHROME_PATH:-}"
if [ -z "$CHROME" ]; then
  (cd "$TOOLS" && npx playwright install chromium >/dev/null)
  CHROME="$(find "${PLAYWRIGHT_BROWSERS_PATH:-$HOME/.cache/ms-playwright}" -type f -path '*chrome-linux*' -name chrome 2>/dev/null | head -1)"
fi
[ -x "$CHROME" ] || { echo "Chromium not found; set CHROME_PATH" >&2; exit 1; }

cat > "$TOOLS/puppeteer.json" <<EOF
{"executablePath": "$CHROME", "args": ["--no-sandbox", "--disable-gpu"]}
EOF

for src in "$DIAGRAMS"/*.mmd; do
  out="${src%.mmd}.png"
  "$TOOLS/node_modules/.bin/mmdc" -p "$TOOLS/puppeteer.json" -c "$DIAGRAMS/mermaid-config.json" \
    -i "$src" -o "$out" -s 2 -b white -q
  echo "rendered $(basename "$out")"
done
