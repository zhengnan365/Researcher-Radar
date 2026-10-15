#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/www/wwwroot/researcher-radar}"
BACKEND_DIR="$PROJECT_DIR/backend"

cd "$BACKEND_DIR"

if [ ! -f ".venv/bin/activate" ]; then
  echo "Virtualenv not found: $BACKEND_DIR/.venv" >&2
  exit 1
fi

source .venv/bin/activate

echo "== Zotero config =="
python manage.py shell -c "from papers.models import ZoteroConfig; c=ZoteroConfig.get_active(); print({'library_type': c.library_type if c else None, 'user_id': c.user_id if c else None, 'group_id': c.group_id if c else None, 'has_api_key': bool(c.api_key) if c else False, 'enabled': c.enabled if c else None})"

echo "== Zotero API network =="
curl -I --max-time 20 https://api.zotero.org/ || true

echo "== Zotero library smoke test =="
python manage.py shell -c "from papers.services.zotero_api import read_zotero_library; data=read_zotero_library(max_items=3, refresh=True, full_sync=False); print({'items': data.get('total_items'), 'cached_total_items': data.get('cached_total_items'), 'collections': len(data.get('collections', [])), 'sync_error': data.get('sync_error', '')})"
