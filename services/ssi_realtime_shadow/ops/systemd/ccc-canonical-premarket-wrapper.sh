#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/ccc-realtime/app/services/ssi_realtime_shadow"
COMPOSE_FILE="$APP_DIR/docker-compose.yml"
TODAY="${1:-$(TZ=Asia/Ho_Chi_Minh date +%F)}"

log() {
  echo "[$(TZ=Asia/Ho_Chi_Minh date '+%Y-%m-%d %H:%M:%S')] $*"
}

restart_collector() {
  local status=$?
  local restart_status=0
  trap - EXIT
  log "Canonical premarket restarting collector"
  docker compose -f "$COMPOSE_FILE" up -d collector || restart_status=$?
  if [[ "$restart_status" -ne 0 ]]; then
    log "Canonical premarket collector restart failed status=$restart_status"
    [[ "$status" -ne 0 ]] || status="$restart_status"
  fi
  log "Canonical premarket end day=$TODAY status=$status"
  exit "$status"
}

log "Canonical premarket safety check day=$TODAY"
docker compose -f "$COMPOSE_FILE" run --rm --no-deps collector \
  python -m app.canonical_premarket check \
    --date "$TODAY" \
    --db-dir /app/data

trap restart_collector EXIT
log "Canonical premarket stopping collector"
docker compose -f "$COMPOSE_FILE" stop collector
docker compose -f "$COMPOSE_FILE" run --rm --no-deps collector \
  python -m app.rebuild_engine \
    --market-db-dir /app/data \
    --engine-db /app/data/ccc_engine.db \
    --as-of-date "$TODAY"
docker compose -f "$COMPOSE_FILE" run --rm --no-deps collector \
  python -m app.canonical_premarket validate \
    --date "$TODAY" \
    --engine-db /app/data/ccc_engine.db
