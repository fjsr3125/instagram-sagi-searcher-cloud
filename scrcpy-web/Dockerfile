# ===========================================
# ws-scrcpy ARM64対応ビルド
# ===========================================

# ビルドステージ
FROM node:20-alpine AS builder

RUN apk add --no-cache git python3 make g++

WORKDIR /app
RUN git clone --depth 1 https://github.com/NetrisTV/ws-scrcpy.git .

RUN npm ci
RUN npm run dist

# 実行ステージ
FROM node:20-alpine

RUN apk add --no-cache android-tools

WORKDIR /app
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./

EXPOSE 8000
CMD ["node", "dist/index.js"]
