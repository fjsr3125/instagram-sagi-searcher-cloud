#!/bin/bash
set -e

ADB_HOST="${ANDROID_ADB_SERVER_ADDRESS:-redroid}"
ADB_PORT="${ANDROID_ADB_SERVER_PORT:-5555}"

echo "Starting ADB server..."
adb start-server || true

echo "Waiting for Redroid at ${ADB_HOST}:${ADB_PORT}..."
MAX_RETRIES=30
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "Attempt $RETRY_COUNT/$MAX_RETRIES..."

    # タイムアウト付きでADB接続
    RESULT=$(timeout 10 adb connect "${ADB_HOST}:${ADB_PORT}" 2>&1 || echo "timeout")
    echo "Result: $RESULT"

    if echo "$RESULT" | grep -qE "connected|already"; then
        echo "Successfully connected to Redroid!"
        break
    fi

    sleep 3
done

# 接続確認
echo "Connected devices:"
adb devices

# Appium起動
exec "$@"
