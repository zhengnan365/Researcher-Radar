#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${PROJECT_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
BACKEND_DIR="$PROJECT_DIR/backend"
LOG_FILE="$PROJECT_DIR/logs/researcher-radar.log"
if [ "$PROJECT_DIR" = "/www/wwwroot/researcher-radar" ]; then
  LOG_FILE="$PROJECT_DIR/logs/literature_daily.log"
fi
CRON_INPUT="${1:-${CRON_EXPR:-0 8 * * *}}"

normalize_cron_expr() {
  local raw="$1"
  raw="$(echo "$raw" | xargs)"
  if [[ "$raw" =~ ^[0-9]{1,2}$ ]]; then
    echo "0 $raw * * *"
    return
  fi
  if [[ "$raw" =~ ^([0-9]{1,2}):([0-9]{1,2})$ ]]; then
    echo "${BASH_REMATCH[2]} ${BASH_REMATCH[1]} * * *"
    return
  fi
  if [ "$(echo "$raw" | awk '{print NF}')" -eq 5 ]; then
    echo "$raw"
    return
  fi
  echo ""
}

CRON_EXPR_NORMALIZED="$(normalize_cron_expr "$CRON_INPUT")"
if [ -z "$CRON_EXPR_NORMALIZED" ]; then
  echo "Invalid cron expression: $CRON_INPUT" >&2
  echo "Examples: 8, 08:30, 0 8 * * *" >&2
  exit 1
fi

CRON_CMD="cd $BACKEND_DIR && set -a && . $PROJECT_DIR/.env && set +a && $BACKEND_DIR/.venv/bin/python manage.py fetch_daily_papers >> $LOG_FILE 2>&1"
CRON_LINE="$CRON_EXPR_NORMALIZED $CRON_CMD"

if [ ! -x "$BACKEND_DIR/.venv/bin/python" ]; then
  echo "Virtualenv python not found: $BACKEND_DIR/.venv/bin/python" >&2
  exit 1
fi

mkdir -p "$PROJECT_DIR/logs"

current_cron="$(mktemp)"
crontab -l > "$current_cron" 2>/dev/null || true

if grep -Fq "$CRON_CMD" "$current_cron"; then
  grep -Fv "$CRON_CMD" "$current_cron" > "$current_cron.next" || true
  mv "$current_cron.next" "$current_cron"
  printf "\n%s\n" "$CRON_LINE" >> "$current_cron"
  crontab "$current_cron"
  echo "Cron job updated: $CRON_LINE"
else
  printf "\n%s\n" "$CRON_LINE" >> "$current_cron"
  crontab "$current_cron"
  echo "Cron job installed: $CRON_LINE"
fi

rm -f "$current_cron"
