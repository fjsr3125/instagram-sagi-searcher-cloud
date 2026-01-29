#!/bin/bash
set -e

# Redroidが起動するまで待機してADB接続
echo "Waiting for Redroid to be ready..."
MAX_RETRIES=30
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if adb connect "${ANDROID_ADB_SERVER_ADDRESS:-redroid}:${ANDROID_ADB_SERVER_PORT:-5555}" 2>/dev/null | grep -q "connected"; then
        echo "Successfully connected to Redroid"
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "Retry $RETRY_COUNT/$MAX_RETRIES: Waiting for Redroid..."
    sleep 2
done

# 接続確認
adb devices

# Appium起動
exec "$@"
