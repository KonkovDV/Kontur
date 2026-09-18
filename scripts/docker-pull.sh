#!/usr/bin/env bash
# scripts/docker-pull.sh — загрузить все image-ы для offline-режима.
# Запускать из корня репозитория: bash scripts/docker-pull.sh
# Или через: make offline-pull

set -euo pipefail

IMAGES=(
  "postgres:16-alpine"
  "redis:7-alpine"
  "rabbitmq:3.13-management-alpine"
  "minio/minio:RELEASE.2024-09-13T20-26-02Z"
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
echo "==> All images pulled. Offline mode ready."
echo "    Run: make offline-up"
