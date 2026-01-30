FROM node:20-bookworm

ARG APPIUM_VERSION=3.0.0
ENV DEBIAN_FRONTEND=noninteractive
ENV ANDROID_HOME=/opt/android-sdk
ENV PATH="${ANDROID_HOME}/platform-tools:${PATH}"

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    openjdk-17-jre-headless \
    curl \
    ca-certificates \
    git \
    unzip \
 && rm -rf /var/lib/apt/lists/*

# Google公式platform-tools (ARM64対応)
RUN mkdir -p ${ANDROID_HOME} \
 && curl -fsSL https://dl.google.com/android/repository/platform-tools-latest-linux.zip -o /tmp/platform-tools.zip \
 && unzip /tmp/platform-tools.zip -d ${ANDROID_HOME} \
 && rm /tmp/platform-tools.zip \
 && chmod +x ${ANDROID_HOME}/platform-tools/*

RUN npm install -g appium@${APPIUM_VERSION} \
 && appium driver install uiautomator2 \
 && npm cache clean --force

COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 4723
ENTRYPOINT ["docker-entrypoint.sh"]
