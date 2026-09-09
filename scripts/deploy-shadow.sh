#!/usr/bin/env bash
set -euo pipefail

ROOT="${ATLAS_SHADOW_ROOT:-/opt/atlas-python}"
COMPOSE="$ROOT/deploy/compose.shadow.yaml"
ENV_FILE="$ROOT/shared/.env.production"

test -f "$COMPOSE" || { echo "缺少 $COMPOSE" >&2; exit 1; }
test -f "$ENV_FILE" || { echo "缺少 $ENV_FILE" >&2; exit 1; }

docker compose --project-name atlas-python --env-file "$ENV_FILE" -f "$COMPOSE" build
docker compose --project-name atlas-python --env-file "$ENV_FILE" -f "$COMPOSE" up -d
docker compose --project-name atlas-python --env-file "$ENV_FILE" -f "$COMPOSE" ps
for attempt in {1..30}; do
  if curl --fail --silent --show-error http://127.0.0.1:8790/health; then
    exit 0
  fi
  sleep 2
done
echo "影子 API 未在 60 秒内通过健康检查" >&2
exit 1
