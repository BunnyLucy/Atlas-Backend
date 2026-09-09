#!/usr/bin/env bash
set -euo pipefail

ROOT="${ATLAS_SYSTEMD_ROOT:-/opt/atlas-python}"
ENV_FILE="$ROOT/shared/.env.production"
test "$(id -u)" -eq 0 || { echo "请使用 sudo 运行" >&2; exit 1; }
test -s "$ENV_FILE" || { echo "缺少 $ENV_FILE" >&2; exit 1; }

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y postgresql postgresql-contrib python3-venv pipx rsync curl
if ! command -v uv >/dev/null; then
  PIPX_HOME=/opt/pipx PIPX_BIN_DIR=/usr/local/bin pipx install uv
fi
export UV_PYTHON_INSTALL_DIR="$ROOT/runtime"
uv python install 3.13

id atlas-python >/dev/null 2>&1 || useradd --system --home-dir "$ROOT" --shell /usr/sbin/nologin atlas-python
install -d -o atlas-python -g atlas-python "$ROOT/shared"

set -a
source "$ENV_FILE"
set +a
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD 未配置}"
sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'atlas_python') THEN
    CREATE ROLE atlas_python LOGIN PASSWORD '$POSTGRES_PASSWORD';
  ELSE
    ALTER ROLE atlas_python PASSWORD '$POSTGRES_PASSWORD';
  END IF;
END
\$\$;
SQL
sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='atlas_python'" | grep -q 1 \
  || sudo -u postgres createdb -O atlas_python atlas_python

DATABASE_URL="postgresql+asyncpg://atlas_python:${POSTGRES_PASSWORD}@127.0.0.1:5432/atlas_python"
if grep -q '^ATLAS_DATABASE_URL=' "$ENV_FILE"; then
  sed -i "s#^ATLAS_DATABASE_URL=.*#ATLAS_DATABASE_URL=${DATABASE_URL}#" "$ENV_FILE"
else
  printf 'ATLAS_DATABASE_URL=%s\n' "$DATABASE_URL" >> "$ENV_FILE"
fi
grep -q '^ATLAS_ENV=' "$ENV_FILE" || printf 'ATLAS_ENV=production\n' >> "$ENV_FILE"
grep -q '^ATLAS_COOKIE_SECURE=' "$ENV_FILE" || printf 'ATLAS_COOKIE_SECURE=true\n' >> "$ENV_FILE"
API_HOST=127.0.0.1
if docker network inspect atlas_default >/dev/null 2>&1; then
  API_HOST="$(docker network inspect atlas_default --format '{{(index .IPAM.Config 0).Gateway}}')"
  API_SUBNET="$(docker network inspect atlas_default --format '{{(index .IPAM.Config 0).Subnet}}')"
  if command -v ufw >/dev/null && ufw status | grep -q '^Status: active'; then
    ufw allow from "$API_SUBNET" to "$API_HOST" port 8790 proto tcp comment 'Atlas Caddy to Python API'
  fi
fi
if grep -q '^ATLAS_API_HOST=' "$ENV_FILE"; then
  sed -i "s#^ATLAS_API_HOST=.*#ATLAS_API_HOST=${API_HOST}#" "$ENV_FILE"
else
  printf 'ATLAS_API_HOST=%s\n' "$API_HOST" >> "$ENV_FILE"
fi
chmod 600 "$ENV_FILE"
export ATLAS_DATABASE_URL="$DATABASE_URL" ATLAS_ENV=production ATLAS_COOKIE_SECURE=true ATLAS_API_HOST="$API_HOST"

cd "$ROOT"
PYTHON_BIN="$(uv python find --python-preference only-managed 3.13)"
if [ ! -x .venv/bin/python ] || [[ "$(readlink -f .venv/bin/python)" != "$ROOT/runtime/"* ]]; then
  uv venv --clear --python "$PYTHON_BIN" .venv
fi
UV_DEFAULT_INDEX="${UV_DEFAULT_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}" \
  uv pip install --python .venv/bin/python .

# Preserve any data already written to the former shadow PostgreSQL container.
if docker ps --format '{{.Names}}' | grep -qx atlas-python-postgres-1; then
  docker exec atlas-python-postgres-1 pg_dump -U atlas_python -d atlas_python --clean --if-exists --no-owner --no-privileges > /tmp/atlas-python-shadow.sql
  sed -i '/^SET transaction_timeout =/d' /tmp/atlas-python-shadow.sql
  sudo -u postgres dropdb --if-exists --force atlas_python
  sudo -u postgres createdb -O atlas_python atlas_python
  PGPASSWORD="$POSTGRES_PASSWORD" psql -h 127.0.0.1 -U atlas_python -v ON_ERROR_STOP=1 atlas_python < /tmp/atlas-python-shadow.sql
  rm -f /tmp/atlas-python-shadow.sql
fi
.venv/bin/alembic upgrade head
chown -R atlas-python:atlas-python .venv

install -m 0644 deploy/systemd/atlas-python-api.service /etc/systemd/system/
install -m 0644 deploy/systemd/atlas-python-worker.service /etc/systemd/system/
systemctl daemon-reload

# Only release port 8790 after the native runtime and database are ready.
docker compose --project-name atlas-python --env-file "$ENV_FILE" -f deploy/compose.shadow.yaml down 2>/dev/null || true
systemctl enable --now atlas-python-api atlas-python-worker
systemctl restart atlas-python-api atlas-python-worker

for attempt in {1..30}; do
  curl --fail --silent "http://${API_HOST}:8790/health" && echo && exit 0
  sleep 2
done
journalctl -u atlas-python-api --no-pager -n 80
exit 1
