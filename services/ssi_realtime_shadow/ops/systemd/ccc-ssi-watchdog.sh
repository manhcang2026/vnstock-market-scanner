#!/usr/bin/env bash
set -euo pipefail

CONTAINER="ccc-ssi-shadow"

log() {
  echo "[$(TZ=Asia/Ho_Chi_Minh date '+%Y-%m-%d %H:%M:%S')] $*"
}

if ! state="$(
  docker inspect \
    --format '{{.State.Running}} {{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' \
    "$CONTAINER" 2>/dev/null
)"; then
  log "WATCHDOG_WARNING container=$CONTAINER state=absent action=none"
  exit 0
fi

read -r running health_status <<<"$state"
if [[ "$running" != "true" ]]; then
  log "WATCHDOG_INFO container=$CONTAINER state=stopped action=none"
  exit 0
fi

case "$health_status" in
  healthy | starting)
    exit 0
    ;;
  unhealthy)
    log "WATCHDOG_RESTART container=$CONTAINER reason=unhealthy"
    docker restart "$CONTAINER" >/dev/null
    ;;
  *)
    log "WATCHDOG_WARNING container=$CONTAINER health=${health_status:-unknown} action=none"
    ;;
esac
