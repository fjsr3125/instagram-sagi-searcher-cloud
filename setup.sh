#!/bin/bash
# ===========================================
# Instagram 詐欺チェッカー Cloud版 - セットアップスクリプト
# Contabo (Ubuntu 22.04 x86_64) 向け
# ===========================================

set -e

# カラー出力
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# ヘッダー表示
echo ""
echo "=========================================="
echo " Instagram 詐欺チェッカー Cloud版"
echo " セットアップスクリプト（Contabo/Ubuntu 22.04）"
echo "=========================================="
echo ""

# 1. システムアップデート
log_info "システムをアップデート中..."
sudo apt-get update -qq
sudo apt-get upgrade -y -qq
log_success "システムアップデート完了"

# 2. 必要なパッケージをインストール
log_info "必要なパッケージをインストール中..."
sudo apt-get install -y -qq \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    git \
    linux-modules-extra-$(uname -r)
log_success "パッケージインストール完了"

# 3. Dockerをインストール
if command -v docker &> /dev/null; then
    log_success "Dockerは既にインストールされています"
else
    log_info "Dockerをインストール中..."

    # Docker公式GPGキーを追加
    sudo mkdir -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

    # Dockerリポジトリを追加
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    # Dockerをインストール
    sudo apt-get update -qq
    sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    # 現在のユーザーをdockerグループに追加
    sudo usermod -aG docker $USER

    log_success "Dockerインストール完了"
    log_warn "dockerグループの変更を反映するため、セットアップ完了後に再ログインしてください"
fi

# 4. binder_linuxカーネルモジュールをセットアップ
log_info "binder_linuxカーネルモジュールをセットアップ中..."

# モジュールが存在するか確認
if ! modinfo binder_linux &> /dev/null; then
    log_error "binder_linuxモジュールが見つかりません"
    log_info "カーネルモジュールパッケージを再インストールします..."
    sudo apt-get install -y --reinstall linux-modules-extra-$(uname -r)
fi

# モジュールをロード
if ! lsmod | grep -q binder_linux; then
    log_info "binder_linuxモジュールをロード中..."
    sudo modprobe binder_linux devices="binder,hwbinder,vndbinder"
fi

# 起動時に自動でモジュールを読み込む設定
if [ ! -f /etc/modules-load.d/binder.conf ]; then
    log_info "モジュール自動ロード設定を追加中..."
    sudo tee /etc/modules-load.d/binder.conf >/dev/null <<'EOF'
binder_linux
EOF
fi

# モジュールオプションを設定
if [ ! -f /etc/modprobe.d/binder.conf ]; then
    sudo tee /etc/modprobe.d/binder.conf >/dev/null <<'EOF'
options binder_linux devices=binder,hwbinder,vndbinder
EOF
fi

log_success "binder_linuxモジュール設定完了"

# 5. binderfsをセットアップ
log_info "binderfsをセットアップ中..."

# binderfsディレクトリを作成
if [ ! -d /dev/binderfs ]; then
    sudo mkdir -p /dev/binderfs
fi

# binderfsをマウント
if ! mount | grep -q "binder on /dev/binderfs"; then
    log_info "binderfsをマウント中..."
    sudo mount -t binder binder /dev/binderfs || {
        log_warn "binderfsのマウントに失敗しました（初回は正常な場合があります）"
    }
fi

# /etc/fstabに追加（永続化）
if ! grep -q "binderfs" /etc/fstab; then
    log_info "/etc/fstabにbinderfsを追加中..."
    echo "binder /dev/binderfs binder defaults,nofail 0 0" | sudo tee -a /etc/fstab >/dev/null
fi

# tmpfiles設定（起動時にディレクトリを作成）
if [ ! -f /etc/tmpfiles.d/binderfs.conf ]; then
    sudo tee /etc/tmpfiles.d/binderfs.conf >/dev/null <<'EOF'
d /dev/binderfs 0755 root root -
EOF
fi

log_success "binderfs設定完了"

# 6. データディレクトリを作成
log_info "データディレクトリを作成中..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$SCRIPT_DIR/data/uploads"
mkdir -p "$SCRIPT_DIR/data/results"
mkdir -p "$SCRIPT_DIR/data/screenshots"
mkdir -p "$SCRIPT_DIR/data/appium"
mkdir -p "$SCRIPT_DIR/data/adb"
log_success "データディレクトリ作成完了"

# 7. .envファイルを作成（存在しない場合）
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    log_info ".envファイルを作成中..."
    cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
    log_warn ".envファイルを編集してInstagram認証情報を設定してください"
else
    log_success ".envファイルは既に存在します"
fi

# 8. カーネルモジュール確認
echo ""
log_info "=== セットアップ確認 ==="

echo ""
echo "binder_linuxモジュール:"
if lsmod | grep -q binder_linux; then
    log_success "ロード済み"
else
    log_warn "未ロード（再起動後にロードされます）"
fi

echo ""
echo "binderfsマウント:"
if mount | grep -q "binder on /dev/binderfs"; then
    log_success "マウント済み"
    ls -la /dev/binderfs/
else
    log_warn "未マウント（再起動後にマウントされます）"
fi

echo ""
echo "Docker:"
if command -v docker &> /dev/null; then
    docker --version
    log_success "インストール済み"
else
    log_error "インストールされていません"
fi

echo ""
echo "=========================================="
echo " セットアップ完了"
echo "=========================================="
echo ""
echo "次のステップ:"
echo ""
echo "1. 再ログインしてdockerグループを反映:"
echo "   $ exit"
echo "   $ ssh <USER>@<PUBLIC_IP>"
echo ""
echo "2. .envファイルを編集してInstagram認証情報を設定:"
echo "   $ nano .env"
echo ""
echo "3. Dockerコンテナを起動:"
echo "   $ cd $SCRIPT_DIR"
echo "   $ docker compose up -d"
echo ""
echo "4. アクセス先:"
echo "   - Web UI: http://<PUBLIC_IP>:8000"
echo "   - Android画面: http://<PUBLIC_IP>:6080"
echo ""
echo "=========================================="
