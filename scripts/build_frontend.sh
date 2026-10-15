#!/usr/bin/env bash
set -euo pipefail

DOMAIN="${1:-${DOMAIN:-}}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${PROJECT_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
FRONTEND_DIR="$PROJECT_DIR/frontend"

if [ -z "$DOMAIN" ]; then
  echo "请提供域名：bash scripts/build_frontend.sh your-domain.com" >&2
  exit 1
fi

if [ ! -d "$FRONTEND_DIR" ]; then
  echo "Frontend directory not found: $FRONTEND_DIR" >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm not found. Install with: apt install -y nodejs npm" >&2
  exit 1
fi

cd "$FRONTEND_DIR"

cat > .env.production <<EOF
VITE_API_BASE_URL=https://$DOMAIN/api
VITE_ADMIN_URL=https://$DOMAIN/admin/
EOF

npm install
npm run build

echo "Frontend built at $FRONTEND_DIR/dist"
