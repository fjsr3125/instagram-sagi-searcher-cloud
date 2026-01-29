FROM node:20-bookworm

ARG APPIUM_VERSION=3.0.0
ENV DEBIAN_FRONTEND=noninteractive
ENV ANDROID_HOME=/opt/android-sdk
ENV PATH="${ANDROID_HOME}/platform-tools:${PATH}"

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    openjdk-17-jre-headless \
    android-tools-adb \
    curl \
    ca-certificates \
    git \
 && rm -rf /var/lib/apt/lists/*

# ANDROID_HOME構造を作成し、システムのadbをリンク
RUN mkdir -p ${ANDROID_HOME}/platform-tools \
 && ln -s /usr/bin/adb ${ANDROID_HOME}/platform-tools/adb

RUN npm install -g appium@${APPIUM_VERSION} \
 && appium driver install uiautomator2 \
 && npm cache clean --force

EXPOSE 4723
