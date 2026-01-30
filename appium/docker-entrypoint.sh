#!/bin/bash
set -e

# ADB接続はAppiumのcapabilities (remoteAdbHost) で行うため、
# ここではAppiumを直接起動する

echo "Starting Appium server..."
echo "ADB connection will be handled via Appium capabilities (remoteAdbHost)"

exec "$@"
