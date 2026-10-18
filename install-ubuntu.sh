#!/usr/bin/env bash
# Hush installer for Ubuntu (Docker). Run on the server, from the project folder:
#   chmod +x install-ubuntu.sh && ./install-ubuntu.sh
#
# Optional environment overrides:
#   MEDIA_DIR=/mnt/media   host folder holding your media (mounted read-only at /media)
#   HUSH_PASSWORD=...      login password (prompted if unset and no .env exists)
#   WHISPER=1|0            1 = audio scanning (large image), 0 = subtitles only
set -euo pipefail

cd "$(dirname "$0")"

MEDIA_DIR="${MEDIA_DIR:-/mnt/media}"
WHISPER="${WHISPER:-1}"

if [ "$(id -u)" -eq 0 ]; then SUDO=""; else SUDO="sudo"; fi

# 1. Docker
if ! command -v docker >/dev/null 2>&1; then
  echo ">> Installing Docker"
  curl -fsSL https://get.docker.com | $SUDO sh
fi
if ! docker info >/dev/null 2>&1; then
  # Not in the docker group yet (or not logged in again): use sudo for this run.
  DOCKER="$SUDO docker"
  [ -n "$SUDO" ] && $SUDO usermod -aG docker "$USER" && \
    echo ">> Added $USER to the docker group (log out and in to use docker without sudo)"
else
  DOCKER="docker"
fi

# 2. Config
if [ ! -f config.yaml ]; then
  cp config.example.yaml config.yaml
  echo ">> Created config.yaml from the example. Edit it to keep only your sources."
fi

# 3. Password
if [ ! -f .env ]; then
  if [ -z "${HUSH_PASSWORD:-}" ]; then
    read -r -s -p "Choose a Hush password: " HUSH_PASSWORD; echo
  fi
  [ -n "$HUSH_PASSWORD" ] || { echo "Password cannot be empty"; exit 1; }
  umask 077
  printf 'HUSH_PASSWORD=%s\n' "$HUSH_PASSWORD" > .env
  echo ">> Wrote .env"
fi

# 4. Media mount (compose file defaults to /mnt/media)
if [ "$MEDIA_DIR" != "/mnt/media" ]; then
  sed -i "s#- /mnt/media:/media:ro#- ${MEDIA_DIR}:/media:ro#" docker-compose.yml
fi
[ -d "$MEDIA_DIR" ] || echo "!! $MEDIA_DIR does not exist. Create or mount it, or rerun with MEDIA_DIR=/your/path"

# 5. Build and start
$DOCKER compose build --build-arg "WHISPER=${WHISPER}"
$DOCKER compose up -d

# 6. Health check
echo ">> Waiting for Hush to respond"
for _ in $(seq 1 30); do
  if curl -fsS -o /dev/null http://127.0.0.1:8642/api/session; then
    IP="$(hostname -I | awk '{print $1}')"
    echo ">> Hush is up: http://${IP}:8642"
    exit 0
  fi
  sleep 2
done
echo "!! Hush did not respond. Check logs: $DOCKER compose logs hush"
exit 1
