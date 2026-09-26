#!/bin/sh
# Собрать образы и сохранить их в tar. Сам скрипт сеть использует.
# Прогон из tar: docker load -i <tar>, затем compose с docker-compose.offline.yml.
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
cd "$root"
out=${1:-out/kontur_images.tar}
mkdir -p "$(dirname "$out")"
docker compose -f docker-compose.yml -f docker-compose.demo.yml build
images=$(docker compose -f docker-compose.yml -f docker-compose.demo.yml config --images)
# shellcheck disable=SC2086
docker save -o "$out" $images
if command -v sha256sum >/dev/null 2>&1; then
  sha256sum "$out" > "$out.sha256"
else
  shasum -a 256 "$out" > "$out.sha256"
fi
echo "$out"
