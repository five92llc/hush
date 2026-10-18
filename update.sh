#!/usr/bin/env bash
# Update Hush on the server from GitHub, then restart it.
# First time on a server (no git yet): sudo apt-get install -y git, then run:
#   cd ~/hush && git init -q -b main && git remote add origin https://github.com/five92llc/hush.git \
#     && git fetch -q origin main && git reset -q --hard origin/main && ./update.sh
# config.yaml, .env, data/ and .venv are git-ignored, so an update never touches them.
set -euo pipefail
cd "$(dirname "$0")"

before="$(git rev-parse HEAD 2>/dev/null || echo none)"
git fetch -q origin main
git reset -q --hard origin/main
after="$(git rev-parse HEAD)"

if [ "$before" = "$after" ] && [ "${1:-}" != "--force" ]; then
  echo ">> Already up to date ($(git rev-parse --short HEAD))"; exit 0
fi

if [ "$before" = none ] || ! git diff --quiet "$before" "$after" -- requirements.txt pyproject.toml 2>/dev/null; then
  echo ">> Dependencies changed: installing"
  .venv/bin/pip install -q -r requirements.txt
fi

sudo systemctl restart hush
for _ in $(seq 1 20); do
  if curl -fsS -o /dev/null http://127.0.0.1:8642/api/session; then
    echo ">> Updated to $(git rev-parse --short HEAD) and running"; exit 0
  fi
  sleep 1
done
echo "!! Hush did not come back. Check: journalctl -u hush -n 50"; exit 1
