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
base=$(basename "$out")
dir=$(dirname "$out")
if command -v sha256sum >/dev/null 2>&1; then
  (cd "$dir" && sha256sum "$base") > "$dir/SHA256SUMS"
else
  (cd "$dir" && shasum -a 256 "$base") > "$dir/SHA256SUMS"
fi
cp "$dir/SHA256SUMS" "$out.sha256"
echo "$out"
