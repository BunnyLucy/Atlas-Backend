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
curl --fail --silent --show-error http://127.0.0.1:8790/health
