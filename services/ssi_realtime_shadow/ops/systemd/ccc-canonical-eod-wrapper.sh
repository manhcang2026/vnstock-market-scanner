#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/ccc-realtime/app/services/ssi_realtime_shadow"
COMPOSE_FILE="$APP_DIR/docker-compose.yml"
DAY=""

log() {
  echo "[$(TZ=Asia/Ho_Chi_Minh date '+%Y-%m-%d %H:%M:%S')] $*"
}

restart_collector() {
  local status=$?
  local restart_status=0
  trap - EXIT
  log "Canonical EOD restarting collector"
  docker compose -f "$COMPOSE_FILE" up -d collector || restart_status=$?
  if [[ "$restart_status" -ne 0 ]]; then
    log "Canonical EOD collector restart failed status=$restart_status"
    [[ "$status" -ne 0 ]] || status="$restart_status"
  fi
  log "Canonical EOD end day=$DAY status=$status"
  exit "$status"
}

log "Canonical EOD resolving safe target"
if ! RESOLUTION="$(docker compose -f "$COMPOSE_FILE" run --rm --no-deps collector \
  python -m app.canonical_eod \
    --resolve-target \
    --db-dir /app/data)"; then
  log "Canonical EOD target resolution failed: $RESOLUTION"
  exit 2
fi
log "$RESOLUTION"
case "$RESOLUTION" in
  "EOD_TARGET day="*)
    DAY="${RESOLUTION#EOD_TARGET day=}"
    DAY="${DAY%% *}"
    ;;
  REFUSED_ACTIVE_MARKET*|REFUSED_EOD_NOT_READY*|SKIP_NO_EOD_TARGET*)
    exit 0
    ;;
  *)
    log "Unexpected canonical EOD resolution: $RESOLUTION"
    exit 2
    ;;
esac

log "Canonical EOD start day=$DAY"
trap restart_collector EXIT
docker compose -f "$COMPOSE_FILE" stop collector
docker compose -f "$COMPOSE_FILE" run --rm --no-deps collector \
  python -m app.canonical_eod \
    --date "$DAY" \
    --db-dir /app/data \
    --request-interval 0.5
