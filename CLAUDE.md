# Instagram 詐欺チェッカー Cloud版

## 経緯

### バージョン履歴

1. **local.ver** - 最初のローカル版
   ```
   /Users/fujimakisora/Documents/project-dir/instagram_sagi_checker
   ```

2. **docker.ver** - Docker化版（Apple Siliconで動作せず）
   ```
   /Users/fujimakisora/Documents/project-dir/instagram_sagi_checker_docker
   ```

3. **cloud.ver** - 今回作成（Oracle Cloud向け）
   ```
   /Users/fujimakisora/Documents/project-dir/instagram_sagi_checker_cloud
   ```

### なぜCloud版が必要か

docker.verをApple Silicon Mac + Colimaで動かそうとしたが、**Redroid（Androidエミュレータ）が動作しない**ことが判明。

- 原因: RedroidはLinuxカーネルモジュール（ashmem, binder）が必要
- ColimaのVM環境では提供されない
- 解決策: 各自がクラウドLinux VMにデプロイする方式へ変更

---

## 参照すべきファイル

### local.ver（ロジックの参考）
```
/Users/fujimakisora/Documents/project-dir/instagram_sagi_checker/
```
- Pythonスクリプト、Appiumロジックの元実装

### docker.ver（Docker構成の参考）
```
/Users/fujimakisora/Documents/project-dir/instagram_sagi_checker_docker/
├── docker-compose.yml      # Docker構成（要調整）
├── web/
│   ├── main.py             # FastAPI Web UI
│   ├── Dockerfile
│   └── requirements.txt
├── checker/
│   └── checker_appium.py   # Appiumチェッカーロジック
└── README.md
```

---

## 新しい方針

**各自がOracle Cloudにデプロイする方式**

- 想定ユーザー: 20人程度
- 各自がOracle Cloud Always Free枠を使う
- **永久無料**で運用可能

### Oracle Cloud Always Free スペック
- ARM (Ampere): 4コア / 24GB RAM
- ストレージ: 200GB
- Redroidに十分なスペック

---

## 作るべきもの

1. **Oracle Cloud用セットアップスクリプト** - ワンコマンドで環境構築
2. **デプロイガイド** - 初心者向け手順書（スクショ付き）
3. **docker-compose.yml** - Oracle ARM Linux VM向けに調整（ARM版Redroid使用）

---

## 次のステップ

1. **Oracle CloudでARM VM作成して動作確認** ← 次ここから
2. Redroid ARM版の動作検証
3. セットアップスクリプト作成
4. デプロイガイド作成（スクショ付き）
5. 20人に配布

---

## 進捗ログ

### 2025-01-16
- プロジェクト初期化
- docker.ver / local.ver のコード確認完了
- 作業計画を策定（フェーズ1〜5）
- **次回**: Oracle CloudでARM VM作成（手動作業）
  - ログイン → Compute → Create Instance
  - Shape: VM.Standard.A1.Flex (4 OCPU / 24GB RAM)
  - Image: Ubuntu 22.04
  - Public IP必須

### 2025-01-29
- 新規インスタンス作成: `instance-20260129-0829` (IP: 150.230.104.24)
- setup.sh実行完了（Docker、binderfs設定OK）
- `docker compose pull redroid`実行中にサーバーがハング
- **原因調査中**: カーネルパニックまたはOOMの可能性
- **次回**: swap設定、Docker同時ダウンロード制限を適用してから再試行

### 2025-01-29（続き）
- Redroid起動時にサーバーがハングする問題を調査
- **根本原因**: Ubuntu 22.04のbinderfs方式とRedroidの互換性問題
- **解決策**: Ubuntu 20.04にダウングレード（legacy binderサポート）
- 以下のファイルを更新:
  - `oci-arm-host-capacity/.env` - Ubuntu 20.04イメージIDに変更
  - `docker-compose.yml` - legacy binderデバイスマッピングに変更
  - `setup.sh` - Ubuntu 20.04対応、ashmem追加、binderfs削除
- **次回**: 現在のインスタンスをTerminate → Ubuntu 20.04で再作成

