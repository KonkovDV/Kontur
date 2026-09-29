#!/usr/bin/env bash
# scripts/docker-pull.sh — загрузить все image-ы для offline-режима.
# Запускать из корня репозитория: bash scripts/docker-pull.sh
# Или через: make offline-pull

set -euo pipefail

IMAGES=(
  "postgres:16-alpine"
  "redis:7-alpine"
  "rabbitmq:3.13-management-alpine"
  "bitnamilegacy/minio:2025.7.23-debian-12-r5"
)

echo "==> Pulling images for offline use..."
for IMG in "${IMAGES[@]}"; do
  echo "  pulling ${IMG}..."
  docker pull "${IMG}"
done

echo ""
echo "==> Image digests (for integrity verification):"
for IMG in "${IMAGES[@]}"; do
  DIGEST=$(docker inspect --format='{{index .RepoDigests 0}}' "${IMG}" 2>/dev/null || echo "<not available>")
  printf "  %-55s %s\n" "${IMG}" "${DIGEST}"
done

echo ""
echo "==> Building core and gateway for offline use..."
export KONTUR_GIT_SHA="$(git rev-parse HEAD)"
docker compose build core gateway

echo "==> All images pulled. Offline mode ready."
echo "    Run: make offline-up"
