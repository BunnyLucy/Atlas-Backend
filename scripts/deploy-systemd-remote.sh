#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:?用法: $0 ubuntu@服务器IP SSH密钥路径}"
KEY="${2:?用法: $0 ubuntu@服务器IP SSH密钥路径}"
ROOT="/opt/atlas-python"
SSH=(ssh -i "$KEY" -o BatchMode=yes)

rsync -az --delete \
  --exclude .git --exclude .venv --exclude .env --exclude shared/ \
  -e "ssh -i $KEY -o BatchMode=yes" ./ "$TARGET:/tmp/atlas-python-release/"
"${SSH[@]}" "$TARGET" "sudo mkdir -p '$ROOT/shared' && sudo rsync -a --delete --exclude shared/ /tmp/atlas-python-release/ '$ROOT/' && sudo '$ROOT/scripts/install-systemd.sh'"
"${SSH[@]}" "$TARGET" "systemctl is-active atlas-python-api atlas-python-worker"