### 2025-01-29（セットアップ最適化）
- setup.shをbinderfs方式（kernel 5.15+）に対応
- iptablesでポート80/443/8000を開放、永続化
- HTTPS対応: Caddyリバースプロキシを追加（DuckDNS対応）
- GitHub Actions改善:
  - build-images.yml: semverタグ対応（v1.0.0形式）
  - ci.yml: ShellCheck、docker-compose構文チェック追加
- **新規ファイル**:
  - `Caddyfile` - Caddyリバースプロキシ設定
  - `.github/workflows/ci.yml` - CIワークフロー

### 2026-01-29（機能改善）
- **複数アカウント対応**
  - `INSTAGRAM_ACCOUNTS`環境変数（JSON配列形式）
  - アカウント使用統計追跡（`data/account_stats.json`）
  - 1日60フォロー上限でのアカウントローテーション
  - アカウント状況のリアルタイム表示UI
- **キュー処理**
  - 同時実行は1つのみ（順番待ち方式）
  - `POST /queue`, `GET /queue`, `DELETE /queue/{id}`エンドポイント
  - 待ち状況のリアルタイム表示UI
  - キャンセル機能
- **変更ファイル**:
  - `.env.example` - 複数アカウント形式追加
  - `web/main.py` - アカウント管理、キュー処理追加
  - `checker/checker_appium.py` - logout(), switch_account()追加
  - `web/templates/index.html` - キュー・アカウント状況UI
  - `web/static/style.css` - 新UIスタイル
- **次回**: UIAutomator2ドライバーインストール確認、動作検証

---

## トラブルシューティング

### 問題: Redroid起動時にサーバーがハング（解決済み）

#### 症状
- Dockerイメージpull: ✅ 成功
- コンテナ作成: ✅ 成功
- **Redroid起動: ❌ 起動直後にサーバーがハング**（SSH不可、ping不通）

#### 根本原因
**binderfsの設定不備またはRedroidイメージとの不一致**

#### 解決策
**binderfsを正しく設定**（setup.shで自動化済み）

```bash
# binder_linuxモジュールをロード
sudo modprobe binder_linux devices="binder,hwbinder,vndbinder"

# binderfsをマウント
sudo mkdir -p /dev/binderfs
sudo mount -t binder binder /dev/binderfs

# 権限設定
sudo chmod 666 /dev/binderfs/binder /dev/binderfs/hwbinder /dev/binderfs/vndbinder

# 永続化（/etc/fstabに追加）
echo "binder /dev/binderfs binder defaults,nofail 0 0" | sudo tee -a /etc/fstab
```

参考: [Redroid Issue #859](https://github.com/remote-android/redroid-doc/issues/859)

---

### 問題: Dockerイメージpull中にサーバーがハング/タイムアウト

#### 症状
- `docker compose pull` または `docker compose up -d` 実行中にSSH切断
- pingも通らなくなる
- Oracle Cloudコンソールではインスタンスは"RUNNING"

#### 原因
1. Ubuntu cloud-optimizedカーネルのDockerとの互換性問題
2. メモリ不足（swap未設定）
3. Docker pullの同時ダウンロードによる負荷

#### 解決策

**1. Swap設定（必須）**
```bash
sudo fallocate -l 8G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

**2. Docker同時ダウンロード制限**
```bash
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json <<EOF
{
  "max-concurrent-downloads": 1
}
EOF
sudo systemctl restart docker
```

**3. カーネルパラメータ調整（OOMパニック防止）**
```bash
sudo tee -a /etc/sysctl.conf <<EOF
vm.panic_on_oom = 0
vm.oom_dump_tasks = 1
EOF
sudo sysctl -p
```

**4. 代替: ローカルでイメージをpullしてサーバーに転送**
```bash
# ローカル
docker pull ghcr.io/fjsr3125/instagram-sagi-searcher-cloud-redroid:latest --platform linux/arm64
docker save -o redroid.tar ghcr.io/fjsr3125/instagram-sagi-searcher-cloud-redroid:latest
scp redroid.tar ubuntu@<IP>:/tmp/

# サーバー
docker load -i /tmp/redroid.tar
```

#### 参考リンク
- [Kernel Panic with Docker on Ubuntu Cloud-optimized Kernels](https://forum.gitlab.com/t/kernel-panic-with-docker-on-some-cloud-optimized-ubuntu-kernels/70739)
- [Redroid ARM Memory Issues - GitHub #160](https://github.com/remote-android/redroid-doc/issues/160)
